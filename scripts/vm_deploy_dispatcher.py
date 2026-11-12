"""Optional local-file transport. Not a network daemon or arbitrary command runner."""
import argparse
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import time


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
    last = private / 'last-job'
    seen = last.read_text() if last.exists() else ''
    (exchange / 'public/ready.json').write_text(json.dumps({'role': role, 'pid': os.getpid(), 'started': time.time()}))
    while True:
        try:
            job = json.loads((exchange / 'job.json').read_text())
            assert set(job) <= {'sequence', 'action', 'commit', 'expected', 'plan', 'confirm'}
            assert re.fullmatch('[0-9a-f]{32}', job['sequence'])
            if job['sequence'] == seen:
                time.sleep(.2)
                continue
            assert job['action'] in ('inspect', 'plan', 'apply', 'rollback', 'status', 'stop')
            for key, size in [('commit', 40), ('expected', 40), ('plan', 32), ('confirm', 64)]:
                if key in job:
                    assert re.fullmatch('[0-9a-f]{' + str(size) + '}', job[key])
        except (ValueError, OSError, KeyError, AssertionError, TypeError):
            time.sleep(.2)
            continue
        seen = job['sequence']
        last.write_text(seen)
        if job['action'] == 'stop':
            (exchange / 'public/stopped.json').write_text(json.dumps({'role': role, 'sequence': seen}))
            return 0
        command = ['/home/ubuntu/securityaiagent/.venv/bin/python', str(exchange / 'vm_deploy.py'),
                   job['action'], '--exchange', str(exchange)]
        for key in ('commit', 'expected', 'plan', 'confirm'):
            if key in job:
                command += ['--' + key, job[key]]
        with (private / (seen + '.log')).open('wb') as stream:
            # Do not kill a mutating operation on a transport timeout. The host may
            # time out; inspect its eventual receipt/journal before issuing recovery.
            result = subprocess.run(command, stdout=stream, stderr=stream)
        (exchange / 'public/receipt.json').write_text(json.dumps({'role': role, 'sequence': seen, 'exit_code': result.returncode}))


if __name__ == '__main__':
    raise SystemExit(main())
