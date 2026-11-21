import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import ssl

import pytest
from cryptography.hazmat.primitives import serialization
from pydantic import ValidationError

from common.service_config import ServiceConfigError, read_config, validate_config
from controller.candidate_execution import plan_hash
from controller.operator_execution import parse_plan
from scripts import run_local_https_verification as harness
from validation.independent_api.api import AttachmentService, attachment_server
from validation.independent_api.configuration import registry_for
from validation.local_https import authority, certificates
from verifier.operator import replay
from worker.limits import WorkerLimits
from worker.operator_app import StepRequest
from worker.operator_service import OperatorService
from worker.policy import PolicyViolation, TargetPolicy
from worker.registry import load_scope_registry
from worker.scope import ScopeViolation
from worker.tls import bind_registry_tls, load_trust


def configured(tmp_path, material, port=18443):
    api = AttachmentService('cookie', True)
    env = dict(LAB_USER_A_PASSWORD=api.members[0].password, LAB_USER_B_PASSWORD=api.members[1].password,
               OPERATOR_PROOF_A=api.attachments[0].receipt, OPERATOR_PROOF_B=api.attachments[1].receipt)
    config = registry_for('cookie', port)
    config['targets']['lab-web']['origin'] = f'https://127.0.0.1:{port}'
    path = tmp_path/'registry.json'
    harness.write_json(path, config)
    registry = load_scope_registry(path).bind_proofs(env)
    return api, env, path, registry


@pytest.mark.parametrize('auth,vulnerable,transport,case', harness.CASES)
def test_actual_tls_matrix(tmp_path, auth, vulnerable, transport, case):
    result = harness.run_case(tmp_path, auth, vulnerable, transport, case)
    assert result['passed'], result
    assert result['temporary_key_directory_removed']
    assert result['preview_target_http'] == 0 and not any(result['preview_network_delta'].values())
    assert result['planned_scope']['tls']['verification'] == 'dedicated-ca-ip-san-v1'
    assert result['replay']['verdict_matches']
    if case in harness.ERRORS:
        assert result['network']['tcp_accepted'] == 1 and result['target_http_received'] == 0
        assert result['reason_code'] == harness.ERRORS[case] and result['verdict'] == 'INCONCLUSIVE'


def test_startup_requires_valid_ca_and_keeps_paths_private(tmp_path):
    with certificates() as c:
        api, env, path, registry = configured(tmp_path, c)
        with pytest.raises(ScopeViolation, match='Worker-owned'):
            OperatorService(registry=registry, accounts=registry.credentials(env))
        for contents in (b'', b'not a certificate', b'-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----'):
            ca = tmp_path/'sensitive-local-path.pem'
            ca.write_bytes(contents)
            with pytest.raises(ScopeViolation) as error:
                bind_registry_tls(registry, ca)
            assert error.value.code == 'TLS_CA_INVALID' and str(ca) not in str(error.value)
        with pytest.raises(ScopeViolation) as error:
            load_trust(c['private_directory']/'server.pem')
        assert error.value.code == 'TLS_CA_INVALID'  # A leaf is not a CA bundle.


def test_expired_ca_is_rejected_at_startup(tmp_path):
    _, cert = authority('Expired synthetic CA', datetime.now(timezone.utc)-timedelta(days=5))
    path = tmp_path/'expired.pem'
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    with pytest.raises(ScopeViolation) as error:
        load_trust(path)
    assert error.value.code == 'TLS_CA_INVALID'


def test_identity_depends_on_contents_not_paths_and_context_is_frozen(tmp_path):
    with certificates() as c:
        _, env, _, registry = configured(tmp_path, c)
        second = tmp_path/'different-name.pem'
        second.write_bytes(c['ca_file'].read_bytes())
        one, two = bind_registry_tls(registry, c['ca_file']), bind_registry_tls(registry, second)
        assert one.snapshot('lab-web', 'operator-resource-http', WorkerLimits()).policy == two.snapshot('lab-web', 'operator-resource-http', WorkerLimits()).policy
        ctx = one.tls_trust.checked_context()
        original_der = ctx.get_ca_certs(binary_form=True)
        c['ca_file'].write_bytes(c['alternate_bundle'])
        assert ctx.get_ca_certs(binary_form=True) == original_der  # No hot reload.
        with pytest.raises(ScopeViolation) as error:
            one.snapshot('lab-web', 'operator-resource-http', WorkerLimits())
        assert error.value.code == 'TLS_TRUST_CHANGED_RESTART_REQUIRED'
        restarted = bind_registry_tls(registry, c['ca_file'])
        assert restarted.snapshot('lab-web', 'operator-resource-http', WorkerLimits()).snapshot_sha256 != two.snapshot('lab-web', 'operator-resource-http', WorkerLimits()).snapshot_sha256


def test_ca_change_after_first_request_stops_before_next_http(tmp_path):
    with certificates() as c:
        api = AttachmentService('cookie', True)
        counts = dict(tcp_accepted=0, tls_handshake_attempts=0, tls_handshake_failed=0, tls_handshake_completed=0)
        with attachment_server(api, ssl_context=c['server_context'], connection_counts=counts) as port:
            _, _, path, _ = configured(tmp_path, c, port)
            env = dict(LAB_USER_A_PASSWORD=api.members[0].password, LAB_USER_B_PASSWORD=api.members[1].password,
                       OPERATOR_PROOF_A=api.attachments[0].receipt, OPERATOR_PROOF_B=api.attachments[1].receipt)
            registry = bind_registry_tls(load_scope_registry(path).bind_proofs(env), c['ca_file'])
            service = OperatorService(registry=registry, accounts=registry.credentials(env))
            policy = service.policy()
            async def flow():
                first = await service.operator_step('tls-drift', 'lab-web', **policy.sequence()[0].model_dump(), expected_snapshot_sha256=policy.scope_policy.snapshot_sha256)
                assert first.ok and api.received == 1
                c['ca_file'].write_bytes(c['alternate_bundle'])
                second = await service.operator_step('tls-drift', 'lab-web', **policy.sequence()[1].model_dump(), expected_snapshot_sha256=policy.scope_policy.snapshot_sha256)
                assert not second.ok and second.error_code == 'TLS_TRUST_CHANGED_RESTART_REQUIRED'
            asyncio.run(flow())
            assert api.received == counts['tcp_accepted'] == 1


def test_ca_setting_is_worker_only_and_operator_startup_binds_it(tmp_path, monkeypatch):
    from worker.app import create_app_from_env
    with certificates() as c:
        _, env, path, registry = configured(tmp_path, c)
        values = dict(env, TARGET_CA_BUNDLE=str(c['ca_file']), TARGET_REGISTRY_PATH=str(path), WORKER_TOKEN='test-worker-token-123456789')
        checked = validate_config('worker', values)
        assert checked['scope_policies'][0]['tls']['ca_bundle_sha256'] == hashlib.sha256(c['ca_file'].read_bytes()).hexdigest()
        assert str(c['private_directory']) not in json.dumps(checked)
        for role in ('controller', 'target', 'operator-target'):
            with pytest.raises(ServiceConfigError):
                validate_config(role, values)
        for name in ('TARGET_BASE_URL',):
            monkeypatch.delenv(name, raising=False)
        for name, value in values.items():
            monkeypatch.setenv(name, value)
        app = create_app_from_env()
        assert app.state.tool_service.policy().scope_policy.tls.ca_bundle_sha256 == checked['scope_policies'][0]['tls']['ca_bundle_sha256']


def test_model_tool_cannot_choose_tls_or_origin():
    payload = dict(run_id='test', target_id='lab-web', account_ref='user-a', operation='login', resource_id=None,
                   expected_snapshot_sha256='0'*64)
    for key, value in [('verify', False), ('ca_bundle', '/tmp/unapproved'), ('url', 'https://127.0.0.2:443')]:
        with pytest.raises(ValidationError):
            StepRequest.model_validate(dict(payload, **{key: value}))


def test_mutated_ssl_context_is_not_used(tmp_path):
    with certificates() as c:
        trust = load_trust(c['ca_file'])
        ctx = trust.checked_context()
        assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname and not ctx.hostname_checks_common_name
        ctx.load_verify_locations(cadata=c['alternate_bundle'].decode())
        with pytest.raises(ScopeViolation) as error:
            trust.checked_context()
        assert error.value.code == 'TLS_TRUST_INVALID'


def test_http_fingerprints_and_saved_artifacts_stay_compatible():
    root = Path('reports/independent_api_validation_20261113')
    matrix = json.loads((root/'matrix.json').read_text())
    for row in matrix['cases']:
        folder = root/row['path']
        plan = parse_plan(folder/'plan.json')
        assert plan_hash(plan.model_dump(mode='json')) == plan.plan_sha256
        assert 'tls' not in plan.policy.scope_policy.model_dump(mode='json')
        if row['run_id']:
            assert replay(folder/'runs'/row['run_id'])['verdict_matches']
    registry = load_scope_registry()
    assert registry.snapshot('lab-web', 'access-control-http', WorkerLimits()).snapshot_sha256 == 'd8136fafff1bda07b32b13feab426c76ccf570e40ac52c9b8e494f48ef2a9d1a'


def test_generic_https_policy_and_canonical_ip_origins(tmp_path):
    with certificates() as c:
        config = json.loads(Path('config/targets.json').read_text())
        config['targets']['lab-web']['origin'] = 'https://127.0.0.1:443'
        path = tmp_path/'registry.json'
        harness.write_json(path, config)
        registry = bind_registry_tls(load_scope_registry(path), c['ca_file'])
        snapshot = registry.snapshot('lab-web', 'access-control-http', WorkerLimits())
        assert snapshot.record().tls is not None
        assert snapshot.snapshot_sha256 != load_scope_registry().snapshot('lab-web', 'access-control-http', WorkerLimits()).snapshot_sha256
    assert TargetPolicy('lab-web', 'https', '::1', 443).base_url == 'https://[::1]:443'
    with pytest.raises(PolicyViolation):
        TargetPolicy('lab-web', 'https', 'example.com', 443)


def test_publication_rejects_private_key_even_json_escaped(tmp_path):
    with certificates() as c:
        harness.write_json(tmp_path/'leaked.json', {'key': c['private_values'][0]})
        with pytest.raises(AssertionError, match='SECRET_REDACTION_FAILED'):
            harness.publication_check(tmp_path, c['private_values'])
