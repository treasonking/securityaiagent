"""Read-only operator policy checks; no network clients or target requests."""
from __future__ import annotations

import argparse
import json
import os

from worker.limits import limits_from_env
from worker.registry import DEFAULT_REGISTRY, load_scope_registry
from worker.scope import ScopeViolation


def main() -> None:
    parser = argparse.ArgumentParser(description="Check the worker's scope policy without HTTP")
    parser.add_argument("command", choices=["check-policy"])
    parser.add_argument("--registry", default=os.getenv("TARGET_REGISTRY_PATH", str(DEFAULT_REGISTRY)))
    args = parser.parse_args()
    try:
        registry = load_scope_registry(args.registry, expected_origin=os.getenv("TARGET_BASE_URL") or None)
        limits = limits_from_env()
        rows = []
        for target_id, target in registry.policies.items():
            for scenario in sorted(registry.profile(target_id).scenarios):
                snapshot = registry.snapshot(target_id, scenario, limits)
                rows.append({"target_id": target_id, "origin": target.base_url, "scenario_id": scenario,
                             "accounts": snapshot.accounts, "operations": snapshot.operations,
                             **snapshot.record().model_dump(mode="json")})
        print(json.dumps({"ok": True, "schema_version": "2.0", "applies": "worker startup; frozen per run",
                          "policies": rows}, indent=2, allow_nan=False))
    except (ScopeViolation, ValueError, OverflowError) as exc:
        code = exc.code if isinstance(exc, ScopeViolation) else "SCOPE_INVALID"
        print(json.dumps({"ok": False, "reason_code": code, "message": "Operator policy/global limits rejected; no HTTP sent."}))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
