"""Audit the published independent API archive offline with the current Workspace."""
import argparse
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from controller.workspace import RUN, Workspace, WorkspaceError, checked, read_json


ARCHIVE = Path(__file__).resolve().parents[1] / "reports/independent_api_validation_20261113"
VERDICTS = ("VULNERABLE", "BLOCKED_BY_ACCESS_CONTROL", "INCONCLUSIVE")
TRANSPORTS = ("function", "mcp")
NORMAL = [f"{auth}-{mode}-{t}-normal" for auth in ("cookie", "bearer")
          for mode in ("vulnerable", "fixed") for t in TRANSPORTS]
CASES = NORMAL + [f"cookie-vulnerable-{t}-{case}" for case in
                  ("policy_change", "budget2", "owner_mismatch", "proof_rotation") for t in TRANSPORTS]
INPUTS = ("report.json", "verification_contract.json", "evidence.json", "candidate_execution.json")
DRAFT_DENIALS = {"DRAFT_BLOCKED", "DRAFT_NOT_COMPLETED", "DRAFT_UNCONFIRMED"}


class ArchiveError(ValueError):
    """An error whose message is a safe, fixed code for the public report."""


def observe(workspace, run_id):
    try:
        conclusion = workspace.run_view(run_id)["conclusion"]
    except WorkspaceError as exc:
        conclusion = {"verdict": None, "state": "unavailable", "reason_code": exc.code}
    try:
        workspace.disclosure_review(run_id)  # Preview only, without a confirmation digest.
        preview, reason = True, None
    except WorkspaceError as exc:
        preview, reason = False, exc.code
    return dict(current=conclusion["verdict"], state=conclusion["state"],
                conclusion_reason=conclusion["reason_code"], preview=preview, preview_reason=reason)


def stage_run(root, name, run_id, sums, workspace):
    # Run both product reads against the same immutable input bytes. A digest here
    # identifies the published fixture, not its author.
    dest = workspace.reports / run_id
    if dest.exists():
        raise ArchiveError("DUPLICATE_RUN")
    dest.mkdir(parents=True)
    for filename in INPUTS:
        parts = (name, "runs", run_id, filename)
        source = checked(root, *parts)
        data = source.read_bytes()
        if sha256(data).hexdigest() != sums.get("/".join(parts)):
            raise ArchiveError("ARCHIVE_INPUT_MISMATCH")
        (dest / filename).write_bytes(data)


def verify_pre_run(root, name, entry):
    receipt = read_json(root, name, "result.json")
    expected = {"run_id": None, "expected_verdict": None, "status": "REJECTED_BEFORE_RUN",
                "reason_code": "WORKER_POLICY_CHANGED", "claimed_count": 0}
    if not all(k in record and record[k] == v for record in (entry, receipt)
               for k, v in expected.items()):
        raise ArchiveError("PRE_RUN_RECORD_MISMATCH")
    runs = checked(root, name, "runs")
    if runs.exists() and any(runs.iterdir()):
        raise ArchiveError("UNEXPECTED_RUN")


def evaluate(root, workspace, name, entries, sums):
    row = dict(case=name, run_id=None, expected=None, current=None, matches=None, preview=None,
               expected_preview=None, input_error=None)
    try:
        if len(entries) != 1:
            raise ArchiveError("DUPLICATE_CASE" if entries else "MISSING_CASE")
        entry, = entries
        if name.endswith("-policy_change"):
            verify_pre_run(root, name, entry)
            row["pre_run_reason"] = "WORKER_POLICY_CHANGED"
            return row
        if entry.get("expected_verdict") not in VERDICTS:
            raise ArchiveError("INVALID_EXPECTATION")
        row["expected"] = entry["expected_verdict"]
        run_id = entry.get("run_id")
        if not isinstance(run_id, str) or not RUN.fullmatch(run_id):
            raise ArchiveError("INVALID_RUN_ID")
        row["run_id"] = run_id
        stage_run(root, name, run_id, sums, workspace)
        row.update(observe(workspace, run_id))
        if row["current"] is None or (not row["preview"] and row["preview_reason"] not in DRAFT_DENIALS):
            raise ArchiveError("PRODUCT_INPUT_ERROR")
        row["matches"] = row["current"] == row["expected"]
        row["expected_preview"] = row["expected"] == "VULNERABLE"
    except ArchiveError as exc:
        row["input_error"] = str(exc)
    except (OSError, WorkspaceError, TypeError, KeyError):
        row["input_error"] = "ARCHIVE_INPUT_UNREADABLE"
    return row


def omission_control(workspace, baseline):
    control = dict(case=baseline["case"], run_id=baseline["run_id"], passed=False)
    if baseline["input_error"] or baseline["current"] != "VULNERABLE" or not baseline["preview"]:
        return dict(control, input_error="BASELINE_UNAVAILABLE")
    # Only the temporary staged copy is changed, after the original case was evaluated.
    evidence = workspace.reports / baseline["run_id"] / "evidence.json"
    items = json.loads(evidence.read_bytes())
    control.update(before=len(items), after=len(items) - 1)
    evidence.write_text(json.dumps(items[:-1]), encoding="utf-8")
    control.update(observe(workspace, baseline["run_id"]))
    withheld = control["state"] == "withheld" and control["current"] == "INCONCLUSIVE"
    unreadable = control["conclusion_reason"] == "SAVED_INPUT_UNREADABLE"
    control["passed"] = (withheld or unreadable) and control["preview"] is False
    return control


def audit(root):
    by_case = defaultdict(list)
    errors = []
    try:
        entries = read_json(root, "matrix.json")["cases"]
        if not isinstance(entries, list):
            raise ArchiveError("INVALID_MATRIX")
        for entry in entries:
            if isinstance(entry, dict) and entry.get("path") in CASES:
                by_case[entry["path"]].append(entry)
            else:
                errors.append("UNKNOWN_CASE")
    except (ValueError, TypeError, KeyError, OSError):
        errors.append("INVALID_MATRIX")
    try:
        sums = read_json(root, "SHA256SUMS.json")
        if not isinstance(sums, dict):
            raise ArchiveError("INVALID_CHECKSUMS")
    except (ValueError, OSError):
        sums = {}
        errors.append("INVALID_CHECKSUMS")

    with TemporaryDirectory(prefix="securityai-verdict-audit-") as temp:
        workspace = Workspace(profiles={}, state_path=Path(temp) / "state", reports_path=Path(temp) / "runs",
                              policy_client=None, client_factory=None)
        rows = [evaluate(root, workspace, name, by_case[name], sums) for name in CASES]
        control = omission_control(workspace, rows[0])

    table = {v: dict.fromkeys(VERDICTS, 0) for v in VERDICTS}
    runs = [r for r in rows if not r["case"].endswith("-policy_change")]
    policies = [r for r in rows if r["case"].endswith("-policy_change")]
    evaluated = [r for r in runs if not r["input_error"]]
    for row in evaluated:
        table[row["expected"]][row["current"]] += 1
    summary = dict(expected_runs=len(runs), evaluated_runs=len(evaluated),
                   pre_run_rejections=sum("pre_run_reason" in r for r in policies),
                   unevaluable=sum(bool(r["input_error"]) for r in rows),
                   verdict_mismatches=sum(not r["matches"] for r in evaluated),
                   wrongly_allowed=sum(r["preview"] and not r["expected_preview"] for r in evaluated),
                   wrongly_denied=sum(not r["preview"] and r["expected_preview"] for r in evaluated))
    passed = not errors and control["passed"] and not any(summary[k] for k in
              ("unevaluable", "verdict_mismatches", "wrongly_allowed", "wrongly_denied"))
    return dict(archive="independent_api_validation_20261113", passed=passed, summary=summary,
                confusion=table, runs=runs, pre_run=policies, omission=control, input_errors=errors)


def markdown(result):
    summary = result["summary"]
    lines = ["# 저장된 합성 사례 판정 감사", "",
             f"감사 결과 **{'통과' if result['passed'] else '실패'}**. 저장 run 평가 "
             f"{summary['evaluated_runs']}/{summary['expected_runs']}건. 실행 전 거절 "
             f"{summary['pre_run_rejections']}건은 판정·미리보기 분모에서 제외했다.", "",
             "| 사례 | 기대 판정 | 현재 결론 | 일치 | 초안 미리보기 | 사유 |",
             "|---|---|---|---|---|---|"]
    for r in result["runs"]:
        allowed = {True: "허용", False: "거절", None: "평가 불가"}[r["preview"]]
        match = {True: "예", False: "아니오", None: "—"}[r["matches"]]
        reason = r["input_error"] or r.get("preview_reason") or r.get("conclusion_reason")
        lines.append(f"| {r['case']} | {r['expected'] or '—'} | {r['current'] or '—'} | {match} | {allowed} | {reason} |")
    lines.extend(["", "## 기대 판정 × 현재 결론", "", "| 기대 ＼ 현재 | " + " | ".join(VERDICTS) + " |",
                  "|---|---:|---:|---:|"])
    for v, counts in result["confusion"].items():
        lines.append("| " + v + " | " + " | ".join(str(counts[k]) for k in VERDICTS) + " |")
    lines.extend(["", f"평가 가능한 {summary['evaluated_runs']}건 중 잘못 허용한 초안 {summary['wrongly_allowed']}건, "
                  f"잘못 거절한 초안 {summary['wrongly_denied']}건. 전체 사례 중 평가 불가 {summary['unevaluable']}건.",
                  "", "## 실행 전 정책 거절 확인", ""])
    for row in result["pre_run"]:
        lines.append(f"- {row['case']} · {row['input_error'] or row['pre_run_reason']}")
    probe = result["omission"]
    lines.extend(["", "## 임시 사본에서 증거 한 건 누락", "",
                  f"{probe['case']} · {'통과' if probe['passed'] else '실패'}"])
    if "current" in probe:
        lines.append(f"- 증거 {probe['before']} → {probe['after']}개. 현재 결론 {probe['current'] or '평가 불가'} "
                     f"({probe['conclusion_reason']}). 초안 미리보기 "
                     f"{'허용' if probe['preview'] else '거절'} ({probe['preview_reason'] or '—'}).")
    else:
        lines.append(f"- {probe['input_error']}")
    lines.extend(f"- {error}" for error in result["input_errors"])
    lines.extend(["", "이 수치는 2026-11-13에 저장한 합성 사례의 오프라인 회귀 결과다. "
                  "모델 탐지율, 외부 서비스 성능, 실제 초안 다운로드는 평가 범위 밖이다."])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args(argv)
    result = audit(ARCHIVE)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.format == "json" else markdown(result))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
