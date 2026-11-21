"""Public HTTPX/HTTPCore transport API with numeric, peer-checked asyncio sockets.

No hostname is passed to the socket connector. HTTP origin and TLS SNI stay intact.
One request/connection, zero retries, no proxy; observations are not verifier inputs.
"""
import asyncio
import socket

import httpcore
import httpx

from common.domain_contract import address
from worker.scope import ScopeViolation
from worker.tls import tls_failure_code


class SystemResolver:
    async def resolve(self, host, port):
        records = await asyncio.get_running_loop().getaddrinfo(
            host, port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP, flags=0)
        if any(r[0] not in (socket.AF_INET, socket.AF_INET6) or (r[0] == socket.AF_INET6 and r[4][3]) for r in records):
            raise ValueError('unsupported resolver address family/scope')
        return [r[4][0] for r in records]


def checked_answers(values, network):
    if not values:
        raise ScopeViolation('DNS_NO_RESULTS', 'registered hostname has no addresses')
    if len(values) > 256:
        raise ScopeViolation('DNS_RESULT_INVALID', 'resolver answer limit exceeded')
    try:
        ips = sorted({address(v) for v in values}, key=lambda v: (v.version, int(v)))
    except ValueError:
        raise ScopeViolation('DNS_RESULT_INVALID', 'unsupported numeric DNS result') from None
    normalized = [str(v) for v in ips]
    return normalized, all(network.permits(ip) for ip in ips)


def verify_peer(peer, selected, port):
    try:
        if address(peer[0]) == address(selected) and peer[1] == port and (len(peer) < 4 or peer[3] == 0):
            return str(address(peer[0])), peer[1]
    except (ValueError, TypeError, IndexError):
        pass
    raise ScopeViolation('DNS_PEER_MISMATCH', 'connected peer differs from the checked IP and port')


class PinnedStream(httpcore.AsyncNetworkStream):
    def __init__(self, reader, writer, backend):
        self.reader, self.writer, self.backend = reader, writer, backend
        self.secure = False

    async def read(self, max_bytes, timeout=None):
        async with asyncio.timeout(timeout):
            return await self.reader.read(max_bytes)

    async def write(self, buffer, timeout=None):
        if not self.secure:
            raise ScopeViolation('TLS_REQUIRED', 'HTTP requires the verified TLS stream')
        async with asyncio.timeout(timeout):
            self.writer.write(buffer)
            await self.writer.drain()

    async def aclose(self):
        self.writer.close()
        try:
            await asyncio.wait_for(self.writer.wait_closed(), 1)
        except (OSError, TimeoutError):
            pass

    async def start_tls(self, ssl_context, server_hostname=None, timeout=None):
        b, o = self.backend, self.backend.observation
        try:
            if server_hostname != b.policy.host or ssl_context is not b.trust.checked_context():
                raise ScopeViolation('TLS_TRUST_INVALID', 'registered TLS identity required')
            o.update(stage='tls', tls_server_name=server_hostname, tls_attempts=1)
            async with asyncio.timeout(timeout):
                await self.writer.start_tls(ssl_context, server_hostname=server_hostname, ssl_handshake_timeout=timeout)
            b.record_peer(self.writer.get_extra_info('peername'))
        except BaseException as exc:
            await self.aclose()
            if isinstance(exc, Exception):
                code = tls_failure_code(exc, domain=True)
                if code:
                    o['reason_code'] = code
                    raise ScopeViolation(code, 'registered domain TLS verification failed') from None
            raise
        self.secure = True
        o['stage'] = 'http'
        return self

    def get_extra_info(self, info):
        if info == 'server_addr':
            return self.writer.get_extra_info('peername')
        if info == 'client_addr':
            return self.writer.get_extra_info('sockname')
        if info == 'is_readable':
            return self.reader.at_eof()
        return self.writer.get_extra_info(info)


class PinnedBackend(httpcore.AsyncNetworkBackend):
    def __init__(self, policy, trust, resolver, observation):
        self.policy, self.trust, self.resolver, self.observation = policy, trust, resolver, observation

    def record_peer(self, peer):
        o = self.observation
        try:
            o.update(peer_ip=str(address(peer[0])), peer_port=int(peer[1]))
        except (ValueError, TypeError, IndexError):
            pass
        ip, port = verify_peer(peer, o['selected_ip'], self.policy.port)
        o.update(peer_ip=ip, peer_port=port, peer_verified=True)

    async def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        if (host, port) != (self.policy.host, self.policy.port) or local_address is not None or socket_options:
            raise ScopeViolation('SCOPE_ORIGIN_MISMATCH', 'only the registered connection is permitted')
        self.trust.checked_context()
        o = self.observation
        o['stage'] = 'dns'
        try:
            async with asyncio.timeout(timeout):
                values = await self.resolver.resolve(host, port)
        except Exception:
            raise ScopeViolation('DNS_LOOKUP_FAILED', 'registered hostname resolution failed') from None
        answers, allowed = checked_answers(values, self.policy.network)
        o['dns_results'] = answers
        if not allowed:
            raise ScopeViolation('DNS_ADDRESS_OUT_OF_SCOPE', 'all resolver addresses must be approved')
        selected = answers[0]  # Deterministic IPv4 then IPv6, numeric order. No address retry.
        o.update(selected_ip=selected, stage='tcp', tcp_attempts=1)
        ip = address(selected)
        raw = socket.socket(socket.AF_INET if ip.version == 4 else socket.AF_INET6, socket.SOCK_STREAM)
        raw.setblocking(False)
        writer = None
        try:
            async with asyncio.timeout(timeout):
                # sock_connect accepts an already parsed numeric address; no hostname lookup.
                endpoint = (selected, port) if ip.version == 4 else (selected, port, 0, 0)
                await asyncio.get_running_loop().sock_connect(raw, endpoint)
                o['stage'] = 'peer'
                self.record_peer(raw.getpeername())  # Before SNI, credentials or HTTP.
                reader, writer = await asyncio.open_connection(sock=raw)
            return PinnedStream(reader, writer, self)
        except BaseException:
            if writer is not None:
                writer.close()
            raw.close()
            raise


class ResponseStream(httpx.AsyncByteStream):
    def __init__(self, stream):
        self.stream = stream

    async def __aiter__(self):
        async for chunk in self.stream:
            yield chunk

    async def aclose(self):
        await self.stream.aclose()


class DomainTransport(httpx.AsyncBaseTransport):
    def __init__(self, policy, trust, resolver, observation):
        self.policy, self.observation = policy, observation
        self.pool = httpcore.AsyncConnectionPool(ssl_context=trust.checked_context(),
            max_connections=1, max_keepalive_connections=0, http1=True, http2=False, retries=0,
            network_backend=PinnedBackend(policy, trust, resolver, observation))

    async def handle_async_request(self, request):
        p, o = self.policy, self.observation
        expected_host = p.host if p.port == 443 else f'{p.host}:{p.port}'
        if ((request.url.scheme, request.url.host, request.url.port or 443) != ('https', p.host, p.port)
                or request.headers.get_list('host') != [expected_host]):
            raise ScopeViolation('SCOPE_ORIGIN_MISMATCH', 'registered domain and Host required')
        try:
            response = await self.pool.handle_async_request(httpcore.Request(
                method=request.method, url=httpcore.URL(scheme=b'https', host=p.host.encode('ascii'),
                    port=p.port, target=request.url.raw_path), headers=request.headers.raw, content=request.stream,
                extensions={'timeout': request.extensions.get('timeout', {})}))
            o.update(stage='complete', http_response_received=True)
            return httpx.Response(response.status, headers=response.headers, stream=ResponseStream(response.stream),
                                  extensions=response.extensions)
        except ScopeViolation as exc:
            o['reason_code'] = exc.code
            raise
        except Exception:
            o['reason_code'] = 'DOMAIN_CONNECTION_FAILED'
            raise ScopeViolation('DOMAIN_CONNECTION_FAILED', 'registered domain connection failed') from None

    async def aclose(self):
        await self.pool.aclose()
