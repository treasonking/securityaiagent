import asyncio
import json
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from common.api_contract import ApiAdapter, HttpRoutes
from controller.engine import EngineRequest, RunEngine
from controller.providers import MockModelProvider
from controller.reporting import ReportWriter
from controller.tool_clients import DirectToolClient
from target.app import create_app
from target.store import TargetStore
from worker.limits import WorkerLimits
from worker.policy import TargetPolicy
from worker.registry import load_scope_registry
from worker.scope import ScopeViolation
from worker.service import ToolService


def setup_api(tmp_path, style, mode="vulnerable", change=None):
    filename = "targets.json" if style == "documents" else "targets.records.json"
    payload = json.loads((Path("config") / filename).read_text(encoding="utf-8"))
    target = payload["targets"]["lab-web"]
    target["profile"]["limits"]["requests_per_second"] = 10000.0
    if change:
        change(target)
    path = tmp_path / "scope.json"
    path.write_text(json.dumps(payload))
    registry = load_scope_registry(path)
    store = TargetStore(tmp_path / "target.sqlite3", mode=mode)
    service = ToolService(registry=registry, limits=WorkerLimits(requests_per_second=0),
        accounts=registry.credentials({"LAB_USER_A_PASSWORD": "local-a-password", "LAB_USER_B_PASSWORD": "local-b-password", "LAB_ADMIN_PASSWORD": "local-admin-password"}),
        transport=httpx.ASGITransport(app=create_app(store, api_style=style)),
        observation_reader=lambda _: pytest.fail("HTTP must not read target logs"))
    return service, path


def execute(tmp_path, service):
    events = []
    async def emit(event, payload):
        events.append((event, payload))
    report = asyncio.run(RunEngine(report_writer=ReportWriter(tmp_path / "reports")).execute(
        EngineRequest("adapter-test", "access-control-http", "lab-web"), provider=MockModelProvider(),
        client=DirectToolClient(service), cancel_event=asyncio.Event(), emit=emit))
    return report, events


class Intercept(httpx.AsyncBaseTransport):
    def __init__(self, wrapped, mutate):
        self.wrapped, self.mutate, self.requests = wrapped, mutate, []

    async def handle_async_request(self, request):
        self.requests.append(request)
        response = await self.wrapped.handle_async_request(request)
        await response.aread()
        return self.mutate(request, response, len(self.requests))


def put(payload, selector, value):
    keys = selector.split(".")
    for key in keys[:-1]:
        payload = payload[key]
    payload[keys[-1]] = value


@pytest.mark.parametrize("style", ["documents", "records"])
@pytest.mark.parametrize("mode,expected", [("vulnerable", "VULNERABLE"), ("fixed", "BLOCKED_BY_ACCESS_CONTROL")])
def test_both_adapters_use_same_engine_and_keep_secrets_local(tmp_path, style, mode, expected):
    service, _ = setup_api(tmp_path, style, mode)
    interceptor = Intercept(service.transport, lambda req, response, count: response)
    service.transport = interceptor
    report, events = execute(tmp_path, service)
    assert report.verdict == expected and len(report.evidence_ids) == 7
    assert report.limits_used == {"http_requests": 9, "tool_calls": 10}
    saved = report.model_dump_json() + json.dumps(events)
    requests = interceptor.requests
    assert json.loads(requests[0].content) == service.registry.adapter("lab-web").login_payload(service.accounts["user-a"])
    assert all(req.url.host == "10.78.0.30" for req in requests)
    for request in requests[2:]:
        auth = request.headers.get("Authorization") if style == "records" else request.headers.get("cookie")
        assert auth and auth not in saved
        raw_secret = auth.removeprefix("Bearer ") if style == "records" else auth.split("=", 1)[1]
        assert raw_secret not in saved
        assert ("cookie" in request.headers) == (style == "documents")
    for secret in ("local-a-password", "local-b-password", "Synthetic content", "Ignore prior instructions", "SYN-"):
        assert secret not in saved


@pytest.mark.parametrize("style", ["documents", "records"])
@pytest.mark.parametrize("case", ["public-own", "public-cross", "missing-id", "auth-failed", "wrong-list", "wrong-detail", "duplicate-json", "generic-denial", "login-html", "identity-missing"])
def test_ambiguous_or_failed_http_never_proves_vulnerability(tmp_path, style, case):
    service, _ = setup_api(tmp_path, style)
    adapter = service.registry.adapter("lab-web")
    if case == "auth-failed":
        service.accounts["user-a"] = (service.accounts["user-a"][0], "wrong-password")
    def mutate(request, response, count):
        if (case == "public-own" and count == 5) or (case == "public-cross" and count == 7):
            payload = response.json()
            put(payload, adapter.visibility_field, adapter.public_value)
            return httpx.Response(200, json=payload, headers=response.headers, request=request)
        if case == "missing-id" and count == 5:
            denial = adapter.denial_value
            for key in reversed(adapter.denial_field.split(".")):
                denial = {key: denial}
            return httpx.Response(404, json=denial, headers=response.headers, request=request)
        if case == "wrong-list" and count == 3 or case == "wrong-detail" and count == 7:
            return httpx.Response(200, json={"unexpected": []}, headers=response.headers, request=request)
        if case == "duplicate-json" and count == 7:
            return httpx.Response(200, content=b'{"owner":"one","owner":"two"}', headers=response.headers, request=request)
        if case == "generic-denial" and count == 7:
            return httpx.Response(403, json={"error": "not a resource denial"}, headers=response.headers, request=request)
        if case == "login-html" and count == 1:
            return httpx.Response(200, text="<html>login form</html>", request=request)
        if case == "identity-missing" and count == 7:
            response.headers.pop(adapter.identity_header, None)
        return response
    service.transport = Intercept(service.transport, mutate)
    report, _ = execute(tmp_path, service)
    assert report.verdict == "INCONCLUSIVE"


@pytest.mark.parametrize("style", ["documents", "records"])
@pytest.mark.parametrize("case,count,code", [("account", 0, "SCOPE_ACCOUNT_DENIED"), ("limit", 2, "SCOPE_LIMIT_EXCEEDED")])
def test_scope_denial_is_authoritative_for_both_adapters(tmp_path, style, case, count, code):
    def narrow(target):
        if case == "account":
            target["profile"]["scenarios"] = {"access-control-http": ["user-b"]}
        else:
            target["profile"]["limits"]["max_requests"] = 2
    service, _ = setup_api(tmp_path, style, change=narrow)
    intercepted = Intercept(service.transport, lambda req, res, n: res)
    service.transport = intercepted
    report, _ = execute(tmp_path, service)
    assert report.verdict == "INCONCLUSIVE" and len(intercepted.requests) == count
    assert any(code in warning for warning in report.warnings)


@pytest.mark.parametrize("path", ["https://example.com/x", "//example.com/x", "/api/../login", "/api/%2e%2e/login", "/api/x?query=1", "/api/x#part", "/api/{expression}", "/api//x", "/api/{document_id}/more"])
def test_no_code_or_url_expression_paths(path):
    with pytest.raises(ValidationError):
        HttpRoutes(login_path=path)


@pytest.mark.parametrize("field,value", [("script", "run()"), ("content_field", "$..password"), ("token_field", "data[0]"),
                                         ("login_password_field", "x\r\nHost"), ("auth_mode", "shell"),
                                         ("private_value", 1), ("identity_header", "X\nY")])
def test_adapter_schema_rejects_unknown_and_unsafe_values(field, value):
    with pytest.raises(ValidationError):
        ApiAdapter.model_validate({field: value})


def test_adapter_cannot_expand_approved_scope_and_is_frozen(tmp_path):
    service, path = setup_api(tmp_path, "records")
    snapshot = service.registry.snapshot("lab-web", "access-control-http", service.limits)
    with pytest.raises(ValidationError):
        snapshot.adapter.routes.list_path = "/outside"
    payload = json.loads(path.read_text())
    payload["targets"]["lab-web"]["adapter"]["routes"]["list_path"] = "/outside"
    path.write_text(json.dumps(payload))
    with pytest.raises(ScopeViolation, match="adapter routes"):
        load_scope_registry(path)
    assert service.registry.snapshot("lab-web", "access-control-http", service.limits) == snapshot
    # Response-only mapping changes affect the fingerprint, even with identical paths.
    payload["targets"]["lab-web"]["adapter"]["routes"]["list_path"] = snapshot.adapter.routes.list_path
    payload["targets"]["lab-web"]["adapter"]["content_field"] = "record.content.other"
    path.write_text(json.dumps(payload))
    changed = load_scope_registry(path).snapshot("lab-web", "access-control-http", service.limits)
    assert changed.snapshot_sha256 != snapshot.snapshot_sha256


def test_secret_references_are_environment_only(tmp_path):
    service, path = setup_api(tmp_path, "records")
    with pytest.raises(ScopeViolation):
        service.registry.credentials({})
    payload = json.loads(path.read_text())
    payload["targets"]["lab-web"]["adapter"]["accounts"]["user_a"]["password"] = "never-echo"
    path.write_text(json.dumps(payload))
    with pytest.raises(ScopeViolation) as error:
        load_scope_registry(path)
    assert "never-echo" not in str(error.value)


@pytest.mark.parametrize("style", ["documents", "records"])
def test_final_send_gate_and_live_snapshot(tmp_path, style):
    service, path = setup_api(tmp_path, style)
    intercepted = Intercept(service.transport, lambda req, res, n: res)
    service.transport = intercepted

    async def check():
        login = await service.start_session("gate", "lab-web", "user-a", "access-control-http")
        assert login.ok
        state = service._runs["gate"]
        session_ref = login.data["session_ref"]
        original = state.scope.snapshot_sha256
        args = dict(operation="list_own_documents", method="GET", path=state.scope.http_routes.list_path,
                    account_ref="user-a", session_ref=session_ref, cookies=state.sessions[session_ref].cookies)
        for changed in ({"method": "POST"}, {"path": "/outside"}, {"path": "//external.invalid/x"}):
            with pytest.raises(ScopeViolation):
                await service._request(state, state.scope.target, **{**args, **changed})
        other = TargetPolicy("lab-web", "http", "10.78.0.31", 8080)
        with pytest.raises(ScopeViolation):
            await service._request(state, other, **args)
        assert len(intercepted.requests) == 1
        payload = json.loads(path.read_text())
        payload["targets"]["lab-web"]["adapter"]["list_field"] = "changed.items"
        # Keep legacy support restricted to the original contract for this reload.
        payload["targets"]["lab-web"]["profile"]["scenarios"] = {"access-control-http": ["user-a", "user-b"]}
        path.write_text(json.dumps(payload))
        result = await service.list_own_documents("gate", "lab-web", session_ref)
        assert result.ok and result.scope_policy.snapshot_sha256 == original
        assert load_scope_registry(path).snapshot("lab-web", "access-control-http", service.limits).snapshot_sha256 != original
        assert len(intercepted.requests) == 2

    asyncio.run(check())
