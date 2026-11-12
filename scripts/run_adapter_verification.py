"""Local synthetic TCP matrix. Never contacts deployed VMs or external sites."""
from __future__ import annotations

import asyncio
import json
import secrets
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from controller.engine import EngineRequest, RunEngine
from controller.providers import MockModelProvider
from controller.reporting import ReportWriter
from controller.tool_clients import FunctionWorkerClient, MCPWorkerClient
from scripts.run_http_verification import local_server
from target.store import TargetStore
from worker.app import build_worker_app
from worker.limits import WorkerLimits
from worker.policy import TargetPolicy
from worker.registry import load_scope_registry
from worker.service import ToolService


def run_matrix(output: Path):
    # Import the legacy module without initializing a deployed/default target DB.
    import os
    temp_root = ROOT / "verification_tmp"
    temp_root.mkdir(exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    with tempfile.TemporaryDirectory(prefix="adapter-matrix-", dir=temp_root) as directory:
        temp = Path(directory)
        previous = os.environ.get("TARGET_DATABASE_PATH")
        os.environ["TARGET_DATABASE_PATH"] = str(temp / "unused.sqlite3")
        try:
            from target.app import create_app
        finally:
            if previous is None:
                os.environ.pop("TARGET_DATABASE_PATH", None)
            else:
                os.environ["TARGET_DATABASE_PATH"] = previous
        for style, config in (("documents", "targets.json"), ("records", "targets.records.json")):
            for mode in ("vulnerable", "fixed"):
                store = TargetStore(temp / f"{style}-{mode}.sqlite3", mode=mode)
                target_app = create_app(store, api_style=style)
                observed = {}

                @target_app.middleware("http")
                async def count_requests(request, call_next):
                    run_id = request.headers.get("X-SecurityLab-Run")
                    if run_id:
                        observed[run_id] = observed.get(run_id, 0) + 1
                    return await call_next(request)

                with local_server(target_app) as target_port:
                    for case in (("allowed", "account-denied", "limit-two") if mode == "vulnerable" else ("allowed",)):
                        payload = json.loads((ROOT / "config" / config).read_text(encoding="utf-8"))
                        profile = payload["targets"]["lab-web"]["profile"]
                        if case == "account-denied":
                            profile["scenarios"] = {"access-control-http": ["user-a"]}
                        if case == "limit-two":
                            profile["limits"]["max_requests"] = 2
                        registry_path = temp / "scope.json"
                        registry_path.write_text(json.dumps(payload), encoding="utf-8")
                        registry = load_scope_registry(registry_path).with_test_origins(
                            {"lab-web": TargetPolicy("lab-web", "http", "127.0.0.1", target_port)})
                        for transport in ("function", "mcp"):
                            def no_logs(_):
                                raise AssertionError("HTTP verifier cannot read target logs")
                            service = ToolService(registry=registry,
                                accounts=registry.credentials({"LAB_USER_A_PASSWORD": "local-a-password",
                                    "LAB_USER_B_PASSWORD": "local-b-password", "LAB_ADMIN_PASSWORD": "local-admin-password"}),
                                limits=WorkerLimits(), observation_reader=no_logs)
                            token = secrets.token_urlsafe(32)
                            app = build_worker_app(service, worker_token=token, allowed_clients={"127.0.0.1"})
                            with local_server(app) as worker_port:
                                base = f"http://127.0.0.1:{worker_port}"
                                client = FunctionWorkerClient(base_url=base, token=token) if transport == "function" else MCPWorkerClient(server_url=base + "/mcp", token=token)
                                run_id = "adapter-" + uuid.uuid4().hex
                                codes = []
                                async def emit(event, data):
                                    if event == "tool_finished" and data.get("error_code"):
                                        codes.append(data["error_code"])
                                report = asyncio.run(RunEngine(report_writer=ReportWriter(output)).execute(
                                    EngineRequest(run_id, "access-control-http", "lab-web"), provider=MockModelProvider(),
                                    client=client, cancel_event=asyncio.Event(), emit=emit))
                            expected = ("VULNERABLE" if mode == "vulnerable" else "BLOCKED_BY_ACCESS_CONTROL") if case == "allowed" else "INCONCLUSIVE"
                            count = {"allowed": 9, "account-denied": 1, "limit-two": 2}[case]
                            expected_codes = {"allowed": [], "account-denied": ["SCOPE_ACCOUNT_DENIED"], "limit-two": ["SCOPE_LIMIT_EXCEEDED"]}[case]
                            assert report.verdict == expected, report.warnings
                            assert report.limits_used["http_requests"] == observed.get(run_id, 0) == count
                            assert codes == expected_codes
                            assert len(report.evidence_ids) == (7 if case == "allowed" else 0)
                            rows.append({"run_id": run_id, "api": style, "fixture_mode": mode, "transport": transport,
                                         "case": case, "verdict": report.verdict, "verification_basis": report.verification_basis,
                                         "evidence_count": len(report.evidence_ids), "limits_used": report.limits_used,
                                         "target_observed_requests": observed[run_id], "rejection_codes": codes,
                                         "scope_policy": report.scope_policy.model_dump(mode="json"),
                                         "started_at": report.started_at, "finished_at": report.finished_at})
    path = output / f"matrix-{uuid.uuid4().hex[:12]}.json"
    path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(json.dumps({"matrix": str(path), "runs": len(rows), "normal_combinations": 8, "negative_combinations": 8}))
    return rows


if __name__ == "__main__":
    run_matrix(ROOT / "reports" / "api_adapters")
