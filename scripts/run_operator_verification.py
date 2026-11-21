"""Local actual TCP verification; all sockets, data and secrets belong to this run."""
from __future__ import annotations
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import secrets
import subprocess
import tempfile
import time

from controller.candidates import analyse
from controller.operator_client import ResourceClient, ResourcePolicyClient
from controller.operator_execution import ResourceHistory, execute_plan, preview, write_plan
from scripts.operator_fixture import IndependentAPI, local_server, settings, specification
from verifier.operator import replay
from worker.app import build_worker_app
from worker.limits import WorkerLimits
from worker.operator_service import OperatorService
from worker.registry import load_scope_registry


def write_json(path,value):
    path.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')


def assert_redacted(folder,api,token):
    values=[*api.passwords.values(),*api.proofs.values(),*api.sessions,api.shared_token,token]
    for path in folder.rglob('*'):
        if path.is_file():
            body=path.read_text(encoding='utf-8')
            if any(secret in body for secret in values):
                raise AssertionError('SECRET_REDACTION_FAILED')


async def workflow(folder,source,registry,service,api,base,token,transport,case):
    policy=ResourcePolicyClient(base,token)
    history=ResourceHistory(folder/'history')
    catalogue=analyse(source,registry,'lab-web')
    write_json(folder/'catalogue.json',catalogue)
    candidate=catalogue['candidates'][0]
    if candidate['status']!='READY_FOR_REVIEW': raise AssertionError('CANDIDATE_NOT_READY')
    before=len(api.requests)
    plan=await preview(source,registry,candidate['candidate_id'],transport,policy,history)
    preview_requests=len(api.requests)-before
    write_plan(plan,folder/'plan.json')
    # Separate review/confirmation step: check displayed policy and flow before run.
    assert plan.provider=='mock' and plan.transport==transport and plan.expected_http_requests==11
    assert plan.expected_tool_calls==12 and plan.sequence==list(plan.policy.sequence())
    assert plan.policy.scope_policy==service.policy().scope_policy
    write_json(folder/'plan_review.json',{'plan_sha256':plan.plan_sha256,'approval_actor':'codex',
        'approval_identity_authenticated':False,'sequence_steps_checked':11,'preview_target_requests':preview_requests})
    if case=='prelogin_policy_change':
        class RacingClient(ResourceClient):
            async def step(self,**payload):
                if not service._runs:
                    changed=api.environment()
                    changed['OPERATOR_PROOF_B']=secrets.token_urlsafe(32)
                    service.registry=service.registry.bind_proofs(changed)
                return await super().step(**payload)
        factory=lambda t:RacingClient(base,token,t)
    else:
        factory=lambda t:ResourceClient(base,token,t)
    start=len(api.requests)
    report=await execute_plan(source,registry,plan,plan.plan_sha256,policy,history,factory,folder/'runs',approval_actor='codex')
    observed=len(api.requests)-start
    run_dir=folder/'runs'/report['run_id']
    rerun=replay(run_dir)
    write_json(folder/'replay.json',rerun)
    expected=('INCONCLUSIVE' if case!='normal' else 'VULNERABLE' if api.vulnerable else 'BLOCKED_BY_ACCESS_CONTROL')
    expected_http=0 if case=='prelogin_policy_change' else 2 if case=='budget2' else 7 if case=='redirect' else 11
    expected_evidence=0 if case=='prelogin_policy_change' else 2 if case=='budget2' else 6 if case=='redirect' else 11
    row={'auth':api.auth,'mode':'vulnerable' if api.vulnerable else 'fixed','transport':transport,'case':case,
        'run_id':report['run_id'],'status':report['status'],'expected_verdict':expected,'actual_verdict':report['verdict'],
        'reason_code':report['reason_code'],'preview_target_requests':preview_requests,'observed_target_http_requests':observed,
        'expected_target_http_requests':expected_http,'worker_usage':report['limits_used'],
        'evidence_count':len(report['evidence_ids']),'replay':rerun,
        'scope_matches_plan':report['scope_policy']==plan.policy.scope_policy.model_dump(mode='json') if report['scope_policy'] else None,
        'path':folder.name}
    row['passed']=(preview_requests==0 and observed==expected_http and report['verdict']==expected
        and rerun['verdict_matches'] and len(report['evidence_ids'])==expected_evidence
        and report['limits_used']['http_requests']==observed
        and (case!='normal' or report['limits_used']['tool_calls']==12 and row['scope_matches_plan']))
    assert_redacted(folder,api,token)
    write_json(folder/'result.json',row)
    return row


def run_case(root,auth,vulnerable,transport,case='normal'):
    name=f'{auth}-'+('vulnerable' if vulnerable else 'fixed')+f'-{transport}-{case}'
    folder=root/name
    folder.mkdir()
    api=IndependentAPI(auth,vulnerable,fault=case if case in ('redirect','public') else None)
    token=secrets.token_urlsafe(32)
    with tempfile.TemporaryDirectory(prefix='operator-fixture-') as temporary, local_server(api.app) as target_port:
        work=Path(temporary)
        config=settings(auth,f'http://127.0.0.1:{target_port}')
        if case=='budget2': config['targets']['lab-web']['profile']['limits']['max_requests']=2
        source,registry=work/'openapi.json',work/'registry.json'
        write_json(source,specification(auth)); write_json(registry,config)
        reg=load_scope_registry(registry).bind_proofs(api.environment())
        service=OperatorService(registry=reg,accounts=reg.credentials(api.environment()),limits=WorkerLimits(requests_per_second=1000.0))
        app=build_worker_app(service,worker_token=token,allowed_clients={'127.0.0.1'})
        with local_server(app) as worker_port:
            row=asyncio.run(workflow(folder,source,registry,service,api,f'http://127.0.0.1:{worker_port}',token,transport,case))
        # These are operator inputs only; neither fixture state nor expected mode enters verifier.
        write_json(folder/'registered_inputs.json',config)
        write_json(folder/'source_openapi.json',specification(auth))
    assert_redacted(folder,api,token)
    return row


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--smoke',action='store_true',help='one cookie/function positive case only')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    start=time.monotonic()
    matrix={'schema_version':'operator-tcp-matrix-v1','started_at':datetime.now(timezone.utc).isoformat(),
        'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'working_tree_dirty':bool(subprocess.check_output(['git','status','--porcelain'],text=True).strip()),
        'python':platform.python_version(),'os':platform.platform(),'provider':'mock',
        'target_fixture':'independent in-memory JSON API; no target DB/logs/TargetStore/canary helpers',
        'approval_actor':'codex','cases':[]}
    cases=[(a,v,t,'normal') for a in ('cookie','bearer') for v in (True,False) for t in ('function','mcp')]
    if args.smoke: cases=cases[:1]
    else: cases += [('cookie',True,t,c) for t in ('function','mcp') for c in ('budget2','prelogin_policy_change','redirect','public')]
    for auth,vulnerable,transport,case in cases:
        try:
            row=run_case(args.output,auth,vulnerable,transport,case)
        except Exception as exc:
            # No raw exception, URL body, tokens or credentials in public artifacts.
            row={'auth':auth,'mode':'vulnerable' if vulnerable else 'fixed','transport':transport,'case':case,
                'passed':False,'failure_type':type(exc).__name__}
        matrix['cases'].append(row)
        write_json(args.output/'matrix.json',matrix)
        print(json.dumps(row),flush=True)
    matrix.update(finished_at=datetime.now(timezone.utc).isoformat(),elapsed_seconds=round(time.monotonic()-start,3),
                  passed=all(r['passed'] for r in matrix['cases']))
    write_json(args.output/'matrix.json',matrix)
    raise SystemExit(0 if matrix['passed'] else 1)


if __name__=='__main__': main()
