"""Versioned, operator-owned domain authority and bounded connection observations."""
import ipaddress
import re
from typing import Literal

from pydantic import Field, field_validator
from common.api_contract import FrozenModel


def hostname(value):
    if not isinstance(value, str) or not value.isascii() or not 1 <= len(value) <= 253:
        raise ValueError('ASCII DNS hostname required')
    value = value.lower()
    labels = value.split('.')
    if (len(labels) < 2 or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', x) for x in labels)
            or any(x.startswith('xn--') for x in labels) or not re.search('[a-z]', labels[-1])
            or all(re.fullmatch(r'(?:0x[0-9a-f]+|[0-9]+)', x) for x in labels)):
        raise ValueError('unambiguous DNS labels required; no trailing dot or IDN')
    return value


def address(value):
    if not isinstance(value, str) or '%' in value:
        raise ValueError('unscoped numeric address required')
    ip = ipaddress.ip_address(value)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        raise ValueError('mapped IPv6 is not supported')
    return ip


class DomainNetworkPolicy(FrozenModel):
    version: Literal['domain-network-v1'] = 'domain-network-v1'
    allowed_ip_ranges: tuple[str, ...]
    allow_non_global: bool = False
    resolver: Literal['system-a-aaaa-all-v1'] = 'system-a-aaaa-all-v1'
    connection: Literal['numeric-peer-checked-per-request-v1'] = 'numeric-peer-checked-per-request-v1'

    @field_validator('allowed_ip_ranges', mode='before')
    @classmethod
    def ranges(cls, value):
        if not isinstance(value, (list, tuple)) or not 1 <= len(value) <= 128:
            raise ValueError('bounded explicit IP ranges required')
        networks = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError('IP range required')
            address(item.split('/')[0])
            net = ipaddress.ip_network(item, strict=False)
            if not net.prefixlen or (net.version == 6 and net.overlaps(ipaddress.ip_network('::ffff:0:0/96'))):
                raise ValueError('/0 and mapped address ranges forbidden')
            networks.append(net)
        normalized = [n for version in (4, 6) for n in ipaddress.collapse_addresses(n for n in networks if n.version == version)]
        if any(n.prefixlen == 0 for n in normalized):
            raise ValueError('combined /0 is forbidden')
        return tuple(str(n) for n in normalized)

    def permits(self, ip):
        # The flag alone grants nothing: the address must also match an explicit range.
        ip = address(str(ip))
        if ip.is_unspecified or ip.is_multicast or (ip.is_reserved and not ip.is_loopback):
            return False
        if not ip.is_global and not self.allow_non_global:
            return False
        return any(ip.version == n.version and ip in n for n in map(ipaddress.ip_network, self.allowed_ip_ranges))


class DomainScope(DomainNetworkPolicy):
    hostname: str
    port: int = Field(ge=1, le=65535)

    @field_validator('hostname')
    @classmethod
    def canonical_host(cls, value):
        return hostname(value)


class DomainObservation(FrozenModel):
    version: Literal['domain-connection-v1'] = 'domain-connection-v1'
    origin: str
    dns_results: list[str] = Field(default_factory=list, max_length=256)
    selected_ip: str | None = None
    peer_ip: str | None = None
    peer_port: int | None = None
    peer_verified: bool = False
    tls_server_name: str | None = None
    stage: Literal['dns', 'tcp', 'peer', 'tls', 'http', 'complete'] = 'dns'
    reason_code: str | None = None
    tcp_attempts: int = 0
    tls_attempts: int = 0
    http_response_received: bool = False
