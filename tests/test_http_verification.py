from __future__ import annotations

import asyncio
import json
from dataclasses import replace

import httpx
import pytest

from common.schemas import Evidence, RunReport, Verdict
from controller.engine import EngineRequest, RunEngine
from controller.providers import MockModelProvider
from controller.reporting import ReportWriter
from controller.tool_clients import DirectToolClient
from tests.helpers import make_service
from verifier.core import evidence_identity_digest
from verifier.http import verify_http_access_control


def execute(tmp_path, service, run_id="http-test"):
    emitted = []
    async def go():
        async def emit(kind, payload):
            emitted.append((kind, payload))
        return await RunEngine(report_writer=ReportWriter(tmp_path / "reports")).execute(
            EngineRequest(run_id, "access-control-http", "lab-web"),
            provider=MockModelProvider(), client=DirectToolClient(service),
            cancel_event=asyncio.Event(), emit=emit,
        )
    report = asyncio.run(go())
    evidence = [Evidence.model_validate(payload["evidence"]) for kind, payload in emitted if kind == "evidence_added"]
    return report, evidence, emitted


def no_reader(_):
    pytest.fail("HTTP workflow accessed target-local observations")


@pytest.mark.parametrize("mode,expected", [("vulnerable", "VULNERABLE"), ("fixed", "BLOCKED_BY_ACCESS_CONTROL")])
@pytest.mark.parametrize("renamed", [False, True])
def test_http_controls_dynamic_canaries_and_privacy(tmp_path, mode, expected, renamed):
    service, store = make_service(tmp_path, mode)
    service.observation_reader = no_reader
    if renamed:
        with store._connect() as connection:
            connection.execute("UPDATE documents SET document_id='doc-renamed-732', marker='SYN-random-canary-abc732' WHERE owner_id='acct-b'")
            connection.execute("UPDATE documents SET document_id='doc-another-914', marker='SYN-distinct-canary-xyz914' WHERE owner_id='acct-a'")
    report, evidence, emitted = execute(tmp_path, service)
    assert report.verdict == expected
    assert report.verification_basis == "http_observation"
    assert report.environment["target_server_log"] == "not_used"
    assert report.mode == "unknown"
    assert report.limits_used == {"http_requests": 9, "tool_calls": 10}
    assert len(evidence) == 7
    assert all(item.synthetic_document_marker is None for item in evidence)
    saved = json.dumps(emitted) + report.model_dump_json()
    for secret in ("local-a-password", "local-b-password", "lab_session", "Ignore prior instructions", "Synthetic content", "SYN-", "Set-Cookie", "Bearer"):
        assert secret not in saved
    if renamed:
        assert evidence[3].path == "/documents/doc-renamed-732"


@pytest.fixture
def good_evidence(tmp_path):
    service, _ = make_service(tmp_path, "fixed")
    service.observation_reader = no_reader
    report, evidence, _ = execute(tmp_path, service)
    assert report.verdict == Verdict.BLOCKED_BY_ACCESS_CONTROL
    return evidence


@pytest.mark.parametrize("case", [
    "duplicate", "mixed-run", "wrong-account", "wrong-resource", "shared-session", "changed-session",
    "expired-cross", "expired-after", "owner-failed", "owner-unknown", "changed-resource", "same-canary",
    "login-200", "error-200", "public-200", "denial-leak", "denial-resource", "wrong-list-owner", "overlap-list",
    "duplicate-request", "duplicate-id", "wrong-method", "reordered", "missing", "wrong-document-id",
])
def test_http_rejects_ambiguous_or_mismatched_evidence(good_evidence, case):
    evidence = [item.model_copy(deep=True) for item in good_evidence]
    cross = evidence[4]
    if case == "duplicate": evidence.append(evidence[0])
    elif case == "mixed-run": cross.run_id = "other-run"
    elif case == "wrong-account": cross.account_ref = "user-b"
    elif case == "wrong-resource": cross.path = "/documents/doc-other-001"
    elif case == "shared-session":
        for item in evidence: item.http_observation.session_binding = "0" * 64
    elif case == "changed-session": cross.http_observation.session_binding = "0" * 64
    elif case == "expired-cross": cross.http_observation.authenticated_account = None
    elif case == "expired-after": evidence[6].status_code = 403
    elif case == "owner-failed": evidence[3].status_code = 500
    elif case == "owner-unknown": evidence[3].http_observation.owner_ref = None
    elif case == "changed-resource": evidence[5].http_observation.private_canary_digest = "0" * 64
    elif case == "same-canary":
        for index in (2, 6): evidence[index].http_observation.private_canary_digest = evidence[3].http_observation.private_canary_digest
    elif case in {"login-200", "error-200", "public-200"}:
        cross.status_code = 200
        cross.body_hash = evidence[3].body_hash
        if case == "public-200":
            cross.http_observation.document_id = evidence[3].http_observation.document_id
            cross.http_observation.owner_ref = "user-b"
    elif case == "denial-leak": cross.http_observation.canary_present = True
    elif case == "denial-resource": cross.http_observation.document_id = evidence[3].http_observation.document_id
    elif case == "wrong-list-owner": evidence[0].http_observation.owner_ref = "user-b"
    elif case == "overlap-list": evidence[0].http_observation.listed_document_ids = evidence[1].http_observation.listed_document_ids
    elif case == "duplicate-request": cross.request_id = evidence[3].request_id
    elif case == "duplicate-id": cross.evidence_id = evidence[3].evidence_id
    elif case == "wrong-method": cross.method = "POST"
    elif case == "reordered": evidence.reverse()
    elif case == "missing": evidence.pop()
    elif case == "wrong-document-id": evidence[3].http_observation.document_id = "doc-other-001"
    assert verify_http_access_control(evidence, run_id="http-test").verdict == Verdict.INCONCLUSIVE


class InterceptTransport(httpx.AsyncBaseTransport):
    def __init__(self, wrapped, attack):
        self.wrapped, self.attack, self.paths = wrapped, attack, []

    async def handle_async_request(self, request):
        self.paths.append(str(request.url))
        response = await self.wrapped.handle_async_request(request)
        await response.aread()
        if len(self.paths) == 7:  # Cross-account request, after independent controls.
            return await self.attack(request, response)
        return response


@pytest.mark.parametrize("failure", ["unauthenticated", "login-page", "public", "timeout", "network", "oversize", "redirect", "denial-with-canary", "error-denial", "html-denial"])
def test_http_transport_failures_are_inconclusive_and_redacted(tmp_path, failure):
    service, _ = make_service(tmp_path, "fixed")
    service.observation_reader = no_reader
    async def attack(request, response):
        if failure == "timeout": raise httpx.ReadTimeout("secret-cookie-password-raw", request=request)
        if failure == "network": raise httpx.ConnectError("secret-cookie-password-raw", request=request)
        if failure == "redirect": return httpx.Response(302, headers={"location": "http://203.0.113.1/leak"})
        if failure == "oversize": return httpx.Response(200, content=b"x" * 70000)
        if failure == "unauthenticated": return httpx.Response(403, json={"detail": "login required"})
        if failure == "login-page": return httpx.Response(200, text="<html>secret-cookie-password-raw login</html>")
        if failure == "public": return httpx.Response(200, json={"visibility": "public", "body": "shared public content"})
        if failure == "error-denial": return httpx.Response(403, headers={"X-SecurityLab-Account": "acct-a"}, json={"detail": "common error"})
        if failure == "html-denial": return httpx.Response(403, headers={"X-SecurityLab-Account": "acct-a"}, text="login page")
        return httpx.Response(403, headers={"X-SecurityLab-Account": "acct-a"}, json={
            "canary": {"kind": "synthetic-private", "value": "SYN-any-private-canary"}})
    transport = InterceptTransport(service.transport, attack)
    service.transport = transport
    report, evidence, emitted = execute(tmp_path, service)
    assert report.verdict == Verdict.INCONCLUSIVE
    assert all(url.startswith("http://10.78.0.30:8080/") for url in transport.paths)
    assert "secret-cookie-password-raw" not in json.dumps(emitted) + report.model_dump_json()
    if failure in {"timeout", "network", "oversize", "redirect"}:
        assert len(transport.paths) == 7
        assert len(evidence) == 4


@pytest.mark.parametrize("limits", [{"max_requests": 6}, {"max_tool_calls": 6}, {"max_tool_calls": 9}, {"max_response_bytes": 20}])
def test_http_limits_never_produce_a_final_verdict(tmp_path, limits):
    service, _ = make_service(tmp_path, "vulnerable")
    service.limits = replace(service.limits, **limits)
    report, _, _ = execute(tmp_path, service)
    assert report.verdict == Verdict.INCONCLUSIVE
    state = service._runs[report.run_id]
    assert state.request_count <= service.limits.max_requests
    assert state.tool_count <= service.limits.max_tool_calls


def test_http_digest_covers_metadata_and_legacy_report_defaults(good_evidence, tmp_path):
    before = evidence_identity_digest(good_evidence)
    good_evidence[4].http_observation.canary_present = True
    assert evidence_identity_digest(good_evidence) != before
    report = json.loads((tmp_path / "reports/http-test/report.json").read_text(encoding="utf-8"))
    report.pop("verification_basis")
    report["schema_version"] = "1.0"
    report["scenario_id"] = "access-control"
    report["environment"]["target_server_log"] = "offline-pending"
    assert RunReport.model_validate(report).verification_basis == "pending_target_log"
    report["environment"]["target_server_log"] = "offline-correlated"
    assert RunReport.model_validate(report).verification_basis == "target_log_correlated"


def test_local_socket_function_mcp_matrix(tmp_path):
    from scripts.run_http_verification import run_matrix
    rows = run_matrix(tmp_path / "matrix")
    assert len(rows) == 4
    assert all(row["evidence_count"] == row["independent_log_checks"] == 7 for row in rows)


def test_http_controller_persistence_and_offline_import_rejection(tmp_path):
    from fastapi.testclient import TestClient
    from controller.api import AppSettings, create_app
    from controller.repository import Repository
    from tests.test_controller_api import _headers, _login, _wait_for_terminal

    service, _ = make_service(tmp_path, "vulnerable")
    service.observation_reader = no_reader
    repository = Repository(tmp_path / "controller.sqlite3")
    app = create_app(settings=AppSettings(
        database_path=tmp_path / "controller.sqlite3", reports_path=tmp_path / "reports",
        session_secret="test-session-secret-at-least-24-characters", access_token="test-local-access-token",
        offline_import_token="offline-test-token", allowed_origins=frozenset({"http://testserver"}),
        allowed_hosts=frozenset({"testserver"}), allowed_clients=frozenset({"testclient"}),
    ), clients={"function": DirectToolClient(service)}, repository=repository)
    with TestClient(app) as client:
        csrf = _login(client)["csrf_token"]
        conversation = client.post("/api/conversations", json={"title": "HTTP"}, headers=_headers(csrf)).json()
        route = f"/api/conversations/{conversation['conversation_id']}/messages"
        payload = {"message": "run", "scenario_id": "access-control-http", "target_id": "lab-web", "provider": "mock", "tool_transport": "function"}
        submitted = client.post(route, json=payload, headers=_headers(csrf))
        assert submitted.status_code == 200
        run_id = submitted.json()["run_id"]
        run = _wait_for_terminal(client, run_id)
        assert run["report"]["verdict"] == "VULNERABLE"
        assert run["report"]["verification_basis"] == "http_observation"
        evidence = [Evidence.model_validate(item) for item in repository.list_evidence(run_id)]
        assert len(evidence) == 7
        before = repository.get_run_internal(run_id)["report"]
        imported = client.post("/api/internal/offline-verification", headers={"Authorization": "Bearer offline-test-token"}, json={
            "run_id": run_id, "verdict": "INCONCLUSIVE", "verified_findings": [], "warnings": [],
            "evidence_count": 7, "correlated_count": 0, "evidence_digest": evidence_identity_digest(evidence),
        })
        assert imported.status_code == 409
        assert repository.get_run_internal(run_id)["report"] == before
        assert client.post(route, json={**payload, "scenario_id": "arbitrary-verifier"}, headers=_headers(csrf)).status_code == 422
        saved = json.dumps(repository.list_events(run_id)) + json.dumps(repository.list_evidence(run_id)) + json.dumps(before)
        assert "lab_session" not in saved and "local-a-password" not in saved and "Ignore prior instructions" not in saved


def test_worker_scenario_and_session_cannot_be_rebound(tmp_path):
    service, _ = make_service(tmp_path, "fixed")
    async def go():
        for scenario, account, target in [("other", "user-a", "lab-web"), ("access-control-http", "admin", "lab-web"), ("access-control-http", "user-a", "outside")]:
            result = await service.start_session("reject", target, account, scenario)
            assert not result.ok
        a = await service.start_session("binding", "lab-web", "user-a", "access-control-http")
        assert a.ok
        result = await service.start_session("binding", "lab-web", "user-b", "access-control")
        assert not result.ok
        service.policies["other"] = service.policies["lab-web"]
        result = await service.list_own_documents("binding", "other", a.data["session_ref"])
        assert not result.ok
        assert service._runs["binding"].request_count == 1
    asyncio.run(go())


def test_http_provider_only_receives_registered_identifiers(tmp_path):
    service, _ = make_service(tmp_path, "vulnerable")
    service.observation_reader = no_reader
    calls = []
    class InspectProvider(MockModelProvider):
        async def propose_candidates(self, **kwargs):
            calls.append(kwargs)
            return await super().propose_candidates(**kwargs)
    async def go():
        async def emit(*_args): pass
        return await RunEngine(report_writer=ReportWriter(tmp_path / "reports")).execute(
            EngineRequest("provider-test", "access-control-http", "lab-web"),
            provider=InspectProvider(), client=DirectToolClient(service), cancel_event=asyncio.Event(), emit=emit)
    assert asyncio.run(go()).verdict == "VULNERABLE"
    assert calls == [{"scenario_id": "access-control-http", "target_id": "lab-web"}]
