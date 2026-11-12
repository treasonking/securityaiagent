"""Fixed operator read sequence using the existing bounded HTTP transport."""
import asyncio
import hmac
import re
import secrets
import time

import httpx

from common.api_contract import select
from common.operator_contract import CONTRACT, SCENARIO, ResourceEvidence, ResourceResult, ResourceStep, digest
from worker.scope import ScopeViolation
from worker.service import ToolService, _Session


class OperatorService(ToolService):
    def policy(self):
        return self.registry.snapshot('lab-web', SCENARIO, self.limits).policy

    def _result(self, state, **kwargs):
        return ResourceResult(ok=kwargs['ok'],run_id=state.run_id,scope_policy=state.scope.record(),
            request_count=state.request_count,tool_count=state.tool_count,
            evidence=kwargs.get('evidence'),error_code=kwargs.get('error_code'))

    def _error(self, run_id, exc):
        code = exc.code if isinstance(exc,ScopeViolation) else 'TRANSPORT_OR_RESPONSE_ERROR'
        state=self._runs.get(run_id)
        if state:
            state.failed=True
            state.ended_monotonic=state.ended_monotonic or time.monotonic()
            state.sessions.clear()
            return self._result(state,ok=False,error_code=code)
        return ResourceResult(ok=False,run_id=run_id,error_code=code)

    def _authorize_request(self,state,policy,operation,method,path,account_ref,session_ref,cookies,payload):
        if self.registry.snapshot(state.target_id,SCENARIO,self.limits).snapshot_sha256!=state.scope.snapshot_sha256:
            raise ScopeViolation('CANDIDATE_POLICY_CHANGED','worker policy changed before HTTP send')
        super()._authorize_request(state,policy,operation,method,path,account_ref,session_ref,cookies,payload)
        sequence=state.scope.policy.sequence()
        index=state.operator_index
        if index >= len(sequence):
            raise ScopeViolation('SCOPE_SEQUENCE_DENIED','read sequence completed')
        expected=sequence[index]
        if (account_ref,operation,method,path)!=(expected.account_ref,expected.operation,*state.scope.path(expected)):
            raise ScopeViolation('SCOPE_SEQUENCE_DENIED','request is out of order')

    async def operator_step(self,run_id,target_id,account_ref,operation,resource_id,
                            expected_snapshot_sha256,contract_version=CONTRACT):
        try:
            # Always compare the current frozen worker policy before creating a run or logging in.
            snapshot=self.registry.snapshot(target_id,SCENARIO,self.limits)
            if contract_version!=CONTRACT or expected_snapshot_sha256!=snapshot.snapshot_sha256:
                raise ScopeViolation('CANDIDATE_POLICY_CHANGED','resource contract/snapshot mismatch')
            if account_ref not in snapshot.accounts:
                raise ScopeViolation('SCOPE_ACCOUNT_DENIED','registered account required')
            try:
                step=ResourceStep(account_ref=account_ref,operation=operation,resource_id=resource_id)
            except ValueError:
                raise ScopeViolation('SCOPE_RESOURCE_DENIED','invalid resource step') from None
            state=await self._state(run_id,create=True,scope=snapshot,candidate_snapshot=expected_snapshot_sha256)
            if not hasattr(state,'operator_index'):
                state.operator_index=0
                state.operator_lock=asyncio.Lock()
            async with state.operator_lock:
                self._check_run(state)
                if state.operator_index>=11 or step!=snapshot.policy.sequence()[state.operator_index]:
                    raise ScopeViolation('SCOPE_SEQUENCE_DENIED','unregistered resource or read order')
                self._count_tool(state)
                adapter=snapshot.adapter
                method,path=snapshot.path(step)
                session_ref=None if operation=='login' else account_ref
                session=state.sessions.get(session_ref)
                response,request_id=await self._request(state,snapshot.target,operation=operation,method=method,path=path,
                    account_ref=account_ref,session_ref=session_ref,cookies=session.cookies if session else None,
                    json=adapter.login_payload(self.accounts[account_ref]) if operation=='login' else None)
                if operation=='login':
                    try:
                        payload=self._object(response)
                        token=response.cookies.get(adapter.cookie_name) if adapter.auth_mode=='cookie' else select(payload,adapter.token_field)
                        if response.status_code!=200 or not isinstance(token,str) or not re.fullmatch(r'[A-Za-z0-9._~-]{1,2048}',token):
                            raise ValueError()
                    except Exception:
                        raise ScopeViolation('AUTHENTICATION_FAILED','login was not established') from None
                    for existing in state.sessions.values():
                        old=existing.bearer if adapter.auth_mode=='bearer' else existing.cookies.get(adapter.cookie_name)
                        if hmac.compare_digest(token,old):
                            raise ScopeViolation('SESSION_NOT_INDEPENDENT','authentication sessions are not independent')
                    session=_Session(account_ref,httpx.Cookies({adapter.cookie_name:token}) if adapter.auth_mode=='cookie' else httpx.Cookies(),
                                     target_id,bearer=token if adapter.auth_mode=='bearer' else None)
                    session.binding=digest(secrets.token_bytes(32))
                    state.sessions[account_ref]=session
                    metadata={'response_kind':'login','reason_code':'LOGIN_ESTABLISHED'}
                else:
                    metadata=self._metadata(state,response,operation)
                item=ResourceEvidence(run_id=run_id,evidence_id=digest(secrets.token_bytes(32)),request_id=request_id,
                    snapshot_sha256=snapshot.snapshot_sha256,step_index=state.operator_index,account_ref=account_ref,
                    operation=operation,method=method,path=path,status_code=response.status_code,
                    session_binding=session.binding,**metadata)
                state.evidence.append(item)
                state.operator_index+=1
                return self._result(state,ok=True,evidence=item)
        except asyncio.CancelledError:
            state=self._runs.get(run_id)
            if state:
                state.cancelled=True
                state.cancel_event.set()
                state.sessions.clear()
                state.ended_monotonic=time.monotonic()
            raise
        except Exception as exc:
            return self._error(run_id,exc)

    @classmethod
    def _object(cls,response):
        if response.headers.get('content-type','').split(';')[0].strip().lower()!='application/json':
            raise ValueError('JSON required')
        return cls._json_object(response)

    def _metadata(self,state,response,operation):
        result={'response_kind':'unknown','reason_code':'RESPONSE_UNPROVEN'}
        try:
            payload=self._object(response)
        except (ValueError,UnicodeError,RecursionError):
            result['reason_code']='RESPONSE_SCHEMA_INVALID'
            return result
        policy=state.scope.policy
        adapter=policy.adapter
        refs=('user-a','user-b')
        if operation=='identity':
            principal=select(payload,adapter.principal_field)
            if response.status_code==200 and isinstance(principal,str):
                result['principal_ref']=next((a for a in refs if policy.accounts.account(a).principal_id==principal),None)
                if result['principal_ref']:
                    result.update(response_kind='identity',reason_code='IDENTITY_OBSERVED')
            return result
        proof=select(payload,adapter.proof_field)
        result['proof_present']=proof is not None
        if isinstance(proof,str):
            matched=next((a for a in refs if hmac.compare_digest(proof,self.registry.proof_values[a])),None)
            if matched:
                result['proof_ref']=matched
                result['proof_digest']=digest(b'operator-run-proof-v1\0'+state.run_id.encode()+b'\0'+proof.encode())
        denial=adapter.denial_value
        for key in reversed(adapter.denial_field.split('.')):
            denial={key:denial}
        if response.status_code==adapter.denial_status and payload==denial:
            result.update(response_kind='denied',reason_code='EXPLICIT_RESOURCE_DENIAL')
            return result
        rid,owner,visibility=(select(payload,k) for k in (adapter.resource_id_field,adapter.owner_field,adapter.visibility_field))
        result['resource_ref']=next((a for a in refs if isinstance(rid,str) and policy.accounts.account(a).resource_id==rid),None)
        result['owner_ref']=next((a for a in refs if isinstance(owner,str) and policy.accounts.account(a).principal_id==owner),None)
        if response.status_code==200 and type(visibility) is type(adapter.private_value) and visibility==adapter.private_value:
            result.update(response_kind='private_resource',reason_code='PRIVATE_RESOURCE_OBSERVED')
        return result

    async def operator_finish(self,run_id,expected_snapshot_sha256):
        state=self._runs.get(run_id)
        if (state is None or state.scope.snapshot_sha256!=expected_snapshot_sha256
                or self.policy().scope_policy.snapshot_sha256!=expected_snapshot_sha256
                or getattr(state,'operator_index',0)!=11):
            return self._error(run_id,ScopeViolation('INCOMPLETE_WORKFLOW','all registered steps are required'))
        async with state.operator_lock:
            return await super().finish_run(run_id)
