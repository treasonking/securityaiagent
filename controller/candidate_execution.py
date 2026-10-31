"""Explicit operator preview/run; plans never supply tool arguments or authority."""
from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Literal

import httpx
from pydantic import Field, model_validator

from common.api_contract import FrozenModel
from controller.candidates import analyse, canonical, digest, read_local, unique, fail_constant
from controller.engine import EngineRequest, RunEngine, RunCancelled
from controller.providers import MockModelProvider
from controller.reporting import ReportWriter
from controller.tool_clients import FunctionWorkerClient, MCPWorkerClient
from worker.candidate_policy import CandidatePolicy, CONTRACT, Hash

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / 'data' / 'candidate_plans'


class CandidateError(ValueError):
    pass


class Plan(FrozenModel):
    schema_version: Literal['1.0'] = '1.0'
    plan_id: str = Field(pattern=r'^plan_[0-9a-f]{32}$')
    created_at: int = Field(gt=0)
    expires_at: int = Field(gt=0)
    candidate_id: Hash
    source_sha256: Hash
    registry_sha256: Hash
    worker_origin: str = Field(max_length=200)
    policy: CandidatePolicy
    provider: Literal['mock'] = 'mock'
    transport: Literal['function', 'mcp']
    accounts: list[Literal['user-a', 'user-b']] = ['user-a', 'user-b']
    expected_http_requests: Literal[9] = 9
    expected_tool_calls: Literal[10] = 10
    verification_status: Literal['NOT_EXECUTED'] = 'NOT_EXECUTED'
    plan_sha256: Hash

    @model_validator(mode='after')
    def invariants(self):
        if self.expires_at - self.created_at != 300 or self.accounts != ['user-a', 'user-b']:
            raise ValueError('invalid plan constraints')
        return self


def plan_hash(value):
    return digest(canonical({k: v for k, v in value.items() if k != 'plan_sha256'}))


def parse_plan(path):
    try:
        value = json.loads(read_local(path), object_pairs_hook=unique, parse_constant=fail_constant)
        stack = [(value, 0)]
        while stack:
            node, depth = stack.pop()
            if depth > 32:
                raise ValueError()
            if isinstance(node, (dict, list)):
                stack.extend((v, depth + 1) for v in (node.values() if isinstance(node, dict) else node))
        return Plan.model_validate(value)
    except Exception:
        raise CandidateError('PLAN_INVALID') from None


def select_candidate(source, registry, candidate_id):
    try:
        catalogue = analyse(source, registry, 'lab-web')
    except Exception:
        raise CandidateError('CANDIDATE_REANALYSIS_FAILED') from None
    matches = [c for c in catalogue['candidates'] if c['candidate_id'] == candidate_id]
    if len(matches) != 1:
        raise CandidateError('CANDIDATE_NOT_UNIQUE')
    if matches[0]['status'] != 'READY_FOR_REVIEW':
        raise CandidateError('CANDIDATE_NOT_READY')
    return catalogue


class PolicyClient:
    def __init__(self, base_url, token, *, transport=None):
        self.base_url, self.token, self.transport = base_url, token, transport

    async def read(self):
        try:
            async with httpx.AsyncClient(base_url=self.base_url, trust_env=False, follow_redirects=False,
                    timeout=10, transport=self.transport) as client:
                async with client.stream('GET', '/v1/operator/candidate-policy',
                        headers={'Authorization': 'Bearer ' + self.token}) as response:
                    if response.status_code in (404, 405):
                        raise CandidateError('WORKER_UPDATE_REQUIRED')
                    if response.status_code != 200:
                        raise CandidateError('WORKER_POLICY_UNAVAILABLE')
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > 32768:
                            raise CandidateError('WORKER_CONTRACT_INVALID')
            value = json.loads(body, object_pairs_hook=unique, parse_constant=fail_constant)
            if value.get('contract_version') != CONTRACT:
                raise CandidateError('WORKER_UPDATE_REQUIRED')
            return CandidatePolicy.model_validate(value)
        except CandidateError:
            raise
        except Exception:
            raise CandidateError('WORKER_CONTRACT_INVALID') from None


class PlanHistory:
    """Operator-owned single-host ledger. Exclusive create provides process-safe consumption."""
    def __init__(self, directory=HISTORY):
        self.directory = Path(directory)

    def issue(self, plan):
        self.directory.mkdir(parents=True, exist_ok=True)
        with (self.directory / (plan.plan_id + '.issued.json')).open('x', encoding='utf-8') as output:
            output.write(plan.model_dump_json(indent=2))

    def validate(self, plan):
        try:
            issued = parse_plan(self.directory / (plan.plan_id + '.issued.json'))
        except Exception:
            raise CandidateError('PLAN_NOT_ISSUED') from None
        if issued != plan:
            raise CandidateError('PLAN_CHANGED')

    def claim(self, plan, run_id):
        self.validate(plan)
        try:
            with (self.directory / (plan.plan_id + '.claimed.json')).open('x', encoding='utf-8') as output:
                output.write(json.dumps({'plan_sha256': plan.plan_sha256, 'run_id': run_id}))
        except FileExistsError:
            raise CandidateError('PLAN_ALREADY_CONSUMED') from None


def write_new_plan(plan, output):
    output = Path(output)
    summary = output.with_suffix('.md')
    if output.suffix != '.json' or output.exists() or summary.exists():
        raise CandidateError('NEW_OUTPUT_REQUIRED')
    with output.open('x', encoding='utf-8') as file:
        file.write(plan.model_dump_json(indent=2))
    with summary.open('x', encoding='utf-8') as file:
        file.write(plan_summary(plan))


def plan_summary(plan):
    p = plan.policy
    return (f'# Candidate execution preview\n\nNOT_EXECUTED; review is not a vulnerability finding.\n\n'
            f'- Plan: {plan.plan_id}\n- Digest: {plan.plan_sha256}\n'
            f'- Created / expires (Unix UTC seconds): {plan.created_at} / {plan.expires_at}\n'
            f'- Target: {p.target_id} ({p.origin}); adapter: {p.adapter_id}; auth: {p.auth_mode}\n'
            f'- Scenario: {p.scenario_id}; provider: mock; transport: {plan.transport}\n'
            f'- Accounts: user-a, user-b; login → own lists → private controls/cross-read/rechecks\n'
            f'- Routes: POST {p.routes.login_path}; GET {p.routes.list_path}; GET {p.routes.detail_path}\n'
            f'- Expected normal usage: HTTP 9, tools 10 (not guaranteed)\n'
            f'- Worker maximum limits: {p.scope_policy.effective_limits.model_dump_json()}\n'
            f'- Worker profile: {p.scope_policy.profile_id} r{p.scope_policy.revision}\n'
            f'- Expected snapshot: {p.scope_policy.snapshot_sha256}\n'
            '- Policy control: REST worker query, target HTTP 0; digest is not a signature.\n')


async def preview(source, registry, candidate_id, transport, policy_client, history, *, now=time.time):
    if transport not in ('function', 'mcp'):
        raise CandidateError('TRANSPORT_INVALID')
    catalogue = select_candidate(source, registry, candidate_id)
    policy = await policy_client.read()
    if catalogue['registry_sha256'] != policy.registry_sha256:
        raise CandidateError('WORKER_REGISTRY_MISMATCH')
    created = int(now())
    value = dict(plan_id='plan_' + uuid.uuid4().hex, created_at=created, expires_at=created + 300,
                 candidate_id=candidate_id, source_sha256=catalogue['source_sha256'],
                 registry_sha256=catalogue['registry_sha256'], worker_origin=policy_client.base_url,
                 policy=policy, transport=transport, plan_sha256='0' * 64)
    provisional = Plan(**value)
    value = provisional.model_dump(mode='json')
    value['plan_sha256'] = plan_hash(value)
    plan = Plan.model_validate(value)
    history.issue(plan)
    return plan


class BoundClient:
    """The selected template is never converted into tool arguments."""
    def __init__(self, client, snapshot):
        self.client, self.snapshot = client, snapshot

    def __getattr__(self, name):
        return getattr(self.client, name)

    async def start_session(self, run_id, target_id, account_ref, scenario_id='access-control'):
        payload = dict(run_id=run_id, target_id=target_id, account_ref=account_ref, scenario_id=scenario_id,
                       expected_snapshot_sha256=self.snapshot, candidate_contract=CONTRACT)
        try:
            if isinstance(self.client, FunctionWorkerClient):
                return await self.client._post('/v1/tools/start-session', payload)
            if isinstance(self.client, MCPWorkerClient):
                return await self.client._call('start_session', payload)
            raise CandidateError('BOUND_CLIENT_REQUIRED')
        except Exception:
            # Do not allow transport exception text/raw response into engine reports.
            raise CandidateError('CANDIDATE_SESSION_REJECTED') from None


async def execute_plan(source, registry, plan, confirmation, policy_client, history, client_factory, report_root,
                       *, now=time.time, cancel_event=None, emit=None, timeout=180):
    if confirmation != plan.plan_sha256 or plan_hash(plan.model_dump(mode='json')) != confirmation:
        raise CandidateError('PLAN_CONFIRMATION_MISMATCH')
    history.validate(plan)
    if not plan.created_at <= int(now()) < plan.expires_at:
        raise CandidateError('PLAN_EXPIRED')
    if plan.worker_origin != policy_client.base_url:
        raise CandidateError('WORKER_ORIGIN_CHANGED')
    catalogue = select_candidate(source, registry, plan.candidate_id)
    if catalogue['source_sha256'] != plan.source_sha256 or catalogue['registry_sha256'] != plan.registry_sha256:
        raise CandidateError('PLAN_INPUT_CHANGED')
    policy = await policy_client.read()
    if policy != plan.policy:
        raise CandidateError('WORKER_POLICY_CHANGED')
    if not plan.created_at <= int(now()) < plan.expires_at:
        raise CandidateError('PLAN_EXPIRED')
    run_id = 'run_' + uuid.uuid4().hex
    history.claim(plan, run_id)
    run_dir = Path(report_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    link = dict(schema_version='1.0', run_id=run_id, candidate_id=plan.candidate_id, plan_id=plan.plan_id,
                plan_sha256=plan.plan_sha256, source_sha256=plan.source_sha256,
                registry_sha256=plan.registry_sha256, expected_scope_policy=plan.policy.scope_policy.model_dump(mode='json'),
                actual_scope_policy=None, control_calls={'preview_policy': 1, 'run_policy': 1},
                status='INTERRUPTED', verdict='INCONCLUSIVE')
    link_path = run_dir / 'candidate_execution.json'
    link_path.write_text(json.dumps(link, indent=2), encoding='utf-8')
    client = None
    async def quiet(*_):
        pass
    try:
        client = BoundClient(client_factory(plan.transport), plan.policy.scope_policy.snapshot_sha256)
        async with asyncio.timeout(timeout):
            report = await RunEngine(report_writer=ReportWriter(Path(report_root))).execute(
                EngineRequest(run_id, 'access-control-http', 'lab-web'), provider=MockModelProvider(), client=client,
                cancel_event=cancel_event or asyncio.Event(), emit=emit or quiet)
        link.update(status=str(report.status), verdict=str(report.verdict),
                    actual_scope_policy=report.scope_policy.model_dump(mode='json') if report.scope_policy else None)
        return report
    except (RunCancelled, asyncio.CancelledError):
        link['status'] = 'CANCELLED'
        raise CandidateError('RUN_CANCELLED') from None
    except TimeoutError:
        link['status'] = 'TIMED_OUT'
        raise CandidateError('RUN_TIMED_OUT') from None
    except Exception:
        link['status'] = 'FAILED'
        raise CandidateError('RUN_FAILED') from None
    finally:
        if client and link['status'] != 'COMPLETED':
            try:
                await asyncio.wait_for(client.cancel_run(run_id), timeout=5)
            except Exception:
                pass
        link_path.write_text(json.dumps(link, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description='Operator candidate preview and explicit mock run')
    parser.add_argument('command', choices=['preview', 'run'])
    parser.add_argument('--input', required=True)
    parser.add_argument('--registry', required=True)
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--target', choices=['lab-web'], default='lab-web')
    parser.add_argument('--candidate-id')
    parser.add_argument('--transport', choices=['function', 'mcp'])
    parser.add_argument('--output', type=Path)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--confirm-plan-sha256')
    args = parser.parse_args()
    try:
        from common.service_config import read_config, validate_config
        settings = read_config('controller', args.env_file)
        validate_config('controller', settings)
        # Only explicit validated controller values are used; no ambient credentials/settings.
        base = settings.get('WORKER_URL', 'http://10.77.0.20:9000')
        policy_client = PolicyClient(base, settings['WORKER_TOKEN'])
        history = PlanHistory()
        if args.command == 'preview':
            if not args.candidate_id or not args.transport or args.output is None or args.plan or args.confirm_plan_sha256:
                raise CandidateError('PREVIEW_ARGUMENTS_REQUIRED')
            if args.output.exists() or args.output.with_suffix('.md').exists() or not args.output.parent.is_dir():
                raise CandidateError('NEW_OUTPUT_WITH_EXISTING_PARENT_REQUIRED')
            plan = asyncio.run(preview(args.input, args.registry, args.candidate_id, args.transport, policy_client, history))
            write_new_plan(plan, args.output)
            print(plan.model_dump_json(indent=2))
            print(plan_summary(plan))
        else:
            if args.plan is None or not args.confirm_plan_sha256 or args.transport or args.candidate_id or args.output:
                raise CandidateError('RUN_CONFIRMATION_REQUIRED')
            plan = parse_plan(args.plan)
            def factory(transport):
                return (FunctionWorkerClient(base_url=base, token=settings['WORKER_TOKEN']) if transport == 'function'
                        else MCPWorkerClient(server_url=settings.get('MCP_WORKER_URL', base + '/mcp'), token=settings['WORKER_TOKEN']))
            report = asyncio.run(execute_plan(args.input, args.registry, plan, args.confirm_plan_sha256, policy_client,
                history, factory, ROOT / 'reports' / 'runs', timeout=float(settings.get('CONTROLLER_RUN_TIMEOUT_SECONDS', '180'))))
            print(json.dumps({'run_id': report.run_id, 'status': report.status, 'verdict': report.verdict}))
            if report.verdict == 'INCONCLUSIVE' or report.status != 'COMPLETED':
                raise SystemExit(1)
    except Exception as exc:
        print(json.dumps({'ok': False, 'reason_code': str(exc) if isinstance(exc, CandidateError) else 'CANDIDATE_EXECUTION_INVALID'}))
        raise SystemExit(2) from None


if __name__ == '__main__':
    main()
