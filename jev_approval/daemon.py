"""Optional authenticated localhost service; it never exposes an execution API."""
from __future__ import annotations
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import os
import threading
import urllib.request
from .config import Config
from .schema import Envelope, ContractError, MAX_INPUT_BYTES, canonical, strict_json
from .engine import Engine
from .provider import NoRedirect, SystemOneProvider

class ApprovalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False
    def __init__(self, address, engine: Engine, token: str):
        if address[0] != '127.0.0.1' or len(token) < 32:
            raise ContractError('loopback_and_strong_token_required')
        self.engine, self.token = engine, token
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(address, Handler)
    def process_request(self, request, client_address):
        # Bound socket-handler threads as well as upstream model requests.
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise
    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

class Handler(BaseHTTPRequestHandler):
    server: ApprovalServer
    protocol_version = 'HTTP/1.0'
    def setup(self):
        super().setup()
        self.connection.settimeout(3)
    def log_message(self, *args):
        pass  # Never log URL or header contents supplied by clients.
    def reply(self, code: int, payload: dict):
        data = canonical(payload)
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def do_POST(self):
        try:
            if self.path != '/review':
                return self.reply(404, {'error': 'not_found'})
            expected = 'Bearer ' + self.server.token
            supplied = self.headers.get('Authorization', '')
            if not hmac.compare_digest(supplied.encode(), expected.encode()):
                return self.reply(401, {'error': 'unauthorized'})
            if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length', [])) != 1:
                return self.reply(400, {'error': 'content_length_required'})
            size = int(self.headers['Content-Length'])
            if size < 1 or size > MAX_INPUT_BYTES:
                return self.reply(413, {'error': 'invalid_size'})
            data = self.rfile.read(size)
            if len(data) != size:
                return self.reply(400, {'error': 'incomplete_body'})
            env = Envelope.parse(strict_json(data))
            self.reply(200, self.server.engine.review(env).json())
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            return
        except Exception:
            try:
                self.reply(400, {'error': 'invalid_request'})
            except OSError:
                pass

def remote_review(env: Envelope, cfg: Config) -> dict:
    token = os.environ.get(cfg.daemon_token_env, '')
    if len(token) < 32 or not cfg.daemon_url:
        raise ContractError('daemon_not_configured')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    req = urllib.request.Request(cfg.daemon_url, data=canonical(env.json()), method='POST', headers={
        'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    with opener.open(req, timeout=cfg.timeout_seconds + .5) as response:
        data = response.read(MAX_INPUT_BYTES + 1)
    answer = strict_json(data)
    if (not isinstance(answer, dict) or answer.get('schema_version') != 1
            or answer.get('request_id') != env.request_id
            or answer.get('snapshot_hash') != env.snapshot_hash
            or answer.get('policy_hash') != env.policy_hash
            or answer.get('decision') not in ('allow', 'deny', 'defer')):
        raise ContractError('daemon_response_binding_mismatch')
    # Client-side off/shadow mode cannot be upgraded by the service configuration.
    from .questions import QUESTION_HASH
    if (cfg.mode != 'enforce' or not cfg.allow_remote_context
            or env.source != 'codex-native'
            or env.policy_hash not in cfg.approved_policy_hashes
            or cfg.approved_question_hash != QUESTION_HASH
            or answer.get('question_hash') != QUESTION_HASH):
        answer['decision'] = 'defer'
    if answer.get('decision') != 'defer':
        # Re-run the caller's stricter thresholds on a validated response vector.
        from .schema import Vector
        from .engine import candidate_policy
        saved = answer.get('vector', {})
        wire = {'model': saved.get('model'), 'usage': saved.get('usage'), 'answers': {}}
        for name, choice in saved.get('choices', {}).items():
            wire['answers'][name] = {'type': 'choice', **choice}
        for name, value in saved.get('hazards', {}).items():
            wire['answers'][name] = {'type': 'noul', 'noul': value}
        vector = Vector.parse(wire, cfg.model)
        candidate, _ = candidate_policy(env, vector, cfg)
        g = env.guards
        if (candidate != answer['decision'] or not g['context_complete']
                or not g['authorization_current']
                or any(g[k] for k in ('mandatory_review', 'fresh_review', 'retry', 'escalated', 'cancelled'))):
            answer['decision'] = 'defer'
    return answer

def make_engine(cfg: Config) -> Engine:
    key = os.environ.get('TYPESAFE_API_KEY', '')
    provider = SystemOneProvider(cfg, key) if key and cfg.allow_remote_context else None
    return Engine(cfg, provider)

def serve(cfg: Config, port: int = 8766) -> None:
    token = os.environ.get(cfg.daemon_token_env, '')
    with ApprovalServer(('127.0.0.1', port), make_engine(cfg), token) as server:
        server.serve_forever(poll_interval=.25)
