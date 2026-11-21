"""Test-only resolver answers. Not selected by environment, registry or HTTP API."""
import socket
from contextlib import contextmanager
from unittest.mock import patch

HOST = 'attachments.securityai.test'


class TestResolver:
    __test__ = False

    def __init__(self, case='normal'):
        self.case, self.calls = case, []

    async def resolve(self, host, port):
        assert host == HOST
        self.calls.append({'hostname': host, 'port': port})
        if self.case == 'lookup_failed':
            raise OSError('synthetic error; must not be published')
        if self.case == 'empty':
            return []
        if self.case == 'mixed':
            return ['127.0.0.1', '127.0.0.2', '127.0.0.1']
        if self.case == 'outside' or self.case == 'rebind' and len(self.calls) > 1:
            return ['127.0.0.2']
        return ['127.0.0.1', '127.0.0.1']


@contextmanager
def forbid_hostname_lookup():
    """All integration host resolutions must use the injected boundary, never OS DNS."""
    original = socket.getaddrinfo
    attempted = []
    def checked(host, *args, **kwargs):
        if isinstance(host, bytes):
            host = host.decode('ascii')
        if host is not None:
            try:
                from common.domain_contract import address
                address(host)
            except (ValueError, TypeError):
                attempted.append(host)
                raise AssertionError('unexpected OS hostname resolution')
        return original(host, *args, **kwargs)
    with patch('socket.getaddrinfo', checked):
        yield attempted
