from __future__ import annotations

from pathlib import Path

import httpx

from target.app import create_app as create_target_app
from target.store import TargetStore
from worker.policy import TargetPolicy
from worker.service import ToolService, WorkerLimits


def make_service(tmp_path: Path, mode: str, *, max_requests: int = 30) -> tuple[ToolService, TargetStore]:
    store = TargetStore(tmp_path / f"target-{mode}.sqlite3", mode=mode)
    target_app = create_target_app(store)
    service = ToolService(
        policies={
            "lab-web": TargetPolicy(
                target_id="lab-web",
                scheme="http",
                host="10.78.0.30",
                port=8080,
            )
        },
        accounts={
            "user-a": ("user_a", "local-a-password"),
            "user-b": ("user_b", "local-b-password"),
            "admin": ("admin", "local-admin-password"),
        },
        limits=WorkerLimits(max_requests=max_requests, requests_per_second=0),
        transport=httpx.ASGITransport(app=target_app),
        observation_reader=store.observation,
    )
    return service, store
