"""Second local synthetic API: bearer sessions and nested records, same fixture store."""
from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from target.store import TargetStore


class SignIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    login_name: str
    passphrase: str


def create_records_app(store: TargetStore) -> FastAPI:
    app = FastAPI(title="SecurityLab synthetic records API", docs_url=None, redoc_url=None)
    app.state.store = store

    def response(body, status, account=None):
        headers = {"Cache-Control": "no-store"}
        if account is not None:
            headers["X-Lab-Principal"] = account.account_id
        return JSONResponse(body, status_code=status, headers=headers)

    def account_for(header):
        return store.account_for_session(header[7:]) if header and header.startswith("Bearer ") else None

    @app.get("/health")
    async def health():
        return {"status": "ok", "mode": store.mode, "api": "records", "data": "synthetic-only"}

    @app.post("/api/session")
    async def login(payload: SignIn):
        authenticated = store.authenticate(payload.login_name, payload.passphrase)
        if authenticated is None:
            return response({"error": {"code": "authentication_failed"}}, 401)
        token, _ = authenticated
        return response({"session": {"access_token": token}}, 200)

    @app.get("/api/me/records")
    async def mine(authorization: str | None = Header(default=None)):
        account = account_for(authorization)
        if account is None:
            return response({"error": {"code": "authentication_failed"}}, 401)
        items = [{"key": item["document_id"], "owner": {"key": item["owner_id"]}}
                 for item in store.list_documents(account)]
        return response({"principal": {"key": account.account_id}, "data": {"items": items}}, 200, account)

    @app.get("/api/records/{document_id}")
    async def detail(document_id: str, authorization: str | None = Header(default=None)):
        account = account_for(authorization)
        if account is None:
            return response({"error": {"code": "authentication_failed"}}, 401)
        status, item = store.fetch_document(account, document_id)
        if item is None:
            return response({"error": {"code": "record_unavailable"}}, status, account)
        return response({"record": {"key": item["document_id"], "owner": {"key": item["owner_id"]},
                                    "shared": item["visibility"] != "private",
                                    "content": {"type": "lab-private", "text": item["canary"]["value"]}}},
                        status, account)

    return app
