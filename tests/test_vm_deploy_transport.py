import json
import sys
import subprocess

import pytest

from scripts import vm_deploy_host as host, vm_deploy_dispatcher as dispatcher
from scripts.vm_deploy import DeployError, VM, load, write


def exchange(tmp_path):
    folder = tmp_path / 'worker'
    write(folder / 'public/ready.json', {'role': 'worker', 'protocol': 2})
    return folder


def failing_child_receipt(folder):
    job = load(folder / 'job.json')
    receipt = {**{k: job[k] for k in ('sequence', 'action')}, 'role': 'worker', 'exit_code': 23}
    # Both paths let this reproduce the original bug and exercise the new protocol.
    write(folder / 'public/receipt.json', receipt)
    write(folder / 'public' / ('receipt-' + job['sequence'] + '.json'), receipt)


def test_old_success_file_cannot_override_new_job_exit_failure(tmp_path, monkeypatch):
    folder = exchange(tmp_path)
    old = {'role': 'worker', 'action': 'apply', 'sequence': '0' * 32, 'ok': True}
    write(folder / 'public/apply.json', old)
    monkeypatch.setattr(host.time, 'sleep', lambda _: failing_child_receipt(folder))
    monkeypatch.setattr(sys, 'argv', ['host', 'apply', '--exchange', str(tmp_path), '--role', 'worker',
                                    '--plan', '1' * 32, '--confirm', '2' * 64])
    assert host.main() == 2
    assert (folder / 'pending.json').exists()
    assert load(folder / 'public/apply.json') == old


def network_vm(tmp_path, monkeypatch, role='worker', ipv4=None, ipv6=None):
    vm = VM(role, tmp_path)
    calls = []
    def command(args, cwd=None):
        calls.append(args)
        if args[:3] == ['ip', '-j', 'address']:
            return '[]'
        if args[:3] == ['ip', '-6', '-j']:
            return json.dumps(ipv6 or [])
        if args[0] == 'ip':
            return json.dumps(ipv4 or [])
        return '*filter\n:INPUT DROP [0:0]\nCOMMIT'
    monkeypatch.setattr(vm, 'cmd', command)
    return vm, calls


@pytest.mark.parametrize('role', ['worker', 'target'])
def test_ipv6_only_default_route_rejected(tmp_path, monkeypatch, role):
    vm, _ = network_vm(tmp_path, monkeypatch, role, ipv6=[{'dst': 'default', 'gateway': 'fe80::1'}])
    with pytest.raises(DeployError, match='INTERNET_ISOLATION_UNPROVEN'):
        vm.network()


def terminal_pair(folder, job, *, rc=0, result=None, receipt_changes=None):
    identity = {k: job[k] for k in ('sequence', 'action', 'role')}
    if result is not None:
        write(folder / 'public' / ('result-' + job['sequence'] + '.json'), result)
    receipt = dict(identity, exit_code=rc)
    receipt.update(receipt_changes or {})
    write(folder / 'public' / ('receipt-' + job['sequence'] + '.json'), receipt)


@pytest.mark.parametrize('fault', ['missing', 'old_sequence', 'action', 'role', 'invalid_json',
                                 'false_result', 'exit_nonzero', 'exit_missing', 'exit_bool', 'receipt_sequence'])
def test_uncorrelated_or_failed_completion_blocks_another_submission(tmp_path, monkeypatch, fault):
    folder = exchange(tmp_path)
    def complete(_):
        job = load(folder / 'job.json')
        result = dict(job, ok=True)
        rc, receipt_changes = 0, {}
        if fault == 'missing': result = None
        if fault == 'old_sequence': result['sequence'] = 'f' * 32
        if fault == 'action': result['action'] = 'rollback'
        if fault == 'role': result['role'] = 'target'
        if fault == 'false_result': result['ok'] = False
        if fault == 'exit_nonzero': rc = 23
        if fault == 'exit_missing': rc = None
        if fault == 'exit_bool': rc = False
        if fault == 'receipt_sequence': receipt_changes['sequence'] = 'e' * 32
        terminal_pair(folder, job, rc=rc, result=result, receipt_changes=receipt_changes)
        if fault == 'invalid_json':
            (folder / 'public' / ('result-' + job['sequence'] + '.json')).write_text('{')
    monkeypatch.setattr(host.time, 'sleep', complete)
    outcome = host.send(folder, {'action': 'apply'})
    assert outcome['ok'] is False
    original_job = (folder / 'job.json').read_bytes()
    pending = (folder / 'pending.json').read_bytes()
    with pytest.raises(DeployError, match='PREVIOUS_JOB_UNRESOLVED'):
        host.send(folder, {'action': 'rollback'})
    assert (folder / 'job.json').read_bytes() == original_job
    assert (folder / 'pending.json').read_bytes() == pending


def test_real_child_exits_before_result_write_with_old_apply_success(tmp_path, monkeypatch):
    folder = exchange(tmp_path)
    private = tmp_path / 'private'
    private.mkdir()
    (folder / 'vm_deploy.py').write_text('raise SystemExit(23)\n')
    old = {'role': 'worker', 'action': 'apply', 'sequence': '0' * 32, 'ok': True}
    write(folder / 'public/apply.json', old)
    actual_run = subprocess.run
    def python_child(command, **kwargs):
        assert '--sequence' in command
        return actual_run([sys.executable, *command[1:]], **kwargs)
    monkeypatch.setattr(dispatcher.subprocess, 'run', python_child)
    monkeypatch.setattr(host.time, 'sleep', lambda _: dispatcher.execute_job('worker', folder, private, load(folder / 'job.json')))
    outcome = host.send(folder, {'action': 'apply'})
    assert not outcome['ok'] and outcome['receipt']['exit_code'] == 23
    assert outcome['result'] is None and outcome['result_state'] == 'missing'
    assert load(folder / 'public/apply.json') == old
    assert (folder / 'pending.json').exists()


def test_success_is_correlated_and_old_alias_is_ignored(tmp_path, monkeypatch):
    folder = exchange(tmp_path)
    write(folder / 'public/apply.json', {'ok': False, 'sequence': '0' * 32})
    def complete(_):
        job = load(folder / 'job.json')
        terminal_pair(folder, job, result=dict(job, ok=True))
    monkeypatch.setattr(host.time, 'sleep', complete)
    outcome = host.send(folder, {'action': 'apply'})
    assert outcome['ok'] is True
    assert outcome['job']['sequence'] == outcome['receipt']['sequence'] == outcome['result']['sequence']
    assert not (folder / 'pending.json').exists()


def test_timeout_collects_late_result_without_resending(tmp_path):
    folder = exchange(tmp_path)
    with pytest.raises(DeployError, match='JOB_TIMEOUT'):
        host.send(folder, {'action': 'apply'}, timeout=0)
    job_bytes = (folder / 'job.json').read_bytes()
    job = load(folder / 'pending.json')
    with pytest.raises(DeployError, match='PREVIOUS_JOB_UNRESOLVED'):
        host.send(folder, {'action': 'apply'}, timeout=0)
    terminal_pair(folder, job, result=dict(job, ok=True))
    assert host.collect(folder, job['sequence'])['ok']
    assert (folder / 'job.json').read_bytes() == job_bytes


def test_dispatcher_spawn_failure_is_not_a_success(tmp_path, monkeypatch):
    folder = exchange(tmp_path)
    def cannot_spawn(*a, **k): raise OSError('private exception text')
    monkeypatch.setattr(dispatcher.subprocess, 'run', cannot_spawn)
    job = {'role': 'worker', 'action': 'apply', 'sequence': '1' * 32}
    receipt = dispatcher.execute_job('worker', folder, tmp_path, job)
    assert receipt['exit_code'] is None
    assert 'private exception text' not in json.dumps(receipt)
    assert host.read_completion(folder, job)['ok'] is False


def test_consumed_job_stays_consumed_after_other_jobs(tmp_path):
    assert dispatcher.claim_job(tmp_path, '1' * 32)
    assert dispatcher.claim_job(tmp_path, '2' * 32)
    assert not dispatcher.claim_job(tmp_path, '1' * 32)


def test_stop_has_matching_result_and_receipt(tmp_path):
    folder = exchange(tmp_path)
    job = {'role': 'worker', 'action': 'stop', 'sequence': '1' * 32}
    dispatcher.execute_job('worker', folder, tmp_path, job)
    assert host.read_completion(folder, job)['ok'] is True


@pytest.mark.parametrize('family,dst', [('4', 'default'), ('4', '0.0.0.0/0'), ('6', '::/0')])
def test_each_family_default_route_is_rejected(tmp_path, monkeypatch, family, dst):
    vm, _ = network_vm(tmp_path, monkeypatch, ipv4=[{'dst': dst}] if family == '4' else [],
                       ipv6=[{'dst': dst}] if family == '6' else [])
    with pytest.raises(DeployError, match='INTERNET_ISOLATION_UNPROVEN'):
        vm.network()


def test_both_route_tables_are_collected_and_ipv6_change_invalidates_plan(tmp_path, monkeypatch):
    from tests.test_vm_deploy import FakeVM, plan_for
    ipv6 = [{'dst': 'fe80::/64', 'dev': 'eth0', 'metric': 100}]
    vm, calls = network_vm(tmp_path, monkeypatch, ipv6=ipv6)
    before = vm.network()
    assert ['ip', '-4', '-j', 'route', 'show', 'table', 'all'] in calls
    assert ['ip', '-6', '-j', 'route', 'show', 'table', 'all'] in calls
    assert before['routes_ipv4'] == [] and before['routes_ipv6'] == ipv6
    fake = FakeVM(tmp_path / 'fake')
    plan = plan_for(fake)
    plan['before']['network'] = before
    from scripts.vm_deploy import digest
    plan['plan_sha256'] = digest({k: v for k, v in plan.items() if k != 'plan_sha256'})
    write(fake.state / 'plans' / (plan['id'] + '.json'), plan)
    import copy
    fake.before = copy.deepcopy(plan['before'])
    fake.before['network']['routes_ipv6'][0]['metric'] = 200
    with pytest.raises(DeployError, match='CURRENT_STATE_CHANGED'):
        fake.apply(plan['id'], plan['plan_sha256'])
    assert fake.events == []


def test_controller_records_ipv6_default_without_worker_restriction(tmp_path, monkeypatch):
    vm, _ = network_vm(tmp_path, monkeypatch, 'controller', ipv6=[{'dst': 'default'}])
    assert vm.network()['routes_ipv6'] == [{'dst': 'default'}]
