import copy
import json
from pathlib import Path
import sqlite3

import pytest

from scripts.vm_deploy import (DeployError, VM, database_rows, digest, env_values,
                              full_commit, inside, load, rows_preserved, verify_plan, write)


def plan_for(vm, running=True):
    old = vm.original
    new = vm.releases / ('1' * 32)
    new.mkdir(parents=True)
    (new / '.env.worker').write_text('WORKER_TOKEN=secret\n')
    from scripts.vm_deploy import file_hash
    before = {'role': 'worker', 'commit': 'a' * 40, 'checkout': str(old), 'network': {},
              'listener': {'pid': 101, 'checkout': str(old)} if running else None, 'launcher': 'service_config'}
    plan = {'id': '1' * 32, 'role': 'worker', 'commit': 'b' * 40, 'before': before,
            'checkout': str(new), 'new_environment_sha256': file_hash(new / '.env.worker'),
            'new_preserved_config_hashes': {}, 'frontend_hashes': {}}
    plan['plan_sha256'] = digest(plan)
    write(vm.state / 'plans' / (plan['id'] + '.json'), plan)
    return plan


class FakeVM(VM):
    """Model real transitions and distinct original/new listeners; never open sockets."""
    def __init__(self, home):
        super().__init__('worker', home)
        self.events = []
        self.current = None
        self.fail = None

    def cmd(self, args, cwd=None):
        return 'b' * 40 if 'rev-parse' in args else ''

    def inventory(self):
        return copy.deepcopy(self.before)

    def listener(self):
        return self.current

    def network(self):
        return {}

    def stop(self, expected):
        assert self.current == expected
        self.events.append('stop')
        self.current = None

    def backup_copy(self, plan):
        self.events.append('backup')
        if self.fail == 'backup':
            raise OSError('private details must not be public')

    def launch(self, root, launcher, log):
        self.events.append('launch-old' if root == self.original else 'launch-new')
        if root != self.original and self.fail == 'health':
            raise DeployError('HEALTH_TIMEOUT')
        self.current = {'pid': 101 if root == self.original else 202, 'checkout': str(root)}
        return self.current

    def health(self):
        return {'status_code': 200, 'status': 'ok'}

    def preservation(self, plan):
        self.events.append('preserve')
        if self.fail == 'preservation':
            raise DeployError('ORIGINAL_DATABASE_CHANGED')
        return {'ok': True}

    def validate_recovery_source(self, plan):
        return None


@pytest.mark.parametrize('value', ['2120841', 'main', '-a' * 20, 'A' * 40, '../bad', None])
def test_release_requires_literal_full_commit(value):
    with pytest.raises(DeployError, match='FULL_COMMIT_REQUIRED'):
        full_commit(value)


def test_version_mismatch_never_stages_or_stops(tmp_path, monkeypatch):
    vm = FakeVM(tmp_path)
    vm.before = {'commit': 'a' * 40}
    monkeypatch.setattr(vm, 'stage', lambda *a: pytest.fail('must not stage'))
    with pytest.raises(DeployError, match='VERSION_MISMATCH'):
        vm.plan(tmp_path, 'b' * 40, 'c' * 40)
    assert vm.events == []


@pytest.mark.parametrize('change', ['commit', 'network', 'environment_reference', 'listener'])
def test_plan_rejects_drift_before_stop(tmp_path, change):
    vm = FakeVM(tmp_path)
    plan = plan_for(vm)
    vm.before = copy.deepcopy(plan['before'])
    vm.before[change] = 'changed'
    with pytest.raises(DeployError, match='CURRENT_STATE_CHANGED'):
        vm.apply(plan['id'], plan['plan_sha256'])
    assert vm.events == []


def test_plan_tamper_and_wrong_confirmation(tmp_path):
    vm = FakeVM(tmp_path)
    plan = plan_for(vm)
    with pytest.raises(DeployError, match='PLAN_CONFIRMATION_MISMATCH'):
        verify_plan(plan, '0' * 64, plan['before'])
    plan['commit'] = 'c' * 40
    with pytest.raises(DeployError, match='PLAN_CONFIRMATION_MISMATCH'):
        verify_plan(plan, plan['plan_sha256'], plan['before'])


@pytest.mark.parametrize('running', [True, False])
@pytest.mark.parametrize('failure', ['backup', 'health', 'preservation'])
def test_failure_recovers_original_running_or_stopped_state(tmp_path, running, failure):
    vm = FakeVM(tmp_path)
    plan = plan_for(vm, running)
    vm.before, vm.current, vm.fail = plan['before'], plan['before']['listener'], failure
    with pytest.raises(DeployError, match='DEPLOYMENT_FAILED_ROLLED_BACK'):
        vm.apply(plan['id'], plan['plan_sha256'])
    assert vm.current == plan['before']['listener']
    history = load(vm.state / 'history' / (plan['id'] + '.json'))
    assert history['status'] == 'ROLLED_BACK_AFTER_FAILURE'
    assert 'private details' not in json.dumps(history)
    with pytest.raises(DeployError, match='PLAN_ALREADY_USED'):
        vm.apply(plan['id'], plan['plan_sha256'])


def test_success_idempotence_and_explicit_rollback(tmp_path):
    vm = FakeVM(tmp_path)
    plan = plan_for(vm)
    vm.before, vm.current = plan['before'], plan['before']['listener']
    assert vm.apply(plan['id'], plan['plan_sha256'])['status'] == 'HEALTHY'
    assert vm.events == ['stop', 'backup', 'launch-new', 'preserve']
    vm.before = {'checkout': plan['checkout'], 'commit': plan['commit'],
                 'environment_sha256': plan['new_environment_sha256'], 'preserved_config_hashes': {}}
    assert vm.apply(plan['id'], plan['plan_sha256'])['status'] == 'ALREADY_HEALTHY'
    assert vm.events.count('stop') == 1
    assert vm.rollback(plan['id'], plan['plan_sha256'])['status'] == 'ROLLED_BACK'
    assert vm.current == plan['before']['listener']


def test_rollback_refuses_newer_release(tmp_path):
    vm = FakeVM(tmp_path)
    plan = plan_for(vm)
    vm.journal(plan, 'HEALTHY')
    write(vm.state / 'active.json', {'checkout': '/different/release'})
    with pytest.raises(DeployError, match='NEWER_DEPLOYMENT_ACTIVE'):
        vm.rollback(plan['id'], plan['plan_sha256'])
    assert vm.events == []


def test_failed_recovery_is_durable_and_not_reported_success(tmp_path, monkeypatch):
    vm = FakeVM(tmp_path)
    plan = plan_for(vm)
    vm.before, vm.current, vm.fail = plan['before'], plan['before']['listener'], 'health'
    def fail_recovery(*args): raise OSError('failure')
    monkeypatch.setattr(vm, 'recover', fail_recovery)
    with pytest.raises(DeployError, match='DEPLOYMENT_FAILED_RECOVERY_REQUIRED'):
        vm.apply(plan['id'], plan['plan_sha256'])
    assert load(vm.state / 'history' / (plan['id'] + '.json'))['status'] == 'RECOVERY_REQUIRED'


def test_database_comparison_detects_duplicate_row_loss(tmp_path):
    path = tmp_path / 'test.sqlite3'
    with sqlite3.connect(path) as con:
        con.execute('CREATE TABLE sample(value TEXT)')
        con.executemany('INSERT INTO sample VALUES (?)', [('a',), ('a',)])
    before = {'test.sqlite3': database_rows(path)}
    with sqlite3.connect(path) as con:
        con.execute('DELETE FROM sample WHERE rowid=1')
    assert not rows_preserved(before, {'test.sqlite3': database_rows(path)})
    assert rows_preserved(before, before)


@pytest.mark.parametrize('text', ['KEY=${OTHER}', 'KEY=one\nKEY=two', 'KEY="unfinished'])
def test_environment_rejects_interpolation_duplicate_and_bad_syntax(tmp_path, text):
    path = tmp_path / 'settings'
    path.write_text(text)
    with pytest.raises(DeployError, match='INVALID_ENVIRONMENT'):
        env_values(path)


def test_runtime_path_must_stay_inside_checkout(tmp_path):
    with pytest.raises(DeployError, match='PATH_OUTSIDE_CHECKOUT'):
        inside(tmp_path / '../outside', tmp_path)


def test_recovery_refuses_changed_version_before_stopping_service(tmp_path):
    vm = FakeVM(tmp_path)
    plan = plan_for(vm)
    with pytest.raises(DeployError, match='RECOVERY_VERSION_CHANGED'):
        VM.validate_recovery_source(vm, plan)
    assert vm.events == []


def test_staged_environment_drift_never_stops_service(tmp_path):
    vm = FakeVM(tmp_path)
    plan = plan_for(vm)
    vm.before = plan['before']
    (Path(plan['checkout']) / '.env.worker').write_text('WORKER_TOKEN=changed\n')
    with pytest.raises(DeployError, match='STAGED_RUNTIME_CHANGED'):
        vm.apply(plan['id'], plan['plan_sha256'])
    assert vm.events == []


@pytest.mark.parametrize('job', [{'action': 'shell'}, {'action': 'plan', 'commit': '2120841'},
                                {'action': 'apply', 'confirm': 'not-a-digest'}, {'action': 'inspect', 'command': 'whoami'}])
def test_host_rejects_invalid_jobs_before_delivery(tmp_path, job):
    from scripts.vm_deploy_host import send
    with pytest.raises(DeployError, match='INVALID_'):
        send(tmp_path, job, timeout=0)
    assert not list(tmp_path.iterdir())
