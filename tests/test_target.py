from __future__ import annotations

from fastapi.testclient import TestClient

from target.app import create_app
from target.store import TargetStore


def _login(client: TestClient, username: str, password: str) -> None:
    response = client.post(
        "/login",
        json={"username": username, "password": password},
        headers={"X-SecurityLab-Run": "test-run", "X-SecurityLab-Request": "login-request"},
    )
    assert response.status_code == 200
    assert response.cookies.get("lab_session")


def test_vulnerable_mode_reproduces_cross_account_access(tmp_path):
    store = TargetStore(tmp_path / "target.sqlite3", mode="vulnerable")
    with TestClient(create_app(store)) as client:
        _login(client, "user_a", "local-a-password")
        response = client.get(
            "/documents/doc-b-001",
            headers={"X-SecurityLab-Run": "run-1", "X-SecurityLab-Request": "fetch-b"},
        )
    assert response.status_code == 200
    assert response.json()["marker"] == "SYN-B-PRIVATE-001"
    assert store.observation("fetch-b")["marker"] == "SYN-B-PRIVATE-001"


def test_fixed_mode_denies_cross_account_access_but_allows_owner(tmp_path):
    store = TargetStore(tmp_path / "target.sqlite3", mode="fixed")
    with TestClient(create_app(store)) as client:
        _login(client, "user_a", "local-a-password")
        own = client.get("/documents/doc-a-001")
        cross = client.get("/documents/doc-b-001")
    assert own.status_code == 200
    assert own.json()["marker"] == "SYN-A-PRIVATE-001"
    assert cross.status_code == 404


def test_login_failure_is_not_access_control_block(tmp_path):
    store = TargetStore(tmp_path / "target.sqlite3", mode="fixed")
    with TestClient(create_app(store)) as client:
        response = client.post("/login", json={"username": "user_a", "password": "wrong"})
    assert response.status_code == 401
