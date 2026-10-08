from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from common.schemas import Evidence
from verifier.core import verify_access_control


def _resolve_database(value: Path) -> Path:
    return value / "target.sqlite3" if value.is_dir() else value


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline target-log correlation for a completed run")
    parser.add_argument("command", choices=["evaluate"])
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--local-evidence", type=Path, required=True)
    args = parser.parse_args()
    evidence_path = args.run_dir / "evidence.json"
    database_path = _resolve_database(args.local_evidence)
    if not evidence_path.exists():
        raise SystemExit(f"missing sanitized controller evidence: {evidence_path}")
    if not database_path.exists():
        raise SystemExit(f"missing target-local database: {database_path}")
    evidence = [Evidence.model_validate(item) for item in json.loads(evidence_path.read_text(encoding="utf-8"))]
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        for item in evidence:
            observation = connection.execute(
                "SELECT request_id, path, status_code, marker FROM observations WHERE request_id=?",
                (item.request_id,),
            ).fetchone()
            if (
                observation
                and observation["path"] == item.path
                and observation["status_code"] == item.status_code
                and observation["marker"] == item.synthetic_document_marker
            ):
                item.server_observation = "target_log_correlated"
    result = verify_access_control(evidence)
    output = {
        "verdict": result.verdict,
        "verified_findings": [item.model_dump(mode="json") for item in result.findings],
        "warnings": result.warnings,
        "evidence_count": len(evidence),
        "correlated_count": sum(item.server_observation == "target_log_correlated" for item in evidence),
    }
    output_path = args.run_dir / "offline_verification.json"
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
