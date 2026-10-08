from __future__ import annotations

import pytest

from worker.policy import PolicyViolation, TargetPolicy


def policy() -> TargetPolicy:
    return TargetPolicy(target_id="lab-web", scheme="http", host="10.78.0.30", port=8080)


@pytest.mark.parametrize(
    "value",
    [
        "http://10.78.0.30:8080/documents/a",
        "//10.78.0.30:8080/documents/a",
        "/%2f%2fevil.example/a",
        "/documents/../admin",
        "/documents/%2e%2e/admin",
        "/user@evil.example/path",
        "/documents/a?next=http://evil.example",
        "/\\evil.example/path",
    ],
)
def test_absolute_and_encoded_scope_bypasses_are_rejected(value):
    with pytest.raises(PolicyViolation):
        policy().normalize_relative_path(value)


def test_only_fixture_document_ids_are_accepted():
    assert policy().document_path("doc-b-001") == "/documents/doc-b-001"
    for value in ("../../etc/passwd", "doc-b-001%2f..", "[::1]", "doc-b-1"):
        with pytest.raises(PolicyViolation):
            policy().document_path(value)


def test_hostname_and_non_http_registry_entries_are_rejected():
    with pytest.raises(PolicyViolation):
        TargetPolicy(target_id="bad", scheme="https", host="example.com", port=443)
    with pytest.raises(PolicyViolation):
        TargetPolicy(target_id="bad", scheme="http", host="example.com", port=8080)
