"""Real TLS target / function-MCP matrix, reusing the independent attachment API."""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import secrets
import shutil
import ssl
import subprocess
import tempfile
import time

from controller.candidate_execution import CandidateError
from controller.operator_client import ResourcePolicyClient
from controller.operator_execution import ResourceHistory
from scripts.run_independent_api_validation import ObservedWorker, prepare, publication_check, run_plan, write_json
from validation.independent_api.api import AttachmentService, attachment_server
from validation.independent_api.configuration import registry_for, specification
from validation.independent_api.transport import worker_server
from validation.local_https import certificates
from verifier.operator import replay
from worker.app import build_worker_app
from worker.limits import WorkerLimits
from worker.operator_service import OperatorService
from worker.registry import load_scope_registry
from worker.tls import bind_registry_tls


ERRORS = {'untrusted_ca': 'TLS_CERT_UNTRUSTED', 'wrong_san': 'TLS_CERT_IP_SAN_MISMATCH', 'expired': 'TLS_CERT_EXPIRED'}
CASES = [(a, v, t, 'normal') for a in ('cookie', 'bearer') for v in (True, False) for t in ('function', 'mcp')]
CASES += [('cookie', True, t, c) for c in (*ERRORS, 'ca_rotation') for t in ('function', 'mcp')]


def new_worker(registry, environment, token, ca_file):
    registered = bind_registry_tls(load_scope_registry(registry).bind_proofs(environment), ca_file)
    service = OperatorService(registry=registered, accounts=registered.credentials(environment),
                              limits=WorkerLimits(requests_per_second=1000.0))
    return service, ObservedWorker(build_worker_app(service, worker_token=token, allowed_clients={'127.0.0.1'}))


def case_flow(folder, api, token, material, auth, vulnerable, transport, case):
    environment = {'LAB_USER_A_PASSWORD': api.members[0].password, 'LAB_USER_B_PASSWORD': api.members[1].password,
                   'OPERATOR_PROOF_A': api.attachments[0].receipt, 'OPERATOR_PROOF_B': api.attachments[1].receipt}
    counts = dict(tcp_accepted=0, tls_handshake_attempts=0, tls_handshake_failed=0, tls_handshake_completed=0)
    rotation = None
    with attachment_server(api, ssl_context=material['server_context'], connection_counts=counts) as port:
        config = registry_for(auth, port)
        config['targets']['lab-web']['origin'] = f'https://127.0.0.1:{port}'
        source, registry = folder/'openapi.json', folder/'registered_inputs.json'
        write_json(source, specification(auth))
        write_json(registry, config)
        service, app = new_worker(registry, environment, token, material['ca_file'])
        history = ResourceHistory(folder/'history')
        with worker_server(app) as worker_port:
            policy = ResourcePolicyClient(f'http://127.0.0.1:{worker_port}', token)
            before = dict(counts)
            plan = asyncio.run(prepare(folder, source, registry, transport, policy, history, api))
            preview_counts = {k: counts[k]-before[k] for k in counts}
            if case != 'ca_rotation':
                report = asyncio.run(run_plan(folder, source, registry, plan, policy, history, token))
        wire_counts = dict(app.counts)
        if case == 'ca_rotation':
            old_plan = plan
            before = dict(counts)
            material['ca_file'].write_bytes(material['alternate_bundle'])  # Same path; different valid CA content.
            replacement, app2 = new_worker(registry, environment, token, material['ca_file'])
            current = replacement.policy().scope_policy
            with worker_server(app2, worker_port):
                reason = None
                try:
                    asyncio.run(run_plan(folder, source, registry, old_plan, policy, history, token))
                except CandidateError as exc:
                    reason = str(exc)
                rotation = {'same_ca_path': True, 'old_plan_sha256': old_plan.plan_sha256,
                            'old_snapshot': old_plan.policy.scope_policy.model_dump(mode='json'),
                            'new_snapshot': current.model_dump(mode='json'), 'reason_code': reason,
                            'target_http_after_rejected_plan': api.received,
                            'network_delta_after_rejected_plan': {k: counts[k]-before[k] for k in counts},
                            'old_plan_claimed': (folder/'history'/(old_plan.plan_id+'.claimed.json')).exists()}
                fresh = folder/'fresh_preview'
                fresh.mkdir()
                plan = asyncio.run(prepare(fresh, source, registry, transport, policy, history, api))
                rotation['new_plan_sha256'] = plan.plan_sha256
                rotation['fresh_preview_target_requests'] = json.loads((fresh/'plan_review.json').read_text())['preview_target_requests']
                report = asyncio.run(run_plan(folder, source, registry, plan, policy, history, token))
            for key in wire_counts:
                wire_counts[key] += app2.counts[key]
            write_json(folder/'ca_rotation.json', rotation)
    # The listener has stopped, so failed-handshake counters cannot race publication.
    rerun = replay(folder/'runs'/report['run_id'])
    write_json(folder/'replay.json', rerun)
    link = json.loads((folder/'runs'/report['run_id']/'candidate_execution.json').read_text())
    claim = json.loads((folder/'history'/(plan.plan_id+'.claimed.json')).read_text())
    expected = 'INCONCLUSIVE' if case in ERRORS else 'VULNERABLE' if vulnerable else 'BLOCKED_BY_ACCESS_CONTROL'
    row = {'auth': auth, 'mode': 'vulnerable' if vulnerable else 'fixed', 'transport': transport, 'case': case,
           'run_id': report['run_id'], 'plan_id': plan.plan_id, 'plan_sha256': plan.plan_sha256,
           'planned_scope': plan.policy.scope_policy.model_dump(mode='json'), 'actual_scope': report['scope_policy'],
           'preview_target_http': json.loads((folder/'plan_review.json').read_text())['preview_target_requests'],
           'preview_network_delta': preview_counts, 'network': counts, 'target_http_received': api.received,
           'worker_usage': report['limits_used'], 'evidence_count': len(report['evidence_ids']),
           'status': report['status'], 'verdict': report['verdict'], 'expected_verdict': expected,
           'reason_code': report['reason_code'], 'replay': rerun, 'worker_transport_receipts': wire_counts,
           'plan_link_matches': link['plan_sha256'] == plan.plan_sha256 and link['expected_scope_policy'] == report['scope_policy']
                                and link['actual_scope_policy'] == report['scope_policy'] and claim['run_id'] == report['run_id'],
           'tls_certificate': material['public'], 'rotation': rotation}
    ok = (row['preview_target_http'] == 0 and not any(preview_counts.values()) and row['plan_link_matches']
          and row['actual_scope'] == row['planned_scope'] and rerun['verdict_matches'] and report['verdict'] == expected
          and wire_counts[transport] > 0 and wire_counts['mcp' if transport == 'function' else 'function'] == 0)
    if case in ERRORS:
        ok &= (report['status'] == 'FAILED' and report['reason_code'] == ERRORS[case] and api.received == 0
               and report['limits_used'] == {'http_requests': 1, 'tool_calls': 1} and row['evidence_count'] == 0
               and counts['tcp_accepted'] == counts['tls_handshake_attempts'] == counts['tls_handshake_failed'] == 1
               and counts['tls_handshake_completed'] == 0)
    else:
        ok &= (report['status'] == 'COMPLETED' and api.received == 11 and row['evidence_count'] == 11
               and report['limits_used'] == {'http_requests': 11, 'tool_calls': 12}
               and counts['tls_handshake_completed'] == 11 and counts['tls_handshake_failed'] == 0)
    if rotation:
        ok &= (rotation['reason_code'] == 'WORKER_POLICY_CHANGED' and rotation['target_http_after_rejected_plan'] == 0
               and not any(rotation['network_delta_after_rejected_plan'].values()) and not rotation['old_plan_claimed']
               and rotation['old_snapshot']['tls'] != rotation['new_snapshot']['tls']
               and rotation['old_snapshot']['snapshot_sha256'] != rotation['new_snapshot']['snapshot_sha256']
               and rotation['fresh_preview_target_requests'] == 0 and plan.plan_sha256 != old_plan.plan_sha256)
    row['passed'] = bool(ok)
    write_json(folder/'target_measurement.json', {'http_received': api.received, 'network': counts,
                                               'events': api.events, 'verifier_input': False})
    write_json(folder/'result.json', row)
    return row


def run_case(output, auth, vulnerable, transport, case='normal'):
    if (auth, vulnerable, transport, case) not in CASES:
        raise ValueError('unknown registered TLS case')
    name = f'{auth}-'+('vulnerable' if vulnerable else 'fixed')+f'-{transport}-{case}'
    destination = output/name
    if destination.exists():
        raise FileExistsError('new output required')
    api, token = AttachmentService(auth, vulnerable), secrets.token_urlsafe(36)
    with tempfile.TemporaryDirectory(prefix='local-tls-evidence-') as temporary:
        folder = Path(temporary)
        with certificates(case) as material:
            private_root = material['private_directory']
            forbidden = [*material['private_values'], str(private_root), private_root.as_posix(), token]
            try:
                row = case_flow(folder, api, token, material, auth, vulnerable, transport, case)
            except Exception as exc:
                row = {'auth': auth, 'mode': 'vulnerable' if vulnerable else 'fixed', 'transport': transport,
                       'case': case, 'passed': False, 'failure_type': type(exc).__name__}
                write_json(folder/'result.json', row)
            checked = publication_check(folder, [*api.secret_values, *forbidden])
            write_json(folder/'publication_check.json', checked)
            publication_check(folder, [*api.secret_values, *forbidden])
        row['temporary_key_directory_removed'] = not private_root.exists()
        row['passed'] &= row['temporary_key_directory_removed']
        write_json(folder/'result.json', row)
        publication_check(folder, [*api.secret_values, *forbidden])
        shutil.copytree(folder, destination)
    return dict(row, path=name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    sources = [Path(__file__), Path('validation/local_https.py'), Path('validation/independent_api/api.py'),
               *Path('worker').glob('*.py'), Path('common/tls_contract.py'), Path('common/operator_contract.py'),
               Path('common/schemas.py'), Path('common/service_config.py'), Path('controller/operator_execution.py'), Path('verifier/operator.py')]
    matrix = {'started_at_utc': datetime.now(timezone.utc).isoformat(), 'provider': 'mock',
              'code_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
              'working_tree_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip()),
              'command': 'python -m scripts.run_local_https_verification --output <new-directory>',
              'python': platform.python_version(), 'platform': platform.platform(), 'openssl': ssl.OPENSSL_VERSION,
              'runtime_initial_context_ca_records': len(ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT).get_ca_certs()),
              'source_sha256': {p.resolve().relative_to(Path.cwd()).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}, 'cases': []}
    for auth, vulnerable, transport, case in CASES:
        row = run_case(args.output, auth, vulnerable, transport, case)
        matrix['cases'].append(row)
        write_json(args.output/'matrix.json', matrix)
        print(json.dumps({k: row.get(k) for k in ('auth', 'mode', 'transport', 'case', 'passed', 'reason_code', 'target_http_received', 'failure_type')}), flush=True)
    matrix.update(passed=all(r['passed'] for r in matrix['cases']), elapsed_seconds=round(time.monotonic()-start, 3))
    write_json(args.output/'matrix.json', matrix)
    return 0 if matrix['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
