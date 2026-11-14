from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit
from common.domain_contract import DomainNetworkPolicy, DomainScope, address, hostname


_DOCUMENT_ID = re.compile(r"^doc-[a-z]+-[0-9]{3}$")


class PolicyViolation(ValueError):
    pass


@dataclass(frozen=True)
class TargetPolicy:
    target_id: str
    scheme: str
    host: str
    port: int
    network: DomainNetworkPolicy | None = None

    @property
    def domain_scope(self):
        return None if self.network is None else DomainScope(hostname=self.host, port=self.port, **self.network.model_dump())

    @property
    def base_url(self) -> str:
        host = f"[{self.host}]" if ':' in self.host else self.host
        return f"{self.scheme}://{host}:{self.port}"

    def __post_init__(self) -> None:
        if self.scheme not in {"http", "https"}:
            raise PolicyViolation("only registered HTTP/HTTPS lab schemes are supported")
        try:
            address(self.host)
        except ValueError:
            try:
                canonical = hostname(self.host)
            except ValueError:
                raise PolicyViolation('invalid target host') from None
            if self.scheme != 'https' or self.network is None:
                raise PolicyViolation('DNS targets require HTTPS and explicit network policy')
            object.__setattr__(self, 'host', canonical)
        else:
            if self.network is not None:
                raise PolicyViolation('IP literal targets retain the existing IP policy')
        if not 1 <= self.port <= 65535:
            raise PolicyViolation("invalid target port")

    @classmethod
    def from_origin(cls, target_id, origin, network=None):
        parsed = urlsplit(origin)
        policy = cls(target_id, parsed.scheme, parsed.hostname or '', parsed.port or (443 if parsed.scheme == 'https' else 80), network)
        normalized = origin.lower() if policy.network is not None else origin
        if normalized != policy.base_url:
            raise PolicyViolation('registered origin must contain only canonical scheme, host and explicit port')
        return policy

    def normalize_relative_path(self, value: str) -> str:
        if not value.startswith("/") or value.startswith("//") or "\\" in value:
            raise PolicyViolation("path must be one normalized absolute-path reference")
        parsed = urlsplit(value)
        if parsed.scheme or parsed.netloc or parsed.username or parsed.hostname or parsed.query or parsed.fragment:
            raise PolicyViolation("URL components outside the registered origin are forbidden")
        decoded = value
        for _ in range(3):
            next_value = unquote(decoded)
            if next_value == decoded:
                break
            decoded = next_value
        if decoded.startswith("//") or "://" in decoded or "@" in decoded or "\\" in decoded:
            raise PolicyViolation("encoded URL authority or separator is forbidden")
        segments = decoded.split("/")
        if any(segment in {".", ".."} for segment in segments):
            raise PolicyViolation("dot segments are forbidden")
        return decoded

    def document_path(self, document_id: str) -> str:
        if not _DOCUMENT_ID.fullmatch(document_id):
            raise PolicyViolation("document_id does not match the published synthetic fixture format")
        return self.normalize_relative_path(f"/documents/{document_id}")

    def assert_response_url(self, url: str) -> None:
        parsed = urlsplit(url)
        port = parsed.port or (80 if parsed.scheme == "http" else 443)
        if (parsed.scheme, parsed.hostname, port) != (self.scheme, self.host, self.port):
            raise PolicyViolation("response escaped the registered target origin")
