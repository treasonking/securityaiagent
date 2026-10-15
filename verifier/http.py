"""HTTP-only rules for the registered synthetic scenario. No target-local readers."""
from __future__ import annotations

import re

from common.schemas import Evidence, Verdict, VerifiedFinding
from verifier.core import VerificationResult


PURPOSES = (
    "http-list-user-a", "http-list-user-b", "http-own-a", "http-own-b",
    "http-cross-b", "http-recheck-b", "http-recheck-a",
)
ACCOUNTS = ("user-a", "user-b", "user-a", "user-b", "user-a", "user-b", "user-a")


def verify_http_access_control(evidence: list[Evidence], *, run_id: str) -> VerificationResult:
    def inconclusive(reason: str) -> VerificationResult:
        return VerificationResult(Verdict.INCONCLUSIVE, [], [reason])

    if len(evidence) != len(PURPOSES) or tuple(item.purpose for item in evidence) != PURPOSES:
        return inconclusive("HTTP scenario evidence is missing, duplicated, or out of sequence")
    for field in ("evidence_id", "request_id"):
        values = [getattr(item, field) for item in evidence]
        if any(not value for value in values) or len(set(values)) != len(values):
            return inconclusive("duplicate or missing HTTP evidence identity")
    for item, account in zip(evidence, ACCOUNTS):
        observation = item.http_observation
        if (item.run_id != run_id or item.method != "GET" or item.account_ref != account
                or item.server_observation != "http_observation" or observation is None
                or observation.target_id != "lab-web" or observation.authenticated_account != account):
            return inconclusive("HTTP run, request account, or authenticated response identity mismatch")
    # All observations have now passed the presence check.
    a_list, b_list, own_a, own_b, cross, again_b, again_a = evidence
    a_binding = a_list.http_observation.session_binding
    b_binding = b_list.http_observation.session_binding
    if a_binding == b_binding or any(
        item.http_observation.session_binding != (a_binding if account == "user-a" else b_binding)
        for item, account in zip(evidence, ACCOUNTS)
    ):
        return inconclusive("HTTP sessions are shared or inconsistent")
    lists = []
    for item in (a_list, b_list):
        ids = item.http_observation.listed_document_ids
        if (item.path != "/documents" or item.status_code != 200 or not ids
                or item.http_observation.owner_ref != item.account_ref
                or item.http_observation.response_kind != "document_list"
                or len(set(ids)) != len(ids)
                or any(re.fullmatch(r"doc-[a-z]+-[0-9]{3}", value) is None for value in ids)):
            return inconclusive("normal owner document list is unverified")
        lists.append(set(ids))
    if lists[0] & lists[1]:
        return inconclusive("ambiguous resource ownership across accounts")
    for item, account, ids in ((own_a, "user-a", lists[0]), (own_b, "user-b", lists[1]),
                               (again_a, "user-a", lists[0]), (again_b, "user-b", lists[1])):
        obs = item.http_observation
        if (item.status_code != 200 or obs.owner_ref != account or obs.document_id not in ids
                or obs.response_kind != "private_document"
                or item.path != f"/documents/{obs.document_id}"
                or not obs.private_canary_digest or not obs.canary_present):
            return inconclusive("normal private owner control failed")
    for first, last in ((own_a, again_a), (own_b, again_b)):
        if (first.path != last.path or first.http_observation.private_canary_digest
                != last.http_observation.private_canary_digest):
            return inconclusive("owner resource changed during observation")
    if own_a.http_observation.private_canary_digest == own_b.http_observation.private_canary_digest:
        return inconclusive("canary is not distinct between normal owner documents")
    if cross.path != own_b.path:
        return inconclusive("cross-account request is not the controlled resource")
    obs = cross.http_observation
    if (cross.status_code == 200 and obs.document_id == own_b.http_observation.document_id
            and obs.response_kind == "private_document"
            and obs.owner_ref == "user-b" and obs.canary_present
            and obs.private_canary_digest == own_b.http_observation.private_canary_digest):
        verdict = Verdict.VULNERABLE
        reason = "Independent authenticated sessions and owner controls show the same private canary in user-a's cross-account response."
    elif (cross.status_code in {403, 404} and not obs.canary_present
          and obs.response_kind == "document_denied"
          and obs.private_canary_digest is None and obs.document_id is None and obs.owner_ref is None):
        verdict = Verdict.BLOCKED_BY_ACCESS_CONTROL
        reason = "The authenticated cross-account request was denied; owner and requester controls remained valid before and after it."
    else:
        return inconclusive("cross-account response is not decisive HTTP evidence")
    return VerificationResult(verdict, [VerifiedFinding(
        finding_type="cross_account_document_access", verdict=verdict,
        evidence_ids=[item.evidence_id for item in evidence], reason=reason,
    )], ["Limited to these synthetic accounts, resource, and observation time; not a site-wide safety claim."])
