"""Repeatable, internal white-box applicability matrix over real loopback TCP."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile
import time

from controller.candidate_execution import CandidateError
from controller.candidates import analyse
from controller.operator_client import ResourceClient, ResourcePolicyClient
from controller.operator_execution import ResourceHistory, execute_plan, preview, write_plan
from validation.independent_api.api import AttachmentService, attachment_server
from validation.independent_api.configuration import registry_for, specification
from validation.independent_api.transport import worker_server
from verifier.operator import replay
from worker.app import build_worker_app
from worker.limits import WorkerLimits
from worker.operator_service import OperatorService
from worker.registry import load_scope_registry


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def publication_check(folder, secret_values):
    """Fail before copying staging artifacts into the public output directory."""
    files = [p for p in folder.rglob('*') if p.is_file()]
    for path in files:
        if path.suffix not in ('.json', '.md'):
            raise AssertionError('UNEXPECTED_PUBLIC_ARTIFACT')
        content = path.read_bytes()
        if any(value.encode() in content for value in secret_values):
            raise AssertionError('SECRET_REDACTION_FAILED')
    return {'files_checked': len(files), 'secret_values_checked': len(set(secret_values)), 'matches': 0}


class ObservedWorker:
    """Transport counters outside the verifier; no headers, bodies or logs."""
    def __init__(self, app):
        self.app = app
        self.counts = {'policy': 0, 'function': 0, 'mcp': 0, 'cancel': 0}

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http':
            path = scope['path']
            key = ('policy' if path == '/v1/operator/resource-policy' else
                   'function' if path in ('/v1/operator/resource-step', '/v1/operator/resource-finish') else
                   'mcp' if path.startswith('/mcp') else 'cancel' if path == '/v1/runs/cancel' else None)
            if key:
                self.counts[key] += 1
        await self.app(scope, receive, send)


def new_worker(registry, environment, token):
    registered = load_scope_registry(registry).bind_proofs(environment)
    service = OperatorService(registry=registered, accounts=registered.credentials(environment),
                              limits=WorkerLimits(requests_per_second=1000.0))
    app = ObservedWorker(build_worker_app(service, worker_token=token, allowed_clients={'127.0.0.1'}))
    return service, app


async def prepare(folder, source, registry, transport, policy, history, api):
    catalogue = analyse(source, registry, 'lab-web')
    write_json(folder / 'catalogue.json', catalogue)
    candidate = catalogue['candidates'][0]
    if candidate['status'] != 'READY_FOR_REVIEW':
        raise AssertionError('CANDIDATE_NOT_READY')
    before = api.received
    plan = await preview(source, registry, candidate['candidate_id'], transport, policy, history)
    delta = api.received - before
    write_plan(plan, folder / 'plan.json')
    if (delta != 0 or plan.provider != 'mock' or plan.expected_http_requests != 11
            or plan.expected_tool_calls != 12 or plan.sequence != list(plan.policy.sequence())):
        raise AssertionError('PLAN_REVIEW_FAILED')
    registered = load_scope_registry(registry)
    if plan.policy.adapter != registered.adapter('lab-web') or plan.policy.accounts != registered.profile('lab-web').accounts:
        raise AssertionError('PLAN_REGISTRATION_MISMATCH')
    write_json(folder / 'plan_review.json', {
        'plan_sha256': plan.plan_sha256, 'approval_actor': 'codex', 'approval_identity_authenticated': False,
        'provider': 'mock', 'transport': transport, 'registered_accounts_resources_checked': True,
        'sequence_steps_checked': 11, 'preview_target_requests': delta,
        'target_counter_before': before, 'target_counter_after': api.received,
        'scope_snapshot_sha256': plan.policy.scope_policy.snapshot_sha256,
    })
    return plan


async def run_plan(folder, source, registry, plan, policy, history, token):
    return await execute_plan(source, registry, plan, plan.plan_sha256, policy, history,
                              lambda transport: ResourceClient(policy.base_url, token, transport),
                              folder / 'runs', approval_actor='codex')


def exercise(folder, api, token, auth, vulnerable, transport, case):
    # The server never sees registry, agent aliases, expected verdicts or proof refs.
    environment = {'LAB_USER_A_PASSWORD': api.members[0].password, 'LAB_USER_B_PASSWORD': api.members[1].password,
                   'OPERATOR_PROOF_A': api.attachments[0].receipt, 'OPERATOR_PROOF_B': api.attachments[1].receipt}
    with attachment_server(api) as target_port:
        config = registry_for(auth, target_port, 2 if case == 'budget2' else 11)
        source, registry = folder / 'openapi.json', folder / 'registered_inputs.json'
        write_json(source, specification(auth))
        write_json(registry, config)
        history = ResourceHistory(folder / 'history')
        service, app = new_worker(registry, environment, token)
        report = None
        rejection = None
        with worker_server(app) as worker_port:
            policy = ResourcePolicyClient(f'http://127.0.0.1:{worker_port}', token)
            plan = asyncio.run(prepare(folder, source, registry, transport, policy, history, api))
            current_snapshot = service.policy().scope_policy.snapshot_sha256
            if case != 'policy_change':
                report = asyncio.run(run_plan(folder, source, registry, plan, policy, history, token))
        wire_counts = dict(app.counts)
        if case == 'policy_change':
            # Restart a real local Worker on its own old port with a different
            # proof commitment. Do not change the controller's input registry.
            changed = dict(environment, OPERATOR_PROOF_B=secrets.token_urlsafe(36))
            api.secret_values.append(changed['OPERATOR_PROOF_B'])
            replacement, new_app = new_worker(registry, changed, token)
            current_snapshot = replacement.policy().scope_policy.snapshot_sha256
            with worker_server(new_app, worker_port):
                try:
                    report = asyncio.run(run_plan(folder, source, registry, plan, policy, history, token))
                except CandidateError as exc:
                    rejection = str(exc)
            for key in wire_counts:
                wire_counts[key] += new_app.counts[key]
        observed = api.received
        expected = (None if case == 'policy_change' else 'INCONCLUSIVE' if case != 'normal'
                    else 'VULNERABLE' if vulnerable else 'BLOCKED_BY_ACCESS_CONTROL')
        rerun = replay(folder / 'runs' / report['run_id']) if report else None
        if rerun:
            write_json(folder / 'replay.json', rerun)
        issued = list((folder / 'history').glob('*.issued.json'))
        claimed = list((folder / 'history').glob('*.claimed.json'))
        row = {
            'auth': auth, 'mode': 'vulnerable' if vulnerable else 'fixed', 'transport': transport, 'case': case,
            'plan_id': plan.plan_id, 'plan_sha256': plan.plan_sha256,
            'planned_snapshot': plan.policy.scope_policy.snapshot_sha256, 'worker_snapshot_at_run': current_snapshot,
            'run_id': report['run_id'] if report else None,
            'status': report['status'] if report else 'REJECTED_BEFORE_RUN',
            'expected_verdict': expected, 'actual_verdict': report['verdict'] if report else None,
            'reason_code': report['reason_code'] if report else rejection,
            'preview_target_requests': json.loads((folder / 'plan_review.json').read_text())['preview_target_requests'],
            'observed_target_http_requests': observed,
            'worker_usage': report['limits_used'] if report else None,
            'evidence_count': len(report['evidence_ids']) if report else 0,
            'replay': rerun, 'issued_count': len(issued), 'claimed_count': len(claimed),
            'scope_matches_plan': report['scope_policy'] == plan.policy.scope_policy.model_dump(mode='json') if report else None,
            'worker_transport_receipts': wire_counts,
        }
        if report:
            link = json.loads((folder / 'runs' / report['run_id'] / 'candidate_execution.json').read_text())
            claim = json.loads(claimed[0].read_text()) if claimed else {}
            row['plan_run_link_matches'] = (link['plan_sha256'] == plan.plan_sha256 and link['plan_id'] == plan.plan_id
                                             and link['actual_scope_policy'] == report['scope_policy']
                                             and claim.get('run_id') == report['run_id'])
        else:
            row['plan_run_link_matches'] = None
        if case == 'policy_change':
            row['passed'] = (report is None and rejection == 'WORKER_POLICY_CHANGED' and observed == 0
                             and current_snapshot != row['planned_snapshot'] and not claimed and len(issued) == 1
                             and wire_counts == {'policy': 2, 'function': 0, 'mcp': 0, 'cancel': 0})
        else:
            expected_count = 2 if case == 'budget2' else 11
            transport_seen = wire_counts[transport] > 0 and wire_counts['mcp' if transport == 'function' else 'function'] == 0
            row['passed'] = bool(report and observed == expected_count and report['verdict'] == expected
                                 and report['limits_used']['http_requests'] == observed
                                 and len(report['evidence_ids']) == expected_count and rerun['verdict_matches']
                                 and row['scope_matches_plan'] and row['plan_run_link_matches']
                                 and len(issued) == len(claimed) == 1 and transport_seen
                                 and (case == 'budget2' or report['limits_used']['tool_calls'] == 12))
        row['passed'] = row['passed'] and row['preview_target_requests'] == 0
        # Test oracle and counters are written outside run directories and are
        # never arguments to verify_operator/replay.
        write_json(folder / 'target_measurement.json', {'received': observed, 'events': api.events,
                                                       'verifier_input': False, 'boundary': 'HTTP handler entry'})
        write_json(folder / 'result.json', row)
        return row


def run_case(output, auth, vulnerable, transport, case='normal'):
    if (auth not in ('cookie', 'bearer') or transport not in ('function', 'mcp')
            or case not in ('normal', 'policy_change', 'budget2', 'owner_mismatch', 'proof_rotation')):
        raise ValueError('unknown matrix case')
    name = f'{auth}-' + ('vulnerable' if vulnerable else 'fixed') + f'-{transport}-{case}'
    destination = output / name
    if destination.exists():
        raise FileExistsError('case output already exists')
    api = AttachmentService(auth, vulnerable, case if case in ('owner_mismatch', 'proof_rotation') else None)
    token = secrets.token_urlsafe(36)
    with tempfile.TemporaryDirectory(prefix='independent-attachments-') as temporary:
        folder = Path(temporary)
        try:
            row = exercise(folder, api, token, auth, vulnerable, transport, case)
        except Exception as exc:
            # Preserve sanitized partial evidence without exposing exception text.
            row = {'auth': auth, 'mode': 'vulnerable' if vulnerable else 'fixed', 'transport': transport,
                   'case': case, 'passed': False, 'failure_type': type(exc).__name__}
            write_json(folder / 'result.json', row)
        checked = publication_check(folder, [*api.secret_values, token])
        write_json(folder / 'publication_check.json', checked)
        publication_check(folder, [*api.secret_values, token])
        shutil.copytree(folder, destination)
    return dict(row, path=name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    cases = [(a, v, t, 'normal') for a in ('cookie', 'bearer') for v in (True, False) for t in ('function', 'mcp')]
    cases += [('cookie', True, t, c) for c in ('policy_change', 'budget2', 'owner_mismatch', 'proof_rotation') for t in ('function', 'mcp')]
    matrix = {'classification': 'internal white-box adapter applicability; not blind or external evaluation',
              'started_at': datetime.now(timezone.utc).isoformat(), 'provider': 'mock',
              'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
              'working_tree_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip()),
              'cases': []}
    for auth, vulnerable, transport, case in cases:
        row = run_case(args.output, auth, vulnerable, transport, case)
        matrix['cases'].append(row)
        write_json(args.output / 'matrix.json', matrix)
        print(json.dumps({k: row.get(k) for k in ('auth', 'mode', 'transport', 'case', 'passed', 'reason_code', 'observed_target_http_requests', 'failure_type')}), flush=True)
    matrix.update(passed=all(row['passed'] for row in matrix['cases']), elapsed_seconds=round(time.monotonic()-started, 3))
    sources = [Path(__file__), *Path('validation/independent_api').glob('*.py'), *Path('validation/independent_api').glob('*.json'),
               *[Path(p) for p in ('common/operator_contract.py', 'controller/operator_execution.py',
                                   'controller/operator_candidates.py', 'controller/operator_client.py',
                                   'worker/operator_service.py', 'worker/operator_scope.py', 'verifier/operator.py')]]
    matrix['source_sha256'] = {p.as_posix() if not p.is_absolute() else p.relative_to(Path.cwd()).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    write_json(args.output / 'matrix.json', matrix)
    return 0 if matrix['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
