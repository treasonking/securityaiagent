"""Only the resource worker exposes resource tools; v1 tools remain unchanged."""
from fastapi import FastAPI, Depends, Header, HTTPException, Request
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.routing import Mount
from common.api_contract import FrozenModel
from common.operator_contract import ResourceResult, ResourcePolicy, CONTRACT


class StepRequest(FrozenModel):
    run_id: str
    target_id: str
    account_ref: str
    operation: str
    resource_id: str | None
    expected_snapshot_sha256: str
    contract_version: str = CONTRACT


class FinishRequest(FrozenModel):
    run_id: str
    expected_snapshot_sha256: str


class CancelRequest(FrozenModel):
    run_id: str


def build_operator_app(service,*,worker_token,allowed_clients=None,allowed_mcp_hosts=None,allowed_mcp_origins=None):
    from worker.app import MCPAuthMiddleware, _authorized
    if not worker_token: raise RuntimeError('WORKER_TOKEN required')
    allowed=allowed_clients or {'127.0.0.1','::1','testclient'}
    api=FastAPI(docs_url=None,redoc_url=None)
    async def auth(request:Request,authorization:str|None=Header(default=None)):
        if not request.client or request.client.host not in allowed:
            raise HTTPException(403,'controller address is not allowed')
        if not _authorized(worker_token,authorization): raise HTTPException(401,'authentication required')
    @api.get('/health')
    async def health(): return {'status':'ok','scenario':'operator-resource-http'}
    @api.get('/v1/operator/resource-policy',dependencies=[Depends(auth)],response_model=ResourcePolicy)
    async def policy(): return service.policy()
    @api.post('/v1/operator/resource-step',dependencies=[Depends(auth)],response_model=ResourceResult)
    async def step(payload:StepRequest): return await service.operator_step(**payload.model_dump())
    @api.post('/v1/operator/resource-finish',dependencies=[Depends(auth)],response_model=ResourceResult)
    async def finish(payload:FinishRequest): return await service.operator_finish(**payload.model_dump())
    @api.post('/v1/runs/cancel',dependencies=[Depends(auth)],response_model=ResourceResult)
    async def cancel(payload:CancelRequest): return await service.cancel_run(payload.run_id)
    mcp=FastMCP('Operator registered resource worker',streamable_http_path='/mcp',json_response=True,stateless_http=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True,
          allowed_hosts=sorted(allowed_mcp_hosts or {'127.0.0.1:*','localhost:*','[::1]:*','testserver'}),
          allowed_origins=sorted(allowed_mcp_origins or set())))
    @mcp.tool()
    async def operator_resource_step(run_id:str,target_id:str,account_ref:str,operation:str,resource_id:str|None,
                                     expected_snapshot_sha256:str,contract_version:str=CONTRACT):
        """Perform only the next operator-registered step; no discovery or URL inputs."""
        return (await service.operator_step(run_id,target_id,account_ref,operation,resource_id,expected_snapshot_sha256,contract_version)).model_dump(mode='json')
    @mcp.tool()
    async def operator_resource_finish(run_id:str,expected_snapshot_sha256:str):
        """Seal the complete registered workflow."""
        return (await service.operator_finish(run_id,expected_snapshot_sha256)).model_dump(mode='json')
    app=mcp.streamable_http_app()
    app.routes.append(Mount('/',app=api))
    app.add_middleware(MCPAuthMiddleware,token=worker_token,allowed_clients=allowed)
    app.state.tool_service=service
    app.state.mcp=mcp
    return app
