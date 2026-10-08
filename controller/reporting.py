from __future__ import annotations

import json
from pathlib import Path

from common.schemas import Evidence, RunReport


class ReportWriter:
    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)

    def write(self, report: RunReport, evidence: list[Evidence] | None = None) -> tuple[Path, Path]:
        run_dir = self.output_dir / report.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        json_path = run_dir / "report.json"
        markdown_path = run_dir / "report.md"
        json_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        if evidence is not None:
            (run_dir / "evidence.json").write_text(
                json.dumps([item.model_dump(mode="json") for item in evidence], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        findings = "\n".join(
            f"- `{item.finding_type}`: **{item.verdict}** — {item.reason}" for item in report.verified_findings
        ) or "- No evidence-verified finding."
        warnings = "\n".join(f"- {item}" for item in report.warnings) or "- None."
        markdown_path.write_text(
            "\n".join(
                [
                    f"# SecurityLab run {report.run_id}",
                    "",
                    f"- Scenario: `{report.scenario_id}`",
                    f"- Target: `{report.target_id}`",
                    f"- Mode: `{report.mode}`",
                    f"- Provider: `{report.provider_mode}`",
                    f"- Tool transport: `{report.tool_transport}`",
                    f"- Status: `{report.status}`",
                    f"- Verdict: **{report.verdict}**",
                    "",
                    "## Verified findings",
                    "",
                    findings,
                    "",
                    "## Warnings and limits",
                    "",
                    warnings,
                    "",
                    "This report contains synthetic markers and redacted metadata only. It does not include cookies, passwords, API keys, worker tokens, or full response bodies.",
                ]
            ),
            encoding="utf-8",
        )
        return json_path, markdown_path
