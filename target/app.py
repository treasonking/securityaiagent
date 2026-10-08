from __future__ import annotations

import os
from pathlib import Path

from fastapi import Cookie, FastAPI, Header, HTTPException, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict

from target.store import TargetStore


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    password: str


def create_app(store: TargetStore | None = None) -> FastAPI:
    default_database = Path(__file__).resolve().parents[1] / "data" / "target.sqlite3"
    target_store = store or TargetStore(
        Path(os.getenv("TARGET_DATABASE_PATH", str(default_database))),
        mode=os.getenv("TARGET_MODE", "vulnerable"),
        passwords={
            "user-a": os.getenv("LAB_USER_A_PASSWORD") or "local-a-password",
            "user-b": os.getenv("LAB_USER_B_PASSWORD") or "local-b-password",
            "admin": os.getenv("LAB_ADMIN_PASSWORD") or "local-admin-password",
        },
    )
    app = FastAPI(title="SecurityLab synthetic target", docs_url=None, redoc_url=None)
    app.state.store = target_store

    @app.middleware("http")
    async def no_store(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/", response_class=HTMLResponse)
    async def home() -> str:
        return """<!doctype html><html lang='ko'><meta charset='utf-8'>
        <title>합성 문서 업무 사이트</title><body><h1>합성 문서 업무 사이트</h1>
        <p>SecurityLab 로컬 실습 전용이며 실제 개인정보를 포함하지 않습니다.</p></body></html>"""

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "mode": target_store.mode, "data": "synthetic-only"}

    @app.post("/login")
    async def login(
        payload: LoginRequest,
        response: Response,
        x_securitylab_run: str = Header(default="untracked"),
        x_securitylab_request: str = Header(default="untracked"),
    ) -> dict[str, str]:
        authenticated = target_store.authenticate(payload.username, payload.password)
        status = 200 if authenticated else 401
        account = authenticated[1] if authenticated else None
        target_store.record_observation(
            run_id=x_securitylab_run,
            request_id=x_securitylab_request,
            method="POST",
            path="/login",
            status_code=status,
            account_id=account.account_id if account else None,
        )
        if authenticated is None:
            raise HTTPException(status_code=401, detail="invalid synthetic account")
        token, account = authenticated
        response.set_cookie("lab_session", token, httponly=True, samesite="strict", secure=False, max_age=900)
        response.headers["X-SecurityLab-Mode"] = target_store.mode
        return {"status": "authenticated", "role": account.role}

    @app.get("/documents")
    async def list_documents(
        lab_session: str | None = Cookie(default=None),
        x_securitylab_run: str = Header(default="untracked"),
        x_securitylab_request: str = Header(default="untracked"),
    ) -> dict[str, object]:
        account = target_store.account_for_session(lab_session)
        status = 200 if account else 401
        target_store.record_observation(
            run_id=x_securitylab_run,
            request_id=x_securitylab_request,
            method="GET",
            path="/documents",
            status_code=status,
            account_id=account.account_id if account else None,
        )
        if account is None:
            raise HTTPException(status_code=401, detail="session missing or expired")
        return {"documents": target_store.list_documents(account)}

    @app.get("/documents/{document_id}")
    async def fetch_document(
        document_id: str,
        lab_session: str | None = Cookie(default=None),
        x_securitylab_run: str = Header(default="untracked"),
        x_securitylab_request: str = Header(default="untracked"),
    ) -> Response:
        account = target_store.account_for_session(lab_session)
        if account is None:
            target_store.record_observation(
                run_id=x_securitylab_run,
                request_id=x_securitylab_request,
                method="GET",
                path=f"/documents/{document_id}",
                status_code=401,
                account_id=None,
            )
            raise HTTPException(status_code=401, detail="session missing or expired")
        status, document = target_store.fetch_document(account, document_id)
        marker = document["marker"] if document else None
        target_store.record_observation(
            run_id=x_securitylab_run,
            request_id=x_securitylab_request,
            method="GET",
            path=f"/documents/{document_id}",
            status_code=status,
            account_id=account.account_id,
            marker=marker,
        )
        if document is None:
            raise HTTPException(status_code=status, detail="document not found")
        from fastapi.responses import JSONResponse

        return JSONResponse(document, status_code=status)

    @app.post("/logout")
    async def logout(response: Response, lab_session: str | None = Cookie(default=None)) -> dict[str, str]:
        target_store.destroy_session(lab_session)
        response.delete_cookie("lab_session")
        return {"status": "logged_out"}

    return app


app = create_app()
