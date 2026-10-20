from __future__ import annotations

import math
import os
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class WorkerLimits:
    max_requests: int = 30
    max_tool_calls: int = 12
    timeout_seconds: float = 5.0
    run_timeout_seconds: float = 180.0
    max_response_bytes: int = 65_536
    requests_per_second: float = 2.0
    max_concurrency: int = 1
    max_runs: int = 100
    state_ttl_seconds: float = 600.0

    def __post_init__(self) -> None:
        integers = {"max_requests", "max_tool_calls", "max_response_bytes", "max_concurrency", "max_runs"}
        for name, value in asdict(self).items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("worker limits must be finite numbers, not booleans")
            if name in integers and type(value) is not int:
                raise ValueError("worker count and byte limits must be integers")
            if value < 0 or (value == 0 and name != "requests_per_second"):
                raise ValueError("worker limits must be positive (global rate zero means no global rate cap)")


def limits_from_env() -> WorkerLimits:
    # Used by both worker startup and the offline policy checker.
    return WorkerLimits(
        max_requests=int(os.getenv("HTTP_MAX_REQUESTS", "30")),
        max_tool_calls=int(os.getenv("AGENT_MAX_STEPS", "12")),
        timeout_seconds=float(os.getenv("HTTP_TIMEOUT_SECONDS", "5")),
        run_timeout_seconds=float(os.getenv("RUN_TIMEOUT_SECONDS", "180")),
        max_response_bytes=int(os.getenv("HTTP_MAX_RESPONSE_BYTES", "65536")),
        requests_per_second=float(os.getenv("HTTP_REQUESTS_PER_SECOND", "2")),
        max_concurrency=int(os.getenv("HTTP_MAX_CONCURRENCY", "1")),
        max_runs=int(os.getenv("WORKER_MAX_RUNS", "100")),
        state_ttl_seconds=float(os.getenv("WORKER_STATE_TTL_SECONDS", "600")),
    )
