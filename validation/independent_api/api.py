"""Standalone attachment service using only the Python standard library.

No agent contracts, registries, verifiers or existing target implementations are
imported here. The server knows application identities, not agent aliases.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import secrets
import threading


@dataclass(frozen=True)
class Member:
    subject: str
    handle: str
    password: str


@dataclass(frozen=True)
class Attachment:
    key: str
    project: str
    holder: str
    receipt: str


class AttachmentService:
    """Two private project attachments; membership controls the download metadata."""

    def __init__(self, auth, vulnerable, fault=None):
        if auth not in ('cookie', 'bearer') or fault not in (None, 'owner_mismatch', 'proof_rotation'):
            raise ValueError('unsupported experiment setting')
        self.auth, self.vulnerable, self.fault = auth, vulnerable, fault
        self.members = (
            Member('member_K73', 'cedar_editor', secrets.token_urlsafe(32)),
            Member('member_R92', 'quartz_reviewer', secrets.token_urlsafe(32)),
        )
        self.attachments = (
            Attachment('attachment_M4s8', 'project_cedar', self.members[0].subject, secrets.token_urlsafe(36)),
            Attachment('attachment_N9t2', 'project_quartz', self.members[1].subject, secrets.token_urlsafe(36)),
        )
        self.project_members = {a.project: frozenset([a.holder]) for a in self.attachments}
        self.by_key = {a.key: a for a in self.attachments}
        self.sessions = {}
        self.secret_values = [m.password for m in self.members] + [a.receipt for a in self.attachments]
        self.owner_reads = {}
        self.received = 0
        self.events = []  # counts/operation/status only; never verifier input
        self.lock = threading.Lock()

    def token(self):
        value = secrets.token_urlsafe(36)
        self.secret_values.append(value)
        return value

    def handle(self, method, path, headers, body):
        # Serialize the small synthetic service so measurements have a stable order.
        with self.lock:
            self.received += 1
            status, response, extra, operation = self.dispatch(method, path, headers, body)
            self.events.append({'ordinal': self.received, 'operation': operation, 'status': status})
            return status, response, extra

    def dispatch(self, method, path, headers, body):
        if method == 'POST' and path == '/gateway/authenticate':
            try:
                data = json.loads(body)
                member = next((m for m in self.members if m.handle == data.get('handle')), None)
                valid = member and isinstance(data.get('secret'), str) and hmac.compare_digest(member.password, data['secret'])
            except (ValueError, AttributeError):
                valid = False
            if not valid:
                return 401, {'problem': {'kind': 'login_rejected'}}, {}, 'login'
            token = self.token()
            self.sessions[token] = member.subject
            if self.auth == 'cookie':
                return 200, {'session': {'active': True}}, {'Set-Cookie': f'project_sid={token}; HttpOnly; SameSite=Strict; Path=/'}, 'login'
            return 200, {'session': {'grant': {'credential': token}}}, {}, 'login'
        token = None
        if self.auth == 'bearer':
            authorization = headers.get('Authorization', '')
            if authorization.startswith('Bearer '):
                token = authorization[7:]
        else:
            cookie = SimpleCookie()
            cookie.load(headers.get('Cookie', ''))
            if 'project_sid' in cookie:
                token = cookie['project_sid'].value
        who = self.sessions.get(token)
        if not who:
            return 401, {'problem': {'kind': 'session_required'}}, {}, 'unauthenticated'
        if method == 'GET' and path == '/gateway/session/profile':
            return 200, {'context': {'member': {'subject': who}}}, {}, 'identity'
        prefix = '/workspace/attachments/'
        if method != 'GET' or not path.startswith(prefix) or path[len(prefix):] not in self.by_key:
            return 404, {'problem': {'kind': 'route_missing'}}, {}, 'unknown'
        item = self.by_key[path[len(prefix):]]
        owner_read = who == item.holder
        if not self.vulnerable and who not in self.project_members[item.project]:
            return 403, {'problem': {'kind': 'attachment_forbidden'}}, {}, 'cross_attachment'
        if owner_read:
            self.owner_reads[item.key] = self.owner_reads.get(item.key, 0) + 1
        holder = item.holder
        receipt = item.receipt
        if self.fault == 'owner_mismatch' and owner_read:
            holder = next(m.subject for m in self.members if m.subject != item.holder)
        if self.fault == 'proof_rotation' and owner_read and self.owner_reads[item.key] >= 2:
            receipt = self.token()  # new synthetic value, tracked for the publication scan
        response = {'artifact': {'key': item.key, 'project': item.project,
                                'acl': {'holder': holder, 'classification': 'restricted'}},
                    'content': {'audit': {'receipt': receipt}}}
        return 200, response, {}, 'owner_attachment' if owner_read else 'cross_attachment'


@contextmanager
def attachment_server(service):
    """Reserve an ephemeral loopback listener; no URL/port input and no disk DB."""
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Never print authorization headers or response bodies.

        def respond(self):
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 <= length <= 4096:
                self.send_error(413)
                return
            status, payload, headers = service.handle(self.command, self.path, self.headers, self.rfile.read(length))
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(data)

        do_GET = respond
        do_POST = respond

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .05}, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        if thread.is_alive():
            raise RuntimeError('attachment server did not stop')
