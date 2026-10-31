"""Candidate preview/run TCP matrix on isolated synthetic fixtures only."""
import asyncio
import json
import os
import secrets
import tempfile
import uuid
from pathlib import Path

from common.schemas import Evidence
from controller.candidate_execution import PolicyClient, PlanHistory, preview, execute_plan, write_new_plan
from controller.candidates import analyse
from controller.tool_clients import FunctionWorkerClient, MCPWorkerClient
from scripts.run_http_verification import local_server
from target.store import TargetStore
from verifier.http import verify_http_access_control
from worker.app import build_worker_app
from worker.limits import WorkerLimits
from worker.registry import load_scope_registry
from worker.service import ToolService

ROOT = Path(__file__).resolve().parents[1]


def run_matrix(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    temp_root = ROOT / 'verification_tmp'
    temp_root.mkdir(exist_ok=True)
    rows = []
    with tempfile.TemporaryDirectory(prefix='candidate-matrix-', dir=temp_root) as directory:
        temp = Path(directory)
        previous = os.environ.get('TARGET_DATABASE_PATH')
        os.environ['TARGET_DATABASE_PATH'] = str(temp / 'unused.sqlite3')
        try:
            from target.app import create_app
        finally:
            if previous is None:
                os.environ.pop('TARGET_DATABASE_PATH', None)
            else:
                os.environ['TARGET_DATABASE_PATH'] = previous
        for style in ('documents', 'records'):
            for mode in ('vulnerable', 'fixed'):
                target = create_app(TargetStore(temp / f'{style}-{mode}.sqlite3', mode=mode), api_style=style)
                observed = []
                @target.middleware('http')
                async def count(request, call_next):
                    observed.append(request.headers.get('X-SecurityLab-Run'))
                    return await call_next(request)
                with local_server(target) as target_port:
                    payload = json.loads((ROOT / 'config' / ('targets.json' if style == 'documents' else 'targets.records.json')).read_text())
                    # Only the test harness creates this temporary operator registry.
                    payload['targets']['lab-web']['origin'] = f'http://127.0.0.1:{target_port}'
                    registry_path = temp / 'registry.json'
                    registry_path.write_text(json.dumps(payload))
                    registry = load_scope_registry(registry_path)
                    def no_logs(_):
                        raise AssertionError('HTTP verifier must not read logs')
                    service = ToolService(registry=registry, limits=WorkerLimits(), accounts=registry.credentials({
                        'LAB_USER_A_PASSWORD': 'local-a-password', 'LAB_USER_B_PASSWORD': 'local-b-password',
                        'LAB_ADMIN_PASSWORD': 'local-admin-password'}), observation_reader=no_logs)
                    token = secrets.token_urlsafe(32)
                    with local_server(build_worker_app(service, worker_token=token, allowed_clients={'127.0.0.1'})) as worker_port:
                        base = f'http://127.0.0.1:{worker_port}'
                        source = ROOT / 'examples' / 'openapi' / (style + '.json')
                        candidate = analyse(source, registry_path, 'lab-web')['candidates'][0]['candidate_id']
                        for transport in ('function', 'mcp'):
                            history = PlanHistory(temp / 'history')
                            policy = PolicyClient(base, token)
                            async def run():
                                before = len(observed)
                                plan = await preview(source, registry_path, candidate, transport, policy, history)
                                assert len(observed) == before
                                write_new_plan(plan, output / (plan.plan_id + '.json'))
                                def factory(selected):
                                    return FunctionWorkerClient(base_url=base, token=token) if selected == 'function' else MCPWorkerClient(server_url=base+'/mcp', token=token)
                                report = await execute_plan(source, registry_path, plan, plan.plan_sha256,
                                    policy, history, factory, output)
                                return plan, report, len(observed) - before
                            plan, report, count = asyncio.run(run())
                            evidence = [Evidence.model_validate(x) for x in json.loads((output / report.run_id / 'evidence.json').read_text())]
                            expected = 'VULNERABLE' if mode == 'vulnerable' else 'BLOCKED_BY_ACCESS_CONTROL'
                            assert report.status == 'COMPLETED' and report.verdict == expected
                            assert verify_http_access_control(evidence, run_id=report.run_id).verdict == report.verdict
                            assert len(evidence) == 7 and count == 9
                            assert report.limits_used == {'http_requests': 9, 'tool_calls': 10}
                            assert report.scope_policy.snapshot_sha256 == plan.policy.scope_policy.snapshot_sha256
                            rows.append(dict(api=style, fixture_mode=mode, transport=transport, run_id=report.run_id,
                                plan_id=plan.plan_id, plan_sha256=plan.plan_sha256, candidate_id=candidate,
                                preview_target_requests=0, run_target_requests=count, verdict=report.verdict,
                                evidence_count=len(evidence), verdict_matches=True, limits_used=report.limits_used))
    path = output / ('matrix-' + uuid.uuid4().hex[:12] + '.json')
    path.write_text(json.dumps(rows, indent=2), encoding='utf-8')
    print(json.dumps({'matrix': str(path), 'runs': len(rows)}))
    return rows


if __name__ == '__main__':
    run_matrix(ROOT / 'reports' / 'candidate_execution')
