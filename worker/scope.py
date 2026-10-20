"""Strict operator-owned profiles and immutable, normalized per-run snapshots."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from common.schemas import PolicyRecord, ScenarioId
from worker.limits import WorkerLimits
from worker.policy import PolicyViolation, TargetPolicy


AccountRef = Literal["user-a", "user-b", "admin"]
Operation = Literal["login", "list_own_documents", "fetch_document"]
PositiveInt = Annotated[int, Field(strict=True, gt=0)]
PositiveNumber = Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False)]


class ScopeViolation(PolicyViolation):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class ProfileLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    max_requests: PositiveInt
    max_tool_calls: PositiveInt
    timeout_seconds: PositiveNumber
    run_timeout_seconds: PositiveNumber
    max_response_bytes: PositiveInt
    requests_per_second: PositiveNumber
    max_concurrency: PositiveInt
    max_runs: PositiveInt
    state_ttl_seconds: PositiveNumber


class ScopeProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    profile_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    revision: PositiveInt
    enabled: bool
    scenarios: dict[ScenarioId, tuple[AccountRef, ...]]
    operations: tuple[Operation, ...]
    limits: ProfileLimits

    @field_validator("operations", mode="before")
    @classmethod
    def operation_list(cls, value):
        if not isinstance(value, (list, tuple)) or not value or len(set(value)) != len(value):
            raise ValueError("operations must be a nonempty unique list")
        return tuple(value)

    @field_validator("scenarios", mode="before")
    @classmethod
    def account_lists(cls, value):
        if not isinstance(value, dict) or not value:
            raise ValueError("scenarios must be a nonempty mapping")
        result = {}
        for scenario, accounts in value.items():
            if not isinstance(accounts, (list, tuple)) or not accounts or len(set(accounts)) != len(accounts):
                raise ValueError("accounts must be a nonempty unique list")
            result[scenario] = tuple(accounts)
        return result

    @model_validator(mode="after")
    def scenario_ceiling(self):
        # Published scenario contract is a ceiling; profiles can only narrow it.
        if "admin" in self.scenarios.get("access-control-http", ()):
            raise ValueError("HTTP scenario only supports its two user accounts")
        return self

    def normalized(self) -> dict:
        value = self.model_dump(mode="json")
        value["operations"] = sorted(value["operations"])
        value["scenarios"] = {key: sorted(accounts) for key, accounts in sorted(value["scenarios"].items())}
        return value


@dataclass(frozen=True)
class ScopeSnapshot:
    target: TargetPolicy
    scenario_id: str
    accounts: tuple[str, ...]
    operations: tuple[str, ...]
    limits: WorkerLimits
    profile_id: str
    revision: int
    snapshot_sha256: str

    def record(self) -> PolicyRecord:
        return PolicyRecord(profile_id=self.profile_id, revision=self.revision,
                            snapshot_sha256=self.snapshot_sha256, effective_limits=asdict(self.limits))

    def authorize(self, account_ref: str, operation: str) -> None:
        if account_ref not in self.accounts:
            raise ScopeViolation("SCOPE_ACCOUNT_DENIED", "account is outside the scope profile")
        if operation not in self.operations:
            raise ScopeViolation("SCOPE_OPERATION_DENIED", "operation is outside the scope profile")

    def authorize_request(self, target: TargetPolicy, account_ref: str, operation: str, method: str, path: str) -> None:
        self.authorize(account_ref, operation)
        if target != self.target:
            raise ScopeViolation("SCOPE_ORIGIN_MISMATCH", "request target does not match the run snapshot")
        try:
            normalized = target.normalize_relative_path(path)
        except PolicyViolation:
            raise ScopeViolation("SCOPE_PATH_DENIED", "path is outside the normalized operation boundary") from None
        if path != normalized:
            raise ScopeViolation("SCOPE_PATH_DENIED", "request path must already be canonical")
        expected = {"login": ("POST", "/login"), "list_own_documents": ("GET", "/documents")}
        if operation == "fetch_document":
            if not path.startswith("/documents/"):
                raise ScopeViolation("SCOPE_PATH_DENIED", "document path is outside the registered operation")
            try:
                expected[operation] = ("GET", target.document_path(path[len("/documents/"):]))
            except PolicyViolation:
                raise ScopeViolation("SCOPE_PATH_DENIED", "document path is outside the registered operation") from None
        if expected.get(operation) != (method, path):
            raise ScopeViolation("SCOPE_PATH_DENIED", "method/path does not match the registered operation")


def make_snapshot(target: TargetPolicy, profile: ScopeProfile, scenario: str, global_limits: WorkerLimits) -> ScopeSnapshot:
    if not profile.enabled:
        raise ScopeViolation("SCOPE_DISABLED", "scope profile is disabled")
    if scenario not in profile.scenarios:
        raise ScopeViolation("SCOPE_SCENARIO_DENIED", "scenario is outside the scope profile")
    values = {}
    for name, global_value in asdict(global_limits).items():
        profile_value = getattr(profile.limits, name)
        # Legacy global zero means unlimited rate; the positive profile still caps it.
        values[name] = profile_value if name == "requests_per_second" and global_value == 0 else min(global_value, profile_value)
    if scenario == "access-control-http":
        values["max_requests"] = min(values["max_requests"], 9)
        values["max_tool_calls"] = min(values["max_tool_calls"], 10)
    effective = WorkerLimits(**values)
    canonical = json.dumps({"schema_version": "2.0", "target_id": target.target_id, "origin": target.base_url,
                            "profile": profile.normalized(), "scenario_id": scenario,
                            "effective_limits": asdict(effective)}, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return ScopeSnapshot(target, scenario, tuple(sorted(profile.scenarios[scenario])), tuple(sorted(profile.operations)),
                         effective, profile.profile_id, profile.revision, hashlib.sha256(canonical.encode()).hexdigest())
