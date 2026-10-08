from __future__ import annotations

import asyncio
import hmac
import json
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from common.sanitize import redact_text
from common.schemas import Evidence, OfflineVerificationImport, RunReport, RunStatus, Verdict
from controller.auth import SessionSigner
from controller.engine import RunEngine
from controller.manager import ManagerSettings, RunManager
from controller.reporting import ReportWriter
from controller.repository import Repository
from controller.tool_clients import FunctionWorkerClient, MCPWorkerClient, ToolClient
from verifier.core import evidence_identity_digest


@dataclass(frozen=True)
class AppSettings:
    database_path: Path
    reports_path: Path
    session_secret: str
    access_token: str
    allowed_origins: frozenset[str]
    allowed_hosts: frozenset[str] = frozenset({"127.0.0.1", "localhost"})
    allowed_clients: frozenset[str] = frozenset({"127.0.0.1", "::1"})
    session_ttl_seconds: int = 3600
    secure_cookie: bool = False
    max_concurrency: int = 1
    run_timeout_seconds: float = 180.0
    model_id: str | None = None
    model_max_calls: int = 8
    openai_configured: bool = False
    offline_import_token: str | None = None


class SessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    access_token: str = Field(min_length=1, max_length=512)


class ConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(default="새 보안 검증", max_length=120)


class MessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=4000)
    scenario_id: Literal["access-control"] = "access-control"
    target_id: Literal["lab-web"] = "lab-web"
    provider: Literal["mock", "openai"] = "mock"
    tool_transport: Literal["function", "mcp"] = "function"


def create_app(
    *,
    settings: AppSettings,
    clients: dict[str, ToolClient],
    repository: Repository | None = None,
) -> FastAPI:
    repo = repository or Repository(settings.database_path)
    repo.interrupt_unfinished_runs()
    if len(settings.access_token) < 16:
        raise ValueError("APP_ACCESS_TOKEN must contain at least 16 characters")
    signer = SessionSigner(settings.session_secret, ttl_seconds=settings.session_ttl_seconds)
    manager = RunManager(
        repository=repo,
        engine=RunEngine(report_writer=ReportWriter(settings.reports_path)),
        clients=clients,
        settings=ManagerSettings(
            max_concurrency=settings.max_concurrency,
            model_id=settings.model_id,
            model_max_calls=settings.model_max_calls,
            run_timeout_seconds=settings.run_timeout_seconds,
        ),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        await manager.shutdown()

    app = FastAPI(title="SecurityLab controller", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=sorted(settings.allowed_hosts))
    app.state.repository = repo
    app.state.manager = manager

    @app.middleware("http")
    async def origin_guard(request: Request, call_next):
        client_host = request.client.host if request.client else ""
        if client_host not in settings.allowed_clients:
            return Response(status_code=403, content="client address rejected")
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not request.url.path.startswith(
            "/api/internal/"
        ):
            origin = request.headers.get("origin")
            if origin not in settings.allowed_origins:
                return Response(status_code=403, content="origin rejected")
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    async def owner(
        sl_session: str | None = Cookie(default=None),
    ) -> str:
        owner_id = signer.validate(sl_session)
        if owner_id is None:
            raise HTTPException(status_code=401, detail="local session required")
        return owner_id

    async def write_owner(
        sl_session: str | None = Cookie(default=None),
        x_csrf_token: str | None = Header(default=None),
    ) -> str:
        owner_id = signer.validate(sl_session)
        if owner_id is None:
            raise HTTPException(status_code=401, detail="local session required")
        if not signer.validate_csrf(sl_session or "", x_csrf_token):
            raise HTTPException(status_code=403, detail="CSRF validation failed")
        return owner_id

    @app.post("/api/session")
    async def create_session(payload: SessionRequest, response: Response) -> dict[str, str]:
        if not hmac.compare_digest(payload.access_token, settings.access_token):
            raise HTTPException(status_code=401, detail="invalid local access token")
        token = signer.issue()
        response.set_cookie(
            "sl_session",
            token,
            httponly=True,
            samesite="strict",
            secure=settings.secure_cookie,
            path="/",
            max_age=settings.session_ttl_seconds,
        )
        return {"csrf_token": signer.csrf(token), "mode": "local-single-user"}

    @app.get("/api/session")
    async def get_session(sl_session: str | None = Cookie(default=None), owner_id: str = Depends(owner)):
        return {"csrf_token": signer.csrf(sl_session or ""), "mode": "local-single-user", "owner": owner_id}

    @app.delete("/api/session")
    async def logout(
        response: Response,
        sl_session: str | None = Cookie(default=None),
        _owner_id: str = Depends(write_owner),
    ) -> dict[str, str]:
        signer.revoke(sl_session)
        response.delete_cookie("sl_session", path="/")
        return {"status": "logged_out"}

    @app.get("/api/health")
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "database_journal_mode": repo.journal_mode(),
            "transports": sorted(clients),
            "phase_2": {"nmap": "not_implemented", "playwright": "not_implemented"},
        }

    @app.get("/api/config")
    async def config(_owner_id: str = Depends(owner)) -> dict[str, object]:
        return {
            "workflow": "fixed-scenario-verifier-with-llm-candidate-generation",
            "providers": {
                "mock": {"configured": True, "verified": True},
                "openai": {"configured": settings.openai_configured, "verified": False},
            },
            "transports": sorted(clients),
        }

    @app.post("/api/internal/offline-verification")
    async def import_offline_verification(
        payload: OfflineVerificationImport,
        authorization: str | None = Header(default=None),
    ) -> dict[str, object]:
        expected = (
            f"Bearer {settings.offline_import_token}" if settings.offline_import_token else None
        )
        if not expected or not authorization or not hmac.compare_digest(expected, authorization):
            raise HTTPException(status_code=401, detail="offline verifier authentication required")
        run = repo.get_run_internal(payload.run_id)
        if run is None or run["status"] != RunStatus.COMPLETED or not run["report"]:
            raise HTTPException(status_code=409, detail="completed online run is required")
        evidence_items = [Evidence.model_validate(item) for item in repo.list_evidence(payload.run_id)]
        if payload.evidence_count != len(evidence_items):
            raise HTTPException(status_code=409, detail="evidence count mismatch")
        if payload.evidence_digest != evidence_identity_digest(evidence_items):
            raise HTTPException(status_code=409, detail="evidence identity digest mismatch")
        if payload.verdict != Verdict.INCONCLUSIVE and payload.correlated_count != len(evidence_items):
            raise HTTPException(status_code=409, detail="final verdict requires all evidence to correlate")
        evidence_ids = {item.evidence_id for item in evidence_items}
        if any(not set(item.evidence_ids).issubset(evidence_ids) for item in payload.verified_findings):
            raise HTTPException(status_code=409, detail="finding references unknown evidence")
        report = RunReport.model_validate(run["report"])
        report.verdict = payload.verdict
        report.verified_findings = payload.verified_findings
        report.warnings = list(dict.fromkeys(report.warnings + payload.warnings))
        report.environment["target_server_log"] = "offline-correlated"
        repo.update_run_report(payload.run_id, report)
        repo.save_findings(report)
        if payload.correlated_count == len(evidence_items):
            repo.mark_evidence_offline_correlated(payload.run_id)
            for item in evidence_items:
                item.server_observation = "target_log_correlated"
        ReportWriter(settings.reports_path).write(report, evidence_items)
        repo.append_event(
            payload.run_id,
            "offline_verification_imported",
            {"verdict": payload.verdict, "correlated_count": payload.correlated_count},
        )
        return {"run_id": payload.run_id, "verdict": payload.verdict, "imported": True}

    @app.post("/api/conversations")
    async def create_conversation(payload: ConversationRequest, owner_id: str = Depends(write_owner)):
        return repo.create_conversation(owner_id, payload.title)

    @app.get("/api/conversations")
    async def list_conversations(owner_id: str = Depends(owner)):
        return {"conversations": repo.list_conversations(owner_id)}

    @app.get("/api/conversations/{conversation_id}/messages")
    async def messages(conversation_id: str, owner_id: str = Depends(owner)):
        if not repo.conversation_owned(conversation_id, owner_id):
            raise HTTPException(status_code=404, detail="conversation not found")
        return {"messages": repo.list_messages(conversation_id)}

    @app.get("/api/conversations/{conversation_id}/runs")
    async def conversation_runs(conversation_id: str, owner_id: str = Depends(owner)):
        if not repo.conversation_owned(conversation_id, owner_id):
            raise HTTPException(status_code=404, detail="conversation not found")
        return {"runs": repo.list_runs(conversation_id, owner_id)}

    @app.post("/api/conversations/{conversation_id}/messages")
    async def submit_message(
        conversation_id: str,
        payload: MessageRequest,
        owner_id: str = Depends(write_owner),
    ):
        if not repo.conversation_owned(conversation_id, owner_id):
            raise HTTPException(status_code=404, detail="conversation not found")
        if payload.tool_transport not in clients:
            raise HTTPException(status_code=422, detail="requested tool transport is not configured")
        if payload.provider == "openai" and not settings.openai_configured:
            raise HTTPException(status_code=422, detail="OpenAI provider is not configured")
        repo.add_message(conversation_id, "user", redact_text(payload.message))
        run_id = repo.create_run(
            conversation_id=conversation_id,
            owner_id=owner_id,
            scenario_id=payload.scenario_id,
            target_id=payload.target_id,
            provider_mode=payload.provider,
            tool_transport=payload.tool_transport,
        )
        repo.add_message(conversation_id, "assistant", f"검증 작업 `{run_id}`을 대기열에 추가했습니다.")
        manager.submit(
            run_id=run_id,
            scenario_id=payload.scenario_id,
            target_id=payload.target_id,
            provider_mode=payload.provider,
            tool_transport=payload.tool_transport,
        )
        return {"run_id": run_id, "status": RunStatus.QUEUED}

    @app.get("/api/runs/{run_id}")
    async def get_run(run_id: str, owner_id: str = Depends(owner)):
        run = repo.get_run(run_id, owner_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return run

    @app.post("/api/runs/{run_id}/cancel")
    async def cancel_run(run_id: str, owner_id: str = Depends(write_owner)):
        run = repo.get_run(run_id, owner_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        if not repo.request_cancel(run_id, owner_id):
            raise HTTPException(status_code=409, detail="run is not cancellable")
        await manager.cancel(run_id, str(run["tool_transport"]))
        return {"run_id": run_id, "cancel_requested": True}

    @app.get("/api/runs/{run_id}/evidence")
    async def evidence(run_id: str, owner_id: str = Depends(owner)):
        if repo.get_run(run_id, owner_id) is None:
            raise HTTPException(status_code=404, detail="run not found")
        return {"evidence": repo.list_evidence(run_id)}

    @app.get("/api/runs/{run_id}/events")
    async def events(
        run_id: str,
        request: Request,
        owner_id: str = Depends(owner),
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ):
        if repo.get_run(run_id, owner_id) is None:
            raise HTTPException(status_code=404, detail="run not found")
        try:
            cursor = max(0, int(last_event_id or 0))
        except ValueError:
            cursor = 0

        async def stream():
            nonlocal cursor
            idle = 0
            while not await request.is_disconnected():
                batch = repo.list_events(run_id, cursor)
                for event in batch:
                    cursor = event["event_id"]
                    yield (
                        f"id: {cursor}\n"
                        f"event: {event['event_type']}\n"
                        f"data: {json.dumps(event['payload'], ensure_ascii=False)}\n\n"
                    )
                run = repo.get_run(run_id, owner_id)
                if run and run["status"] in {
                    RunStatus.COMPLETED,
                    RunStatus.CANCELLED,
                    RunStatus.TIMED_OUT,
                    RunStatus.FAILED,
                    RunStatus.INTERRUPTED,
                } and not repo.list_events(run_id, cursor):
                    break
                idle += 1
                if idle % 50 == 0:
                    yield ": keepalive\n\n"
                await asyncio.sleep(0.1)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/runs/{run_id}/event-log")
    async def event_log(run_id: str, owner_id: str = Depends(owner)):
        if repo.get_run(run_id, owner_id) is None:
            raise HTTPException(status_code=404, detail="run not found")
        return {"events": repo.list_events(run_id)}

    frontend_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
    return app


def create_app_from_env() -> FastAPI:
    root = Path(__file__).resolve().parents[1]

    def resolve_path(value: str, fallback: str) -> Path:
        path = Path(value or fallback)
        return path if path.is_absolute() else root / path

    token = os.getenv("WORKER_TOKEN", "")
    if not token:
        raise RuntimeError("WORKER_TOKEN must be configured before starting the controller")
    secret = os.getenv("APP_SESSION_SECRET", "")
    if len(secret) < 24:
        raise RuntimeError("APP_SESSION_SECRET must contain at least 24 characters")
    access_token = os.getenv("APP_ACCESS_TOKEN", "")
    if len(access_token) < 16:
        raise RuntimeError("APP_ACCESS_TOKEN must contain at least 16 characters")
    function_client = FunctionWorkerClient(base_url=os.getenv("WORKER_URL", "http://10.77.0.20:9000"), token=token)
    mcp_client = MCPWorkerClient(server_url=os.getenv("MCP_WORKER_URL", "http://10.77.0.20:9000/mcp"), token=token)
    settings = AppSettings(
        database_path=resolve_path(os.getenv("DATABASE_PATH", ""), "data/securitylab.sqlite3"),
        reports_path=root / "reports" / "runs",
        session_secret=secret,
        access_token=access_token,
        allowed_origins=frozenset(
            item.strip()
            for item in os.getenv("UI_ALLOWED_ORIGINS", "http://192.168.56.10:8000").split(",")
            if item.strip()
        ),
        allowed_hosts=frozenset(
            item.strip()
            for item in os.getenv(
                "UI_ALLOWED_HOSTS", "192.168.56.10,localhost,127.0.0.1"
            ).split(",")
            if item.strip()
        ),
        allowed_clients=frozenset(
            item.strip()
            for item in os.getenv(
                "CONTROLLER_ALLOWED_CLIENTS", "192.168.56.1,127.0.0.1,::1"
            ).split(",")
            if item.strip()
        ),
        session_ttl_seconds=int(os.getenv("APP_SESSION_TTL_SECONDS", "3600")),
        secure_cookie=os.getenv("APP_SECURE_COOKIE", "false").lower() == "true",
        max_concurrency=int(os.getenv("RUN_MAX_CONCURRENCY", "1")),
        run_timeout_seconds=float(os.getenv("CONTROLLER_RUN_TIMEOUT_SECONDS", "180")),
        model_id=os.getenv("OPENAI_MODEL") or None,
        model_max_calls=int(os.getenv("MODEL_MAX_CALLS", "8")),
        openai_configured=bool(os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_MODEL")),
        offline_import_token=os.getenv("OFFLINE_VERIFICATION_TOKEN") or None,
    )
    return create_app(settings=settings, clients={"function": function_client, "mcp": mcp_client})
