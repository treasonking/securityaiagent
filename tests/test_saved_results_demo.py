import json
import secrets
import socket

from fastapi.testclient import TestClient
import pytest

from scripts import review_saved_results as demo


def test_demo_review_and_execution_boundary(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Offline review attempted a network connection")

    token = secrets.token_hex(16)
    app = demo.prepare_demo(tmp_path, token)
    with TestClient(app, base_url=demo.ORIGIN, client=(demo.HOST, 51473),
                    headers={"origin": demo.ORIGIN}) as client:
        # Windows creates a loopback socketpair when TestClient starts its event loop.
        monkeypatch.setattr(socket.socket, "connect", forbidden)
        assert client.get("/api/operator/runs").status_code == 401
        login = client.post("/api/session", json={"access_token": token})
        assert login.status_code == 200
        csrf = login.json()["csrf_token"]
        assert client.get("/api/operator/profiles").json() == {
            "profiles": [], "configured": False, "saved_results_only": True,
        }
        assert client.get("/api/health").json()["transports"] == []
        rows = client.get("/api/operator/runs").json()["runs"]
        assert {r["run_id"] for r in rows} == {r for _, r, _ in demo.EXAMPLES}
        for row in rows:
            url = "/api/operator/runs/" + row["run_id"]
            result = client.get(url).json()
            assert len(result["evidence"]) == 11 and result["replay"]["verdict_matches"]
            draft = url + "/disclosure-draft"
            preview = client.get(draft)
            if row["conclusion"]["verdict"] == "VULNERABLE":
                payload = {"review_digest": preview.json()["review_digest"], "confirmed": True}
                assert client.post(draft, json=payload).status_code == 403
                issued = client.post(draft, json=payload, headers={"x-csrf-token": csrf})
                assert issued.content == preview.json()["markdown"].encode()
            else:
                assert row["conclusion"]["verdict"] == "BLOCKED_BY_ACCESS_CONTROL"
                assert preview.status_code == 409
                issued = client.post(draft, json={"review_digest": "0"*64, "confirmed": True},
                                     headers={"x-csrf-token": csrf})
                assert issued.status_code == 409 and issued.json()["detail"]["code"] == "DRAFT_BLOCKED"
        client.headers.update({"x-csrf-token": csrf})
        for path, payload in [
            ("/api/operator/preview", {"profile_id": "offline", "transport": "function"}),
            ("/api/operator/plans/opplan_" + "0"*32 + "/run", {"confirmed": True, "plan_sha256": "0"*64}),
            ("/api/conversations", {}),
            ("/api/conversations/anything/messages", {"message": "demo"}),
        ]:
            denied = client.post(path, json=payload)
            assert denied.status_code == 403 and "read-only" in denied.json()["detail"]
        assert client.get("/api/operator/jobs").json()["jobs"] == []
        assert client.delete("/api/session").status_code == 200
        assert client.get("/api/operator/runs").status_code == 401
    # A live connection still holding this file prevents deletion on Windows.
    (tmp_path / "sessions.sqlite3").unlink()


def test_demo_refuses_changed_fixture(tmp_path, monkeypatch):
    case, run_id, _ = demo.EXAMPLES[0]
    source = tmp_path / "archives" / case / "runs" / run_id
    source.mkdir(parents=True)
    for name in demo.INPUTS:
        (source / name).write_bytes((demo.ARCHIVE / case / "runs" / run_id / name).read_bytes())
    (source / "evidence.json").write_text(json.dumps([]))
    monkeypatch.setattr(demo, "ARCHIVE", tmp_path / "archives")
    with pytest.raises(ValueError, match=case):
        demo.prepare_demo(tmp_path / "instance", secrets.token_hex(16))
