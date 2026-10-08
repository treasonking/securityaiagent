from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Verdict(StrEnum):
    VULNERABLE = "VULNERABLE"
    BLOCKED_BY_ACCESS_CONTROL = "BLOCKED_BY_ACCESS_CONTROL"
    INCONCLUSIVE = "INCONCLUSIVE"


class RunStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    run_id: str
    method: Literal["GET", "POST"]
    path: str
    status_code: int
    account_ref: str
    request_id: str
    synthetic_document_marker: str | None = None
    body_hash: str
    server_observation: str
    purpose: str
    created_at: str = Field(default_factory=utc_now)


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    run_id: str
    data: dict[str, Any] = Field(default_factory=dict)
    evidence: Evidence | None = None
    error_code: str | None = None
    message: str | None = None


class FindingCandidate(BaseModel):
    finding_type: str
    rationale: str
    source: Literal["mock_provider", "openai_provider"]


class VerifiedFinding(BaseModel):
    finding_type: str
    verdict: Verdict
    evidence_ids: list[str]
    reason: str


class ModelUsage(BaseModel):
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class RunReport(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    run_id: str
    scenario_id: str
    target_id: str
    mode: Literal["vulnerable", "fixed", "unknown"]
    provider_mode: Literal["mock", "openai"]
    model_id: str | None = None
    tool_transport: Literal["function", "mcp"]
    started_at: str
    finished_at: str
    status: RunStatus
    verdict: Verdict
    finding_candidates: list[FindingCandidate]
    verified_findings: list[VerifiedFinding]
    evidence_ids: list[str]
    limits_used: dict[str, int | float]
    model_usage: ModelUsage
    warnings: list[str]
    environment: dict[str, str]
    recommendations: list[str]
