"""Structural OpenAPI support checks for an already registered operator resource flow."""
from common.operator_contract import CONTRACT, canonical, digest

ID_PATTERN = '^[A-Za-z0-9_-]{1,128}$'


def analyse_document(doc,raw,registry,target_id):
    from controller.candidates import (ImportFailure,LIMITS,METHODS,origin_check,auth_matches,
        anonymous_login_supported,parameters,supplied_inputs,response_schema,schema_type)
    profile,adapter=registry.profile(target_id),registry.adapter(target_id)
    paths=doc['paths']
    if sum(sum(m in METHODS for m in item) for item in paths.values() if isinstance(item,dict))>LIMITS['operations']:
        raise ImportFailure('OPERATION_LIMIT')
    reasons=[]
    def required(schema,selector,kind):
        for key in selector.split('.'):
            if not schema_type(schema,'object') or key not in schema.get('required',[]): return False
            schema=schema.get('properties',{}).get(key,{})
        # This importer does not claim support for arbitrary field constraints/compositions.
        return schema_type(schema,kind) and not any(k in schema for k in ('enum','const','pattern','format'))
    operations={}
    for name,path,method in [('login',adapter.routes.login_path,'post'),('me',adapter.routes.me_path,'get'),('resource',adapter.routes.detail_path,'get')]:
        item=paths.get(path,{})
        op=item.get(method,{})
        operations[name]=op
        if not op:
            reasons.append('REQUIRED_ROUTE_UNPROVEN')
            continue
        _,origin_error=origin_check(doc,item,op,registry.policies[target_id].base_url)
        if origin_error: reasons.append(origin_error)
        if name=='login':
            body=op.get('requestBody',{}).get('content',{}).get('application/json',{}).get('schema',{})
            if (not anonymous_login_supported(doc,op) or any(p.get('required') for p in parameters(item,op))
                    or set(body.get('required',[]))!={adapter.login_user_field,adapter.login_password_field}
                    or not all(required(body,k,'string') for k in (adapter.login_user_field,adapter.login_password_field))
                    or not schema_type(response_schema(op),'object')):
                reasons.append('LOGIN_CONTRACT_UNPROVEN')
            if adapter.auth_mode=='bearer' and not required(response_schema(op),adapter.token_field,'string'):
                reasons.append('TOKEN_SCHEMA_UNPROVEN')
            if adapter.auth_mode=='cookie' and not schema_type(op.get('responses',{}).get('200',{}).get('headers',{}).get('Set-Cookie',{}).get('schema',{}),'string'):
                reasons.append('COOKIE_SCHEMA_UNPROVEN')
        elif not auth_matches(doc,item,op,adapter) or not supplied_inputs(item,op):
            reasons.append('AUTH_OR_INPUT_UNPROVEN')
        if name=='me':
            if parameters(item,op) or not required(response_schema(op),adapter.principal_field,'string'):
                reasons.append('IDENTITY_SCHEMA_UNPROVEN')
        if name=='resource':
            params=parameters(item,op)
            if (len(params)!=1 or params[0].get('in')!='path' or params[0].get('name')!='resource_id'
                    or params[0].get('required') is not True or not schema_type(params[0].get('schema',{}),'string')
                    or params[0]['schema'].get('pattern')!=ID_PATTERN
                    or set(params[0]['schema'])-{'type','pattern','minLength','maxLength'}
                    or params[0]['schema'].get('minLength',1)!=1 or params[0]['schema'].get('maxLength',128)!=128):
                reasons.append('RESOURCE_PARAMETER_UNPROVEN')
            schema=response_schema(op)
            if (not all(required(schema,k,'string') for k in (adapter.resource_id_field,adapter.owner_field,adapter.proof_field))
                    or not required(schema,adapter.visibility_field,'boolean' if type(adapter.private_value) is bool else 'string')
                    or type(adapter.private_value) is not type(adapter.public_value)):
                reasons.append('RESOURCE_PROOF_SCHEMA_UNPROVEN')
            denial=op.get('responses',{}).get(str(adapter.denial_status),{}).get('content',{}).get('application/json',{}).get('schema',{})
            if not required(denial,adapter.denial_field,'string'):
                reasons.append('DENIAL_SCHEMA_UNPROVEN')
    candidate=dict(candidate_id=digest(canonical({'contract':CONTRACT,'target':target_id,'method':'GET','path':adapter.routes.detail_path})),
        method='GET',path_template=adapter.routes.detail_path,adapter_id=adapter.adapter_id,
        status='NEEDS_CONFIGURATION' if reasons else 'READY_FOR_REVIEW',
        reason_codes=sorted(set(reasons)) or ['REGISTERED_RESOURCE_FLOW_MATCH'],verification_status='NOT_EXECUTED')
    return dict(schema_version='operator-catalogue-v1',contract_version=CONTRACT,source_sha256=digest(raw),
        registry_sha256=registry.config_digest(target_id),target_id=target_id,network_requests=0,model_calls=0,
        candidates=[candidate],partial=False)
