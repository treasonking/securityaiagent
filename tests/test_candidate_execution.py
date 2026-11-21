import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from dataclasses import replace

import httpx
import pytest

from controller import candidate_execution as ce
from controller.candidates import analyse
from controller.tool_clients import FunctionWorkerClient, MCPWorkerClient
from scripts.run_http_verification import local_server
from worker.app import build_worker_app
from worker.candidate_policy import CONTRACT, policy_for
from worker.limits import WorkerLimits
from worker.registry import load_scope_registry
from worker.service import ToolService


@pytest.fixture
def setup(tmp_path):
    registry_path = tmp_path / 'registry.json'
    registry_path.write_bytes(Path('config/targets.records.json').read_bytes())
    source = tmp_path / 'source.json'
    source.write_bytes(Path('examples/openapi/records.json').read_bytes())
    registry = load_scope_registry(registry_path)
    sent = []
    def target(request):
        sent.append(request)
        return httpx.Response(401, json={'error': 'login failed'})
    service = ToolService(registry=registry, accounts=registry.credentials({
        'LAB_USER_A_PASSWORD': 'secret-a', 'LAB_USER_B_PASSWORD': 'secret-b', 'LAB_ADMIN_PASSWORD': 'secret-admin'}),
        transport=httpx.MockTransport(target))
    token = 'private-worker-token'
    app = build_worker_app(service, worker_token=token, allowed_clients={'127.0.0.1'})
    wire = httpx.ASGITransport(app=app)
    policy = ce.PolicyClient('http://127.0.0.1:9000', token, transport=wire)
    history = ce.PlanHistory(tmp_path / 'history')
    candidate = analyse(source, registry_path, 'lab-web')['candidates'][0]['candidate_id']
    def factory(transport):
        assert transport == 'function'
        return FunctionWorkerClient(base_url=policy.base_url, token=token, transport=wire)
    return dict(source=source, registry=registry_path, service=service, sent=sent, app=app,
                wire=wire, policy=policy, history=history, candidate=candidate, factory=factory, root=tmp_path / 'reports')


async def make(s, transport='function'):
    return await ce.preview(s['source'], s['registry'], s['candidate'], transport, s['policy'], s['history'], now=lambda: 1000)


async def execute(s, plan, **kwargs):
    return await ce.execute_plan(s['source'], s['registry'], plan, kwargs.pop('confirmation', plan.plan_sha256),
        s['policy'], s['history'], s['factory'], s['root'], now=kwargs.pop('now', lambda: 1001), **kwargs)


def test_preview_is_control_only(setup, monkeypatch):
    def forbidden(*a, **k):
        pytest.fail('preview invoked engine/model')
    monkeypatch.setattr(ce.RunEngine, 'execute', forbidden)
    monkeypatch.setattr(ce.MockModelProvider, 'propose_candidates', forbidden)
    plan = asyncio.run(make(setup))
    assert setup['sent'] == [] and setup['service']._runs == {}
    assert plan.expires_at - plan.created_at == 300
    assert plan.registry_sha256 == setup['service'].registry.config_digest('lab-web')
    assert 'secret' not in plan.model_dump_json() + ce.plan_summary(plan)
    assert 'private-worker-token' not in plan.model_dump_json()


@pytest.mark.parametrize('change', ['transport', 'hash', 'source', 'origin', 'policy', 'candidate'])
def test_plan_rehash_does_not_authorize_change(setup, change):
    async def check():
        plan = await make(setup)
        data = plan.model_dump(mode='json')
        if change == 'transport': data['transport'] = 'mcp'
        if change == 'hash': data['registry_sha256'] = 'a' * 64
        if change == 'source': data['source_sha256'] = 'a' * 64
        if change == 'origin': data['policy']['origin'] = 'http://10.78.0.31:8080'
        if change == 'policy': data['policy']['scope_policy']['effective_limits']['max_requests'] = 1
        if change == 'candidate': data['candidate_id'] = 'a' * 64
        data['plan_sha256'] = ce.plan_hash(data)
        changed = ce.Plan.model_validate(data)
        with pytest.raises(ce.CandidateError, match='PLAN_CHANGED'):
            await execute(setup, changed)
        assert not setup['sent']
    asyncio.run(check())


@pytest.mark.parametrize('change', ['source', 'registry', 'not-ready'])
def test_reanalysis_before_execution(setup, change):
    async def check():
        plan = await make(setup)
        path = setup['registry'] if change == 'registry' else setup['source']
        doc = json.loads(path.read_text())
        if change == 'registry': doc['targets']['lab-web']['profile']['revision'] += 1
        elif change == 'not-ready': doc['paths']['/api/session']['post']['security'] = [{'LabSession': []}]
        else: doc['description'] = 'ignored but bytes changed'
        path.write_text(json.dumps(doc))
        with pytest.raises(ce.CandidateError): await execute(setup, plan)
        assert not setup['sent']
    asyncio.run(check())


@pytest.mark.parametrize('candidate', ['absent', 'duplicate', 'unsupported'])
def test_candidate_selection(setup, candidate):
    if candidate == 'absent': setup['candidate'] = 'a' * 64
    else:
        doc = json.loads(setup['source'].read_text())
        if candidate == 'duplicate':
            doc['paths']['/api/records/{recordId}'] = doc['paths']['/api/records/{id}']
        else:
            doc['servers'] = [{'url': 'http://outside.invalid'}]
        setup['source'].write_text(json.dumps(doc))
    with pytest.raises(ce.CandidateError): asyncio.run(make(setup))
    assert not setup['sent']


@pytest.mark.parametrize('time_value,confirmation', [(1300, True), (999, True), (1001, False)])
def test_expiration_confirmation(setup, time_value, confirmation):
    async def check():
        plan = await make(setup)
        with pytest.raises(ce.CandidateError):
            await execute(setup, plan, confirmation=plan.plan_sha256 if confirmation else None, now=lambda: time_value)
        assert not setup['sent']
    asyncio.run(check())


def test_atomic_consumption_across_instances(setup):
    plan = asyncio.run(make(setup))
    def claim(i):
        try:
            ce.PlanHistory(setup['history'].directory).claim(plan, f'run_{i}')
            return True
        except ce.CandidateError:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(claim, range(16))) == 1


def test_failed_run_consumes_plan(setup):
    async def check():
        plan = await make(setup)
        report = await execute(setup, plan)
        assert report.verdict == 'INCONCLUSIVE' and len(setup['sent']) == 1
        with pytest.raises(ce.CandidateError, match='PLAN_ALREADY_CONSUMED'):
            await execute(setup, plan)
        assert len(setup['sent']) == 1
        saved = (setup['root'] / report.run_id / 'candidate_execution.json').read_text()
        assert plan.candidate_id in saved and 'secret-a' not in saved
    asyncio.run(check())


@pytest.mark.parametrize('change', ['limit', 'profile', 'adapter'])
def test_worker_policy_change_before_run(setup, change):
    async def check():
        plan = await make(setup)
        if change == 'limit': setup['service'].limits = replace(setup['service'].limits, max_requests=2)
        else:
            doc = json.loads(setup['registry'].read_text())
            if change == 'profile': doc['targets']['lab-web']['profile']['revision'] += 1
            else: doc['targets']['lab-web']['adapter']['content_field'] = 'record.content.other'
            worker_file = setup['registry'].with_name('worker-new.json')
            worker_file.write_text(json.dumps(doc))
            setup['service'].registry = load_scope_registry(worker_file)
        with pytest.raises(ce.CandidateError, match='WORKER_POLICY_CHANGED'):
            await execute(setup, plan)
        assert not setup['sent'] and not setup['service']._runs
    asyncio.run(check())


@pytest.mark.parametrize('transport', ['function', 'mcp'])
@pytest.mark.parametrize('change', ['limit', 'profile', 'adapter'])
def test_race_after_policy_check_blocked_before_login(setup, transport, change):
    service = setup['service']
    expected = policy_for(service).scope_policy.snapshot_sha256
    # Represents a restarted worker with a different global limit after the control query.
    registry = service.registry
    if change != 'limit':
        doc = json.loads(setup['registry'].read_text())
        if change == 'profile': doc['targets']['lab-web']['profile']['revision'] += 1
        else: doc['targets']['lab-web']['adapter']['content_field'] = 'record.content.other'
        worker_file = setup['registry'].with_name('worker-race.json')
        worker_file.write_text(json.dumps(doc))
        registry = load_scope_registry(worker_file)
    changed = ToolService(registry=registry, accounts=service.accounts,
        limits=replace(service.limits, max_requests=2) if change == 'limit' else service.limits, transport=service.transport)
    with local_server(build_worker_app(changed, worker_token='test-secret', allowed_clients={'127.0.0.1'})) as port:
        async def check():
            base = f'http://127.0.0.1:{port}'
            raw = FunctionWorkerClient(base_url=base, token='test-secret') if transport == 'function' else MCPWorkerClient(server_url=base+'/mcp', token='test-secret')
            bound = ce.BoundClient(raw, expected)
            async with bound.session():
                assert set(await bound.list_tools()) == {'start_session', 'list_own_documents', 'fetch_document', 'finish_run'}
                result = await bound.start_session('race', 'lab-web', 'user-a', 'access-control-http')
            assert not result.ok and result.error_code == 'CANDIDATE_POLICY_CHANGED'
        asyncio.run(check())
    assert not setup['sent'] and not changed._runs


@pytest.mark.parametrize('binding', [{'candidate_contract': CONTRACT}, {'expected_snapshot_sha256': 'a'*64},
                                    {'candidate_contract': 'old', 'expected_snapshot_sha256': 'a'*64}])
def test_binding_missing_fields(setup, binding):
    result = asyncio.run(setup['service'].start_session('missing', 'lab-web', 'user-a', 'access-control-http', **binding))
    assert not result.ok and result.error_code == 'CANDIDATE_BINDING_REQUIRED'
    assert not setup['sent'] and not setup['service']._runs


@pytest.mark.parametrize('case,expected', [('no-token', 401), ('wrong-client', 403)])
def test_policy_query_authorization(setup, case, expected):
    async def check():
        wire = setup['wire'] if case == 'no-token' else httpx.ASGITransport(app=setup['app'], client=('10.9.9.9', 1))
        async with httpx.AsyncClient(transport=wire, base_url='http://testserver') as client:
            response = await client.get('/v1/operator/candidate-policy', headers={} if case == 'no-token' else {'Authorization': 'Bearer private-worker-token'})
        assert response.status_code == expected
    asyncio.run(check())
    assert not setup['sent']


@pytest.mark.parametrize('status,body', [(404, {}), (200, {'contract_version': 'old'}), (200, {'contract_version': CONTRACT})])
def test_old_or_invalid_worker(status, body):
    client = ce.PolicyClient('http://127.0.0.1:9000', 'secret', transport=httpx.MockTransport(lambda req: httpx.Response(status, json=body)))
    with pytest.raises(ce.CandidateError): asyncio.run(client.read())


@pytest.mark.parametrize('case', ['extra', 'provider', 'duplicate', 'nan', 'deep', 'large'])
def test_plan_input_boundary(setup, tmp_path, case):
    plan = asyncio.run(make(setup))
    data = plan.model_dump(mode='json')
    if case == 'extra': data['command'] = 'secret'
    if case == 'provider': data['provider'] = 'openai'
    raw = json.dumps(data)
    if case == 'duplicate': raw = raw[:-1] + ',"provider":"mock"}'
    if case == 'nan': raw = '{"created_at":NaN}'
    if case == 'deep': raw = '[' * 40 + '0' + ']' * 40
    if case == 'large': raw = ' ' * (2 * 1024 * 1024 + 1)
    path = tmp_path / 'bad.json'
    path.write_text(raw)
    with pytest.raises(ce.CandidateError, match='PLAN_INVALID'): ce.parse_plan(path)


@pytest.mark.parametrize('case', ['cancel', 'timeout'])
def test_interruption_remains_consumed(setup, monkeypatch, case):
    async def interrupted(*args, **kwargs):
        if case == 'cancel': raise ce.RunCancelled()
        await asyncio.sleep(10)
    monkeypatch.setattr(ce.RunEngine, 'execute', interrupted)
    async def check():
        plan = await make(setup)
        with pytest.raises(ce.CandidateError): await execute(setup, plan, timeout=0.01)
        with pytest.raises(ce.CandidateError, match='PLAN_ALREADY_CONSUMED'): await execute(setup, plan)
    asyncio.run(check())
    assert not setup['sent']
    link = json.loads(next(setup['root'].glob('*/candidate_execution.json')).read_text())
    assert link['status'] == ('CANCELLED' if case == 'cancel' else 'TIMED_OUT')
    assert link['verdict'] == 'INCONCLUSIVE'


def test_concurrent_run_only_one_engine(setup):
    async def check():
        plan = await make(setup)
        outcomes = await asyncio.gather(execute(setup, plan), execute(setup, plan), return_exceptions=True)
        assert sum(isinstance(x, ce.CandidateError) and str(x) == 'PLAN_ALREADY_CONSUMED' for x in outcomes) == 1
        assert len(list(setup['root'].glob('*/candidate_execution.json'))) == 1
        assert len(setup['sent']) == 1
    asyncio.run(check())


def test_bound_run_cannot_drop_binding(setup):
    async def check():
        def authenticated(request):
            setup['sent'].append(request)
            return httpx.Response(200, json={'session': {'access_token': 'private-token'}})
        service = setup['service']
        service.transport = httpx.MockTransport(authenticated)
        snapshot = policy_for(service).scope_policy.snapshot_sha256
        first = await service.start_session('bound', 'lab-web', 'user-a', 'access-control-http',
            expected_snapshot_sha256=snapshot, candidate_contract=CONTRACT)
        assert first.ok
        second = await service.start_session('bound', 'lab-web', 'user-b', 'access-control-http')
        assert not second.ok and second.error_code == 'CANDIDATE_BINDING_REQUIRED'
        assert len(setup['sent']) == 1
    asyncio.run(check())


def test_preview_rejects_worker_registry_mismatch(setup):
    doc = json.loads(setup['registry'].read_text())
    doc['targets']['lab-web']['profile']['revision'] += 1
    setup['registry'].write_text(json.dumps(doc))
    with pytest.raises(ce.CandidateError, match='WORKER_REGISTRY_MISMATCH'):
        asyncio.run(make(setup))
    assert not setup['sent']


def test_cli_preview_then_explicit_run(setup, tmp_path, monkeypatch, capsys):
    from common.service_config import read_config, ROOT, SECRETS
    values = read_config('controller', ROOT / '.env.controller.example')
    for key in values.keys() & SECRETS:
        if key != 'OPENAI_API_KEY': values[key] = 'private-' + key + '-for-test-only'
    values['WORKER_TOKEN'] = 'private-worker-token'
    values['WORKER_URL'] = setup['policy'].base_url
    values['MCP_WORKER_URL'] = setup['policy'].base_url + '/mcp'
    envfile = tmp_path / 'controller.env'
    envfile.write_text('\n'.join(k+'='+v for k, v in values.items()))
    monkeypatch.setenv('WORKER_URL', 'http://wrong.invalid')
    monkeypatch.setenv('MODEL_PROVIDER', 'openai')
    monkeypatch.setenv('OPENAI_API_KEY', 'ambient-secret')
    monkeypatch.setattr(ce, 'PlanHistory', lambda: setup['history'])
    monkeypatch.setattr(ce, 'ROOT', tmp_path)
    policy_init = ce.PolicyClient.__init__
    function_init = FunctionWorkerClient.__init__
    def policy_init_asgi(self, base_url, token, **kwargs):
        policy_init(self, base_url, token, transport=setup['wire'])
    def function_init_asgi(self, *, base_url, token, **kwargs):
        function_init(self, base_url=base_url, token=token, transport=setup['wire'])
    monkeypatch.setattr(ce.PolicyClient, '__init__', policy_init_asgi)
    monkeypatch.setattr(FunctionWorkerClient, '__init__', function_init_asgi)
    common = ['--input', str(setup['source']), '--registry', str(setup['registry']), '--env-file', str(envfile)]
    output = tmp_path / 'cli-plan.json'
    monkeypatch.setattr('sys.argv', ['candidate_execution', 'preview', *common, '--candidate-id', setup['candidate'], '--transport', 'function', '--output', str(output)])
    ce.main()
    assert not setup['sent']
    plan = ce.parse_plan(output)
    assert plan.provider == 'mock' and plan.worker_origin == setup['policy'].base_url
    monkeypatch.setattr('sys.argv', ['candidate_execution', 'run', *common, '--plan', str(output)])
    with pytest.raises(SystemExit) as missing: ce.main()
    assert missing.value.code == 2 and not setup['sent']
    monkeypatch.setattr('sys.argv', ['candidate_execution', 'run', *common, '--plan', str(output), '--confirm-plan-sha256', plan.plan_sha256])
    with pytest.raises(SystemExit) as completed: ce.main()
    assert completed.value.code == 1  # fixture rejects login: valid run, inconclusive result
    assert len(setup['sent']) == 1
    output_text = capsys.readouterr().out
    assert 'private-worker-token' not in output_text and 'ambient-secret' not in output_text


@pytest.mark.parametrize('transport', ['function', 'mcp'])
def test_candidate_run_respects_low_worker_limit(setup, transport):
    service = setup['service']
    service.limits = replace(service.limits, max_requests=2)
    def authenticated(request):
        setup['sent'].append(request)
        return httpx.Response(200, json={'session': {'access_token': 'private-token'}})
    service.transport = httpx.MockTransport(authenticated)
    with local_server(setup['app']) as port:
        base = f'http://127.0.0.1:{port}'
        setup['policy'] = ce.PolicyClient(base, 'private-worker-token')
        setup['factory'] = lambda selected: (FunctionWorkerClient(base_url=base, token='private-worker-token')
            if selected == 'function' else MCPWorkerClient(server_url=base+'/mcp', token='private-worker-token'))
        async def check():
            plan = await make(setup, transport)
            assert plan.policy.scope_policy.effective_limits.max_requests == 2
            report = await execute(setup, plan)
            assert report.verdict == 'INCONCLUSIVE'
            assert report.limits_used == {'http_requests': 2, 'tool_calls': 3}
            assert any('SCOPE_LIMIT_EXCEEDED' in x for x in report.warnings)
        asyncio.run(check())
    assert len(setup['sent']) == 2


def test_full_run_policy_race_has_no_applied_policy(setup):
    original_factory = setup['factory']
    def restart_after_control(transport):
        setup['service'].limits = replace(setup['service'].limits, max_requests=2)
        return original_factory(transport)
    setup['factory'] = restart_after_control
    async def check():
        plan = await make(setup)
        report = await execute(setup, plan)
        assert report.verdict == 'INCONCLUSIVE' and report.scope_policy is None
        assert report.limits_used == {'http_requests': 0, 'tool_calls': 0}
        assert not setup['sent'] and not setup['service']._runs
        link = json.loads((setup['root'] / report.run_id / 'candidate_execution.json').read_text())
        assert link['actual_scope_policy'] is None
        assert link['expected_scope_policy'] == plan.policy.scope_policy.model_dump(mode='json')
    asyncio.run(check())
