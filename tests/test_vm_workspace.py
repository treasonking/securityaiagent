import json
from pathlib import Path
import shutil
import pytest

from common.workspace_lifecycle import admission,fence,idle,WorkspaceBusy
from scripts import vm_workspace as ws
from scripts.vm_deploy import VM,DeployError,digest,write


def prepared(root):
    (root/'config/nested').mkdir(parents=True)
    (root/'config/api.json').write_text('{"openapi":"test"}')
    (root/'config/registry.json').write_text('{"registered":true}')
    value={'schema_version':'operator-workspace-v1','profiles':[{'profile_id':'prepared','name':'Prepared',
        'source_path':'../api.json','registry_path':'../registry.json'}]}
    (root/'config/nested/workspace.json').write_text(json.dumps(value))
    state=root/'data/my-workspace'
    for folder in ('plans','bindings','jobs'):(state/folder).mkdir(parents=True)
    identifier='opplan_'+'1'*32
    for name in (identifier+'.issued.json',identifier+'.claimed.json'):(state/'plans'/name).write_text('{"consumed":true}')
    (state/'bindings'/(identifier+'.json')).write_text('{"profile_id":"prepared"}')
    (state/'jobs'/(identifier+'.json')).write_text('{"status":"COMPLETED"}')
    return {'OPERATOR_WORKSPACE_CONFIG':'config/nested/workspace.json','OPERATOR_WORKSPACE_STATE_PATH':'data/my-workspace'}


def test_workspace_paths_relinked_without_copying_unlisted_files(tmp_path):
    old,new=tmp_path/'old',tmp_path/'new';new.mkdir()
    values=prepared(old);before=ws.snapshot(old,values)
    original={p:p.read_bytes() for p in old.rglob('*') if p.is_file()}
    (old/'config/unlisted.json').write_text('do not copy')
    ws.prepare(old,new,values,before)
    actual=ws.snapshot(new,values)
    assert actual['state']==str(new/'data/my-workspace')
    assert not (new/'runtime-config/operator-workspace/unlisted.json').exists()
    for profile in actual['profiles']:
        for reference in profile['references'].values():assert Path(reference['path']).is_relative_to(new)
    assert all(p.read_bytes()==b for p,b in original.items())
    shutil.copytree(old/'data',new/'data')
    ws.preserve(before,ws.snapshot(new,values))


@pytest.mark.parametrize('changed',['config/nested/workspace.json','config/api.json','config/registry.json'])
def test_workspace_reference_drift_rejected_before_staging(tmp_path,changed):
    old,new=tmp_path/'old',tmp_path/'new';new.mkdir()
    values=prepared(old);before=ws.snapshot(old,values)
    with (old/changed).open('a') as f:f.write(' ')
    with pytest.raises(ws.WorkspaceDeploymentError,match='CHANGED_REPLAN'):ws.prepare(old,new,values,before)
    assert not (new/'runtime-config').exists()


def test_external_and_link_references_are_not_followed(tmp_path,monkeypatch):
    old=tmp_path/'old';values=prepared(old)
    outside=tmp_path/'outside.json';outside.write_text('{}')
    values['OPERATOR_WORKSPACE_CONFIG']=str(outside)
    with pytest.raises(ws.WorkspaceDeploymentError,match='EXTERNAL'):ws.snapshot(old,values)
    values['OPERATOR_WORKSPACE_CONFIG']='config/nested/workspace.json'
    monkeypatch.setattr(Path,'is_junction',lambda p:p.name=='api.json')
    with pytest.raises(ws.WorkspaceDeploymentError,match='LINK'):ws.snapshot(old,values)


def test_unconfigured_legacy_and_unsupported_state_paths(tmp_path):
    assert ws.snapshot(tmp_path,{}) is None
    values=prepared(tmp_path/'old');values['OPERATOR_WORKSPACE_STATE_PATH']='reports/runs'
    with pytest.raises(ws.WorkspaceDeploymentError,match='UNDER_DATA'):ws.snapshot(tmp_path/'old',values)


def test_consumed_plans_survive_copy_and_new_claim_refuses_rollback(tmp_path):
    old,new=tmp_path/'old',tmp_path/'new';new.mkdir()
    values=prepared(old);baseline=ws.snapshot(old,values)
    ws.prepare(old,new,values,baseline);shutil.copytree(old/'data',new/'data')
    copied=ws.snapshot(new,values);ws.preserve(baseline,copied);ws.rollback_safe(baseline,copied)
    claim=new/'data/my-workspace/plans'/('opplan_'+'2'*32+'.claimed.json')
    claim.write_text('{"consumed":true}')
    with pytest.raises(ws.WorkspaceDeploymentError,match='ROLLBACK_REFUSED'):ws.rollback_safe(baseline,ws.snapshot(new,values))
    assert claim.exists() and ws.snapshot(old,prepared_values())==baseline


def prepared_values():
    return {'OPERATOR_WORKSPACE_CONFIG':'config/nested/workspace.json','OPERATOR_WORKSPACE_STATE_PATH':'data/my-workspace'}


def test_new_receipts_and_preview_bindings_also_refuse_rollback(tmp_path):
    root=tmp_path/'state';(root/'bindings').mkdir(parents=True)
    (root/'bindings'/('opplan_'+'3'*32+'.json')).write_text('{}')
    with pytest.raises(ws.WorkspaceDeploymentError,match='ROLLBACK_REFUSED'):
        ws.rollback_safe(None,{'state_hashes':ws.state_hashes(root)})


def test_admission_fence_never_interrupts_existing_run_and_blocks_new_submissions(tmp_path):
    jobs=tmp_path/'jobs';jobs.mkdir();job=jobs/('opplan_'+'4'*32+'.json')
    job.write_text('{"status":"RUNNING"}')
    with pytest.raises(WorkspaceBusy,match='RUN_IN_PROGRESS'):
        with fence(tmp_path,'deployment'):pytest.fail('must not proceed')
    assert not (tmp_path/'.deployment-fence.json').exists()
    job.write_text('{"status":"COMPLETED"}')
    before=ws.state_hashes(tmp_path)
    with fence(tmp_path,'deployment'):
        with pytest.raises(WorkspaceBusy,match='MAINTENANCE'):
            with admission(tmp_path):pytest.fail('must not submit')
        assert ws.state_hashes(tmp_path)==before
    with admission(tmp_path):pass


def test_crash_lock_is_not_automatically_removed(tmp_path):
    (tmp_path/'.admission.lock').mkdir()
    with pytest.raises(WorkspaceBusy,match='BUSY'):
        with fence(tmp_path,'deployment'):pass
    assert (tmp_path/'.admission.lock').exists()


def test_setup_identity_captures_secret_settings_without_publishing_values(tmp_path):
    source=tmp_path/'workspace-setup';source.mkdir()
    secret='unique-secret-never-publish'
    path=source/'settings.json';path.write_text(json.dumps({'secret':secret}))
    first=ws.setup_identity(tmp_path)
    assert secret not in json.dumps(first)
    path.write_text('{"changed":true}')
    assert ws.setup_identity(tmp_path)!=first


def test_backup_preserves_workspace_claims_receipts_and_reports(tmp_path):
    vm=VM('controller',tmp_path)
    values=prepared(vm.original)
    new=vm.releases/('5'*32);new.mkdir(parents=True)
    env=vm.original/'.env.controller';env.write_text('\n'.join(k+'='+v for k,v in values.items()))
    observed=ws.snapshot(vm.original,values)
    ws.prepare(vm.original,new,values,observed)
    (new/'.env.controller').write_text('\n'.join(k+'='+v for k,v in values.items()))
    report=vm.original/'reports/runs/run_example';report.mkdir(parents=True);(report/'report.json').write_text('{"old":true}')
    plan={'id':'5'*32,'checkout':str(new),'before':{'checkout':str(vm.original),'environment_reference':str(env),'workspace':observed}}
    vm.cmd=lambda *a,**k:''
    vm.backup_copy(plan)
    assert ws.snapshot(new,values)['state_hashes']==observed['state_hashes']
    assert (new/'reports/runs/run_example/report.json').read_bytes()==(report/'report.json').read_bytes()


@pytest.mark.parametrize('role',['controller','worker','target'])
def test_fixed_registered_workspace_setup_preserves_unrelated_environment(tmp_path,role):
    root=tmp_path/'release';source=tmp_path/'exchange/workspace-setup';source.mkdir(parents=True)
    (root/'config').mkdir(parents=True);(root/'examples/openapi').mkdir(parents=True)
    shutil.copyfile('config/targets.operator.json',root/'config/targets.operator.json')
    shutil.copyfile('examples/openapi/operator-cookie.json',root/'examples/openapi/operator-cookie.json')
    env={} if role=='controller' else {k:'synthetic-secret-'+k for k in ('LAB_USER_A_PASSWORD','LAB_USER_B_PASSWORD','OPERATOR_PROOF_A','OPERATOR_PROOF_B')}
    if role=='target':env['OPERATOR_TARGET_MODE']='fixed'
    (source/'settings.json').write_text(json.dumps({'schema':'vm-operator-workspace-v1','role':role,'environment':env}))
    if role!='target':shutil.copyfile('config/targets.operator.json',source/'registry.json')
    if role=='controller':
        shutil.copyfile('examples/openapi/operator-cookie.json',source/'openapi.json')
        (source/'workspace.json').write_text(json.dumps({'schema_version':'operator-workspace-v1','profiles':[{'profile_id':'prepared','name':'Prepared','source_path':'openapi.json','registry_path':'registry.json'}]}))
    values={'WORKER_TOKEN':'keep-original','APP_ACCESS_TOKEN':'keep-original-ui'} if role=='controller' else {'WORKER_TOKEN':'keep-original'}
    service=ws.setup(root,source.parent,role,values)
    if role=='target':assert service=='operator-target' and values==env
    else:assert values['WORKER_TOKEN']=='keep-original'
    if role=='controller':
        assert values['APP_ACCESS_TOKEN']=='keep-original-ui'
        assert ws.snapshot(root,values)['state']==str(root/'data/operator_workspace')
    if role=='worker':
        policy=json.loads((source/'registry.json').read_text());policy['targets']['lab-web']['base_url']='http://unapproved.test'
        (source/'registry.json').write_text(json.dumps(policy))
        with pytest.raises(ws.WorkspaceDeploymentError,match='NOT_REGISTERED'):ws.setup(root,source.parent,role,values)


def test_host_preparation_is_explicit_single_use_and_fixed_switch_keeps_secrets(tmp_path):
    from scripts.vm_deploy_host import prepare_workspace
    first=prepare_workspace(tmp_path)
    secret=json.loads((tmp_path/'private-workspace-secrets.json').read_text())
    with pytest.raises(DeployError,match='ALREADY_PREPARED'):prepare_workspace(tmp_path)
    fixed=prepare_workspace(tmp_path,True)
    target=json.loads((tmp_path/'target/workspace-setup/settings.json').read_text())
    assert target['environment']==dict(secret,OPERATOR_TARGET_MODE='fixed')
    assert not any(value in json.dumps([first,fixed]) for value in secret.values())
