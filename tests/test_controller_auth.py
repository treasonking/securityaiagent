from controller.auth import SessionSigner
from controller.repository import Repository


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


def test_session_revocation_survives_same_secret_restart(tmp_path, monkeypatch):
    now = 2_000
    monkeypatch.setattr("controller.auth.time.time", lambda: now)
    database = tmp_path / "controller.sqlite3"
    repository = Repository(database)
    secret = "test-session-secret-at-least-24-characters"
    signer = SessionSigner(secret, ttl_seconds=60, store=repository)
    revoked = signer.issue()
    preserved = signer.issue()
    signer.revoke(revoked)

    restarted_repository = Repository(database)
    restarted = SessionSigner(secret, ttl_seconds=60, store=restarted_repository)
    assert restarted.validate(revoked) is None
    assert restarted.validate(preserved) == "local-user"

    raw_database = database.read_bytes().decode("utf-8", errors="ignore")
    decoded = signer._decode(preserved)
    assert decoded is not None
    assert decoded[0] not in raw_database
