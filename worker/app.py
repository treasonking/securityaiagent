from __future__ import annotations

import hmac
import os
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Mount

from common.schemas import ToolResult
from worker.policy import TargetPolicy
from worker.registry import load_target_registry
from worker.service import ToolService, WorkerLimits


class StartSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    target_id: str
    account_ref: str


class ListDocumentsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str
    target_id: str
    session_ref: str


class FetchDocumentRequest(ListDocumentsRequest):
    document_id: str
    purpose: str


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: str


def _authorized(token: str, authorization: str | None) -> bool:
    expected = f"Bearer {token}"
    return bool(token and authorization and hmac.compare_digest(expected, authorization))


class MCPAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, *, token: str, allowed_clients: set[str]) -> None:
        super().__init__(app)
        self.token = token
        self.allowed_clients = allowed_clients

    async def dispatch(self, request: Request, call_next: Any):
        if request.url.path.startswith("/mcp") and not _authorized(self.token, request.headers.get("authorization")):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        if request.url.path.startswith("/mcp"):
            client_host = request.client.host if request.client else ""
            if client_host not in self.allowed_clients:
                return JSONResponse({"error": "controller address is not allowed"}, status_code=403)
        return await call_next(request)


def build_worker_app(
    service: ToolService,
    *,
    worker_token: str,
    allowed_clients: set[str] | None = None,
):
    if not worker_token:
        raise RuntimeError("WORKER_TOKEN must be configured")
    allowed = allowed_clients or {"127.0.0.1", "::1", "testclient"}
    api = FastAPI(title="SecurityLab worker", docs_url=None, redoc_url=None)

    async def authenticate(request: Request, authorization: str | None = Header(default=None)) -> None:
        client_host = request.client.host if request.client else ""
        if client_host not in allowed:
            raise HTTPException(status_code=403, detail="controller address is not allowed")
        if not _authorized(worker_token, authorization):
            raise HTTPException(status_code=401, detail="worker authentication required")

    @api.get("/health")
    async def health() -> dict[str, object]:
        return {"status": "ok", "phase": 1, "nmap": "not_implemented", "playwright": "not_implemented"}

    @api.post("/v1/tools/start-session", response_model=ToolResult, dependencies=[Depends(authenticate)])
    async def start_session(payload: StartSessionRequest) -> ToolResult:
        return await service.start_session(payload.run_id, payload.target_id, payload.account_ref)

    @api.post("/v1/tools/list-own-documents", response_model=ToolResult, dependencies=[Depends(authenticate)])
    async def list_own_documents(payload: ListDocumentsRequest) -> ToolResult:
        return await service.list_own_documents(payload.run_id, payload.target_id, payload.session_ref)

    @api.post("/v1/tools/fetch-document", response_model=ToolResult, dependencies=[Depends(authenticate)])
    async def fetch_document(payload: FetchDocumentRequest) -> ToolResult:
        return await service.fetch_document(
            payload.run_id,
            payload.target_id,
            payload.session_ref,
            payload.document_id,
            payload.purpose,
        )

    @api.post("/v1/tools/finish-run", response_model=ToolResult, dependencies=[Depends(authenticate)])
    async def finish_run(payload: RunRequest) -> ToolResult:
        return await service.finish_run(payload.run_id)

    @api.post("/v1/runs/cancel", response_model=ToolResult, dependencies=[Depends(authenticate)])
    async def cancel_run(payload: RunRequest) -> ToolResult:
        return await service.cancel_run(payload.run_id)

    mcp = FastMCP(
        "SecurityLab bounded worker",
        instructions="Only the published access-control tools are available. Never infer arbitrary URLs or commands.",
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
    )

    @mcp.tool()
    async def start_session(run_id: str, target_id: str, account_ref: str) -> dict[str, Any]:
        """Start one opaque synthetic-account session for a registered target."""
        return (await service.start_session(run_id, target_id, account_ref)).model_dump(mode="json")

    @mcp.tool()
    async def list_own_documents(run_id: str, target_id: str, session_ref: str) -> dict[str, Any]:
        """List only the authenticated synthetic account's document identifiers."""
        return (await service.list_own_documents(run_id, target_id, session_ref)).model_dump(mode="json")

    @mcp.tool()
    async def fetch_document(
        run_id: str,
        target_id: str,
        session_ref: str,
        document_id: str,
        purpose: str,
    ) -> dict[str, Any]:
        """Fetch one fixture-format document and return redacted evidence metadata."""
        return (
            await service.fetch_document(run_id, target_id, session_ref, document_id, purpose)
        ).model_dump(mode="json")

    @mcp.tool()
    async def finish_run(run_id: str) -> dict[str, Any]:
        """Seal the run and return bounded usage totals."""
        return (await service.finish_run(run_id)).model_dump(mode="json")

    app = mcp.streamable_http_app()
    app.routes.append(Mount("/", app=api))
    app.add_middleware(MCPAuthMiddleware, token=worker_token, allowed_clients=allowed)
    app.state.tool_service = service
    app.state.mcp = mcp
    return app


def create_app_from_env():
    token = os.getenv("WORKER_TOKEN", "")
    registry_path = os.getenv(
        "TARGET_REGISTRY_PATH",
        str(__import__("pathlib").Path(__file__).resolve().parents[1] / "config" / "targets.json"),
    )
    policies = load_target_registry(registry_path)
    target_url = os.getenv("TARGET_BASE_URL")
    if target_url:
        from urllib.parse import urlsplit

        parsed = urlsplit(target_url)
        policies["lab-web"] = TargetPolicy(
            target_id="lab-web",
            scheme=parsed.scheme,
            host=parsed.hostname or "",
            port=parsed.port or 80,
        )
    accounts = {
        "user-a": ("user_a", os.getenv("LAB_USER_A_PASSWORD") or "local-a-password"),
        "user-b": ("user_b", os.getenv("LAB_USER_B_PASSWORD") or "local-b-password"),
        "admin": ("admin", os.getenv("LAB_ADMIN_PASSWORD") or "local-admin-password"),
    }
    limits = WorkerLimits(
        max_requests=int(os.getenv("HTTP_MAX_REQUESTS", "30")),
        max_tool_calls=int(os.getenv("AGENT_MAX_STEPS", "12")),
        timeout_seconds=float(os.getenv("HTTP_TIMEOUT_SECONDS", "5")),
        run_timeout_seconds=float(os.getenv("RUN_TIMEOUT_SECONDS", "180")),
        max_response_bytes=int(os.getenv("HTTP_MAX_RESPONSE_BYTES", "65536")),
        requests_per_second=float(os.getenv("HTTP_REQUESTS_PER_SECOND", "2")),
        max_concurrency=int(os.getenv("HTTP_MAX_CONCURRENCY", "1")),
    )
    service = ToolService(policies=policies, accounts=accounts, limits=limits)
    allowed = {item.strip() for item in os.getenv("WORKER_ALLOWED_CLIENTS", "10.77.0.10,127.0.0.1,::1").split(",")}
    return build_worker_app(service, worker_token=token, allowed_clients=allowed)
