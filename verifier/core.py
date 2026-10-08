from __future__ import annotations

from dataclasses import dataclass

from common.schemas import Evidence, Verdict, VerifiedFinding


@dataclass(frozen=True)
class VerificationResult:
    verdict: Verdict
    findings: list[VerifiedFinding]
    warnings: list[str]


def verify_access_control(evidence: list[Evidence]) -> VerificationResult:
    by_purpose = {item.purpose: item for item in evidence}
    warnings: list[str] = []
    required_controls = {
        "safe-own-a": (200, "SYN-A-PRIVATE-001"),
        "safe-own-b": (200, "SYN-B-PRIVATE-001"),
        "safe-admin": (200, "SYN-ADMIN-001"),
    }
    for purpose, (status, marker) in required_controls.items():
        item = by_purpose.get(purpose)
        if item is None or item.status_code != status or item.synthetic_document_marker != marker:
            return VerificationResult(
                verdict=Verdict.INCONCLUSIVE,
                findings=[],
                warnings=[f"required control failed: {purpose}"],
            )
    edge = by_purpose.get("edge-missing")
    if edge is None or edge.status_code != 404:
        warnings.append("EDGE-01 did not return the expected not-found control")
    attack = by_purpose.get("attack-cross-b")
    if attack is None:
        return VerificationResult(
            verdict=Verdict.INCONCLUSIVE,
            findings=[],
            warnings=warnings + ["cross-account evidence is missing"],
        )
    decision_evidence = [by_purpose["safe-own-b"], attack]
    if any(item.server_observation != "target_log_correlated" for item in decision_evidence):
        return VerificationResult(
            verdict=Verdict.INCONCLUSIVE,
            findings=[],
            warnings=warnings + ["target server-log correlation is required before a final access-control verdict"],
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
