"""Fixed-address VM launcher for the independent cookie test API; no existing DB."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from common.service_config import KEYS, validate_config

COUNTER = Path("verification_tmp/operator_target_counter.json")


def create_app_from_env():
    values = {key: os.environ[key] for key in KEYS["operator-target"] if key in os.environ}
    validate_config("operator-target", values)
    from scripts.operator_fixture import IndependentAPI

    api = IndependentAPI("cookie", vulnerable=values["OPERATOR_TARGET_MODE"] == "vulnerable")
    api.passwords = {"alice_17": values["LAB_USER_A_PASSWORD"], "bob_2048": values["LAB_USER_B_PASSWORD"]}
    api.proofs = {"alice-17": values["OPERATOR_PROOF_A"], "2048": values["OPERATOR_PROOF_B"]}
    COUNTER.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    started = datetime.now(timezone.utc).isoformat()

    def save():
        # Operational count only. Never a verifier input or a response/body log.
        row = {"schema_version": "operator-target-counter-v1", "pid": os.getpid(),
               "started_at": started, "updated_at": datetime.now(timezone.utc).isoformat(),
               "received_http_requests": count}
        temporary = COUNTER.with_suffix(".tmp")
        temporary.write_text(json.dumps(row, indent=2), encoding="utf-8")
        temporary.replace(COUNTER)

    save()

    @api.app.middleware("http")
    async def count_received(request, call_next):
        nonlocal count
        count += 1
        save()
        return await call_next(request)

    @api.app.get("/health")
    async def health():
        return {"status": "ok", "service": "independent-operator-target", "auth": "cookie"}

    return api.app
