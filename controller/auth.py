from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time


class SessionSigner:
    owner_id = "local-user"

    def __init__(self, secret: str, *, ttl_seconds: int = 3600) -> None:
        if len(secret) < 24:
            raise ValueError("APP_SESSION_SECRET must contain at least 24 characters")
        if ttl_seconds <= 0:
            raise ValueError("session ttl must be positive")
        self.secret = secret.encode("utf-8")
        self.ttl_seconds = ttl_seconds
        self._revoked: dict[str, int] = {}

    def _signature(self, value: str) -> str:
        digest = hmac.new(self.secret, value.encode("utf-8"), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip("=")

    def issue(self) -> str:
        expires_at = int(time.time()) + self.ttl_seconds
        nonce = secrets.token_urlsafe(24)
        value = f"{self.owner_id}|{nonce}|{expires_at}"
        payload = base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")
        return f"{payload}.{self._signature(payload)}"

    def validate(self, token: str | None) -> str | None:
        if not token or "." not in token:
            return None
        payload, signature = token.rsplit(".", maxsplit=1)
        if not hmac.compare_digest(signature, self._signature(payload)):
            return None
        try:
            decoded = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode()
            owner, nonce, expires_raw = decoded.split("|", maxsplit=2)
            expires_at = int(expires_raw)
        except Exception:
            return None
        now = int(time.time())
        self._purge_revoked(now)
        if owner != self.owner_id or expires_at <= now or nonce in self._revoked:
            return None
        return owner

    def revoke(self, token: str | None) -> None:
        decoded = self._decode(token)
        if decoded is not None:
            nonce, expires_at = decoded
            self._revoked[nonce] = expires_at

    def _decode(self, token: str | None) -> tuple[str, int] | None:
        if not token or "." not in token:
            return None
        payload, signature = token.rsplit(".", maxsplit=1)
        if not hmac.compare_digest(signature, self._signature(payload)):
            return None
        try:
            decoded = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode()
            owner, nonce, expires_raw = decoded.split("|", maxsplit=2)
            if owner != self.owner_id:
                return None
            return nonce, int(expires_raw)
        except Exception:
            return None

    def _purge_revoked(self, now: int) -> None:
        self._revoked = {nonce: expiry for nonce, expiry in self._revoked.items() if expiry > now}

    def csrf(self, token: str) -> str:
        return self._signature(f"csrf:{token}")

    def validate_csrf(self, token: str, csrf: str | None) -> bool:
        return bool(csrf and hmac.compare_digest(self.csrf(token), csrf))
