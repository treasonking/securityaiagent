"""Ephemeral certificates for the existing attachment API; no new application."""
from contextlib import contextmanager
import csv
from datetime import datetime, timedelta, timezone
import io
import ipaddress
import os
from pathlib import Path
import ssl
import subprocess
import tempfile

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def restrict_directory(path):
    if os.name == 'nt':
        identity = subprocess.check_output(['whoami', '/user', '/fo', 'csv', '/nh'], text=True)
        sid = next(csv.reader(io.StringIO(identity.strip())))[1]
        result = subprocess.run(['icacls', str(path), '/inheritance:r', '/grant:r', f'*{sid}:(OI)(CI)F'], capture_output=True)
        if result.returncode:
            raise RuntimeError('TEMPORARY_KEY_PERMISSIONS_FAILED')
        return 'windows-current-user-only-directory-acl'
    path.chmod(0o700)
    return 'posix-directory-0700-key-0600'


def write_private(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)


def authority(label, now):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, label)])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=2))
            .not_valid_after(now+timedelta(days=3)).add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, False, False), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .sign(key, hashes.SHA256()))
    return key, cert


@contextmanager
def certificates(case='normal'):
    if case not in ('normal', 'untrusted_ca', 'wrong_san', 'expired', 'ca_rotation'):
        raise ValueError('unknown TLS experiment')
    now = datetime.now(timezone.utc)
    with tempfile.TemporaryDirectory(prefix='securityai-local-tls-') as directory:
        root = Path(directory)
        permissions = restrict_directory(root)
        ca_key, ca = authority('Temporary attachment validation CA', now)
        _, alternate = authority('Temporary alternate validation CA', now)
        server_key = ec.generate_private_key(ec.SECP256R1())
        # CN deliberately matches the access IP even in wrong-SAN tests: SAN must win.
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, '127.0.0.1')])
        leaf = (x509.CertificateBuilder().subject_name(name).issuer_name(ca.subject).public_key(server_key.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=1))
                .not_valid_after(now-timedelta(hours=1) if case == 'expired' else now+timedelta(days=1))
                .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                .add_extension(x509.KeyUsage(True, False, False, False, False, False, False, False, False), critical=True)
                .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
                .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.2' if case == 'wrong_san' else '127.0.0.1'))]), critical=False)
                .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
                .sign(ca_key, hashes.SHA256()))
        pem = lambda cert: cert.public_bytes(serialization.Encoding.PEM)
        key_bytes = server_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        ca_key_bytes = ca_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        ca_file, cert_file, key_file = root/'trust.pem', root/'server.pem', root/'server.key'
        write_private(ca_file, pem(alternate if case == 'untrusted_ca' else ca))
        write_private(cert_file, pem(leaf))
        write_private(key_file, key_bytes)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(cert_file, key_file)
        try:
            yield {'ca_file': ca_file, 'server_context': ctx, 'alternate_bundle': pem(ca)+pem(alternate),
                   'reference_time_utc': now.isoformat(), 'private_directory': root,
                   'private_values': [key_bytes.decode(), ca_key_bytes.decode(),
                                      ''.join(key_bytes.decode().splitlines()[1:-1]), ''.join(ca_key_bytes.decode().splitlines()[1:-1]),
                                      *key_bytes.decode().splitlines()[1:-1], *ca_key_bytes.decode().splitlines()[1:-1]],
                   'public': {'reference_time_utc': now.isoformat(), 'server_not_before': leaf.not_valid_before_utc.isoformat(),
                              'server_not_after': leaf.not_valid_after_utc.isoformat(), 'server_ip_san': '127.0.0.2' if case == 'wrong_san' else '127.0.0.1',
                              'server_certificate_sha256': leaf.fingerprint(hashes.SHA256()).hex(), 'private_storage': permissions}}
        finally:
            # TemporaryDirectory removes only these newly created private files.
            pass
