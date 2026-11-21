from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from common.schemas import Evidence, Verdict, VerifiedFinding


_EXPECTED = {
    "safe-own-a": ("user-a", "/documents/doc-a-001", 200, "SYN-A-PRIVATE-001"),
    "safe-own-b": ("user-b", "/documents/doc-b-001", 200, "SYN-B-PRIVATE-001"),
    "safe-admin": ("admin", "/documents/doc-admin-001", 200, "SYN-ADMIN-001"),
    "attack-cross-b": ("user-a", "/documents/doc-b-001", None, None),
    "edge-missing": ("user-a", "/documents/doc-missing-999", 404, None),
}

_RECOMMENDATIONS = {
    Verdict.VULNERABLE: [
        "Enforce owner-or-admin authorization on the document detail query.",
        "Restart the target in fixed mode, reset synthetic state, and rerun the identical scenario.",
    ],
    Verdict.BLOCKED_BY_ACCESS_CONTROL: [
        "Retain the owner-or-admin authorization regression test.",
        "Keep target-local log correlation in the repeatable evidence procedure.",
    ],
    Verdict.INCONCLUSIVE: [
        "Resolve the recorded control, correlation, or transport failure and rerun without expanding scope."
    ],
}

CORRELATION_REQUIRED_WARNING = (
    "target server-log correlation is required before a final access-control verdict"
)


def recommendations_for_verdict(verdict: Verdict) -> list[str]:
    return list(_RECOMMENDATIONS[verdict])


@dataclass(frozen=True)
class VerificationResult:
    verdict: Verdict
    findings: list[VerifiedFinding]
    warnings: list[str]


def evidence_identity_digest(evidence: list[Evidence]) -> str:
    fields = (
        "evidence_id",
        "run_id",
        "method",
        "path",
        "status_code",
        "account_ref",
        "request_id",
        "synthetic_document_marker",
        "body_hash",
        "purpose",
    )
    canonical = [
        {**{field: getattr(item, field) for field in fields},
         **({"http_observation": item.http_observation.model_dump(mode="json")} if item.http_observation else {})}
        for item in sorted(evidence, key=lambda value: value.evidence_id)
    ]
    encoded = json.dumps(
        canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def verify_access_control(evidence: list[Evidence]) -> VerificationResult:
    purposes = [item.purpose for item in evidence]
    if len(purposes) != len(set(purposes)):
        return VerificationResult(Verdict.INCONCLUSIVE, [], ["duplicate evidence purpose rejected"])
    request_ids = [item.request_id for item in evidence]
    if len(request_ids) != len(set(request_ids)):
        return VerificationResult(Verdict.INCONCLUSIVE, [], ["duplicate request_id rejected"])
    evidence_ids = [item.evidence_id for item in evidence]
    if len(evidence_ids) != len(set(evidence_ids)):
        return VerificationResult(Verdict.INCONCLUSIVE, [], ["duplicate evidence_id rejected"])
    run_ids = {item.run_id for item in evidence}
    if len(run_ids) != 1:
        return VerificationResult(Verdict.INCONCLUSIVE, [], ["mixed or missing run_id rejected"])
    if set(purposes) != set(_EXPECTED):
        return VerificationResult(
            Verdict.INCONCLUSIVE,
            [],
            ["evidence set does not exactly match the published scenario"],
        )
    by_purpose = {item.purpose: item for item in evidence}
    warnings: list[str] = []
    for purpose, (account_ref, path, status, marker) in _EXPECTED.items():
        item = by_purpose[purpose]
        if item.method != "GET" or item.account_ref != account_ref or item.path != path:
            return VerificationResult(
                verdict=Verdict.INCONCLUSIVE,
                findings=[],
                warnings=[f"evidence identity mismatch: {purpose}"],
            )
        if status is not None and (
            item.status_code != status or item.synthetic_document_marker != marker
        ):
            return VerificationResult(
                verdict=Verdict.INCONCLUSIVE,
                findings=[],
                warnings=[f"required scenario observation failed: {purpose}"],
            )
    attack = by_purpose["attack-cross-b"]
    decision_evidence = [by_purpose["safe-own-b"], attack]
    if any(item.server_observation != "target_log_correlated" for item in decision_evidence):
        return VerificationResult(
            verdict=Verdict.INCONCLUSIVE,
            findings=[],
            warnings=warnings + [CORRELATION_REQUIRED_WARNING],
        )
    if attack.status_code == 200 and attack.synthetic_document_marker == "SYN-B-PRIVATE-001":
        finding = VerifiedFinding(
            finding_type="cross_account_document_access",
            verdict=Verdict.VULNERABLE,
            evidence_ids=[by_purpose["safe-own-b"].evidence_id, attack.evidence_id],
            reason="Authenticated user-a retrieved user-b's exact synthetic private marker after the user-b control succeeded.",
        )
        return VerificationResult(verdict=Verdict.VULNERABLE, findings=[finding], warnings=warnings)
    if attack.status_code in {403, 404} and attack.synthetic_document_marker is None:
        finding = VerifiedFinding(
            finding_type="cross_account_document_access",
            verdict=Verdict.BLOCKED_BY_ACCESS_CONTROL,
            evidence_ids=[by_purpose["safe-own-b"].evidence_id, attack.evidence_id],
            reason="The valid user-b control succeeded while the same resource was denied to authenticated user-a.",
        )
        return VerificationResult(
            verdict=Verdict.BLOCKED_BY_ACCESS_CONTROL,
            findings=[finding],
            warnings=warnings,
        )
    return VerificationResult(
        verdict=Verdict.INCONCLUSIVE,
        findings=[],
        warnings=warnings + [f"cross-account request returned non-decisive status {attack.status_code}"],
    )
