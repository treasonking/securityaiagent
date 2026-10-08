from __future__ import annotations

from fastapi.testclient import TestClient

from tests.helpers import make_service
from worker.app import build_worker_app


def test_worker_rejects_missing_and_wrong_auth_before_tool_execution(tmp_path):
    service, _ = make_service(tmp_path, "vulnerable")
    app = build_worker_app(service, worker_token="worker-test-token", allowed_clients={"testclient"})
    with TestClient(app) as client:
        missing = client.post(
            "/v1/tools/start-session",
            json={"run_id": "run-auth", "target_id": "lab-web", "account_ref": "user-a"},
        )
        wrong = client.post(
            "/v1/tools/start-session",
            headers={"Authorization": "Bearer wrong"},
            json={"run_id": "run-auth", "target_id": "lab-web", "account_ref": "user-a"},
        )
    assert missing.status_code == 401
    assert wrong.status_code == 401


def test_worker_rejects_unregistered_target_without_network_call(tmp_path):
    service, _ = make_service(tmp_path, "vulnerable")
    app = build_worker_app(service, worker_token="worker-test-token", allowed_clients={"testclient"})
    with TestClient(app) as client:
        response = client.post(
            "/v1/tools/start-session",
            headers={"Authorization": "Bearer worker-test-token"},
            json={"run_id": "run-policy", "target_id": "outside", "account_ref": "user-a"},
        )
    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert response.json()["error_code"] == "POLICY_REJECTED"
