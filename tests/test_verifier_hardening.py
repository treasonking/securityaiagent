from __future__ import annotations

import json
import sys
from copy import deepcopy

import pytest

from common.schemas import Evidence, Verdict
from target.store import TargetStore
from verifier.cli import main as verifier_main
from verifier.core import verify_access_control


def _evidence() -> list[Evidence]:
    definitions = (
        ("safe-own-a", "user-a", "/documents/doc-a-001", 200, "SYN-A-PRIVATE-001"),
        ("safe-own-b", "user-b", "/documents/doc-b-001", 200, "SYN-B-PRIVATE-001"),
        ("safe-admin", "admin", "/documents/doc-admin-001", 200, "SYN-ADMIN-001"),
        ("attack-cross-b", "user-a", "/documents/doc-b-001", 200, "SYN-B-PRIVATE-001"),
        ("edge-missing", "user-a", "/documents/doc-missing-999", 404, None),
    )
    return [
        Evidence(
            evidence_id=f"ev-{index}",
            run_id="run-verifier",
            method="GET",
            path=path,
            status_code=status,
            account_ref=account_ref,
            request_id=f"request-{index}",
            synthetic_document_marker=marker,
            body_hash=f"hash-{index}",
            server_observation="target_log_correlated",
            purpose=purpose,
        )
        for index, (purpose, account_ref, path, status, marker) in enumerate(definitions)
    ]


@pytest.mark.parametrize(
    ("mutation", "warning"),
    [
        (lambda items: setattr(items[3], "account_ref", "admin"), "identity mismatch"),
        (lambda items: setattr(items[3], "path", "/documents/doc-admin-001"), "identity mismatch"),
        (lambda items: setattr(items[3], "run_id", "run-other"), "run_id"),
        (lambda items: items.append(deepcopy(items[3])), "duplicate"),
    ],
)
def test_verifier_rejects_wrong_account_document_run_and_duplicates(mutation, warning):
    items = _evidence()
    mutation(items)
    result = verify_access_control(items)
    assert result.verdict == Verdict.INCONCLUSIVE
    assert any(warning in item for item in result.warnings)


def test_offline_verifier_recomputes_correlation_and_rejects_forged_flag(tmp_path, monkeypatch, capsys):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    items = _evidence()
    (run_dir / "evidence.json").write_text(
        json.dumps([item.model_dump(mode="json") for item in items]), encoding="utf-8"
    )
    store = TargetStore(tmp_path / "target.sqlite3", mode="vulnerable")
    account_ids = {"user-a": "acct-a", "user-b": "acct-b", "admin": "acct-admin"}
    for item in items:
        store.record_observation(
            run_id=item.run_id,
            request_id=item.request_id,
            method=item.method,
            path=item.path,
            status_code=item.status_code,
            account_id="acct-admin" if item.purpose == "attack-cross-b" else account_ids[item.account_ref],
            marker=item.synthetic_document_marker,
        )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verifier",
            "evaluate",
            "--run-dir",
            str(run_dir),
            "--local-evidence",
            str(store.path),
        ],
    )
    verifier_main()
    output = json.loads(capsys.readouterr().out)
    assert output["verdict"] == Verdict.INCONCLUSIVE
    assert output["correlated_count"] == 4
    assert output["run_id"] == "run-verifier"
    assert output["evidence_digest"]

    wrong_store = TargetStore(tmp_path / "wrong-target.sqlite3", mode="fixed")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verifier",
            "evaluate",
            "--run-dir",
            str(run_dir),
            "--local-evidence",
            str(wrong_store.path),
        ],
    )
    verifier_main()
    wrong_output = json.loads(capsys.readouterr().out)
    assert wrong_output["verdict"] == Verdict.INCONCLUSIVE
    assert wrong_output["correlated_count"] == 0
