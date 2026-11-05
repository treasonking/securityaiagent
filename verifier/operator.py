"""Replay only versioned redacted evidence and the stored worker contract."""
import argparse
import json
from pathlib import Path
from common.operator_contract import ResourcePolicy, ResourceEvidence


def verify_operator(evidence,policy,*,run_id):
    def result(verdict='INCONCLUSIVE',reason='INCOMPLETE_WORKFLOW'):
        return {'verdict':verdict,'reason_code':reason}
    if len(evidence)!=11: return result()
    if len({e.evidence_id for e in evidence})!=11 or len({e.request_id for e in evidence})!=11:
        return result(reason='DUPLICATE_EVIDENCE_IDENTITY')
    bindings={}
    for index,(e,step) in enumerate(zip(evidence,policy.sequence())):
        route=policy.adapter.routes
        method,path=(('POST',route.login_path) if step.operation=='login' else ('GET',route.me_path) if step.operation=='identity' else ('GET',route.detail(step.resource_id)))
        if (e.run_id!=run_id or e.snapshot_sha256!=policy.scope_policy.snapshot_sha256 or e.step_index!=index
                or (e.account_ref,e.operation,e.method,e.path)!=(step.account_ref,step.operation,method,path)):
            return result(reason='EVIDENCE_CONTRACT_MISMATCH')
        bindings.setdefault(e.account_ref,e.session_binding)
        if e.session_binding!=bindings[e.account_ref]: return result(reason='SESSION_BINDING_CHANGED')
    if bindings['user-a']==bindings['user-b']: return result(reason='SESSION_NOT_INDEPENDENT')
    for index in (0,1):
        if evidence[index].status_code!=200 or evidence[index].response_kind!='login':
            return result(reason='AUTHENTICATION_UNPROVEN')
    for index in (2,3,9,10):
        e=evidence[index]
        if e.status_code!=200 or e.response_kind!='identity' or e.principal_ref!=e.account_ref:
            return result(reason='IDENTITY_UNPROVEN')
    def private(e,owner):
        return (e.status_code==200 and e.response_kind=='private_resource' and e.owner_ref==owner
                and e.resource_ref==owner and e.proof_ref==owner and e.proof_present and bool(e.proof_digest))
    for i,owner in ((4,'user-a'),(5,'user-b'),(7,'user-b'),(8,'user-a')):
        if not private(evidence[i],owner): return result(reason='OWNER_RESOURCE_PROOF_UNPROVEN')
    a,b=evidence[4].proof_digest,evidence[5].proof_digest
    if a==b or evidence[8].proof_digest!=a or evidence[7].proof_digest!=b:
        return result(reason='PROOF_NOT_STABLE_OR_DISTINCT')
    cross=evidence[6]
    if private(cross,'user-b') and cross.proof_digest==b:
        return result('VULNERABLE','CROSS_ACCOUNT_PRIVATE_PROOF')
    if (cross.response_kind=='denied' and cross.status_code==policy.adapter.denial_status
            and not cross.proof_present and cross.proof_digest is None and cross.proof_ref is None
            and cross.resource_ref is None and cross.owner_ref is None):
        return result('BLOCKED_BY_ACCESS_CONTROL','EXPLICIT_DENIAL_WITH_STABLE_CONTROLS')
    return result(reason='CROSS_RESPONSE_UNPROVEN')


def replay(directory):
    from controller.candidates import unique, fail_constant, read_local
    def read(name): return json.loads(read_local(Path(directory)/name),object_pairs_hook=unique,parse_constant=fail_constant)
    report=read('report.json')
    if report.get('schema_version')!='operator-report-v1': raise ValueError('unsupported report contract')
    policy=ResourcePolicy.model_validate(read('verification_contract.json'))
    evidence=[ResourceEvidence.model_validate(e) for e in read('evidence.json')]
    result=verify_operator(evidence,policy,run_id=report['run_id'])
    # A transport failure/cancellation after the last HTTP response still lacks
    # a successful worker finish. Stored partial runs cannot gain a verdict.
    if report.get('status')!='COMPLETED':
        result={'verdict':'INCONCLUSIVE','reason_code':'INCOMPLETE_WORKFLOW'}
    elif (report.get('scope_policy')!=policy.scope_policy.model_dump(mode='json')
          or report.get('limits_used')!={'http_requests':11,'tool_calls':12}
          or report.get('evidence_ids')!=[e.evidence_id for e in evidence]):
        result={'verdict':'INCONCLUSIVE','reason_code':'REPORT_CONTRACT_MISMATCH'}
    return {**result,'run_id':report['run_id'],'verdict_matches':result['verdict']==report['verdict'],'evidence_count':len(evidence)}


def main():
    parser=argparse.ArgumentParser(description='Replay operator-resource-v1 evidence; never target DB/logs')
    parser.add_argument('--run-dir',required=True,type=Path)
    args=parser.parse_args()
    try:
        value=replay(args.run_dir)
        print(json.dumps(value,indent=2))
        raise SystemExit(0 if value['verdict_matches'] else 1)
    except (ValueError,OSError):
        print(json.dumps({'verdict':'INCONCLUSIVE','reason_code':'REPLAY_INPUT_INVALID'}))
        raise SystemExit(2) from None


if __name__=='__main__': main()
