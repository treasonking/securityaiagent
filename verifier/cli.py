from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import httpx

from common.schemas import Evidence
from verifier.core import evidence_identity_digest, verify_access_control


_ACCOUNT_IDS = {"user-a": "acct-a", "user-b": "acct-b", "admin": "acct-admin"}


def _resolve_database(value: Path) -> Path:
    return value / "target.sqlite3" if value.is_dir() else value


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline target-log correlation for a completed run")
    parser.add_argument("command", choices=["evaluate"])
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--local-evidence", type=Path, required=True)
    parser.add_argument("--controller-url")
    parser.add_argument("--import-token")
    args = parser.parse_args()
    evidence_path = args.run_dir / "evidence.json"
    report_path = args.run_dir / "report.json"
    if report_path.exists() and json.loads(report_path.read_text(encoding="utf-8")).get("scenario_id") != "access-control":
        raise SystemExit("offline evaluation is only for the log-based scenario")
    database_path = _resolve_database(args.local_evidence)
    if not evidence_path.exists():
        raise SystemExit(f"missing sanitized controller evidence: {evidence_path}")
    if not database_path.exists():
        raise SystemExit(f"missing target-local database: {database_path}")
    evidence = [Evidence.model_validate(item) for item in json.loads(evidence_path.read_text(encoding="utf-8"))]
    for item in evidence:
        item.server_observation = "target_log_offline_pending"
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        for item in evidence:
            observations = connection.execute(
                """
                SELECT run_id, request_id, method, path, status_code, account_id, marker
                FROM observations WHERE request_id=?
                """,
                (item.request_id,),
            ).fetchall()
            if (
                len(observations) == 1
                and (observation := observations[0])
                and observation["run_id"] == item.run_id
                and observation["request_id"] == item.request_id
                and observation["method"] == item.method
                and observation["path"] == item.path
                and observation["status_code"] == item.status_code
                and observation["account_id"] == _ACCOUNT_IDS.get(item.account_ref)
                and observation["marker"] == item.synthetic_document_marker
            ):
                item.server_observation = "target_log_correlated"
    result = verify_access_control(evidence)
    run_ids = sorted({item.run_id for item in evidence})
    output = {
        "run_id": run_ids[0] if len(run_ids) == 1 else None,
        "verdict": result.verdict,
        "verified_findings": [item.model_dump(mode="json") for item in result.findings],
        "warnings": result.warnings,
        "evidence_count": len(evidence),
        "correlated_count": sum(item.server_observation == "target_log_correlated" for item in evidence),
        "evidence_digest": evidence_identity_digest(evidence),
    }
    output_path = args.run_dir / "offline_verification.json"
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    if bool(args.controller_url) != bool(args.import_token):
        raise SystemExit("--controller-url and --import-token must be supplied together")
    if args.controller_url:
        with httpx.Client(trust_env=False, follow_redirects=False, timeout=10) as client:
            response = client.post(
                f"{args.controller_url.rstrip('/')}/api/internal/offline-verification",
                headers={"Authorization": f"Bearer {args.import_token}"},
                json=output,
            )
        if response.status_code != 200:
            raise SystemExit(f"controller import failed: HTTP {response.status_code}")
        print(json.dumps(response.json(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
