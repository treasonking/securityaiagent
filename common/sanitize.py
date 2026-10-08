from __future__ import annotations

import re
from hashlib import sha256
from typing import Any


_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+\-/]+=*"),
    re.compile(r"(?i)(password|worker_token|api_key|cookie|authorization)\s*[:=]\s*[^\s,;]+"),
)


def redact_text(value: str, *, max_length: int = 4000) -> str:
    redacted = value
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    if len(redacted) > max_length:
        return f"{redacted[:max_length]}...[TRUNCATED]"
    return redacted


def sanitize(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if key.lower() in {"password", "cookie", "authorization", "worker_token", "api_key", "session_id"}:
                cleaned[key] = "[REDACTED]"
            else:
                cleaned[key] = sanitize(item)
        return cleaned
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize(item) for item in value]
    return value


def body_digest(value: bytes) -> str:
    return sha256(value).hexdigest()
