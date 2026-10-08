from __future__ import annotations

import base64
import hashlib
import hmac


class SessionSigner:
    owner_id = "local-user"

    def __init__(self, secret: str) -> None:
        if len(secret) < 24:
            raise ValueError("APP_SESSION_SECRET must contain at least 24 characters")
        self.secret = secret.encode("utf-8")

    def _signature(self, value: str) -> str:
        digest = hmac.new(self.secret, value.encode("utf-8"), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip("=")

    def issue(self) -> str:
        payload = base64.urlsafe_b64encode(self.owner_id.encode()).decode().rstrip("=")
        return f"{payload}.{self._signature(payload)}"

    def validate(self, token: str | None) -> str | None:
        if not token or "." not in token:
            return None
        payload, signature = token.rsplit(".", maxsplit=1)
        if not hmac.compare_digest(signature, self._signature(payload)):
            return None
        try:
            owner = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)).decode()
        except Exception:
            return None
        return owner if owner == self.owner_id else None

    def csrf(self, token: str) -> str:
        return self._signature(f"csrf:{token}")

    def validate_csrf(self, token: str, csrf: str | None) -> bool:
        return bool(csrf and hmac.compare_digest(self.csrf(token), csrf))
