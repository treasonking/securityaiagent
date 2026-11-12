"""Offline, operator-only deployment for the three registered Ubuntu VMs.

No model tool, shell payload, arbitrary endpoint, package install or firewall write.
Run with the existing venv. Public results contain references, never setting values.
"""
from __future__ import annotations

import argparse
from collections import Counter
import contextlib
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import tarfile
import time
import uuid

ROLES = {
    'controller': ('192.168.56.10', 8000, 'controller.api:create_app_from_env', '/api/health'),
    'worker': ('10.77.0.20', 9000, 'worker.app:create_app_from_env', '/health'),
    'target': ('10.78.0.30', 8080, 'target.app:app', '/health'),
}


class DeployError(Exception):
    """Only fixed error codes may enter public output."""


def require(condition, code):
    if not condition:
        raise DeployError(code)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    temp.chmod(0o600)
    temp.replace(path)


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def full_commit(value):
    require(bool(re.fullmatch('[0-9a-f]{40}', value or '')), 'FULL_COMMIT_REQUIRED')
    return value


def inside(path, root):
    path = path.resolve()
    require(path.is_relative_to(root.resolve()), 'PATH_OUTSIDE_CHECKOUT')
    return path


def env_values(path):
    from dotenv.parser import parse_stream
    values = {}
    with path.open(encoding='utf-8-sig') as stream:
        for item in parse_stream(stream):
            require(not item.error, 'INVALID_ENVIRONMENT')
            if item.key is None:
                continue
            require(item.key not in values and item.value is not None and
                    not any(x in item.value for x in ('\n', '\r', '\0', '${')), 'INVALID_ENVIRONMENT')
            values[item.key] = item.value
    return values


def tree_hashes(root):
    if not root.exists():
        return {}
    files = {}
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(), 'RUNTIME_SYMLINK_REJECTED')
        if path.is_file():
            files[path.relative_to(root).as_posix()] = file_hash(path)
    return files


def database_rows(path):
    with contextlib.closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as con:
        require(con.execute('PRAGMA quick_check').fetchone()[0] == 'ok', 'DATABASE_INTEGRITY_FAILED')
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return {table: dict(Counter(hashlib.sha256(repr(row).encode()).hexdigest() for row in
                con.execute('SELECT * FROM "' + table.replace('"', '""') + '"'))) for table in tables}


def databases(root):
    rows = {}
    if root.exists():
        for path in root.rglob('*'):
            require(not path.is_symlink(), 'RUNTIME_SYMLINK_REJECTED')
            if path.is_file():
                with path.open('rb') as stream:
                    sqlite = stream.read(16) == b'SQLite format 3\0'
                if sqlite:
                    rows[path.relative_to(root).as_posix()] = database_rows(path)
    return rows


def rows_preserved(before, after):
    return all(name in after and all(table in after[name] and
               all(after[name][table].get(row, 0) >= count for row, count in rows.items())
               for table, rows in tables.items()) for name, tables in before.items())


def verify_plan(plan, confirmation, current):
    unsigned = {k: v for k, v in plan.items() if k != 'plan_sha256'}
    require(digest(unsigned) == plan.get('plan_sha256') == confirmation, 'PLAN_CONFIRMATION_MISMATCH')
    require(current == plan['before'], 'CURRENT_STATE_CHANGED_REPLAN_REQUIRED')


class VM:
    def __init__(self, role, home=Path('/home/ubuntu')):
        require(role in ROLES, 'UNKNOWN_ROLE')
        self.role = role
        self.original = home / 'securityaiagent'
        self.state = home / 'securityaiagent-deployments'
        self.releases = self.state / 'releases'
        self.python = self.original / '.venv/bin/python'
        self.host, self.port, self.module, self.health_path = ROLES[role]

    def cmd(self, args, cwd=None):
        result = subprocess.run([str(x) for x in args], cwd=cwd or self.original,
                                capture_output=True, text=True, timeout=180)
        require(result.returncode == 0, 'FIXED_COMMAND_FAILED')
        return result.stdout.strip()

    @contextlib.contextmanager
    def lock(self):
        import fcntl
        self.state.mkdir(mode=0o700, exist_ok=True)
        self.state.chmod(0o700)
        with (self.state / 'operation.lock').open('a') as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise DeployError('DEPLOYMENT_BUSY') from None
            yield

    def root_allowed(self, root):
        require(root == self.original or root.parent == self.releases, 'UNREGISTERED_CHECKOUT')
        require(root.resolve() == root, 'CHECKOUT_SYMLINK_REJECTED')

    def listener(self):
        output = self.cmd(['ss', '-H', '-ltnp', 'sport = :' + str(self.port)])
        pids = set(re.findall(r'pid=(\d+)', output))
        require(not output or len(pids) == 1, 'UNKNOWN_LISTENER')
        if not pids:
            return None
        pid = int(pids.pop())
        proc = Path('/proc') / str(pid)
        args = [x.decode() for x in (proc / 'cmdline').read_bytes().split(b'\0') if x]
        root = Path(os.readlink(proc / 'cwd'))
        self.root_allowed(root)
        require('uvicorn' in args and self.module in args, 'UNKNOWN_LISTENER')
        start = (proc / 'stat').read_text().rsplit(')', 1)[1].split()[19]
        return {'pid': pid, 'start_ticks': start, 'checkout': str(root), 'module': self.module}

    def network(self):
        addresses = json.loads(self.cmd(['ip', '-j', 'address']))
        network = [{'name': x['ifname'], 'mac': x.get('address'),
                    'addresses': sorted([a['family'], a['local'], a['prefixlen']] for a in x.get('addr_info', []))}
                   for x in addresses]
        routes = json.loads(self.cmd(['ip', '-j', 'route', 'show', 'table', 'all']))
        normalized_routes = [{k: v for k, v in r.items() if k not in ('expires', 'cache')}
                             for r in routes]
        if self.role != 'controller':
            require(not any(r.get('dst') == 'default' for r in routes), 'INTERNET_ISOLATION_UNPROVEN')
        firewall = {}
        for command in ('iptables-save', 'ip6tables-save'):
            lines = self.cmd(['sudo', '-n', command]).splitlines()
            normalized = '\n'.join(re.sub(r'\[\d+:\d+\]', '[0:0]', x) for x in lines if not x.startswith('#'))
            firewall[command] = hashlib.sha256(normalized.encode()).hexdigest()
        return {'interfaces': network, 'routes': normalized_routes, 'firewall': firewall,
                'no_default_route_required': self.role != 'controller'}

    def inventory(self):
        listener = self.listener()
        active = self.state / 'active.json'
        root = Path(listener['checkout']) if listener else Path(load(active)['checkout']) if active.exists() else self.original
        self.root_allowed(root)
        env = root / ('.env.' + self.role)
        require(env.is_file() and not env.is_symlink(), 'ENVIRONMENT_REFERENCE_MISSING')
        values = env_values(env)
        if listener:
            proc = Path('/proc') / str(listener['pid'])
            actual = dict(x.decode().split('=', 1) for x in (proc / 'environ').read_bytes().split(b'\0') if b'=' in x)
            require(all(actual.get(k) == v for k, v in values.items()), 'RUNNING_ENVIRONMENT_DIFFERS')
        require(not self.cmd(['git', 'status', '--porcelain', '--untracked-files=no'], root), 'TRACKED_CHECKOUT_DIRTY')
        references = {}
        for key, default in [('DATABASE_PATH', 'data/securitylab.sqlite3')] if self.role == 'controller' else (
                [('TARGET_DATABASE_PATH', 'data/target.sqlite3')] if self.role == 'target' else [('TARGET_REGISTRY_PATH', 'config/targets.json')]):
            value = Path(values.get(key) or default)
            path = inside(value if value.is_absolute() else root / value, root)
            permitted = root / ('config' if key == 'TARGET_REGISTRY_PATH' else 'data')
            # A previous release uses runtime-config for the preserved operator registry.
            require(path.is_relative_to(permitted) or (key == 'TARGET_REGISTRY_PATH' and path.is_relative_to(root / 'runtime-config')),
                    'EXTERNAL_RUNTIME_PATH_UNSUPPORTED')
            references[key] = str(path)
        return {'role': self.role, 'commit': self.cmd(['git', 'rev-parse', 'HEAD'], root),
                'checkout': str(root), 'environment_reference': str(env), 'environment_sha256': file_hash(env),
                'setting_names': sorted(values), 'runtime_references': references,
                'runtime_config_hashes': tree_hashes(root / 'config'),
                'preserved_config_hashes': tree_hashes(root / 'runtime-config'),
                'launcher': 'service_config' if (root / 'common/service_config.py').exists() else 'legacy_uvicorn',
                'listener': listener, 'network': self.network()}

    def stage(self, exchange, commit, before, identifier):
        manifest = load(exchange / 'release.json')
        require(manifest['commit'] == commit and file_hash(exchange / 'release.bundle') == manifest['bundle_sha256'], 'RELEASE_MISMATCH')
        root = self.releases / identifier
        root.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        require(not root.exists(), 'RELEASE_ALREADY_EXISTS')
        self.cmd(['git', 'clone', '--no-checkout', '--quiet', exchange / 'release.bundle', root])
        self.cmd(['git', 'checkout', '--detach', commit], root)
        require(self.cmd(['git', 'rev-parse', 'HEAD'], root) == commit, 'RELEASE_MISMATCH')
        old = Path(before['checkout'])
        require(file_hash(old / 'requirements-full.lock') == file_hash(root / 'requirements-full.lock'), 'OFFLINE_DEPENDENCY_CHANGE_REQUIRES_PREPARATION')
        (root / '.venv').symlink_to(self.original / '.venv', target_is_directory=True)
        values = env_values(Path(before['environment_reference']))
        for key, reference in before['runtime_references'].items():
            source = Path(reference)
            if key == 'TARGET_REGISTRY_PATH':
                destination = root / 'runtime-config'
                shutil.copytree(source.parent, destination)
                values[key] = str(destination / source.name)
            else:
                values[key] = str(root / source.relative_to(old))
        new_env = root / ('.env.' + self.role)
        # Write a derived file only; the existing env remains byte-for-byte intact.
        new_env.write_text(''.join(k + "='" + v.replace('\\', '\\\\').replace("'", "\\'") + "'\n" for k, v in values.items()), encoding='utf-8')
        new_env.chmod(0o600)
        require(env_values(new_env) == values, 'ENVIRONMENT_COPY_MISMATCH')
        self.cmd([self.python, '-m', 'common.service_config', 'check', self.role, '--env-file', new_env], root)
        if self.role == 'controller':
            source = exchange / 'frontend-dist'
            require(tree_hashes(source) == manifest['frontend_dist_sha256'] and (source / 'index.html').is_file(), 'FRONTEND_ARTIFACT_MISMATCH')
            shutil.copytree(source, root / 'frontend/dist')
        return root

    def plan(self, exchange, commit, expected):
        full_commit(commit)
        full_commit(expected)
        before = self.inventory()
        require(before['commit'] == expected, 'VERSION_MISMATCH')
        identifier = uuid.uuid4().hex
        root = self.stage(exchange, commit, before, identifier)
        plan = {'schema': 'vm-deployment-v1', 'id': identifier, 'role': self.role, 'commit': commit,
                'before': before, 'checkout': str(root), 'created_at': time.time(),
                'new_environment_sha256': file_hash(root / ('.env.' + self.role)),
                'new_preserved_config_hashes': tree_hashes(root / 'runtime-config'),
                'frontend_hashes': tree_hashes(root / 'frontend/dist'),
                'version_change': expected != commit,
                'data_strategy': 'private consistent copy; originals untouched; rollback retains new data separately'}
        plan['plan_sha256'] = digest(plan)
        write(self.state / 'plans' / (identifier + '.json'), plan)
        return plan

    def plan_read(self, identifier, confirmation):
        require(bool(re.fullmatch('[0-9a-f]{32}', identifier or '')), 'INVALID_PLAN_ID')
        plan = load(self.state / 'plans' / (identifier + '.json'))
        require(plan['role'] == self.role, 'PLAN_ROLE_MISMATCH')
        verify_plan(plan, confirmation, plan['before'])
        return plan

    def journal(self, plan, status, **extra):
        path = self.state / 'history' / (plan['id'] + '.json')
        record = load(path) if path.exists() else {'id': plan['id'], 'commit': plan['commit'], 'events': []}
        record.update(status=status, **extra)
        record['events'].append({'status': status, 'time': time.time()})
        write(path, record)
        return record

    def stop(self, expected):
        actual = self.listener()
        require(actual == expected, 'LISTENER_CHANGED')
        if not actual:
            return
        os.kill(actual['pid'], signal.SIGTERM)
        for _ in range(100):
            if self.listener() is None:
                return
            time.sleep(.1)
        raise DeployError('GRACEFUL_STOP_TIMEOUT_NO_FORCE')

    def health(self):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=3, source_address=('127.0.0.1', 0))
        try:
            connection.request('GET', self.health_path)
            response = connection.getresponse()
            require(response.status == 200 and json.loads(response.read(65536)).get('status') == 'ok', 'HEALTH_FAILED')
            return {'status_code': 200, 'status': 'ok'}
        finally:
            connection.close()

    def launch(self, root, launcher, log):
        require(self.listener() is None, 'PORT_IN_USE')
        if launcher == 'service_config':
            args = [self.python, '-m', 'common.service_config', 'serve', self.role, '--env-file', root / ('.env.' + self.role)]
        else:
            args = [self.python, '-m', 'uvicorn']
            if self.role != 'target':
                args += ['--factory']
            args += [self.module, '--env-file', root / ('.env.' + self.role), '--host', self.host, '--port', str(self.port)]
        # Strip application values inherited from the operator terminal.
        clean = {k: v for k, v in os.environ.items() if k in ('PATH', 'HOME', 'LANG', 'LC_ALL', 'USER', 'LOGNAME')}
        with log.open('ab') as stream:
            process = subprocess.Popen([str(x) for x in args], cwd=root, env=clean,
                                       stdin=subprocess.DEVNULL, stdout=stream, stderr=stream, start_new_session=True)
        try:
            for _ in range(100):
                require(process.poll() is None, 'SERVICE_EXITED')
                listener = self.listener()
                if listener:
                    require(listener['checkout'] == str(root), 'LISTENER_CHANGED')
                    try:
                        self.health()
                        return listener
                    except (OSError, ValueError, DeployError):
                        pass
                time.sleep(.1)
            raise DeployError('HEALTH_TIMEOUT')
        except BaseException:
            # This process group was created by this invocation, never by a port scan.
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    raise DeployError('OWNED_PROCESS_DID_NOT_STOP') from None
            raise

    def backup_copy(self, plan):
        old, new = Path(plan['before']['checkout']), Path(plan['checkout'])
        private = self.state / 'backups' / plan['id']
        private.mkdir(parents=True, mode=0o700)
        self.cmd(['git', 'bundle', 'create', private / 'original.bundle', '--all'], old)
        with tarfile.open(private / 'workspace.tar.gz', 'w:gz') as archive:
            def selected(info):
                parts = Path(info.name).parts
                return None if any(x in parts for x in ('.git', '.venv', 'node_modules', 'verification_tmp')) else info
            archive.add(old, arcname='workspace', filter=selected)
        for name in ('data', 'reports/runs'):
            source = old / name
            tree_hashes(source)  # Reject links before copying any runtime directory.
            if source.exists():
                shutil.copytree(source, new / name, dirs_exist_ok=True)
        baseline = databases(old / 'data')
        for name in baseline:
            src, dst = old / 'data' / name, new / 'data' / name
            # Services are stopped; online backup also handles a retained WAL.
            with contextlib.closing(sqlite3.connect(src.as_uri() + '?mode=ro', uri=True)) as source:
                with contextlib.closing(sqlite3.connect(dst)) as destination:
                    source.backup(destination)
        require(databases(new / 'data') == baseline, 'DATABASE_COPY_MISMATCH')
        write(private / 'baseline.json', {'databases': baseline, 'env': file_hash(Path(plan['before']['environment_reference'])),
                                        'config': tree_hashes(old / 'config'), 'reports': tree_hashes(old / 'reports/runs')})
        return private

    def preservation(self, plan):
        old, new = Path(plan['before']['checkout']), Path(plan['checkout'])
        baseline = load(self.state / 'backups' / plan['id'] / 'baseline.json')
        require(file_hash(Path(plan['before']['environment_reference'])) == baseline['env'], 'ORIGINAL_ENVIRONMENT_CHANGED')
        require(tree_hashes(old / 'config') == baseline['config'], 'ORIGINAL_CONFIG_CHANGED')
        require(tree_hashes(old / 'reports/runs') == baseline['reports'], 'ORIGINAL_REPORTS_CHANGED')
        require(databases(old / 'data') == baseline['databases'], 'ORIGINAL_DATABASE_CHANGED')
        require(rows_preserved(baseline['databases'], databases(new / 'data')), 'DEPLOYED_DATABASE_ROWS_LOST')
        require(self.network() == plan['before']['network'], 'NETWORK_OR_FIREWALL_CHANGED')
        return {'original_environment_config_reports_unchanged': True, 'original_database_rows_exact': True,
                'deployed_database_existing_rows_preserved': True, 'database_count': len(baseline['databases']),
                'network_and_firewall_unchanged': True}

    def validate_recovery_source(self, plan):
        before = plan['before']
        old = Path(before['checkout'])
        require(self.cmd(['git', 'rev-parse', 'HEAD'], old) == before['commit'] and
                not self.cmd(['git', 'status', '--porcelain', '--untracked-files=no'], old), 'RECOVERY_VERSION_CHANGED')
        require(file_hash(Path(before['environment_reference'])) == before['environment_sha256'] and
                tree_hashes(old / 'config') == before['runtime_config_hashes'] and
                tree_hashes(old / 'runtime-config') == before['preserved_config_hashes'], 'RECOVERY_CONFIGURATION_CHANGED')
        require(self.network() == before['network'], 'NETWORK_OR_FIREWALL_CHANGED')

    def recover(self, plan):
        old, new = Path(plan['before']['checkout']), Path(plan['checkout'])
        self.validate_recovery_source(plan)
        current = self.listener()
        if current and current['checkout'] == str(new):
            self.stop(current)
        elif current:
            require(current['checkout'] == str(old), 'UNKNOWN_LISTENER_NOT_STOPPED')
        restored = self.listener()
        if plan['before']['listener']:
            if not restored:
                restored = self.launch(old, plan['before']['launcher'], self.state / 'rollback.log')
            health = self.health()
        else:
            require(restored is None, 'ORIGINAL_STOPPED_STATE_NOT_RESTORED')
            health = {'status': 'originally_stopped'}
        write(self.state / 'active.json', {'checkout': str(old)})
        require(self.network() == plan['before']['network'], 'NETWORK_OR_FIREWALL_CHANGED')
        return {'restored_checkout': str(old), 'health': health, 'new_data_retained_at': str(new / 'data')}

    def apply(self, identifier, confirmation):
        plan = self.plan_read(identifier, confirmation)
        history = self.state / 'history' / (identifier + '.json')
        if history.exists():
            previous = load(history)
            require(previous['status'] == 'HEALTHY', 'PLAN_ALREADY_USED_OR_RECOVERY_REQUIRED')
            current = self.inventory()
            require(current['checkout'] == plan['checkout'] and current['commit'] == plan['commit'], 'ACTIVE_RELEASE_CHANGED')
            require(current['environment_sha256'] == plan['new_environment_sha256'] and
                    current['preserved_config_hashes'] == plan['new_preserved_config_hashes'], 'ACTIVE_CONFIGURATION_CHANGED')
            self.health()
            return {'status': 'ALREADY_HEALTHY', 'id': identifier, 'preservation': self.preservation(plan)}
        verify_plan(plan, confirmation, self.inventory())
        new = Path(plan['checkout'])
        require(self.cmd(['git', 'rev-parse', 'HEAD'], new) == plan['commit'] and
                not self.cmd(['git', 'status', '--porcelain', '--untracked-files=no'], new), 'STAGED_CODE_CHANGED')
        require(file_hash(new / ('.env.' + self.role)) == plan['new_environment_sha256'] and
                tree_hashes(new / 'runtime-config') == plan['new_preserved_config_hashes'] and
                tree_hashes(new / 'frontend/dist') == plan['frontend_hashes'], 'STAGED_RUNTIME_CHANGED')
        self.journal(plan, 'STOPPING')
        try:
            self.stop(plan['before']['listener'])
            self.journal(plan, 'STOPPED')
            self.backup_copy(plan)
            self.journal(plan, 'BACKED_UP')
            self.journal(plan, 'STARTING')
            self.launch(new, 'service_config', self.state / (identifier + '.service.log'))
            preserved = self.preservation(plan)
            write(self.state / 'active.json', {'checkout': str(new)})
            return self.journal(plan, 'HEALTHY', health=self.health(), preservation=preserved)
        except BaseException:
            self.journal(plan, 'RECOVERING')
            try:
                restored = self.recover(plan)
                self.journal(plan, 'ROLLED_BACK_AFTER_FAILURE', recovery=restored)
            except Exception:
                self.journal(plan, 'RECOVERY_REQUIRED')
                raise DeployError('DEPLOYMENT_FAILED_RECOVERY_REQUIRED') from None
            raise DeployError('DEPLOYMENT_FAILED_ROLLED_BACK') from None

    def rollback(self, identifier, confirmation):
        plan = self.plan_read(identifier, confirmation)
        history = load(self.state / 'history' / (identifier + '.json'))
        require(history['status'] in ('HEALTHY', 'STOPPING', 'STOPPED', 'BACKED_UP', 'STARTING', 'RECOVERING',
                                     'RECOVERY_REQUIRED', 'ROLLED_BACK', 'ROLLED_BACK_AFTER_FAILURE'), 'INVALID_RECOVERY_STATE')
        # Refuse to roll back over a different, newer deployment.
        active = self.state / 'active.json'
        if active.exists():
            require(load(active)['checkout'] in (plan['checkout'], plan['before']['checkout']), 'NEWER_DEPLOYMENT_ACTIVE')
        self.journal(plan, 'RECOVERING')
        try:
            restored = self.recover(plan)
            return self.journal(plan, 'ROLLED_BACK', recovery=restored)
        except Exception:
            self.journal(plan, 'RECOVERY_REQUIRED')
            raise DeployError('RECOVERY_REQUIRED') from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('inspect', 'plan', 'apply', 'rollback', 'status'))
    parser.add_argument('--exchange', type=Path, required=True, help='operator-owned local transfer directory')
    parser.add_argument('--commit')
    parser.add_argument('--expected')
    parser.add_argument('--plan')
    parser.add_argument('--confirm')
    args = parser.parse_args()
    role = socket.gethostname().removeprefix('security-')
    result = {'role': role, 'action': args.action, 'ok': False, 'time': time.time()}
    os.umask(0o077)
    try:
        require(sys.platform == 'linux' and os.getuid() == 1000, 'REGISTERED_GUEST_USER_REQUIRED')
        vm = VM(role)
        with vm.lock():
            if args.action in ('inspect', 'status'):
                result['inventory'] = vm.inventory()
                if args.action == 'status':
                    result['history'] = [load(p) for p in sorted((vm.state / 'history').glob('*.json'))]
            elif args.action == 'plan':
                result['plan'] = vm.plan(args.exchange, args.commit, args.expected)
            elif args.action == 'apply':
                result['result'] = vm.apply(args.plan, args.confirm)
            else:
                result['result'] = vm.rollback(args.plan, args.confirm)
        result['ok'] = True
    except DeployError as exc:
        result['reason_code'] = str(exc)
    except Exception as exc:
        result['reason_code'] = 'OPERATION_FAILED'
        result['error_type'] = type(exc).__name__
    # No exception text, command output, environment values, or DB rows are public.
    write(args.exchange / 'public' / (args.action + '.json'), result)
    print(json.dumps(result, indent=2))
    return 0 if result['ok'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
