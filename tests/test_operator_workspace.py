import asyncio
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import time

import httpx
import pytest

from controller.workspace import Workspace,WorkspaceError,checked
from scripts.run_independent_api_validation import publication_check
from validation.operator_workspace import workspace_lab


def login(lab):
    c=httpx.Client(base_url=lab['origin'],trust_env=False,headers={'Origin':lab['origin']},timeout=20)
    r=c.post('/api/session',json={'access_token':lab['access_token']});assert r.status_code==200
    c.headers['X-CSRF-Token']=r.json()['csrf_token']
    return c


def preview(c,transport='function'):
    r=c.post('/api/operator/preview',json={'profile_id':'attachments','transport':transport})
    assert r.status_code==200,r.text
    return r.json()


def submit(c,p):
    return c.post('/api/operator/plans/'+p['plan_id']+'/run',json={'plan_sha256':p['plan_sha256'],'confirmed':True})


def wait(c,p):
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        r=c.get('/api/operator/plans/'+p['plan_id']);assert r.status_code==200
        job=r.json()['job']
        if job and job['status'] not in ('RUNNING','QUEUED'):return job
        time.sleep(.05)
    raise AssertionError('workspace job did not finish')


@pytest.fixture
def lab(tmp_path):
    with workspace_lab(tmp_path/'lab') as value: yield value


def test_ui_api_existing_executor_real_tcp_function_mcp_and_downloads(lab,tmp_path):
    c=login(lab)
    profiles=c.get('/api/operator/profiles').json()
    assert profiles['profiles'][0]['ready'] and lab['api'].received==0
    assert profiles['profiles'][0]['policy']['scope_policy']['domain']['hostname']=='attachments.securityai.test'
    public=[]
    for transport,vulnerable,verdict in [('function',True,'VULNERABLE'),('mcp',False,'BLOCKED_BY_ACCESS_CONTROL')]:
        lab['api'].vulnerable=vulnerable
        before=lab['api'].received
        p=preview(c,transport)
        assert lab['api'].received==before and len(p['sequence'])==11 and p['job'] is None
        assert submit(c,p).status_code==202
        job=wait(c,p);assert job['status']=='COMPLETED'
        r=c.get('/api/operator/runs/'+job['run_id']);assert r.status_code==200
        data=r.json()
        assert data['verdict']==verdict and data['replay']['verdict_matches'] and lab['api'].received-before==11
        assert data['usage']=={'http_requests':11,'tool_calls':12} and len(data['evidence'])==11
        run=lab['workspace'].reports/job['run_id']
        before_hash={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in run.iterdir()}
        for kind in ('markdown','json'):
            download=c.get(f"/api/operator/runs/{job['run_id']}/download/{kind}")
            assert download.status_code==200 and 'attachment;' in download.headers['content-disposition']
            assert job['run_id'] in download.text and data['evidence'][6]['evidence_id'] in download.text
            assert '<ACCOUNT_A_PASSWORD>' in download.text
            public.append(download.text)
        assert before_hash=={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in run.iterdir()}
        assert submit(c,p).status_code==409 and lab['api'].received-before==11
        # New browser/client session restores persisted submissions and stored results.
        with closing(login(lab)) as restored:
            assert restored.get('/api/operator/plans/'+p['plan_id']).json()['job']['run_id']==job['run_id']
            assert restored.get('/api/operator/runs/'+job['run_id']).json()['verdict']==verdict
    dump=tmp_path/'public';dump.mkdir()
    (dump/'api.json').write_text(json.dumps([profiles,*public]),encoding='utf-8')
    publication_check(dump,[*lab['private_values'],*lab['api'].secret_values])
    assert 'password_env' not in json.dumps(profiles) and 'proof_commitments' not in json.dumps(profiles)
    c.close()


def test_auth_csrf_origin_allowlists_and_override_rejection(lab):
    with httpx.Client(base_url=lab['origin'],trust_env=False) as anon:
        for path in ('profiles','jobs','runs','plans/opplan_'+'0'*32,'runs/run_'+'0'*32+'/download/json'):
            assert anon.get('/api/operator/'+path).status_code==401
        anon.cookies.set('sl_session','bad')
        assert anon.get('/api/operator/profiles').status_code==401
    c=login(lab)
    args={'profile_id':'attachments','transport':'function'}
    assert c.post('/api/operator/preview',json=args,headers={'X-CSRF-Token':''}).status_code==403
    assert c.post('/api/operator/preview',json=args,headers={'Origin':'http://unapproved.test'}).status_code==403
    assert c.get('/api/operator/profiles',headers={'Host':'unapproved.test'}).status_code==400
    for key,val in [('origin','https://unapproved.test:443'),('max_requests',999),('ca_bundle','secret.pem'),('accounts',{}),('provider','openai'),('allowed_ip_ranges',['0.0.0.0/0'])]:
        assert c.post('/api/operator/preview',json={**args,key:val}).status_code==422
    p=preview(c)
    assert c.post('/api/operator/plans/'+p['plan_id']+'/run',json={
        'plan_sha256':p['plan_sha256'],'confirmed':True,'origin':'https://unapproved.test:443'}).status_code==422
    for payload in ({'plan_sha256':'0'*64,'confirmed':True},{'plan_sha256':p['plan_sha256'],'confirmed':False}):
        assert c.post('/api/operator/plans/'+p['plan_id']+'/run',json=payload).status_code in (409,422)
    assert lab['api'].received==0
    c.close()


def test_concurrent_submission_and_lost_response_never_reexecute(lab):
    c=login(lab);p=preview(c)
    with ThreadPoolExecutor(max_workers=6) as pool:
        codes=list(pool.map(lambda _:submit(c,p).status_code,range(6)))
    assert codes.count(202)==1 and codes.count(409)==5
    # Discard every POST body: recovering needs only the known preview ID.
    job=wait(c,p)
    assert job['run_id'] and lab['api'].received==11
    assert submit(c,p).status_code==409 and lab['api'].received==11
    assert len(list((lab['workspace'].root/'plans').glob('*.claimed.json')))==1
    c.close()


def test_policy_change_rejected_before_claim_or_target(lab):
    c=login(lab);p=preview(c)
    lab['change_policy']()
    response=submit(c,p)
    assert response.status_code==409 and response.json()['detail']['code']=='WORKER_POLICY_CHANGED'
    assert lab['api'].received==0 and not list((lab['workspace'].root/'jobs').glob('*.json'))
    lab['sync_profile']()
    fresh=preview(c)
    assert fresh['plan_sha256']!=p['plan_sha256'] and lab['api'].received==0
    c.close()


def test_expired_and_changed_saved_plans_are_rejected(lab,monkeypatch):
    import controller.operator_execution as execution
    c=login(lab);p=preview(c)
    # Use the shared preflight's injectable clock, not a UI bypass of plan validation.
    ws=lab['workspace'];profile,plan=ws.plan(p['plan_id'])
    with pytest.raises(Exception,match='PLAN_EXPIRED'):
        asyncio.run(execution.validate_execution(profile.source_path,profile.registry_path,plan,plan.plan_sha256,ws.pc,ws.history,approval_actor='human',now=lambda:plan.expires_at))
    saved=ws.root/'plans'/(p['plan_id']+'.issued.json')
    value=json.loads(saved.read_text());value['created_at']-=301;value['expires_at']-=301
    # A changed plan with unchanged digest is rejected by the shared executor.
    saved.write_text(json.dumps(value),encoding='utf-8')
    assert submit(c,p).status_code==409 and lab['api'].received==0
    from controller.candidate_execution import plan_hash
    value['plan_sha256']=plan_hash(value)
    saved.write_text(json.dumps(value),encoding='utf-8')
    p['plan_sha256']=value['plan_sha256']
    expired=submit(c,p)
    assert expired.status_code==409 and expired.json()['detail']['code']=='PLAN_EXPIRED'
    c.close()


def test_invalid_ids_paths_and_fixed_download_allowlist(lab):
    c=login(lab)
    for value in ('wrong','..','%2e%2e%2fsecret','run_'+'0'*32+'%2f..%2fsecret'):
        assert c.get('/api/operator/runs/'+value).status_code in (404,422)
        assert c.get('/api/operator/plans/'+value).status_code in (404,422)
    assert c.get('/api/operator/runs/run_'+'0'*32+'/download/private.pem').status_code==422
    assert c.get('/api/operator/runs/run_'+'0'*32+'/download/json').status_code==404
    with pytest.raises(WorkspaceError):checked(lab['workspace'].root,'../outside')
    c.close()


def test_unfinished_receipt_restart_is_interrupted_not_requeued(lab):
    from controller.workspace import write_json
    ws=lab['workspace'];c=login(lab);p=preview(c)
    write_json(ws.root/'jobs'/(p['plan_id']+'.json'),dict(plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],profile_id='attachments',status='RUNNING',run_id=None,version=ws.version))
    replacement=Workspace(profiles=ws.profiles,state_path=ws.root,reports_path=ws.reports,policy_client=ws.pc,client_factory=ws.factory)
    assert replacement.job(p['plan_id'])['status']=='INTERRUPTED'
    assert not replacement.tasks and lab['api'].received==0
    assert submit(c,p).status_code==409
    c.close()


def test_old_cli_report_load_and_derived_report_without_mutation(lab):
    baseline=Path('reports/independent_api_validation_20261113')
    row=next(r for r in json.loads((baseline/'matrix.json').read_text())['cases'] if r['run_id'])
    source=baseline/row['path']/'runs'/row['run_id']
    destination=lab['workspace'].reports/row['run_id']
    shutil.copytree(source,destination)
    before={p.name:p.read_bytes() for p in destination.iterdir()}
    with closing(login(lab)) as c:
        r=c.get('/api/operator/runs/'+row['run_id'])
        assert r.status_code==200 and r.json()['version']['commit']=='not-recorded'
        assert c.get('/api/operator/runs/'+row['run_id']+'/download/json').status_code==200
    assert before=={p.name:p.read_bytes() for p in destination.iterdir()}


def test_temporary_runtime_can_be_removed_after_shutdown(tmp_path):
    root=tmp_path/'disposable-runtime'
    with workspace_lab(root) as local:
        with closing(login(local)) as c:
            assert c.get('/api/operator/profiles').status_code==200
        assert local['api'].received==0
    shutil.rmtree(root)
    assert not root.exists()


def test_deployment_fence_blocks_preview_and_run_without_target_requests(lab):
    from common.workspace_lifecycle import fence
    with closing(login(lab)) as c:
        p=preview(c)
        with fence(lab['workspace'].root,'deployment-test'):
            assert c.post('/api/operator/preview',json={'profile_id':'attachments','transport':'function'}).status_code==409
            response=submit(c,p)
            assert response.status_code==409 and response.json()['detail']['code']=='WORKSPACE_MAINTENANCE'
            assert lab['api'].received==0
            assert c.get('/api/operator/plans/'+p['plan_id']).json()['job'] is None
        assert submit(c,p).status_code==202
        assert wait(c,p)['status']=='COMPLETED'


def test_server_only_profile_config_and_symlink_containment(tmp_path,monkeypatch):
    from controller.workspace import load_profiles
    path=tmp_path/'workspace.json'
    profile={'profile_id':'attachments','name':'attachments','source_path':'openapi.json','registry_path':'registry.json'}
    path.write_text(json.dumps({'schema_version':'operator-workspace-v1','profiles':[profile]}))
    assert load_profiles(path)['attachments'].source_path==str((tmp_path/'openapi.json').resolve())
    path.write_text(json.dumps({'schema_version':'operator-workspace-v1','profiles':[profile,profile]}))
    with pytest.raises(ValueError,match='duplicate'):load_profiles(path)
    # Emulate a link even on Windows hosts that deny symlink creation.
    monkeypatch.setattr(Path,'is_symlink',lambda p:p.name=='linked')
    with pytest.raises(WorkspaceError):checked(tmp_path,'linked','report.json')
