from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

import httpx

from controller.engine import EngineRequest, RunEngine
from controller.providers import get_provider
from controller.reporting import ReportWriter
from controller.tool_clients import FunctionWorkerClient, MCPWorkerClient


ROOT = Path(__file__).resolve().parents[1]


async def doctor() -> int:
    checks: dict[str, object] = {
        "python": sys.version.split()[0],
        "worker_token_configured": bool(os.getenv("WORKER_TOKEN")),
        "openai_key_configured": bool(os.getenv("OPENAI_API_KEY")),
        "openai_model_configured": bool(os.getenv("OPENAI_MODEL")),
        "model_provider": os.getenv("MODEL_PROVIDER", "mock"),
        "tool_transport": os.getenv("TOOL_TRANSPORT", "function"),
        "nmap": "phase_2_not_implemented",
        "playwright": "phase_2_not_implemented",
    }
    worker_url = os.getenv("WORKER_URL", "http://10.77.0.20:9000").rstrip("/")
    try:
        async with httpx.AsyncClient(follow_redirects=False, trust_env=False, timeout=3) as client:
            response = await client.get(f"{worker_url}/health")
            checks["worker_health"] = response.json() if response.status_code == 200 else f"HTTP {response.status_code}"
    except Exception as exc:
        checks["worker_health"] = f"not verified: {type(exc).__name__}"
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    return 0 if checks["worker_token_configured"] else 2


async def run_scenario(args: argparse.Namespace) -> int:
    token = os.getenv("WORKER_TOKEN", "")
    if not token:
        print("WORKER_TOKEN is required", file=sys.stderr)
        return 2
    if args.transport == "function":
        client = FunctionWorkerClient(base_url=os.getenv("WORKER_URL", "http://10.77.0.20:9000"), token=token)
    else:
        client = MCPWorkerClient(
            server_url=os.getenv("MCP_WORKER_URL", "http://10.77.0.20:9000/mcp"), token=token
        )
    provider = get_provider(args.provider, model_id=os.getenv("OPENAI_MODEL") or None)
    run_id = f"run_{uuid.uuid4().hex}"
    engine = RunEngine(report_writer=ReportWriter(ROOT / "reports" / "runs"))

    async def emit(event_type: str, payload: dict[str, object]) -> None:
        payload = {key: value for key, value in payload.items() if key != "evidence"}
        print(json.dumps({"event": event_type, **payload}, ensure_ascii=False))

    report = await engine.execute(
        EngineRequest(run_id=run_id, scenario_id=args.scenario, target_id=args.target),
        provider=provider,
        client=client,
        cancel_event=asyncio.Event(),
        emit=emit,
    )
    print(report.model_dump_json(indent=2))
    return 0 if report.status == "COMPLETED" else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="SecurityLab bounded controller CLI")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("doctor")
    run_parser = subcommands.add_parser("run")
    run_parser.add_argument("--scenario", default="access-control", choices=["access-control"])
    run_parser.add_argument("--target", default="lab-web", choices=["lab-web"])
    run_parser.add_argument("--provider", default="mock", choices=["mock", "openai"])
    run_parser.add_argument("--transport", default="function", choices=["function", "mcp"])
    args = parser.parse_args()
    result = asyncio.run(doctor() if args.command == "doctor" else run_scenario(args))
    raise SystemExit(result)


if __name__ == "__main__":
    main()
