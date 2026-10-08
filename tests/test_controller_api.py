from __future__ import annotations

import time

from fastapi.testclient import TestClient

from common.schemas import Evidence
from controller.api import AppSettings, create_app
from controller.repository import Repository
from controller.tool_clients import DirectToolClient
from tests.helpers import make_service
from verifier.core import evidence_identity_digest


def _headers(csrf: str, *, origin: str = "http://testserver") -> dict[str, str]:
    return {"X-CSRF-Token": csrf, "Origin": origin}


def _login(client: TestClient, token: str = "test-local-access-token") -> dict:
    response = client.post(
        "/api/session",
        json={"access_token": token},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 200
    return response.json()


def _wait_for_terminal(client: TestClient, run_id: str, timeout: float = 5) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200
        state = response.json()
        if state["status"] in {"COMPLETED", "CANCELLED", "TIMED_OUT", "FAILED", "INTERRUPTED"}:
            return state
        time.sleep(0.02)
    raise AssertionError("run did not reach a terminal status")


def test_message_to_job_sse_report_history_and_privacy(tmp_path):
    service, _ = make_service(tmp_path, "vulnerable")
    repository = Repository(tmp_path / "controller.sqlite3")
    app = create_app(
        settings=AppSettings(
            database_path=tmp_path / "controller.sqlite3",
            reports_path=tmp_path / "reports",
            session_secret="test-session-secret-at-least-24-characters",
            access_token="test-local-access-token",
            allowed_origins=frozenset({"http://testserver"}),
            allowed_hosts=frozenset({"testserver"}),
            allowed_clients=frozenset({"testclient"}),
        ),
        clients={"function": DirectToolClient(service)},
        repository=repository,
    )
    with TestClient(app) as client:
        session = _login(client)
        csrf = session["csrf_token"]
        config = client.get("/api/config").json()
        assert config["workflow"] == "fixed-scenario-verifier-with-llm-candidate-generation"
        assert config["providers"]["openai"]["configured"] is False
        rejected = client.post(
            "/api/conversations",
            json={"title": "bad origin"},
            headers=_headers(csrf, origin="http://evil.example"),
        )
        assert rejected.status_code == 403
        conversation = client.post(
            "/api/conversations",
            json={"title": "접근 통제"},
            headers=_headers(csrf),
        ).json()
        raw_message = "검증해줘 <script>alert(1)</script> Authorization: Bearer secret-cookie"
        submitted = client.post(
            f"/api/conversations/{conversation['conversation_id']}/messages",
            json={
                "message": raw_message,
                "scenario_id": "access-control",
                "target_id": "lab-web",
                "provider": "mock",
                "tool_transport": "function",
            },
            headers=_headers(csrf),
        )
        assert submitted.status_code == 200
        run_id = submitted.json()["run_id"]
        state = _wait_for_terminal(client, run_id)
        assert state["status"] == "COMPLETED"
        assert state["report"]["verdict"] == "VULNERABLE"
        assert state["report"]["finding_candidates"][0]["source"] == "mock_provider"
        evidence = client.get(f"/api/runs/{run_id}/evidence").json()["evidence"]
        assert len(evidence) == 5
        assert all("body" not in item for item in evidence)
        event_stream = client.get(f"/api/runs/{run_id}/events")
        assert "event: report_ready" in event_stream.text
        history = client.get(
            f"/api/conversations/{conversation['conversation_id']}/messages"
        ).json()["messages"]
        assert "secret-cookie" not in history[0]["content"]
        assert "<script>alert(1)</script>" in history[0]["content"]
        conversations = client.get("/api/conversations").json()["conversations"]
        assert conversations[0]["conversation_id"] == conversation["conversation_id"]
        runs = client.get(
            f"/api/conversations/{conversation['conversation_id']}/runs"
        ).json()["runs"]
        assert runs[0]["run_id"] == run_id

    raw_database = (tmp_path / "controller.sqlite3").read_bytes().decode("utf-8", errors="ignore")
    assert "secret-cookie" not in raw_database
    assert "Ignore prior instructions" not in raw_database


def test_csrf_and_session_are_required(tmp_path):
    service, _ = make_service(tmp_path, "fixed")
    app = create_app(
        settings=AppSettings(
            database_path=tmp_path / "controller.sqlite3",
            reports_path=tmp_path / "reports",
            session_secret="test-session-secret-at-least-24-characters",
            access_token="test-local-access-token",
            allowed_origins=frozenset({"http://testserver"}),
            allowed_hosts=frozenset({"testserver"}),
            allowed_clients=frozenset({"testclient"}),
        ),
        clients={"function": DirectToolClient(service)},
    )
    with TestClient(app) as client:
        assert client.get("/api/conversations").status_code == 401
        assert client.get("/api/session").status_code == 401
        assert client.post(
            "/api/session", json={"access_token": "test-local-access-token"}
        ).status_code == 403
        assert client.post(
            "/api/session",
            json={"access_token": "wrong"},
            headers={"Origin": "http://testserver"},
        ).status_code == 401
        session = _login(client)
        assert client.post(
            "/api/conversations", json={"title": "missing csrf"}, headers={"Origin": "http://testserver"}
        ).status_code == 403
        assert client.post(
            "/api/conversations",
            json={"title": "ok"},
            headers=_headers(session["csrf_token"]),
        ).status_code == 200
        logout = client.delete("/api/session", headers=_headers(session["csrf_token"]))
        assert logout.status_code == 200
        assert client.get("/api/conversations").status_code == 401


def test_controller_rejects_untrusted_host_and_client(tmp_path):
    service, _ = make_service(tmp_path, "fixed")
    app = create_app(
        settings=AppSettings(
            database_path=tmp_path / "controller.sqlite3",
            reports_path=tmp_path / "reports",
            session_secret="test-session-secret-at-least-24-characters",
            access_token="test-local-access-token",
            allowed_origins=frozenset({"http://testserver"}),
            allowed_hosts=frozenset({"controller.local"}),
            allowed_clients=frozenset({"testclient"}),
        ),
        clients={"function": DirectToolClient(service)},
    )
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 400

    blocked_client_app = create_app(
        settings=AppSettings(
            database_path=tmp_path / "blocked-client.sqlite3",
            reports_path=tmp_path / "blocked-reports",
            session_secret="test-session-secret-at-least-24-characters",
            access_token="test-local-access-token",
            allowed_origins=frozenset({"http://testserver"}),
            allowed_hosts=frozenset({"testserver"}),
            allowed_clients=frozenset({"192.168.56.1"}),
        ),
        clients={"function": DirectToolClient(service)},
    )
    with TestClient(blocked_client_app) as client:
        assert client.get("/api/health").status_code == 403


def test_controller_deadline_cancels_provider_and_marks_timeout(tmp_path, monkeypatch):
    class SlowProvider:
        mode = "mock"
        model_id = None

        async def propose_candidates(self, **_kwargs):
            import asyncio

            await asyncio.sleep(30)

    monkeypatch.setattr("controller.manager.get_provider", lambda *_args, **_kwargs: SlowProvider())
    service, _ = make_service(tmp_path, "fixed")
    app = create_app(
        settings=AppSettings(
            database_path=tmp_path / "controller.sqlite3",
            reports_path=tmp_path / "reports",
            session_secret="test-session-secret-at-least-24-characters",
            access_token="test-local-access-token",
            allowed_origins=frozenset({"http://testserver"}),
            allowed_hosts=frozenset({"testserver"}),
            allowed_clients=frozenset({"testclient"}),
            run_timeout_seconds=0.05,
        ),
        clients={"function": DirectToolClient(service)},
    )
    with TestClient(app) as client:
        session = _login(client)
        conversation = client.post(
            "/api/conversations", json={}, headers=_headers(session["csrf_token"])
        ).json()
        submitted = client.post(
            f"/api/conversations/{conversation['conversation_id']}/messages",
            json={"message": "timeout test"},
            headers=_headers(session["csrf_token"]),
        ).json()
        state = _wait_for_terminal(client, submitted["run_id"])
        assert state["status"] == "TIMED_OUT"
        assert "exceeded" in state["error_message"]


def test_queued_run_can_be_cancelled_before_execution(tmp_path, monkeypatch):
    class SlowProvider:
        mode = "mock"
        model_id = None

        async def propose_candidates(self, **_kwargs):
            import asyncio

            await asyncio.sleep(30)

    monkeypatch.setattr("controller.manager.get_provider", lambda *_args, **_kwargs: SlowProvider())
    service, _ = make_service(tmp_path, "fixed")
    app = create_app(
        settings=AppSettings(
            database_path=tmp_path / "controller.sqlite3",
            reports_path=tmp_path / "reports",
            session_secret="test-session-secret-at-least-24-characters",
            access_token="test-local-access-token",
            allowed_origins=frozenset({"http://testserver"}),
            allowed_hosts=frozenset({"testserver"}),
            allowed_clients=frozenset({"testclient"}),
            run_timeout_seconds=0.5,
            max_concurrency=1,
        ),
        clients={"function": DirectToolClient(service)},
    )
    with TestClient(app) as client:
        session = _login(client)
        conversation = client.post(
            "/api/conversations", json={}, headers=_headers(session["csrf_token"])
        ).json()
        first = client.post(
            f"/api/conversations/{conversation['conversation_id']}/messages",
            json={"message": "hold queue"},
            headers=_headers(session["csrf_token"]),
        ).json()
        second = client.post(
            f"/api/conversations/{conversation['conversation_id']}/messages",
            json={"message": "cancel queued"},
            headers=_headers(session["csrf_token"]),
        ).json()
        cancelled = client.post(
            f"/api/runs/{second['run_id']}/cancel",
            json={},
            headers=_headers(session["csrf_token"]),
        )
        assert cancelled.status_code == 200
        assert _wait_for_terminal(client, second["run_id"])["status"] == "CANCELLED"
        assert _wait_for_terminal(client, first["run_id"])["status"] == "TIMED_OUT"


def test_authenticated_offline_verification_import_updates_report(tmp_path):
    service, _ = make_service(tmp_path, "vulnerable")
    repository = Repository(tmp_path / "controller.sqlite3")
    app = create_app(
        settings=AppSettings(
            database_path=tmp_path / "controller.sqlite3",
            reports_path=tmp_path / "reports",
            session_secret="test-session-secret-at-least-24-characters",
            access_token="test-local-access-token",
            allowed_origins=frozenset({"http://testserver"}),
            allowed_hosts=frozenset({"testserver"}),
            allowed_clients=frozenset({"testclient"}),
            offline_import_token="offline-import-token",
        ),
        clients={"function": DirectToolClient(service)},
        repository=repository,
    )
    with TestClient(app) as client:
        session = _login(client)
        conversation = client.post(
            "/api/conversations", json={}, headers=_headers(session["csrf_token"])
        ).json()
        submitted = client.post(
            f"/api/conversations/{conversation['conversation_id']}/messages",
            json={"message": "offline import"},
            headers=_headers(session["csrf_token"]),
        ).json()
        state = _wait_for_terminal(client, submitted["run_id"])
        items = [Evidence.model_validate(item) for item in repository.list_evidence(submitted["run_id"])]
        payload = {
            "run_id": submitted["run_id"],
            "verdict": state["report"]["verdict"],
            "verified_findings": state["report"]["verified_findings"],
            "warnings": ["offline evaluator imported"],
            "evidence_count": len(items),
            "correlated_count": len(items),
            "evidence_digest": evidence_identity_digest(items),
        }
        assert client.post("/api/internal/offline-verification", json=payload).status_code == 401
        bad = dict(payload, evidence_digest="0" * 64)
        assert client.post(
            "/api/internal/offline-verification",
            json=bad,
            headers={"Authorization": "Bearer offline-import-token"},
        ).status_code == 409
        imported = client.post(
            "/api/internal/offline-verification",
            json=payload,
            headers={"Authorization": "Bearer offline-import-token"},
        )
        assert imported.status_code == 200
        refreshed = client.get(f"/api/runs/{submitted['run_id']}").json()
        assert refreshed["report"]["environment"]["target_server_log"] == "offline-correlated"
        refreshed_evidence = client.get(
            f"/api/runs/{submitted['run_id']}/evidence"
        ).json()["evidence"]
        assert all(item["server_observation"] == "target_log_correlated" for item in refreshed_evidence)
