"""New attachment API applicability and publication boundaries (actual TCP)."""
import ast
import asyncio
import json
from pathlib import Path
import secrets

import pytest
from pydantic import ValidationError

from common.operator_contract import ResourceAdapter, ResourceRoutes
from controller.candidate_execution import CandidateError
from controller.candidates import analyse
from controller.operator_client import ResourcePolicyClient
from controller.operator_execution import ResourceHistory, execute_plan
from scripts import run_independent_api_validation as harness
from validation.independent_api.api import AttachmentService, attachment_server
from validation.independent_api.configuration import registry_for, specification
from validation.independent_api.transport import worker_server


NORMAL = [(a, v, t, 'normal') for a in ('cookie', 'bearer') for v in (True, False) for t in ('function', 'mcp')]
NEGATIVE = [('cookie', True, t, c) for c in ('policy_change', 'budget2', 'owner_mismatch', 'proof_rotation') for t in ('function', 'mcp')]


@pytest.mark.parametrize('auth,vulnerable,transport,case', NORMAL + NEGATIVE)
def test_independent_matrix_over_tcp(tmp_path, auth, vulnerable, transport, case, monkeypatch):
    import controller.operator_execution as execution
    import controller.providers as providers
    original = execution.verify_operator
    calls = []

    def verify_only_observations(evidence, policy, *, run_id):
        assert type(evidence) is list and all(type(e).__name__ == 'ResourceEvidence' for e in evidence)
        assert type(policy).__name__ == 'ResourcePolicy'
        calls.append(run_id)
        return original(evidence, policy, run_id=run_id)

    def no_provider(*args, **kwargs):
        pytest.fail('operator validation must not call a model provider')

    monkeypatch.setattr(execution, 'verify_operator', verify_only_observations)
    monkeypatch.setattr(providers.MockModelProvider, 'propose_candidates', no_provider)
    row = harness.run_case(tmp_path, auth, vulnerable, transport, case)
    assert row['passed'], row
    assert row['preview_target_requests'] == 0
    folder = tmp_path / row['path']
    assert json.loads((folder / 'publication_check.json').read_text())['matches'] == 0
    if case == 'policy_change':
        assert row['reason_code'] == 'WORKER_POLICY_CHANGED'
        assert row['run_id'] is None and row['actual_verdict'] is None and row['replay'] is None
        assert not calls and row['claimed_count'] == 0
    else:
        assert row['plan_run_link_matches'] and row['scope_matches_plan']
        assert row['replay']['verdict_matches']
        counts = json.loads((folder / 'target_measurement.json').read_text())
        assert counts['received'] == row['worker_usage']['http_requests']
        if case in ('owner_mismatch', 'proof_rotation'):
            assert row['reason_code'] == 'OWNER_RESOURCE_PROOF_UNPROVEN'
            assert row['actual_verdict'] == 'INCONCLUSIVE' and len(calls) == 1
        if case == 'normal':
            assert row['status'] == 'COMPLETED' and row['evidence_count'] == 11 and len(calls) == 1
            assert row['worker_usage'] == {'http_requests': 11, 'tool_calls': 12}
            assert [e['operation'] for e in counts['events']] == [
                'login', 'login', 'identity', 'identity', 'owner_attachment', 'owner_attachment',
                'cross_attachment', 'owner_attachment', 'owner_attachment', 'identity', 'identity']
            assert counts['events'][6]['status'] == (200 if vulnerable else 403)
        if case == 'budget2':
            assert row['observed_target_http_requests'] == 2 and not calls


@pytest.mark.parametrize('transport', ['function', 'mcp'])
def test_explicit_digest_and_single_use_over_tcp(tmp_path, transport):
    api = AttachmentService('cookie', True)
    env = dict(LAB_USER_A_PASSWORD=api.members[0].password, LAB_USER_B_PASSWORD=api.members[1].password,
               OPERATOR_PROOF_A=api.attachments[0].receipt, OPERATOR_PROOF_B=api.attachments[1].receipt)
    token = secrets.token_urlsafe(32)
    with attachment_server(api) as port:
        source, registry = tmp_path / 'openapi.json', tmp_path / 'registry.json'
        harness.write_json(source, specification('cookie'))
        harness.write_json(registry, registry_for('cookie', port))
        service, app = harness.new_worker(registry, env, token)
        history = ResourceHistory(tmp_path / 'history')
        with worker_server(app) as worker_port:
            policy = ResourcePolicyClient(f'http://127.0.0.1:{worker_port}', token)
            plan = asyncio.run(harness.prepare(tmp_path, source, registry, transport, policy, history, api))
            with pytest.raises(CandidateError, match='PLAN_CONFIRMATION_MISMATCH'):
                asyncio.run(execute_plan(source, registry, plan, '0'*64, policy, history,
                                        lambda t: pytest.fail('unconfirmed plan opened client'),
                                        tmp_path / 'runs', approval_actor='codex'))
            assert api.received == 0 and not list((tmp_path / 'history').glob('*.claimed.json'))
            report = asyncio.run(harness.run_plan(tmp_path, source, registry, plan, policy, history, token))
            assert report['verdict'] == 'VULNERABLE'
            with pytest.raises(CandidateError, match='PLAN_ALREADY_CONSUMED'):
                asyncio.run(harness.run_plan(tmp_path, source, registry, plan, policy, history, token))
            assert api.received == 11 and len(list((tmp_path / 'history').glob('*.claimed.json'))) == 1


def test_publication_fails_closed_before_copy(tmp_path, monkeypatch):
    def leaking(folder, api, token, *args):
        harness.write_json(folder / 'accidental.json', {'value': api.members[0].password})
        return {'passed': True}
    monkeypatch.setattr(harness, 'exercise', leaking)
    with pytest.raises(AssertionError, match='SECRET_REDACTION_FAILED'):
        harness.run_case(tmp_path, 'cookie', True, 'function')
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('kind', ['password', 'token', 'proof', 'rotated_proof'])
def test_publication_detects_every_secret_category(tmp_path, kind):
    value = secrets.token_urlsafe(36)
    harness.write_json(tmp_path / 'public.json', {kind: value})
    with pytest.raises(AssertionError, match='SECRET_REDACTION_FAILED'):
        harness.publication_check(tmp_path, [value])


def test_server_has_no_agent_or_fixture_dependencies():
    path = Path('validation/independent_api/api.py')
    tree = ast.parse(path.read_text())
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name.split('.')[0] for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            imports.append(node.module.split('.')[0])
    assert set(imports) <= {'contextlib', 'dataclasses', 'http', 'hmac', 'json', 'secrets', 'threading'}


def test_adapter_does_not_silently_accept_mismatched_response_structure(tmp_path):
    config = registry_for('cookie', 18080)
    config['targets']['lab-web']['adapter']['proof_field'] = 'content.missing.receipt'
    source, registry = tmp_path / 'spec.json', tmp_path / 'registry.json'
    harness.write_json(source, specification('cookie'))
    harness.write_json(registry, config)
    row = analyse(source, registry, 'lab-web')['candidates'][0]
    assert row['status'] == 'NEEDS_CONFIGURATION'
    assert 'RESOURCE_PROOF_SCHEMA_UNPROVEN' in row['reason_codes']


def test_contract_limitations_remain_explicit():
    with pytest.raises(ValidationError):
        ResourceRoutes(login_path='/gateway/authenticate', me_path='/gateway/session/profile',
                       detail_path='/projects/{project_id}/attachments/{resource_id}')
    adapter = registry_for('cookie', 18080)['targets']['lab-web']['adapter']
    adapter['proof_field'] = 'content.audit[0].receipt'
    with pytest.raises(ValidationError):
        ResourceAdapter.model_validate(adapter)
