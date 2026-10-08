from __future__ import annotations

import time

from fastapi.testclient import TestClient

from controller.api import AppSettings, create_app
from controller.repository import Repository
from controller.tool_clients import DirectToolClient
from tests.helpers import make_service


def _headers(csrf: str, *, origin: str = "http://testserver") -> dict[str, str]:
    return {"X-CSRF-Token": csrf, "Origin": origin}


def _wait_for_terminal(client: TestClient, run_id: str, timeout: float = 5) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200
        state = response.json()
        if state["status"] in {"COMPLETED", "CANCELLED", "FAILED", "INTERRUPTED"}:
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
            allowed_origins=frozenset({"http://testserver"}),
        ),
        clients={"function": DirectToolClient(service)},
        repository=repository,
    )
    with TestClient(app) as client:
        session = client.get("/api/session").json()
        csrf = session["csrf_token"]
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
            allowed_origins=frozenset({"http://testserver"}),
        ),
        clients={"function": DirectToolClient(service)},
    )
    with TestClient(app) as client:
        assert client.get("/api/conversations").status_code == 401
        session = client.get("/api/session").json()
        assert client.post(
            "/api/conversations", json={"title": "missing csrf"}, headers={"Origin": "http://testserver"}
        ).status_code == 403
        assert client.post(
            "/api/conversations",
            json={"title": "ok"},
            headers=_headers(session["csrf_token"]),
        ).status_code == 200
