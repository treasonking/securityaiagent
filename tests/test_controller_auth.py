from controller.auth import SessionSigner


def test_session_tokens_are_random_expire_and_can_be_revoked(monkeypatch):
    now = 1_000
    monkeypatch.setattr("controller.auth.time.time", lambda: now)
    signer = SessionSigner("test-session-secret-at-least-24-characters", ttl_seconds=10)
    first = signer.issue()
    second = signer.issue()
    assert first != second
    assert signer.validate(first) == "local-user"
    signer.revoke(first)
    assert signer.validate(first) is None
    assert signer.validate(second) == "local-user"
    now = 1_011
    assert signer.validate(second) is None
