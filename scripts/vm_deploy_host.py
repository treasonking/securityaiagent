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


def send(folder, job, timeout=620):
    require(job.get('action') in ('inspect', 'plan', 'apply', 'rollback', 'status', 'stop'), 'INVALID_ACTION')
    require(set(job) <= {'action', 'commit', 'expected', 'plan', 'confirm'}, 'INVALID_JOB_FIELDS')
    for key, size in [('commit', 40), ('expected', 40), ('plan', 32), ('confirm', 64)]:
        if key in job:
            require(bool(re.fullmatch('[0-9a-f]{' + str(size) + '}', job[key] or '')), 'INVALID_JOB_IDENTIFIER')
    require((folder / 'public/ready.json').exists(), 'GUEST_DISPATCHER_NOT_READY')
    # A timed-out caller must inspect its receipt before delivering another action.
    pending = folder / 'pending.json'
    if pending.exists():
        previous = load(pending)
        receipt_path = folder / 'public/receipt.json'
        require(receipt_path.exists() and load(receipt_path).get('sequence') == previous['sequence'], 'PREVIOUS_JOB_UNRESOLVED')
    job = dict(job, sequence=uuid.uuid4().hex)
    write(pending, job)
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
        try:
            receipt = load(folder / 'public' / ('stopped.json' if job['action'] == 'stop' else 'receipt.json'))
            if receipt.get('sequence') == job['sequence']:
                result = receipt if job['action'] == 'stop' else load(folder / 'public' / (job['action'] + '.json'))
                write(folder / 'public/history' / (job['sequence'] + '.json'), {'job': job, 'receipt': receipt, 'result': result})
                pending.unlink()
                return {'receipt': receipt, 'result': result}
        except (OSError, ValueError):
            pass
        time.sleep(.2)
    raise DeployError('JOB_TIMEOUT_INSPECT_RECEIPT_BEFORE_RETRY')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('package', 'inspect', 'plan', 'apply', 'rollback', 'status', 'stop'))
    parser.add_argument('--exchange', type=Path, required=True)
    parser.add_argument('--role', choices=('controller', 'worker', 'target'))
    for name in ('commit', 'expected', 'plan', 'confirm'):
        parser.add_argument('--' + name)
    args = parser.parse_args()
    try:
        if args.action == 'package':
            result = package(args.exchange, args.commit)
        else:
            require(args.role is not None, 'ROLE_REQUIRED')
            job = {k: v for k, v in vars(args).items() if v is not None and k not in ('exchange', 'role')}
            result = send(args.exchange / args.role, job)
        print(json.dumps(result, indent=2))
        return 0 if result.get('ok', result.get('result', {}).get('ok', result.get('receipt', {}).get('exit_code', 0) == 0)) else 2
    except DeployError as exc:
        print(json.dumps({'ok': False, 'reason_code': str(exc)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
