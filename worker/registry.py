from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit

from worker.policy import TargetPolicy


def load_target_registry(path: str | Path) -> dict[str, TargetPolicy]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != "1.0":
        raise ValueError("unsupported target registry schema")
    policies: dict[str, TargetPolicy] = {}
    for target_id, target in payload.get("targets", {}).items():
        parsed = urlsplit(target["base_url"])
        policy = TargetPolicy(
            target_id=target_id,
            scheme=parsed.scheme,
            host=parsed.hostname or "",
            port=parsed.port or 80,
        )
        if (
            target.get("allowed_scheme") != policy.scheme
            or target.get("allowed_host") != policy.host
            or int(target.get("allowed_port")) != policy.port
        ):
            raise ValueError(f"target registry origin mismatch for {target_id}")
        policies[target_id] = policy
    if not policies:
        raise ValueError("target registry contains no targets")
    return policies
