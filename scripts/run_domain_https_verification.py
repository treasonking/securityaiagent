"""Registered .test domain, injected resolver, real TLS/socket + function/MCP matrix."""
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
from scripts.run_independent_api_validation import prepare, publication_check, run_plan, write_json
from scripts.run_local_https_verification import new_worker
from validation.independent_api.api import AttachmentService, attachment_server
from validation.independent_api.configuration import registry_for, specification
from validation.independent_api.transport import worker_server
from validation.local_https import certificates
from validation.domain_https import HOST, TestResolver, forbid_hostname_lookup
from verifier.operator import replay

ERRORS = {'outside': 'DNS_ADDRESS_OUT_OF_SCOPE', 'mixed': 'DNS_ADDRESS_OUT_OF_SCOPE',
          'empty': 'DNS_NO_RESULTS', 'lookup_failed': 'DNS_LOOKUP_FAILED',
          'wrong_san': 'TLS_CERT_DOMAIN_MISMATCH', 'rebind': 'DNS_ADDRESS_OUT_OF_SCOPE',
          'redirect': 'TRANSPORT_OR_RESPONSE_ERROR'}
CASES = [(a, v, t, 'normal') for a in ('cookie', 'bearer') for v in (True, False) for t in ('function', 'mcp')]
CASES += [('cookie', True, t, c) for c in (*ERRORS, 'policy_change') for t in ('function', 'mcp')]


def domain_config(auth, port):
    config = registry_for(auth, port)
    config['targets']['lab-web'].update(origin=f'https://{HOST}:{port}',
        network={'allowed_ip_ranges': ['127.0.0.1/32'], 'allow_non_global': True})
    return config


def case_flow(folder, api, token, material, auth, vulnerable, transport, case):
    env = dict(LAB_USER_A_PASSWORD=api.members[0].password, LAB_USER_B_PASSWORD=api.members[1].password,
               OPERATOR_PROOF_A=api.attachments[0].receipt, OPERATOR_PROOF_B=api.attachments[1].receipt)
    counts = dict(tcp_accepted=0, tls_handshake_attempts=0, tls_handshake_failed=0, tls_handshake_completed=0)
    hosts, sni = [], []
    material['server_context'].set_servername_callback(lambda _s, name, _c: sni.append(name))
    resolver, rotation = TestResolver(case), None
    if case == 'redirect':
        # Fault response on the same API, no new API/fixture. No destination is ever resolved.
        api.dispatch = lambda *args: (302, {}, {'Location': 'https://unapproved.securityai.test:443/escape'}, 'redirect')
    with forbid_hostname_lookup() as unapproved_lookups:
        with attachment_server(api, ssl_context=material['server_context'], connection_counts=counts, observed_hosts=hosts) as port:
            source, registry = folder/'openapi.json', folder/'registered_inputs.json'
            write_json(source, specification(auth))
            config = domain_config(auth, port)
            write_json(registry, config)
            service, app = new_worker(registry, env, token, material['ca_file'])
            service._domain_resolver = resolver
            history = ResourceHistory(folder/'history')
            with worker_server(app) as worker_port:
                policy = ResourcePolicyClient(f'http://127.0.0.1:{worker_port}', token)
                before = dict(counts)
                plan = asyncio.run(prepare(folder, source, registry, transport, policy, history, api))
                preview = dict(http=api.received, dns=len(resolver.calls), **{k: counts[k]-before[k] for k in counts})
                if case != 'policy_change':
                    report = asyncio.run(run_plan(folder, source, registry, plan, policy, history, token))
            wire = dict(app.counts)
            if case == 'policy_change':
                old_plan = plan
                changed = folder/'replacement_registry.json'
                config['targets']['lab-web']['network']['allowed_ip_ranges'] = ['127.0.0.1/32', '127.0.0.2/32']
                write_json(changed, config)
                replacement, app2 = new_worker(changed, env, token, material['ca_file'])
                replacement._domain_resolver = resolver
                with worker_server(app2, worker_port):
                    rejection = None
                    try:
                        asyncio.run(run_plan(folder, source, registry, old_plan, policy, history, token))
                    except CandidateError as exc:
                        rejection = str(exc)
                    rotation = dict(status='REJECTED_BEFORE_RUN', run_id=None, reason_code=rejection,
                        old_plan_sha256=old_plan.plan_sha256, old_scope=old_plan.policy.scope_policy.model_dump(mode='json'),
                        new_scope=replacement.policy().scope_policy.model_dump(mode='json'),
                        target_http=api.received, dns_calls=len(resolver.calls), network=dict(counts),
                        claimed=(folder/'history'/(old_plan.plan_id+'.claimed.json')).exists(),
                        run_directories=len(list((folder/'runs').glob('*'))))
                    fresh = folder/'fresh_preview'
                    fresh.mkdir()
                    plan = asyncio.run(prepare(fresh, source, changed, transport, policy, history, api))
                    rotation['fresh_preview_counts'] = dict(http=api.received, dns=len(resolver.calls), **counts)
                    report = asyncio.run(run_plan(folder, source, changed, plan, policy, history, token))
                for k in wire:
                    wire[k] += app2.counts[k]
                write_json(folder/'policy_change.json', rotation)
    run = folder/'runs'/report['run_id']
    connections = json.loads((run/'connection_observations.json').read_text())
    rerun = replay(run)
    write_json(folder/'replay.json', rerun)
    link = json.loads((run/'candidate_execution.json').read_text())
    claim = json.loads((folder/'history'/(plan.plan_id+'.claimed.json')).read_text())
    expected = 'INCONCLUSIVE' if case in ERRORS else 'VULNERABLE' if vulnerable else 'BLOCKED_BY_ACCESS_CONTROL'
    row = dict(auth=auth, mode='vulnerable' if vulnerable else 'fixed', transport=transport, case=case,
        run_id=report['run_id'], plan_id=plan.plan_id, plan_sha256=plan.plan_sha256,
        planned_scope=plan.policy.scope_policy.model_dump(mode='json'), actual_scope=report['scope_policy'],
        preview=preview, network=counts, target_http_received=api.received, worker_usage=report['limits_used'],
        evidence_count=len(report['evidence_ids']), status=report['status'], verdict=report['verdict'],
        expected_verdict=expected, reason_code=report['reason_code'], replay=rerun, worker_transport_receipts=wire,
        dns_calls=resolver.calls, resolver_boundary='injected-test-answers-not-external-DNS',
        unexpected_os_hostname_lookups=unapproved_lookups, observed_sni=sni, observed_hosts=hosts,
        connections=connections, tls_certificate=material['public'], policy_change=rotation,
        plan_link_matches=link['plan_sha256']==plan.plan_sha256 and link['actual_scope_policy']==report['scope_policy']
            and link['expected_scope_policy']==report['scope_policy'] and claim['run_id']==report['run_id'])
    ok = (not any(preview.values()) and not unapproved_lookups and row['plan_link_matches']
          and row['actual_scope']==row['planned_scope'] and rerun['verdict_matches'] and report['verdict']==expected
          and wire[transport]>0 and wire['function' if transport=='mcp' else 'mcp']==0
          and all(name==HOST for name in sni) and all(host==f'{HOST}:{port}' for host in hosts))
    if case in ERRORS:
        http = 1 if case in ('rebind', 'redirect') else 0
        tcp = 1 if case in ('wrong_san', 'rebind', 'redirect') else 0
        requests = 2 if case=='rebind' else 1
        ok &= (report['status']=='FAILED' and report['reason_code']==ERRORS[case] and api.received==http
               and counts['tcp_accepted']==tcp and counts['tls_handshake_attempts']==tcp
               and counts['tls_handshake_failed']==int(case=='wrong_san')
               and row['worker_usage']=={'http_requests':requests,'tool_calls':requests}
               and row['evidence_count']==int(case=='rebind') and len(resolver.calls)==requests
               and len(connections)==requests)
    else:
        ok &= (report['status']=='COMPLETED' and api.received==11 and row['evidence_count']==11
               and row['worker_usage']=={'http_requests':11,'tool_calls':12} and len(resolver.calls)==11
               and counts['tls_handshake_completed']==11 and counts['tls_handshake_failed']==0
               and len(connections)==11 and all(c['peer_verified'] and c['selected_ip']==c['peer_ip']=='127.0.0.1'
                   and c['peer_port']==port and c['tls_server_name']==HOST and c['http_response_received'] for c in connections))
    if rotation:
        ok &= (rotation['reason_code']=='WORKER_POLICY_CHANGED' and rotation['target_http']==rotation['dns_calls']==0
               and not any(rotation['network'].values()) and not any(rotation['fresh_preview_counts'].values())
               and not rotation['claimed'] and rotation['run_directories']==0
               and rotation['old_scope']['snapshot_sha256']!=rotation['new_scope']['snapshot_sha256']
               and old_plan.plan_sha256!=plan.plan_sha256)
    row['passed'] = bool(ok)
    write_json(folder/'target_measurement.json', dict(http_received=api.received, network=counts,
        observed_sni=sni, observed_hosts=hosts, events=api.events, verifier_input=False))
    write_json(folder/'result.json', row)
    return row


def run_case(output, auth, vulnerable, transport, case='normal'):
    if (auth, vulnerable, transport, case) not in CASES:
        raise ValueError('unknown registered domain experiment')
    name = f'{auth}-'+('vulnerable' if vulnerable else 'fixed')+f'-{transport}-{case}'
    destination = output/name
    if destination.exists():
        raise FileExistsError('new output required')
    api, token = AttachmentService(auth, vulnerable), secrets.token_urlsafe(36)
    with tempfile.TemporaryDirectory(prefix='domain-evidence-') as temporary:
        folder = Path(temporary)
        with certificates('wrong_san' if case=='wrong_san' else 'normal', dns_name=HOST) as material:
            private = material['private_directory']
            forbidden = [*material['private_values'], str(private), private.as_posix(), token]
            try:
                row = case_flow(folder, api, token, material, auth, vulnerable, transport, case)
            except Exception as exc:
                row = dict(auth=auth, mode='vulnerable' if vulnerable else 'fixed', transport=transport,
                           case=case, passed=False, failure_type=type(exc).__name__)
                write_json(folder/'result.json', row)
            write_json(folder/'publication_check.json', publication_check(folder, [*api.secret_values, *forbidden]))
        row['temporary_key_directory_removed'] = not private.exists()
        row['passed'] &= row['temporary_key_directory_removed']
        write_json(folder/'result.json', row)
        publication_check(folder, [*api.secret_values, *forbidden])
        shutil.copytree(folder, destination)
    return dict(row, path=name)


def source_hashes(paths, root=None):
    root = (root or Path.cwd()).resolve()
    return {p.resolve().relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    sources = [Path(__file__), *Path('worker').glob('*.py'), *Path('common').glob('*.py'),
               Path('controller/operator_execution.py'), Path('validation/domain_https.py'), Path('validation/local_https.py'),
               Path('validation/independent_api/api.py'), Path('verifier/operator.py')]
    matrix = dict(started_at_utc=datetime.now(timezone.utc).isoformat(), provider='mock',
        code_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        working_tree_dirty=bool(subprocess.check_output(['git','status','--porcelain'],text=True).strip()),
        command='python -m scripts.run_domain_https_verification --output <new-directory>',
        python=platform.python_version(), platform=platform.platform(), openssl=ssl.OPENSSL_VERSION,
        resolver='test injected; OS resolver separately unit-tested; no external DNS',
        source_sha256=source_hashes(sources), cases=[])
    for values in CASES:
        row = run_case(args.output, *values)
        matrix['cases'].append(row)
        write_json(args.output/'matrix.json', matrix)
        print(json.dumps({k:row.get(k) for k in ('auth','mode','transport','case','passed','reason_code','target_http_received','failure_type')}),flush=True)
    matrix.update(passed=all(r['passed'] for r in matrix['cases']),elapsed_seconds=round(time.monotonic()-start,3))
    write_json(args.output/'matrix.json', matrix)
    return 0 if matrix['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
