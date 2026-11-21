"""Repeatable local UI/API validation; no VM, external DNS, new target or model tool."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import time
from datetime import datetime,timezone
import httpx

from scripts.run_independent_api_validation import publication_check,write_json
from validation.local_https import restrict_directory
from validation.operator_workspace import workspace_lab


def authenticated(lab):
    client=httpx.Client(base_url=lab['origin'],trust_env=False,timeout=20,headers={'Origin':lab['origin']})
    response=client.post('/api/session',json={'access_token':lab['access_token']})
    response.raise_for_status();client.headers['X-CSRF-Token']=response.json()['csrf_token']
    return client


def api_flow(lab,public):
    with_authenticated=authenticated(lab)
    try:
        c=with_authenticated
        ready=c.get('/api/operator/profiles');ready.raise_for_status()
        assert lab['api'].received==0 and ready.json()['profiles'][0]['ready']
        write_json(public/'readiness.json',ready.json())
        rows=[]
        for transport,vulnerable,expected in [('function',True,'VULNERABLE'),('mcp',False,'BLOCKED_BY_ACCESS_CONTROL')]:
            lab['api'].vulnerable=vulnerable
            before=lab['api'].received
            response=c.post('/api/operator/preview',json={'profile_id':'attachments','transport':transport});response.raise_for_status()
            plan=response.json();assert lab['api'].received==before
            result=c.post('/api/operator/plans/'+plan['plan_id']+'/run',json={'plan_sha256':plan['plan_sha256'],'confirmed':True});result.raise_for_status()
            deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                job=c.get('/api/operator/plans/'+plan['plan_id']).json()['job']
                if job['status'] not in ('QUEUED','RUNNING'):break
                time.sleep(.05)
            assert job['status']=='COMPLETED'
            observed=c.get('/api/operator/runs/'+job['run_id']).json()
            assert observed['verdict']==expected and observed['replay']['verdict_matches'] and lab['api'].received-before==11
            rows.append(dict(transport=transport,expected=expected,actual=observed['verdict'],target_http=lab['api'].received-before,run_id=job['run_id'],plan_id=plan['plan_id'],digest=plan['plan_sha256']))
            write_json(public/(transport+'-plan.json'),plan)
        write_json(public/'api_flow.json',{'passed':True,'rows':rows,'connections':'Controller/Worker/Target real loopback TCP; Target TLS; injected DNS'})
    finally:with_authenticated.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--browser',action='store_true')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    restrict_directory(args.output)
    public=args.output/'public';public.mkdir()
    trace=[]
    with tempfile.TemporaryDirectory(prefix='securityai-workspace-') as temporary:
        with workspace_lab(Path(temporary)) as lab:
            started=datetime.now(timezone.utc).isoformat()
            if args.browser:
                # Private handoff file, never served or copied into public evidence.
                write_json(args.output/'ready.json',{'origin':lab['origin'],'test_access_token':lab['access_token']})
                print('LOCAL_BROWSER_READY',flush=True)
                command=args.output/'command.json'
                while True:
                    if command.exists():
                        value=json.loads(command.read_text())
                        command.unlink()
                        action=value.get('action')
                        before=lab['api'].received
                        if action=='fixed':lab['api'].vulnerable=False
                        elif action=='policy_change':lab['change_policy']()
                        elif action=='sync_profile':lab['sync_profile']()
                        elif action not in ('measure','stop'):raise ValueError('unknown test-only control')
                        row=dict(action=action,http_before=before,http_after=lab['api'].received,network=dict(lab['counts']),jobs=lab['workspace'].jobs())
                        trace.append(row);write_json(args.output/'measurement.json',row)
                        if action=='stop':break
                    time.sleep(.1)
            else:api_flow(lab,public)
            workspace=lab['workspace']
            for run in workspace.runs():
                folder=public/run['run_id'];folder.mkdir()
                write_json(folder/'result.json',workspace.run_view(run['run_id']))
                write_json(folder/'reproduction.json',workspace.reproduction(run['run_id']))
                (folder/'reproduction.md').write_text(workspace.markdown(run['run_id']),encoding='utf-8')
            sources=[Path('controller/workspace.py'),Path('controller/workspace_api.py'),Path('controller/operator_execution.py'),
                     Path('controller/api.py'),Path('frontend/src/OperatorWorkspace.tsx'),Path('frontend/src/operator-api.ts')]
            write_json(public/'execution.json',dict(started_at_utc=started,provider='mock',browser_session=args.browser,
                trace=trace,jobs=workspace.jobs(),target_http=lab['api'].received,network=dict(lab['counts']),
                version=workspace.version,source_sha256={p.as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
                tls_certificate=lab['certificate'],resolver='injected-test-answers',secrets_in_verifier=False))
            values=[*lab['private_values'],*lab['api'].secret_values]
            write_json(public/'publication_check.json',publication_check(public,values))
            publication_check(public,values)
        # All listeners, temporary DB and ephemeral key material are now closed/removed.
    if (args.output/'ready.json').exists():(args.output/'ready.json').unlink()
    write_json(public/'cleanup.json',{'temporary_runtime_removed':not Path(temporary).exists(),'ready_token_file_removed':not (args.output/'ready.json').exists()})
    print('VALIDATION_EXPORTED',flush=True)


if __name__=='__main__':main()
