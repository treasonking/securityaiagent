"""UI-only routes, protected by the Controller's existing owner/CSRF dependencies."""
from typing import Literal
from fastapi import APIRouter, Depends, Response
from pydantic import Field
from common.api_contract import FrozenModel
from controller.candidate_execution import CandidateError
from controller.workspace import WorkspaceError, diagnostic, safe_code


class PreviewRequest(FrozenModel):
    profile_id: str = Field(pattern=r'^[a-z][a-z0-9-]{0,63}$')
    transport: Literal['function','mcp']


class ExecuteRequest(FrozenModel):
    plan_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    confirmed: Literal[True]


class DraftConfirmation(FrozenModel):
    review_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    confirmed: Literal[True]


def attach_workspace(app,workspace,owner,write_owner):
    router=APIRouter(prefix='/api/operator',dependencies=[Depends(owner)])
    def require():
        if workspace is None: raise WorkspaceError('WORKSPACE_NOT_CONFIGURED',503)
        return workspace

    @app.exception_handler(WorkspaceError)
    async def workspace_error(_request,exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=exc.status,content={'detail':{'code':exc.code,'message':diagnostic(exc.code)}},headers={'Cache-Control':'no-store'})

    async def call(fn,*args):
        try: return await fn(*args)
        except WorkspaceError: raise
        except CandidateError as exc: raise WorkspaceError(safe_code(str(exc))) from None
        except Exception: raise WorkspaceError('WORKSPACE_OPERATION_FAILED') from None

    @router.get('/profiles')
    async def profiles():
        if workspace is None:
            return {'profiles':[],'configured':False,'message':diagnostic('WORKSPACE_NOT_CONFIGURED')}
        return await call(workspace.readiness)

    @router.post('/preview',dependencies=[Depends(write_owner)])
    async def make_preview(payload:PreviewRequest):
        return await call(require().make_preview,payload.profile_id,payload.transport)

    @router.get('/plans/{plan_id}')
    async def plan(plan_id:str):
        try: return require().plan_view(plan_id)
        except CandidateError as exc: raise WorkspaceError(safe_code(str(exc))) from None

    @router.post('/plans/{plan_id}/run',dependencies=[Depends(write_owner)],status_code=202)
    async def run(plan_id:str,payload:ExecuteRequest):
        return await call(require().submit,plan_id,payload.plan_sha256)

    @router.get('/jobs')
    async def jobs():
        return {'jobs':require().jobs()}

    @router.get('/runs')
    async def runs():
        return {'runs':require().runs()}

    @router.get('/runs/{run_id}')
    async def result(run_id:str):
        try: return require().run_view(run_id)
        except WorkspaceError: raise
        except Exception: raise WorkspaceError('RESULT_NOT_READY') from None

    @router.get('/runs/{run_id}/disclosure-draft')
    async def draft_preview(run_id: str):
        return require().disclosure_review(run_id)

    @router.post('/runs/{run_id}/disclosure-draft', dependencies=[Depends(write_owner)])
    async def draft_download(run_id: str, payload: DraftConfirmation):
        draft = require().disclosure_review(run_id, payload.review_digest)
        return Response(draft['markdown'], media_type='text/markdown; charset=utf-8',
                        headers={'Content-Disposition': f'attachment; filename="{run_id}-internal-draft.md"',
                                 'Cache-Control': 'no-store'})

    @router.get('/runs/{run_id}/download/{kind}')
    async def download(run_id:str,kind:Literal['markdown','json']):
        try:
            service=require()
            if kind=='markdown':
                content,media,suffix=service.markdown(run_id),'text/markdown; charset=utf-8','md'
            else:
                import json
                content,media,suffix=json.dumps(service.reproduction(run_id),ensure_ascii=False,indent=2),'application/json','json'
            return Response(content,media_type=media,headers={'Content-Disposition':f'attachment; filename="{run_id}-reproduction.{suffix}"','Cache-Control':'no-store'})
        except WorkspaceError: raise
        except Exception: raise WorkspaceError('RESULT_NOT_READY') from None

    app.include_router(router)
