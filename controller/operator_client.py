"""Operator-only function/MCP transport. No tools are passed to a model."""
from contextlib import asynccontextmanager
import json
import httpx
from common.operator_contract import ResourcePolicy, ResourceResult
from controller.candidate_execution import CandidateError
from controller.candidates import unique,fail_constant
from controller.tool_clients import MCPWorkerClient


class ResourcePolicyClient:
    def __init__(self,base_url,token,*,transport=None):
        self.base_url,self.token,self.transport=base_url,token,transport
    async def read(self):
        try:
            async with httpx.AsyncClient(base_url=self.base_url,headers={'Authorization':'Bearer '+self.token},
                    trust_env=False,follow_redirects=False,timeout=10,transport=self.transport) as client:
                async with client.stream('GET','/v1/operator/resource-policy') as response:
                    if response.status_code!=200: raise CandidateError('RESOURCE_POLICY_UNAVAILABLE')
                    body=bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body)>32768: raise CandidateError('RESOURCE_POLICY_INVALID')
            return ResourcePolicy.model_validate(json.loads(body,object_pairs_hook=unique,parse_constant=fail_constant))
        except CandidateError: raise
        except Exception: raise CandidateError('RESOURCE_POLICY_INVALID') from None


class _ResourceMCP(MCPWorkerClient):
    @staticmethod
    def _decode_result(result):
        structured=getattr(result,'structuredContent',None) or getattr(result,'structured_content',None)
        if isinstance(structured,dict):
            if set(structured)=={'result'}: structured=structured['result']
            return ResourceResult.model_validate(structured)
        for part in getattr(result,'content',[]):
            if getattr(part,'text',None): return ResourceResult.model_validate_json(part.text)
        raise ValueError('missing operator result')


class ResourceClient:
    def __init__(self,base_url,token,transport_name,*,transport=None):
        if transport_name not in ('function','mcp'): raise ValueError('invalid transport')
        self.base_url,self.token,self.transport_name,self.transport=base_url,token,transport_name,transport
        self.mcp=_ResourceMCP(server_url=base_url+'/mcp',token=token) if transport_name=='mcp' else None
        if self.mcp:
            # No tool retries: each resource tool consumes a single fixed sequence step.
            self.mcp._server.max_retry_attempts=0
    @asynccontextmanager
    async def session(self):
        if self.mcp:
            async with self.mcp.session(): yield
        else: yield
    async def post(self,path,payload):
        async with httpx.AsyncClient(base_url=self.base_url,headers={'Authorization':'Bearer '+self.token},
                trust_env=False,follow_redirects=False,timeout=10,transport=self.transport) as client:
            r=await client.post(path,json=payload)
        r.raise_for_status()
        return ResourceResult.model_validate(r.json())
    async def step(self,**payload):
        return (await self.mcp._call('operator_resource_step',payload)) if self.mcp else await self.post('/v1/operator/resource-step',payload)
    async def finish(self,run_id,snapshot):
        payload={'run_id':run_id,'expected_snapshot_sha256':snapshot}
        return (await self.mcp._call('operator_resource_finish',payload)) if self.mcp else await self.post('/v1/operator/resource-finish',payload)
    async def cancel(self,run_id):
        return await self.post('/v1/runs/cancel',{'run_id':run_id})
