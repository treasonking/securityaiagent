"""Worker-owned, frozen dedicated CA trust. Never a model/HTTP tool option."""
from dataclasses import dataclass, field, replace
import hashlib
from pathlib import Path
import re
import ssl
import time

from common.tls_contract import TLSVerification
from worker.scope import ScopeViolation


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _store_hash(context):
    return _hash(b'\n'.join(sorted(_hash(c).encode() for c in context.get_ca_certs(binary_form=True))))


@dataclass(frozen=True)
class DedicatedTrust:
    _path: Path = field(repr=False)
    _sha256: str
    _context_sha256: str
    _context: ssl.SSLContext = field(repr=False, compare=False)

    def checked_context(self):
        try:
            unchanged = _hash(self._path.read_bytes()) == self._sha256
        except OSError:
            unchanged = False
        if not unchanged:
            raise ScopeViolation('TLS_TRUST_CHANGED_RESTART_REQUIRED', 'restart Worker and issue a new preview')
        ctx = self._context
        if (ctx.verify_mode != ssl.CERT_REQUIRED or not ctx.check_hostname or ctx.hostname_checks_common_name
                or ctx.minimum_version != ssl.TLSVersion.TLSv1_2
                or ctx.verify_flags != (ssl.VERIFY_X509_TRUSTED_FIRST | ssl.VERIFY_X509_STRICT)):
            raise ScopeViolation('TLS_TRUST_INVALID', 'TLS verification settings changed')
        if _store_hash(ctx) != self._context_sha256:
            raise ScopeViolation('TLS_TRUST_INVALID', 'TLS context trust contents changed')
        return ctx

    def metadata(self):
        self.checked_context()
        return TLSVerification(ca_bundle_sha256=self._sha256, context_ca_sha256=self._context_sha256)


def load_trust(path):
    try:
        location = Path(path).absolute()
        data = location.read_bytes()
        if not 0 < len(data) <= 1048576:
            raise ValueError()
        text = data.decode('ascii')
        certificates = re.findall(r'-----BEGIN CERTIFICATE-----[A-Za-z0-9+/=\r\n]+-----END CERTIFICATE-----', text)
        rest = re.sub(r'-----BEGIN CERTIFICATE-----[A-Za-z0-9+/=\r\n]+-----END CERTIFICATE-----', '', text)
        if not certificates or rest.strip():
            raise ValueError()  # Reject private keys, other PEM objects and empty stores.
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)  # No system/default CA load.
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.check_hostname = True
        ctx.hostname_checks_common_name = False
        ctx.verify_flags = ssl.VERIFY_X509_TRUSTED_FIRST | ssl.VERIFY_X509_STRICT
        ctx.load_verify_locations(cadata=text)  # Load exactly the bytes fingerprinted above.
        anchors = ctx.get_ca_certs()
        supplied = {ssl.PEM_cert_to_DER_cert(c) for c in certificates}
        if not supplied <= set(ctx.get_ca_certs(binary_form=True)):
            raise ValueError()  # Only CA certificates, not endpoint certificates, belong in this bundle.
        now = time.time()
        if not anchors or any(not ssl.cert_time_to_seconds(c['notBefore']) <= now < ssl.cert_time_to_seconds(c['notAfter']) for c in anchors):
            raise ValueError()
        return DedicatedTrust(location, _hash(data), _store_hash(ctx), ctx)
    except (OSError, ValueError, TypeError, ssl.SSLError):
        raise ScopeViolation('TLS_CA_INVALID', 'dedicated CA bundle is missing or invalid') from None


def bind_registry_tls(registry, ca_bundle=None):
    if not any(p.scheme == 'https' for p in registry.policies.values()):
        if ca_bundle:
            raise ScopeViolation('TLS_CA_NOT_APPLICABLE', 'CA configuration requires a registered HTTPS target')
        return registry
    if not ca_bundle:
        raise ScopeViolation('TLS_CA_REQUIRED', 'HTTPS requires a Worker-owned CA bundle')
    return replace(registry, tls_trust=load_trust(ca_bundle))


def tls_metadata(registry, target):
    if target.scheme != 'https':
        return None
    if registry.tls_trust is None:
        raise ScopeViolation('TLS_CA_REQUIRED', 'HTTPS requires a Worker-owned CA bundle')
    return registry.tls_trust.metadata()


def client_verify(registry, target):
    if target.scheme == 'http':
        return True
    tls_metadata(registry, target)
    return registry.tls_trust.checked_context()


def tls_failure_code(error):
    """Classify structured SSL exceptions; never publish exception text/paths."""
    pending, visited = [error], set()
    ssl_seen = False
    while pending:
        exc = pending.pop()
        if exc is None or id(exc) in visited:
            continue
        visited.add(id(exc))
        if isinstance(exc, ssl.SSLCertVerificationError):
            return {9: 'TLS_CERT_NOT_YET_VALID', 10: 'TLS_CERT_EXPIRED',
                    18: 'TLS_CERT_UNTRUSTED', 19: 'TLS_CERT_UNTRUSTED', 20: 'TLS_CERT_UNTRUSTED',
                    21: 'TLS_CERT_UNTRUSTED', 62: 'TLS_CERT_IP_SAN_MISMATCH',
                    64: 'TLS_CERT_IP_SAN_MISMATCH'}.get(exc.verify_code, 'TLS_CERT_VERIFY_FAILED')
        ssl_seen |= isinstance(exc, ssl.SSLError)
        pending.extend([exc.__cause__, exc.__context__])
    return 'TLS_HANDSHAKE_FAILED' if ssl_seen else None
