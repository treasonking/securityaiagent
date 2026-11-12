"""Optional local-file transport. Not a network daemon or arbitrary command runner."""
import argparse
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import time

if __package__:
    from .vm_deploy import write
else:
    from vm_deploy import write


def valid_job(job, role):
    if not isinstance(job, dict) or not {'sequence', 'action', 'role'} <= set(job):
        return False
    if set(job) - {'sequence', 'action', 'role', 'commit', 'expected', 'plan', 'confirm'}:
        return False
    if job['role'] != role or job['action'] not in ('inspect', 'plan', 'apply', 'rollback', 'status', 'stop'):
        return False
    for key, size in [('sequence', 32), ('commit', 40), ('expected', 40), ('plan', 32), ('confirm', 64)]:
        if key in job and (not isinstance(job[key], str) or not re.fullmatch('[0-9a-f]{' + str(size) + '}', job[key])):
            return False
    return True


def execute_job(role, exchange, private, job):
    """Publish the actual child exit; do not infer success from result files."""
    if not valid_job(job, role):
        raise ValueError('INVALID_JOB')
    identity = {key: job[key] for key in ('sequence', 'action', 'role')}
    if job['action'] == 'stop':
        write(exchange / 'public' / ('result-' + job['sequence'] + '.json'), dict(identity, ok=True))
        receipt = dict(identity, exit_code=0)
        write(exchange / 'public/stopped.json', receipt)
    else:
        command = ['/home/ubuntu/securityaiagent/.venv/bin/python', str(exchange / 'vm_deploy.py'),
                   job['action'], '--exchange', str(exchange), '--sequence', job['sequence']]
        for key in ('commit', 'expected', 'plan', 'confirm'):
            if key in job:
                command += ['--' + key, job[key]]
        with (private / (job['sequence'] + '.log')).open('wb') as stream:
            try:
                result = subprocess.run(command, stdout=stream, stderr=stream)
                receipt = dict(identity, exit_code=result.returncode)
            except OSError:
                receipt = dict(identity, exit_code=None, reason_code='PROCESS_START_FAILED')
    write(exchange / 'public' / ('receipt-' + job['sequence'] + '.json'), receipt)
    write(exchange / 'public/receipt.json', receipt)  # Display alias, never authority.
    return receipt


def claim_job(private, sequence):
    """Persist consumption BEFORE execution; restart never automatically retries."""
    consumed = private / 'consumed'
    consumed.mkdir(mode=0o700, exist_ok=True)
    try:
        with (consumed / sequence).open('x') as stream:
            stream.write(sequence)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        return False
    return True


def serve(role, exchange, private):
    last = private / 'last-job'
    legacy_seen = last.read_text() if last.exists() else ''
    write(exchange / 'public/ready.json', {'role': role, 'protocol': 2, 'pid': os.getpid(), 'started': time.time()})
    while True:
        try:
            job = json.loads((exchange / 'job.json').read_text())
        except (ValueError, OSError):
            time.sleep(.2)
            continue
        if not valid_job(job, role) or job['sequence'] == legacy_seen or not claim_job(private, job['sequence']):
            time.sleep(.2)
            continue
        execute_job(role, exchange, private, job)
        if job['action'] == 'stop':
            return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exchange', type=Path, required=True)
    args = parser.parse_args()
    role = socket.gethostname().removeprefix('security-')
    if role not in ('controller', 'worker', 'target') or os.getuid() != 1000:
        return 2
    exchange = args.exchange.resolve()
    os.umask(0o077)
    private = Path('/home/ubuntu/securityaiagent-deployments/transport')
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    import fcntl
    with (private / 'dispatcher.lock').open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 2
        # Never kill an in-flight change because the host stopped waiting.
        return serve(role, exchange, private)


if __name__ == '__main__':
    raise SystemExit(main())
