import hashlib
import json
import shutil

import pytest

from scripts import audit_saved_verdicts as cli


@pytest.fixture
def archive(tmp_path, monkeypatch):
    copy = shutil.copytree(cli.ARCHIVE, tmp_path / "archive")
    monkeypatch.setattr(cli, "ARCHIVE", copy)
    return copy


def rewrite(path, edit):
    data = json.loads(path.read_bytes())
    edit(data)
    path.write_text(json.dumps(data), encoding="utf-8")


def cli_result(capsys, expected_exit):
    assert cli.main(["--format", "json"]) == expected_exit
    return json.loads(capsys.readouterr().out)


def test_current_product_results_ignore_historical_answers(archive, capsys, monkeypatch):
    def poison_old_results(matrix):
        for row in matrix["cases"]:
            row.update(actual_verdict="old-answer", replay={"verdict": "old-replay"}, passed=False)

    rewrite(archive / "matrix.json", poison_old_results)

    def snapshot():
        return {p.relative_to(archive): hashlib.sha256(p.read_bytes()).digest()
                for p in archive.rglob("*") if p.is_file()}

    before = snapshot()
    preview = cli.Workspace.disclosure_review
    calls = []

    def record_preview(self, run_id, confirmed_digest=None):
        assert confirmed_digest is None
        calls.append(run_id)
        return preview(self, run_id)

    monkeypatch.setattr(cli.Workspace, "disclosure_review", record_preview)
    result = cli_result(capsys, 0)
    assert snapshot() == before
    assert result["summary"] == dict(expected_runs=14, evaluated_runs=14, pre_run_rejections=2,
                                     unevaluable=0, verdict_mismatches=0, wrongly_allowed=0, wrongly_denied=0)
    assert [result["confusion"][v][v] for v in cli.VERDICTS] == [4, 4, 6]
    assert all(r["matches"] and r["preview"] == (r["expected"] == "VULNERABLE") for r in result["runs"])
    assert calls == [r["run_id"] for r in result["runs"]] + [result["omission"]["run_id"]]
    assert all(r["run_id"] is None and r["preview"] is None for r in result["pre_run"])
    probe = result["omission"]
    assert (probe["before"], probe["after"], probe["current"], probe["conclusion_reason"],
            probe["preview"], probe["preview_reason"], probe["passed"]) == (
            11, 10, "INCONCLUSIVE", "REPORT_CONTRACT_MISMATCH", False, "DRAFT_UNCONFIRMED", True)


def test_mismatches_fail_and_count_both_preview_errors(archive, capsys):
    def swap_expectations(matrix):
        for row in matrix["cases"]:
            if row["path"] == "bearer-vulnerable-mcp-normal":
                row["expected_verdict"] = "BLOCKED_BY_ACCESS_CONTROL"
            if row["path"] == "bearer-fixed-mcp-normal":
                row["expected_verdict"] = "VULNERABLE"

    rewrite(archive / "matrix.json", swap_expectations)
    summary = cli_result(capsys, 1)["summary"]
    assert summary["evaluated_runs"] == 14 and summary["verdict_mismatches"] == 2
    assert summary["wrongly_allowed"] == summary["wrongly_denied"] == 1


def test_input_errors_are_not_pre_run_rejections(archive, capsys):
    missing = archive / "cookie-fixed-mcp-normal" / "runs"
    missing.rename(missing.with_name("unavailable"))
    evidence, = (archive / "bearer-fixed-mcp-normal" / "runs").glob("*/evidence.json")
    evidence.write_text("not json")
    (archive / "cookie-vulnerable-mcp-policy_change" / "result.json").unlink()
    result = cli_result(capsys, 1)
    assert result["summary"]["evaluated_runs"] == 12
    assert result["summary"]["pre_run_rejections"] == 1
    assert result["summary"]["unevaluable"] == 3
    failed = {row["case"]: row for row in result["runs"] + result["pre_run"] if row["input_error"]}
    assert set(failed) == {"cookie-fixed-mcp-normal", "bearer-fixed-mcp-normal", "cookie-vulnerable-mcp-policy_change"}
    assert all(row["preview"] is None for row in failed.values())


def test_duplicate_cannot_replace_missing_case(archive, capsys):
    def duplicate(matrix):
        matrix["cases"][1] = matrix["cases"][0]

    rewrite(archive / "matrix.json", duplicate)
    result = cli_result(capsys, 1)
    assert [r["input_error"] for r in result["runs"][:2]] == ["DUPLICATE_CASE", "MISSING_CASE"]
    assert result["omission"]["input_error"] == "BASELINE_UNAVAILABLE"
