"""Explicit workspace preservation for offline VM releases; no external paths."""
import hashlib
import json
from pathlib import Path
import re
import shutil


class WorkspaceDeploymentError(ValueError):
    pass


def require(value, code):
    if not value: raise WorkspaceDeploymentError(code)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local(path, root):
    root=Path(root).absolute()
    path=Path(path).absolute()
    require(path.is_relative_to(root), 'WORKSPACE_EXTERNAL_PATH_UNSUPPORTED')
    for item in (path,*path.parents):
        if item==root: break
        require(not item.is_symlink() and not getattr(item,'is_junction',lambda:False)(), 'WORKSPACE_LINK_UNSUPPORTED')
    resolved=path.resolve()
    require(resolved.is_relative_to(root.resolve()), 'WORKSPACE_EXTERNAL_PATH_UNSUPPORTED')
    require(not any(p in ('.git','.venv','node_modules') for p in resolved.relative_to(root.resolve()).parts), 'WORKSPACE_PATH_UNSUPPORTED')
    return resolved


def config_file(value, base, root):
    path=local(Path(value) if Path(value).is_absolute() else base/value,root)
    require(path.is_file() and path.suffix=='.json', 'WORKSPACE_CONFIG_FILE_REQUIRED')
    require(path.stat().st_size<=2*1024*1024, 'WORKSPACE_CONFIG_TOO_LARGE')
    return path


def unique(pairs):
    out={}
    for k,v in pairs:
        require(k not in out,'WORKSPACE_DUPLICATE_CONFIG_KEY')
        out[k]=v
    return out


def document(path):
    value=json.loads(path.read_text(encoding='utf-8'),object_pairs_hook=unique)
    require(isinstance(value,dict) and set(value)=={'schema_version','profiles'} and value['schema_version']=='operator-workspace-v1', 'WORKSPACE_CONFIG_INVALID')
    require(isinstance(value['profiles'],list) and 1<=len(value['profiles'])<=16,'WORKSPACE_CONFIG_INVALID')
    ids=set()
    for row in value['profiles']:
        require(isinstance(row,dict) and set(row)=={'profile_id','name','source_path','registry_path'},'WORKSPACE_PROFILE_INVALID')
        require(all(isinstance(v,str) and v for v in row.values()),'WORKSPACE_PROFILE_INVALID')
        require(bool(re.fullmatch('[a-z][a-z0-9-]{0,63}',row['profile_id'])) and row['profile_id'] not in ids,'WORKSPACE_PROFILE_INVALID')
        ids.add(row['profile_id'])
    return value


def state_hashes(root):
    root=Path(root)
    if not root.exists(): return {}
    local(root,root.parent)
    result={}
    for path in sorted(root.rglob('*')):
        rel=path.relative_to(root)
        if rel.parts[0] in ('.admission.lock','.deployment-fence.json'):
            require(len(rel.parts)==1,'WORKSPACE_CONTROL_PATH_INVALID')
            require(not path.is_symlink() and not getattr(path,'is_junction',lambda:False)(),'WORKSPACE_LINK_UNSUPPORTED')
            continue
        local(path,root)
        require(rel.parts[0] in ('plans','bindings','jobs'),'WORKSPACE_STATE_FILE_UNSUPPORTED')
        if path.is_dir():
            require(len(rel.parts)==1,'WORKSPACE_STATE_FILE_UNSUPPORTED')
            continue
        pattern=r'opplan_[0-9a-f]{32}\.(issued|claimed)\.json' if rel.parts[0]=='plans' else r'opplan_[0-9a-f]{32}\.json'
        require(len(rel.parts)==2 and bool(re.fullmatch(pattern,path.name)) and path.is_file(),'WORKSPACE_STATE_FILE_UNSUPPORTED')
        result[rel.as_posix()]=sha(path)
    return result


def snapshot(root, values):
    root=Path(root).resolve()
    configured=values.get('OPERATOR_WORKSPACE_CONFIG')
    if not configured:
        require(not values.get('OPERATOR_WORKSPACE_STATE_PATH'),'WORKSPACE_CONFIG_REQUIRED')
        return None
    config=config_file(configured,root,root)
    value=document(config)
    refs=[]
    for profile in value['profiles']:
        paths={k:config_file(profile[k],config.parent,root) for k in ('source_path','registry_path')}
        refs.append({'profile_id':profile['profile_id'],'references':{k:{'path':str(p),'sha256':sha(p)} for k,p in paths.items()}})
    raw=Path(values.get('OPERATOR_WORKSPACE_STATE_PATH') or 'data/operator_workspace')
    state=local(raw if raw.is_absolute() else root/raw,root)
    require(state!=root and state.is_relative_to(root/'data'),'WORKSPACE_STATE_MUST_BE_UNDER_DATA')
    require(not config.is_relative_to(state) and all(not Path(r['path']).is_relative_to(state) for row in refs for r in row['references'].values()),'WORKSPACE_CONFIG_STATE_OVERLAP')
    return {'config':str(config),'config_sha256':sha(config),'profiles':refs,'state':str(state),'state_hashes':state_hashes(state)}


def prepare(old, new, values, observed):
    if observed is None: return
    require(snapshot(old,values)==observed,'WORKSPACE_CHANGED_REPLAN_REQUIRED')
    destination=new/'runtime-config'/'operator-workspace'
    require(not destination.exists(),'WORKSPACE_DESTINATION_EXISTS')
    destination.mkdir(parents=True)
    config=document(Path(observed['config']))
    for profile,row in zip(config['profiles'],observed['profiles']):
        for key in ('source_path','registry_path'):
            name=profile['profile_id']+'-'+key+'.json'
            source=Path(row['references'][key]['path'])
            shutil.copyfile(source,destination/name)
            require(sha(destination/name)==row['references'][key]['sha256'],'WORKSPACE_COPY_MISMATCH')
            profile[key]=name  # Relative to this new configuration file, not cwd.
    derived=destination/'workspace.json'
    derived.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    derived.chmod(0o600)
    values['OPERATOR_WORKSPACE_CONFIG']=str(derived)
    values['OPERATOR_WORKSPACE_STATE_PATH']=str(new/Path(observed['state']).relative_to(old))


def preserve(old, new):
    if old is None: return
    require(new is not None and all(new['state_hashes'].get(k)==v for k,v in old['state_hashes'].items()),'WORKSPACE_HISTORY_LOST')


def rollback_safe(baseline, current):
    # Never merge new claims/receipts into old state, or revive old unused plans.
    expected=baseline['state_hashes'] if baseline else {}
    actual=current['state_hashes'] if current else {}
    require(all(expected.get(k)==v for k,v in actual.items()),'WORKSPACE_NEW_HISTORY_ROLLBACK_REFUSED')


def setup_identity(exchange):
    directory=Path(exchange)/'workspace-setup'
    if not directory.exists(): return {}
    local(directory,Path(exchange))
    files={}
    for p in directory.iterdir():
        local(p,directory)
        require(p.is_file() and p.name in ('settings.json','workspace.json','registry.json','openapi.json'),'WORKSPACE_SETUP_FILE_UNSUPPORTED')
        files[p.name]=sha(p)
    require('settings.json' in files,'WORKSPACE_SETUP_INVALID')
    return files


def setup(root,exchange,role,values):
    """Explicit separate setup for the already published fixed VM target only."""
    identity=setup_identity(exchange)
    if not identity: return role
    src=Path(exchange)/'workspace-setup'
    data=json.loads((src/'settings.json').read_text(),object_pairs_hook=unique)
    require(set(data)=={'schema','role','environment'} and data['schema']=='vm-operator-workspace-v1' and data['role']==role,'WORKSPACE_SETUP_INVALID')
    env=data['environment']
    require(isinstance(env,dict) and all(isinstance(v,str) and '\n' not in v and '\r' not in v for v in env.values()),'WORKSPACE_SETUP_INVALID')
    secret_keys={'LAB_USER_A_PASSWORD','LAB_USER_B_PASSWORD','OPERATOR_PROOF_A','OPERATOR_PROOF_B'}
    allowed={'controller':set(),'worker':secret_keys,'target':secret_keys|{'OPERATOR_TARGET_MODE'}}[role]
    require(set(env)==allowed,'WORKSPACE_SETUP_KEYS_INVALID')
    if role in ('controller','worker'):
        expected={'settings.json','registry.json'}|({'workspace.json','openapi.json'} if role=='controller' else set())
        require(set(identity)==expected,'WORKSPACE_SETUP_FILE_UNSUPPORTED')
        registry=json.loads((src/'registry.json').read_text())
        require(registry==json.loads((root/'config/targets.operator.json').read_text()),'WORKSPACE_SETUP_SCOPE_NOT_REGISTERED')
        dest=root/'runtime-config'/'workspace-setup'
        require(not dest.exists(),'WORKSPACE_SETUP_DESTINATION_EXISTS')
        dest.mkdir(parents=True)
        for name in expected-{'settings.json'}: shutil.copyfile(src/name,dest/name)
        if role=='controller':
            profile=document(dest/'workspace.json')
            require(len(profile['profiles'])==1 and profile['profiles'][0]['source_path']=='openapi.json' and profile['profiles'][0]['registry_path']=='registry.json','WORKSPACE_SETUP_INVALID')
            require(json.loads((src/'openapi.json').read_text())==json.loads((root/'examples/openapi/operator-cookie.json').read_text()),'WORKSPACE_SETUP_SPEC_NOT_REGISTERED')
            values['OPERATOR_WORKSPACE_CONFIG']=str(dest/'workspace.json')
            values.setdefault('OPERATOR_WORKSPACE_STATE_PATH',str(root/'data/operator_workspace'))
        else:
            require(values.get('TARGET_BASE_URL') in (None,'http://10.78.0.30:8080'),'WORKSPACE_SETUP_ORIGIN_CHANGED')
            values.update(env,TARGET_REGISTRY_PATH=str(dest/'registry.json'),HTTP_MAX_REQUESTS='11',AGENT_MAX_STEPS='12')
    else:
        require(set(identity)=={'settings.json'} and env.get('OPERATOR_TARGET_MODE') in ('vulnerable','fixed'),'WORKSPACE_SETUP_INVALID')
        values.clear();values.update(env)
    return 'operator-target' if role=='target' else role
