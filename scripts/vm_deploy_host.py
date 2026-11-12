"""Prepare offline bundles and send bounded jobs through role-specific shared folders."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import uuid

from scripts.vm_deploy import DeployError, full_commit, load, require, tree_hashes, write

ROOT = Path(__file__).resolve().parents[1]


def package(exchange, commit):
    full_commit(commit)
    # HEAD must contain the literal deployment commit; never fetch on a guest.
    subprocess.run(['git', 'merge-base', '--is-ancestor', commit, 'HEAD'], cwd=ROOT, check=True)
    subprocess.run(['git', 'diff', '--quiet', commit, '--', 'frontend'], cwd=ROOT, check=True)
    subprocess.run(['git', 'diff', '--quiet', '--cached', '--', 'frontend'], cwd=ROOT, check=True)
    subprocess.run(['npm.cmd' if os.name == 'nt' else 'npm', 'run', 'build'], cwd=ROOT / 'frontend', check=True)
    exchange.mkdir(parents=True, exist_ok=True)
    bundle = exchange / 'release.bundle'
    subprocess.run(['git', 'bundle', 'create', str(bundle.resolve()), 'HEAD'], cwd=ROOT, check=True)
    manifest = {'commit': commit, 'bundle_sha256': hashlib.sha256(bundle.read_bytes()).hexdigest(),
                'frontend_dist_sha256': tree_hashes(ROOT / 'frontend/dist')}
    for role in ('controller', 'worker', 'target'):
        folder = exchange / role
        (folder / 'public').mkdir(parents=True, exist_ok=True)
        shutil.copyfile(bundle, folder / 'release.bundle')
        shutil.copyfile(ROOT / 'scripts/vm_deploy.py', folder / 'vm_deploy.py')
        shutil.copyfile(ROOT / 'scripts/vm_deploy_dispatcher.py', folder / 'dispatcher.py')
        if role == 'controller':
            dest = folder / 'frontend-dist'
            require(not dest.exists(), 'FRONTEND_DIRECTORY_ALREADY_EXISTS_USE_NEW_EXCHANGE')
            shutil.copytree(ROOT / 'frontend/dist', dest)
        write(folder / 'release.json', manifest)
    return {'ok': True, 'commit': commit, 'bundle_sha256': manifest['bundle_sha256']}


def read_completion(folder, job):
    """Only a matching receipt AND result with exit 0 and ok=true can succeed."""
    sequence = job['sequence']
    receipt_path = folder / 'public' / ('receipt-' + sequence + '.json')
    if not receipt_path.exists():
        return None
    outcome = {'ok': False, 'job': job, 'receipt': None, 'result': None}
    try:
        receipt = load(receipt_path)
    except (OSError, ValueError):
        return dict(outcome, reason_code='RECEIPT_INVALID')
    if not isinstance(receipt, dict) or any(receipt.get(k) != job[k] for k in ('sequence', 'action', 'role')):
        return dict(outcome, reason_code='RECEIPT_IDENTITY_MISMATCH')
    outcome['receipt'] = receipt
    result_state = 'missing'
    try:
        result = load(folder / 'public' / ('result-' + sequence + '.json'))
        if not isinstance(result, dict) or any(result.get(k) != job[k] for k in ('sequence', 'action', 'role')):
            result_state = 'identity_mismatch'
        elif type(result.get('ok')) is not bool:
            result_state = 'invalid_status'
        else:
            result_state = 'matched'
            outcome['result'] = result
    except FileNotFoundError:
        pass
    except (OSError, ValueError):
        result_state = 'invalid'
    outcome['result_state'] = result_state
    # Never infer a successful process exit from an application result or a default.
    if type(receipt.get('exit_code')) is not int or receipt['exit_code'] != 0:
        return dict(outcome, reason_code='RECEIPT_EXIT_FAILED')
    if result_state != 'matched':
        return dict(outcome, reason_code='RESULT_NOT_CORRELATED')
    if outcome['result']['ok'] is not True:
        return dict(outcome, reason_code='GUEST_OPERATION_FAILED')
    return dict(outcome, ok=True)


def collect(folder, sequence):
    """Collect an existing job only. Never submit, retry or resume a guest action."""
    require(bool(re.fullmatch('[0-9a-f]{32}', sequence or '')), 'INVALID_JOB_IDENTIFIER')
    pending = folder / 'pending.json'
    require(pending.exists(), 'NO_PENDING_JOB')
    job = load(pending)
    require(job['sequence'] == sequence, 'PENDING_SEQUENCE_MISMATCH')
    outcome = read_completion(folder, job)
    require(outcome is not None, 'JOB_NOT_FINISHED')
    write(folder / 'public' / ('history-' + sequence + '.json'), outcome)
    # Failed, incomplete, stale or conflicting results remain unresolved. An
    # operator must inspect guest state; another send must not replace this job.
    if outcome['ok']:
        require(load(pending) == job, 'PENDING_JOB_CHANGED')
        pending.unlink()
    return outcome


def send(folder, job, timeout=620):
    require(job.get('action') in ('inspect', 'plan', 'apply', 'rollback', 'status', 'stop'), 'INVALID_ACTION')
    require(set(job) <= {'action', 'commit', 'expected', 'plan', 'confirm'}, 'INVALID_JOB_FIELDS')
    for key, size in [('commit', 40), ('expected', 40), ('plan', 32), ('confirm', 64)]:
        if key in job:
            require(bool(re.fullmatch('[0-9a-f]{' + str(size) + '}', job[key] or '')), 'INVALID_JOB_IDENTIFIER')
    require(folder.name in ('controller', 'worker', 'target'), 'INVALID_ROLE')
    require((folder / 'public/ready.json').exists(), 'GUEST_DISPATCHER_NOT_READY')
    ready = load(folder / 'public/ready.json')
    require(ready.get('protocol') == 2 and ready.get('role') == folder.name, 'DISPATCHER_PROTOCOL_MISMATCH')
    # Even a matching receipt cannot automatically authorize another changing job.
    pending = folder / 'pending.json'
    job = dict(job, sequence=uuid.uuid4().hex, role=folder.name)
    try:
        with pending.open('x', encoding='utf-8') as stream:
            json.dump(job, stream)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        raise DeployError('PREVIOUS_JOB_UNRESOLVED') from None
    temp = folder / 'delivery.tmp'
    temp.write_text(json.dumps(job), encoding='utf-8')
    for attempt in range(100):
        try:
            temp.replace(folder / 'job.json')
            break
        except PermissionError:
            if attempt == 99:
                pending.unlink()  # No job was delivered.
                raise DeployError('DELIVERY_FILE_BUSY') from None
            time.sleep(.05)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if (folder / 'public' / ('receipt-' + job['sequence'] + '.json')).exists():
            return collect(folder, job['sequence'])
        time.sleep(.2)
    raise DeployError('JOB_TIMEOUT_INSPECT_RECEIPT_BEFORE_RETRY')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('package', 'inspect', 'plan', 'apply', 'rollback', 'status', 'stop', 'collect'))
    parser.add_argument('--exchange', type=Path, required=True)
    parser.add_argument('--role', choices=('controller', 'worker', 'target'))
    for name in ('commit', 'expected', 'plan', 'confirm'):
        parser.add_argument('--' + name)
    parser.add_argument('--sequence', help='existing pending job to collect without resending')
    args = parser.parse_args()
    try:
        if args.action == 'package':
            result = package(args.exchange, args.commit)
        else:
            require(args.role is not None, 'ROLE_REQUIRED')
            if args.action == 'collect':
                result = collect(args.exchange / args.role, args.sequence)
            else:
                require(args.sequence is None, 'SEQUENCE_ONLY_FOR_COLLECT')
                job = {k: v for k, v in vars(args).items() if v is not None and k not in ('exchange', 'role', 'sequence')}
                result = send(args.exchange / args.role, job)
        print(json.dumps(result, indent=2))
        return 0 if result.get('ok') is True else 2
    except DeployError as exc:
        print(json.dumps({'ok': False, 'reason_code': str(exc)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
