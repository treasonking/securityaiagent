from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from typing import Protocol


class SessionStore(Protocol):
    def register_session(self, nonce_hash: str, expires_at: int, now: int) -> None: ...

    def session_is_active(self, nonce_hash: str, expires_at: int, now: int) -> bool: ...

    def revoke_session(self, nonce_hash: str, expires_at: int) -> None: ...


class SessionSigner:
    owner_id = "local-user"

    def __init__(
        self,
        secret: str,
        *,
        ttl_seconds: int = 3600,
        store: SessionStore | None = None,
    ) -> None:
        if len(secret) < 24:
            raise ValueError("APP_SESSION_SECRET must contain at least 24 characters")
        if ttl_seconds <= 0:
            raise ValueError("session ttl must be positive")
        self.secret = secret.encode("utf-8")
        self.ttl_seconds = ttl_seconds
        self.store = store
        self._revoked: dict[str, int] = {}

    def _signature(self, value: str) -> str:
        digest = hmac.new(self.secret, value.encode("utf-8"), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip("=")

    def issue(self) -> str:
        now = int(time.time())
        expires_at = now + self.ttl_seconds
        nonce = secrets.token_urlsafe(24)
        if self.store is not None:
            self.store.register_session(self._nonce_hash(nonce), expires_at, now)
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
        if owner != self.owner_id or expires_at <= now:
            return None
        if self.store is not None:
            if not self.store.session_is_active(self._nonce_hash(nonce), expires_at, now):
                return None
        else:
            self._purge_revoked(now)
            if nonce in self._revoked:
                return None
        return owner

    def revoke(self, token: str | None) -> None:
        decoded = self._decode(token)
        if decoded is not None:
            nonce, expires_at = decoded
            if self.store is not None:
                self.store.revoke_session(self._nonce_hash(nonce), expires_at)
            else:
                self._revoked[nonce] = expires_at

    @staticmethod
    def _nonce_hash(nonce: str) -> str:
        return hashlib.sha256(nonce.encode("utf-8")).hexdigest()

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
