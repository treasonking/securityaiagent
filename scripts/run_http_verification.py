"""Test-only loopback harness; never changes the deployed target registry."""
from __future__ import annotations

import asyncio
import json
import os
import platform
import secrets
import socket
import sys
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.schemas import Evidence
from controller.engine import EngineRequest, RunEngine
from controller.providers import MockModelProvider
from controller.reporting import ReportWriter
from controller.tool_clients import FunctionWorkerClient, MCPWorkerClient
from target.store import TargetStore
from worker.app import build_worker_app
from worker.policy import TargetPolicy
from worker.service import ToolService, WorkerLimits


@contextmanager
def local_server(app):
    """Reserve a fresh loopback socket and stop only the server this call owns."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(128)
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="on", access_log=False))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.02)
            if not server.started:
                raise RuntimeError("temporary loopback server did not start")
            yield port
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            if thread.is_alive():
                raise RuntimeError("temporary loopback server did not stop")


def run_matrix(output: Path) -> list[dict]:
    output.mkdir(parents=True, exist_ok=True)
    temp_root = ROOT / "verification_tmp"
    temp_root.mkdir(exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory(prefix="http-matrix-", dir=temp_root) as directory:
        temp = Path(directory)
        # target.app has a legacy module-level app. Isolate its DB before importing it.
        previous = os.environ.get("TARGET_DATABASE_PATH")
        os.environ["TARGET_DATABASE_PATH"] = str(temp / "unused-default.sqlite3")
        try:
            from target.app import create_app
        finally:
            if previous is None:
                os.environ.pop("TARGET_DATABASE_PATH", None)
            else:
                os.environ["TARGET_DATABASE_PATH"] = previous
        for mode in ("vulnerable", "fixed"):
            store = TargetStore(temp / f"{mode}.sqlite3", mode=mode)
            with local_server(create_app(store)) as target_port:
                for transport in ("function", "mcp"):
                    def forbidden_reader(_request_id):
                        raise AssertionError("HTTP workflow must never read target logs")

                    service = ToolService(
                        policies={"lab-web": TargetPolicy("lab-web", "http", "127.0.0.1", target_port)},
                        accounts={"user-a": ("user_a", "local-a-password"),
                                  "user-b": ("user_b", "local-b-password")},
                        limits=WorkerLimits(requests_per_second=0),
                        observation_reader=forbidden_reader,
                    )
                    token = secrets.token_urlsafe(32)
                    app = build_worker_app(service, worker_token=token, allowed_clients={"127.0.0.1"})
                    with local_server(app) as worker_port:
                        base = f"http://127.0.0.1:{worker_port}"
                        client = (FunctionWorkerClient(base_url=base, token=token) if transport == "function"
                                  else MCPWorkerClient(server_url=base + "/mcp", token=token))
                        run_id = "http-" + uuid.uuid4().hex
                        rejection_codes = []
                        async def emit(_event, _payload):
                            if _event == "tool_finished" and _payload.get("error_code"):
                                rejection_codes.append(_payload["error_code"])

                        report = asyncio.run(RunEngine(report_writer=ReportWriter(output)).execute(
                            EngineRequest(run_id, "access-control-http", "lab-web"),
                            provider=MockModelProvider(), client=client,
                            cancel_event=asyncio.Event(), emit=emit,
                        ))
                    # Evaluator-only assertions AFTER the HTTP verdict. Never verifier input.
                    expected = "VULNERABLE" if mode == "vulnerable" else "BLOCKED_BY_ACCESS_CONTROL"
                    if report.verdict != expected:
                        raise AssertionError(f"{transport}/{mode}: {report.verdict}; {report.warnings}")
                    evidence = [Evidence.model_validate(item) for item in json.loads(
                        (output / run_id / "evidence.json").read_text(encoding="utf-8"))]
                    for item in evidence:
                        observation = store.observation(item.request_id)
                        if not observation or any(observation[field] != getattr(item, field)
                                                  for field in ("run_id", "request_id", "method", "path", "status_code")):
                            raise AssertionError("independent target-log identity check failed")
                        if observation["account_id"] != service.account_ids[item.account_ref]:
                            raise AssertionError("independent target-log account check failed")
                        if item.http_observation.private_canary_digest:
                            from common.sanitize import body_digest
                            if body_digest(observation["marker"].encode()) != item.http_observation.private_canary_digest:
                                raise AssertionError("independent target-log canary check failed")
                    results.append({
                        "run_id": run_id, "fixture_mode": mode, "transport": transport,
                        "verdict": report.verdict, "verification_basis": report.verification_basis,
                        "evidence_count": len(evidence), "limits_used": report.limits_used,
                        "scope_policy": report.scope_policy.model_dump(mode="json") if report.scope_policy else None,
                        "rejection_codes": rejection_codes,
                        "started_at": report.started_at, "finished_at": report.finished_at,
                        "independent_log_checks": len(evidence), "python": platform.python_version(),
                    })
    # Unique name preserves all earlier executions.
    matrix_path = output / f"matrix-{uuid.uuid4().hex[:12]}.json"
    matrix_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps({"matrix": str(matrix_path), "results": results}, indent=2))
    return results


if __name__ == "__main__":
    run_matrix(ROOT / "reports" / "http_verification")
