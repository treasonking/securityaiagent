from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from controller.engine import EngineRequest, RunEngine
from controller.providers import MockModelProvider
from controller.reporting import ReportWriter
from controller.tool_clients import DirectToolClient
from target.app import create_app as create_target_app
from target.store import TargetStore
from worker.policy import TargetPolicy
from worker.service import ToolService, WorkerLimits

async def run(mode: str) -> str:
    store = TargetStore(ROOT / "data" / f"target-{mode}.sqlite3", mode=mode)
    store.reset()
    service = ToolService(
        policies={
            "lab-web": TargetPolicy(
                target_id="lab-web", scheme="http", host="10.78.0.30", port=8080
            )
        },
        accounts={
            "user-a": ("user_a", "local-a-password"),
            "user-b": ("user_b", "local-b-password"),
            "admin": ("admin", "local-admin-password"),
        },
        limits=WorkerLimits(requests_per_second=0),
        transport=httpx.ASGITransport(app=create_target_app(store)),
        observation_reader=store.observation,
    )
    run_id = f"local-{mode}-{uuid.uuid4().hex[:12]}"

    async def emit(event_type: str, payload: dict[str, object]) -> None:
        if event_type in {"running", "report_ready"}:
            print(event_type, payload)

    report = await RunEngine(report_writer=ReportWriter(ROOT / "reports" / "runs")).execute(
        EngineRequest(run_id=run_id, scenario_id="access-control", target_id="lab-web"),
        provider=MockModelProvider(),
        client=DirectToolClient(service),
        cancel_event=asyncio.Event(),
        emit=emit,
    )
    print(report.model_dump_json(indent=2))
    print(f"run_dir={ROOT / 'reports' / 'runs' / run_id}")
    print(f"target_db={store.path}")
    return run_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the HTTP core locally without VM claims")
    parser.add_argument("--mode", choices=["vulnerable", "fixed"], required=True)
    args = parser.parse_args()
    asyncio.run(run(args.mode))


if __name__ == "__main__":
    main()
