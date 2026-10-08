from __future__ import annotations

import asyncio
import socket
import threading
import time

import httpx
import pytest
import uvicorn

from controller.engine import EngineRequest, RunEngine
from controller.providers import MockModelProvider
from controller.reporting import ReportWriter
from controller.tool_clients import MCPWorkerClient
from tests.helpers import make_service
from worker.app import build_worker_app


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _start_server(app, port: int):
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", lifespan="on")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 5
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    assert server.started
    return server, thread


def test_agents_sdk_managed_mcp_lists_and_calls_bounded_tools(tmp_path):
    service, _ = make_service(tmp_path, "vulnerable")
    app = build_worker_app(
        service,
        worker_token="mcp-worker-test-token",
        allowed_clients={"127.0.0.1"},
    )
    port = _free_port()
    server, thread = _start_server(app, port)
    url = f"http://127.0.0.1:{port}"

    async def exercise():
        client = MCPWorkerClient(server_url=f"{url}/mcp", token="mcp-worker-test-token")
        async with client.session():
            assert set(await client.list_tools()) == {
                "start_session",
                "list_own_documents",
                "fetch_document",
                "finish_run",
            }
            b_session = await client.start_session("run-mcp", "lab-web", "user-b")
            assert b_session.ok
            listed = await client.list_own_documents("run-mcp", "lab-web", b_session.data["session_ref"])
            assert listed.data["document_ids"] == ["doc-b-001"]
            a_session = await client.start_session("run-mcp", "lab-web", "user-a")
            fetched = await client.fetch_document(
                "run-mcp",
                "lab-web",
                a_session.data["session_ref"],
                "doc-b-001",
                "attack-cross-b",
            )
            assert fetched.ok
            assert fetched.evidence.synthetic_document_marker == "SYN-B-PRIVATE-001"
            rejected = await client.start_session("run-outside", "outside", "user-a")
            assert rejected.error_code == "POLICY_REJECTED"

            cancel_session = await client.start_session("run-cancel", "lab-web", "user-a")
            assert cancel_session.ok
            cancelled = await client.cancel_run("run-cancel")
            assert cancelled.ok
            after_cancel = await client.list_own_documents(
                "run-cancel", "lab-web", cancel_session.data["session_ref"]
            )
            assert after_cancel.error_code == "POLICY_REJECTED"

        async def emit(_event_type, _payload):
            return None

        report = await RunEngine(report_writer=ReportWriter(tmp_path / "mcp-reports")).execute(
            EngineRequest(run_id="run-mcp-engine", scenario_id="access-control", target_id="lab-web"),
            provider=MockModelProvider(),
            client=MCPWorkerClient(server_url=f"{url}/mcp", token="mcp-worker-test-token"),
            cancel_event=asyncio.Event(),
            emit=emit,
        )
        assert report.verdict == "VULNERABLE"
        assert report.tool_transport == "mcp"
        assert report.limits_used["http_requests"] == 11

    try:
        asyncio.run(exercise())
        unauthorized = httpx.post(f"{url}/mcp", timeout=3)
        assert unauthorized.status_code == 401
    finally:
        server.should_exit = True
        thread.join(timeout=5)

    async def disconnected():
        client = MCPWorkerClient(server_url=f"{url}/mcp", token="mcp-worker-test-token")
        async with client.session():
            await client.list_tools()

    with pytest.raises(Exception):
        asyncio.run(disconnected())
