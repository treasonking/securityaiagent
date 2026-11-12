"""Separate operator-resource plan/history/executor; v1 candidate plans stay v1."""
from __future__ import annotations
import argparse
import asyncio
import json
from pathlib import Path
import time
from typing import Literal
import uuid

from pydantic import Field,model_validator
from common.api_contract import FrozenModel
from common.operator_contract import (CONTRACT,SCENARIO,Hash,ResourcePolicy,ResourceStep,canonical,digest)
from common.schemas import utc_now
from controller.candidates import analyse,read_local,unique,fail_constant
from controller.candidate_execution import CandidateError,PlanHistory,plan_hash
from controller.operator_client import ResourceClient,ResourcePolicyClient
from verifier.operator import verify_operator

ROOT=Path(__file__).resolve().parents[1]


class ResourcePlan(FrozenModel):
    schema_version: Literal['operator-plan-v1']='operator-plan-v1'
    plan_id: str=Field(pattern=r'^opplan_[0-9a-f]{32}$')
    created_at: int=Field(gt=0)
    expires_at: int=Field(gt=0)
    candidate_id: Hash
    source_sha256: Hash
    registry_sha256: Hash
    worker_origin: str=Field(max_length=200)
    policy: ResourcePolicy
    sequence: list[ResourceStep]
    provider: Literal['mock']='mock'
    transport: Literal['function','mcp']
    expected_http_requests: Literal[11]=11
    expected_tool_calls: Literal[12]=12
    verification_status: Literal['NOT_EXECUTED']='NOT_EXECUTED'
    plan_sha256: Hash
    @model_validator(mode='after')
    def invariants(self):
        if self.expires_at-self.created_at!=300 or self.sequence!=list(self.policy.sequence()):
            raise ValueError('invalid resource plan')
        return self


def parse_plan(path):
    try:
        value=json.loads(read_local(path),object_pairs_hook=unique,parse_constant=fail_constant)
        stack=[(value,0)]
        while stack:
            node,depth=stack.pop()
            if depth>32: raise ValueError()
            if isinstance(node,(dict,list)):
                stack.extend((v,depth+1) for v in (node.values() if isinstance(node,dict) else node))
        return ResourcePlan.model_validate(value)
    except Exception: raise CandidateError('RESOURCE_PLAN_INVALID') from None


class ResourceHistory(PlanHistory):
    def __init__(self,directory=ROOT/'data/operator_plans'):
        super().__init__(directory)
    def validate(self,plan):
        try: issued=parse_plan(self.directory/(plan.plan_id+'.issued.json'))
        except Exception: raise CandidateError('PLAN_NOT_ISSUED') from None
        if issued!=plan: raise CandidateError('PLAN_CHANGED')


def candidate(source,registry,candidate_id):
    try: cat=analyse(source,registry,'lab-web')
    except Exception: raise CandidateError('CANDIDATE_REANALYSIS_FAILED') from None
    rows=[r for r in cat['candidates'] if r['candidate_id']==candidate_id]
    if cat.get('contract_version')!=CONTRACT or len(rows)!=1 or rows[0]['status']!='READY_FOR_REVIEW':
        raise CandidateError('RESOURCE_CANDIDATE_NOT_READY')
    return cat


async def preview(source,registry,candidate_id,transport,policy_client,history,*,now=time.time):
    cat=candidate(source,registry,candidate_id)
    policy=await policy_client.read()
    if cat['registry_sha256']!=policy.registry_sha256: raise CandidateError('WORKER_REGISTRY_MISMATCH')
    created=int(now())
    plan=ResourcePlan(plan_id='opplan_'+uuid.uuid4().hex,created_at=created,expires_at=created+300,
        candidate_id=candidate_id,source_sha256=cat['source_sha256'],registry_sha256=cat['registry_sha256'],
        worker_origin=policy_client.base_url,policy=policy,sequence=list(policy.sequence()),transport=transport,plan_sha256='0'*64)
    value=plan.model_dump(mode='json')
    value['plan_sha256']=plan_hash(value)
    plan=ResourcePlan.model_validate(value)
    history.issue(plan)
    return plan


def write_plan(plan,path):
    path=Path(path)
    if path.suffix!='.json' or path.exists() or path.with_suffix('.md').exists() or not path.parent.is_dir():
        raise CandidateError('NEW_OUTPUT_REQUIRED')
    with path.open('x',encoding='utf-8') as f: f.write(plan.model_dump_json(indent=2))
    with path.with_suffix('.md').open('x',encoding='utf-8') as f:
        f.write('# Operator resource preview\n\nNOT_EXECUTED; digest is identity, not a signature or human authentication.\n\n')
        f.write(f'Plan: {plan.plan_id}\n\nDigest: {plan.plan_sha256}\n\nProvider: mock; transport: {plan.transport}\n\n')
        f.write(f'Created/expires: {plan.created_at}/{plan.expires_at}; target: {plan.policy.origin}\n\n')
        f.write('Proof: worker-held high-entropy test values; only commitments and run digests are disclosed.\n\n')
        f.write('Expected target HTTP: 11; tools: 12. Preview: only authenticated worker policy lookup.\n\n')
        f.write('Worker scope: '+plan.policy.scope_policy.model_dump_json()+'\n\n')
        f.write('Accounts/resources: '+plan.policy.accounts.model_dump_json()+'\n\n')
        for i,step in enumerate(plan.sequence):
            routes=plan.policy.adapter.routes
            path=routes.login_path if step.operation=='login' else routes.me_path if step.operation=='identity' else routes.detail(step.resource_id)
            f.write(f'{i+1}. {step.account_ref}: {step.operation} {path}\n')


async def execute_plan(source,registry,plan,confirmation,policy_client,history,client_factory,report_root,
                       *,approval_actor,now=time.time,timeout=180):
    if approval_actor not in ('codex','human'): raise CandidateError('APPROVAL_ACTOR_REQUIRED')
    if confirmation!=plan.plan_sha256 or plan_hash(plan.model_dump(mode='json'))!=confirmation:
        raise CandidateError('PLAN_CONFIRMATION_MISMATCH')
    history.validate(plan)
    if not plan.created_at<=int(now())<plan.expires_at: raise CandidateError('PLAN_EXPIRED')
    if policy_client.base_url!=plan.worker_origin: raise CandidateError('WORKER_ORIGIN_CHANGED')
    cat=candidate(source,registry,plan.candidate_id)
    if (cat['source_sha256'],cat['registry_sha256'])!=(plan.source_sha256,plan.registry_sha256):
        raise CandidateError('PLAN_INPUT_CHANGED')
    policy=await policy_client.read()
    if policy!=plan.policy: raise CandidateError('WORKER_POLICY_CHANGED')
    if not plan.created_at<=int(now())<plan.expires_at: raise CandidateError('PLAN_EXPIRED')
    run_id='run_'+uuid.uuid4().hex
    history.claim(plan,run_id)
    folder=Path(report_root)/run_id
    folder.mkdir(parents=True,exist_ok=False)
    link={'schema_version':'operator-link-v1','run_id':run_id,'plan_id':plan.plan_id,'plan_sha256':confirmation,
        'candidate_id':plan.candidate_id,'source_sha256':plan.source_sha256,'registry_sha256':plan.registry_sha256,
        'approval_actor':approval_actor,'approval_identity_authenticated':False,
        'expected_scope_policy':policy.scope_policy.model_dump(mode='json'),'actual_scope_policy':None,
        'control_calls':{'preview_policy':1,'run_policy':1},'status':'INTERRUPTED','verdict':'INCONCLUSIVE'}
    (folder/'candidate_execution.json').write_text(json.dumps(link,indent=2),encoding='utf-8')
    (folder/'verification_contract.json').write_text(policy.model_dump_json(indent=2),encoding='utf-8')
    evidence=[]
    report={'schema_version':'operator-report-v1','run_id':run_id,'scenario_id':SCENARIO,'target_id':'lab-web',
        'provider_mode':'mock','tool_transport':plan.transport,'started_at':utc_now(),'status':'INTERRUPTED',
        'verdict':'INCONCLUSIVE','reason_code':'INCOMPLETE_WORKFLOW','verification_basis':'operator_http_observation',
        'scope_policy':None,'limits_used':{'http_requests':0,'tool_calls':0},'evidence_ids':[]}
    client=None
    try:
        client=client_factory(plan.transport)
        async with asyncio.timeout(timeout):
            async with client.session():
                for index,step in enumerate(policy.sequence()):
                    r=await client.step(run_id=run_id,target_id='lab-web',**step.model_dump(),
                        expected_snapshot_sha256=policy.scope_policy.snapshot_sha256,contract_version=CONTRACT)
                    report['limits_used']={'http_requests':r.request_count,'tool_calls':r.tool_count}
                    if r.scope_policy:
                        report['scope_policy']=r.scope_policy.model_dump(mode='json')
                        if r.scope_policy!=policy.scope_policy: raise CandidateError('WORKER_POLICY_CHANGED')
                    if r.evidence: evidence.append(r.evidence)
                    if not r.ok: raise CandidateError(r.error_code or 'WORKER_STEP_FAILED')
                    if r.run_id!=run_id or (r.request_count,r.tool_count)!=(index+1,index+1):
                        raise CandidateError('WORKER_USAGE_MISMATCH')
                r=await client.finish(run_id,policy.scope_policy.snapshot_sha256)
                report['limits_used']={'http_requests':r.request_count,'tool_calls':r.tool_count}
                if not r.ok: raise CandidateError(r.error_code or 'WORKER_FINISH_FAILED')
                if r.scope_policy!=policy.scope_policy: raise CandidateError('WORKER_POLICY_CHANGED')
                if r.run_id!=run_id or (r.request_count,r.tool_count)!=(11,12):
                    raise CandidateError('WORKER_USAGE_MISMATCH')
                report.update(verify_operator(evidence,policy,run_id=run_id),status='COMPLETED')
    except asyncio.CancelledError:
        report.update(status='CANCELLED',reason_code='RUN_CANCELLED')
    except TimeoutError:
        report.update(status='TIMED_OUT',reason_code='RUN_TIMED_OUT')
    except Exception as exc:
        report.update(status='FAILED',reason_code=str(exc) if isinstance(exc,CandidateError) else 'RUN_TRANSPORT_FAILED')
    finally:
        if client and report['status']!='COMPLETED':
            try:
                cancelled=await asyncio.wait_for(client.cancel(run_id),timeout=5)
                if cancelled.scope_policy==policy.scope_policy:
                    report['scope_policy']=cancelled.scope_policy.model_dump(mode='json')
                    report['limits_used']={'http_requests':cancelled.request_count,'tool_calls':cancelled.tool_count}
            except Exception: pass
        # Partial evidence never becomes a definitive verdict.
        report['finished_at']=utc_now()
        report['evidence_ids']=[e.evidence_id for e in evidence]
        report['warnings']=['Only the registered operator-prepared resources and this observation time. Local contract/evidence files are not signed.']
        link.update(status=report['status'],verdict=report['verdict'],actual_scope_policy=report['scope_policy'])
        for name,value in [('report.json',report),('evidence.json',[e.model_dump(mode='json') for e in evidence]),('candidate_execution.json',link)]:
            (folder/name).write_text(json.dumps(value,indent=2),encoding='utf-8')
        (folder/'report.md').write_text(f"# Operator resource run {run_id}\n\n{report['status']} / {report['verdict']}\n\nReason: {report['reason_code']}\n\nUsage: {report['limits_used']}\n\nEvidence: {len(evidence)}; operator_http_observation\n\nOperator-prepared test values, not general website detection. No raw credentials, proof values or response bodies.\n",encoding='utf-8')
    return report


def main():
    p=argparse.ArgumentParser(description='Versioned operator resource preview and explicitly confirmed mock run')
    p.add_argument('command',choices=['preview','run'])
    for arg in ('input','registry','env-file'): p.add_argument('--'+arg,required=True)
    p.add_argument('--candidate-id')
    p.add_argument('--transport',choices=['function','mcp'])
    p.add_argument('--output',type=Path)
    p.add_argument('--plan',type=Path)
    p.add_argument('--confirm-plan-sha256')
    p.add_argument('--approved-by',choices=['codex','human'])
    args=p.parse_args()
    try:
        from common.service_config import read_config,validate_config
        cfg=read_config('controller',Path(args.env_file))
        validate_config('controller',cfg)
        base=cfg.get('WORKER_URL','http://10.77.0.20:9000')
        pc=ResourcePolicyClient(base,cfg['WORKER_TOKEN'])
        history=ResourceHistory()
        if args.command=='preview':
            if not args.candidate_id or not args.transport or not args.output or args.plan or args.confirm_plan_sha256 or args.approved_by:
                raise CandidateError('PREVIEW_ARGUMENTS_REQUIRED')
            if args.output.exists() or args.output.with_suffix('.md').exists() or not args.output.parent.is_dir():
                raise CandidateError('NEW_OUTPUT_REQUIRED')
            plan=asyncio.run(preview(args.input,args.registry,args.candidate_id,args.transport,pc,history))
            write_plan(plan,args.output)
            print(plan.model_dump_json(indent=2))
        else:
            if not args.plan or not args.confirm_plan_sha256 or not args.approved_by or args.output or args.candidate_id or args.transport:
                raise CandidateError('RUN_CONFIRMATION_REQUIRED')
            plan=parse_plan(args.plan)
            report=asyncio.run(execute_plan(args.input,args.registry,plan,args.confirm_plan_sha256,pc,history,
                lambda t:ResourceClient(base,cfg['WORKER_TOKEN'],t),ROOT/'reports/runs',approval_actor=args.approved_by,
                timeout=float(cfg.get('CONTROLLER_RUN_TIMEOUT_SECONDS','180'))))
            print(json.dumps(report,indent=2))
            raise SystemExit(0 if report['status']=='COMPLETED' and report['verdict']!='INCONCLUSIVE' else 1)
    except Exception as exc:
        print(json.dumps({'ok':False,'reason_code':str(exc) if isinstance(exc,CandidateError) else 'OPERATOR_EXECUTION_INVALID'}))
        raise SystemExit(2) from None


if __name__=='__main__': main()
