import asyncio
import json
import secrets

import httpx
import pytest

from common.service_config import ALL_KEYS, COMMANDS, ServiceConfigError, child_environment, validate_config
from scripts import operator_vm_target
from scripts.operator_fixture import settings
from verifier.operator import verify_operator
from worker.limits import WorkerLimits
from worker.operator_scope import parse_operator_registry
from worker.operator_service import OperatorService


def environment(mode):
    return dict(LAB_USER_A_PASSWORD=secrets.token_urlsafe(24), LAB_USER_B_PASSWORD=secrets.token_urlsafe(24),
                OPERATOR_PROOF_A=secrets.token_urlsafe(32), OPERATOR_PROOF_B=secrets.token_urlsafe(32), OPERATOR_TARGET_MODE=mode)


@pytest.mark.parametrize('mode', ['vulnerable', 'fixed'])
def test_vm_launcher_uses_dedicated_secrets_and_counter(tmp_path, monkeypatch, mode):
    env = environment(mode)
    for key in ALL_KEYS:
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(operator_vm_target, 'COUNTER', tmp_path / 'counter.json')
    app = operator_vm_target.create_app_from_env()
    registry = parse_operator_registry(settings()).bind_proofs(env)
    worker = OperatorService(registry=registry, accounts=registry.credentials(env),
                             limits=WorkerLimits(requests_per_second=1000), transport=httpx.ASGITransport(app=app))
    policy = worker.policy()
    assert json.loads((tmp_path / 'counter.json').read_text())['received_http_requests'] == 0

    async def execute():
        rows = []
        for step in policy.sequence():
            result = await worker.operator_step('vm-launcher-test', 'lab-web', **step.model_dump(),
                                                expected_snapshot_sha256=policy.scope_policy.snapshot_sha256)
            assert result.ok
            rows.append(result.evidence)
        assert (await worker.operator_finish('vm-launcher-test', policy.scope_policy.snapshot_sha256)).ok
        return rows

    rows = asyncio.run(execute())
    assert verify_operator(rows, policy, run_id='vm-launcher-test')['verdict'] == (
        'VULNERABLE' if mode == 'vulnerable' else 'BLOCKED_BY_ACCESS_CONTROL')
    counter = (tmp_path / 'counter.json').read_text()
    assert json.loads(counter)['received_http_requests'] == 11
    assert not any(value in counter for value in env.values())
    assert not list(tmp_path.glob('*.sqlite3'))


@pytest.mark.parametrize('change', ['missing_password', 'missing_proof', 'same_proof', 'short_proof', 'mode', 'foreign_secret'])
def test_vm_target_invalid_configuration_fails_closed(change):
    env = environment('vulnerable')
    if change == 'missing_password': env.pop('LAB_USER_A_PASSWORD')
    if change == 'missing_proof': env.pop('OPERATOR_PROOF_A')
    if change == 'same_proof': env['OPERATOR_PROOF_A'] = env['OPERATOR_PROOF_B']
    if change == 'short_proof': env['OPERATOR_PROOF_A'] = 'short'
    if change == 'mode': env['OPERATOR_TARGET_MODE'] = 'arbitrary'
    if change == 'foreign_secret': env['OPENAI_API_KEY'] = secrets.token_urlsafe(32)
    with pytest.raises(ServiceConfigError) as exc:
        validate_config('operator-target', env)
    assert not any(value in str(exc.value) for value in env.values() if len(value) > 16)


def test_vm_target_fixed_launch_and_environment_isolation():
    env = environment('fixed')
    assert validate_config('operator-target', env)['ok']
    filtered = child_environment(env, {'WORKER_TOKEN': 'do-not-forward', 'OPENAI_API_KEY': 'do-not-forward'})
    assert filtered == env
    command = COMMANDS['operator-target']
    assert command[command.index('--host') + 1] == '10.78.0.30'
    assert command[command.index('--port') + 1] == '8080'
