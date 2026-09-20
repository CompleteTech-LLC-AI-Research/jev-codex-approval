from __future__ import annotations
from dataclasses import dataclass, asdict
import threading
import time
from typing import Callable
from .config import Config
from .schema import Envelope, Vector, ContractError, canonical, digest
from .questions import QUESTION_HASH
from .provider import Provider
from .audit import append_record

@dataclass(frozen=True)
class Decision:
    schema_version: int
    request_id: str
    snapshot_hash: str
    policy_hash: str
    question_hash: str
    decision: str
    candidate: str
    reason: str
    model: str | None
    vector: dict | None
    elapsed_ms: float
    def json(self): return asdict(self)

class CircuitBreaker:
    def __init__(self, failures: int, seconds: float):
        self.limit, self.seconds = failures, seconds
        self.failures, self.open_until = 0, 0.0
        self.lock = threading.Lock()
    def opened(self) -> bool:
        with self.lock:
            return time.monotonic() < self.open_until
    def failure(self) -> None:
        with self.lock:
            self.failures += 1
            if self.failures >= self.limit:
                self.open_until = time.monotonic() + self.seconds
    def success(self) -> None:
        with self.lock:
            self.failures, self.open_until = 0, 0.0

# Protect common credential literals BEFORE egress. This is NOT comprehensive DLP.
import re
SECRET_PATTERNS = (
    re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    re.compile(r'(?i)\b(?:authorization|api[_-]?key|password|secret|access[_-]?token)\s*["\']?\s*[:=]\s*["\']?[^\s"\',}]{8,}'),
    re.compile(r'\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16})\b'),
)

def unsafe_transport_content(value) -> bool:
    # Never silently omit media while classifying a text-only state.
    if isinstance(value, dict):
        if value.get('type') in ('input_image', 'input_audio', 'image', 'audio', 'video'):
            return True
        return any(unsafe_transport_content(v) for v in value.values())
    if isinstance(value, list):
        return any(unsafe_transport_content(v) for v in value)
    return False

def candidate_policy(env: Envelope, vector: Vector, cfg: Config) -> tuple[str, str]:
    compliance = vector.choices['compliance']
    evidence = vector.choices['evidence']
    if evidence.choice != 'sufficient':
        return 'defer', 'additional_evidence_required'
    if any(a.confidence < cfg.min_confidence for a in vector.choices.values()):
        return 'defer', 'low_confidence'
    if compliance.choice == 'violation':
        if (cfg.enable_fast_deny and compliance.confidence >= cfg.deny_confidence
                and compliance.probabilities['violation'] >= cfg.deny_probability):
            return 'deny', 'clear_policy_violation'
        return 'defer', 'violation_requires_guardian'
    expected = {'risk': {'low'}, 'authorization': {'explicit', 'within_task'},
                'evidence': {'sufficient'}, 'compliance': {'compliant'}}
    for k, accepted in expected.items():
        a = vector.choices[k]
        if a.choice not in accepted or a.probabilities[a.choice] < cfg.min_probability:
            return 'defer', 'not_confident_low_risk'
    if any(p > cfg.max_hazard for p in vector.hazards.values()):
        return 'defer', 'hazard_requires_guardian'
    if env.action['tool'] not in cfg.fast_allow_tools:
        return 'defer', 'action_category_not_enabled'
    return 'allow', 'low_risk_policy_compliant'

class Engine:
    def __init__(self, config: Config, provider: Provider | None,
                 audit: Callable[[str, dict], None] = append_record):
        config.validate()
        self.config, self.provider, self.audit = config, provider, audit
        self.breaker = CircuitBreaker(config.breaker_failures, config.breaker_seconds)

    def review(self, env: Envelope) -> Decision:
        started = time.perf_counter()
        cfg, vector = self.config, None
        candidate, reason = 'defer', 'off'
        eligible = False
        state = {'action': env.action, 'context': env.context}
        state_bytes = canonical(state)
        g = env.guards
        if cfg.mode == 'off':
            reason = 'off'
        elif g['cancelled'] or not g['authorization_current']:
            reason = 'cancelled_or_stale'
        elif env.source == 'codex-hook':
            # Hook inputs do not carry complete managed-policy/freshness evidence.
            reason = 'hook_missing_host_authority'
        elif g['mandatory_review'] or g['fresh_review'] or g['retry'] or g['escalated']:
            reason = 'original_review_required'
        elif not g['context_complete']:
            reason = 'incomplete_context'
        elif not cfg.allow_remote_context:
            reason = 'remote_context_not_authorized'
        elif len(state_bytes) > cfg.max_state_bytes:
            reason = 'state_too_large'
        elif unsafe_transport_content(state):
            reason = 'unsupported_media'
        elif any(pattern.search(state_bytes.decode('utf-8')) for pattern in SECRET_PATTERNS):
            reason = 'possible_secret_no_egress'
        elif self.provider is None:
            reason = 'provider_not_configured'
        elif self.breaker.opened():
            reason = 'circuit_open'
        else:
            try:
                vector = Vector.parse(self.provider.evaluate(state), cfg.model)
                self.breaker.success()
                candidate, reason = candidate_policy(env, vector, cfg)
                eligible = (env.source == 'codex-native'
                    and env.policy_hash in cfg.approved_policy_hashes
                    and cfg.approved_question_hash == QUESTION_HASH)
            except Exception:
                # Provider text and tracebacks may contain submitted context.
                self.breaker.failure()
                reason = 'provider_failed_or_invalid_response'
        decision = candidate if cfg.mode == 'enforce' and eligible else 'defer'
        if cfg.mode == 'enforce' and candidate != 'defer' and not eligible:
            reason = 'policy_or_question_set_not_approved'
        result = Decision(1, env.request_id, env.snapshot_hash, env.policy_hash, QUESTION_HASH,
                          decision, candidate, reason, vector.model if vector else None,
                          vector.json() if vector else None,
                          (time.perf_counter() - started) * 1000)
        record = result.json()
        record.update(timestamp_unix=time.time(), mode=cfg.mode, source=env.source,
                      action_hash=digest(env.action), authorization_hash=digest(env.context['authorization_revision']))
        try:
            self.audit(cfg.audit_path, record)
        except Exception:
            if cfg.require_audit:
                result = Decision(1, env.request_id, env.snapshot_hash, env.policy_hash, QUESTION_HASH,
                                  'defer', candidate, 'audit_unavailable', vector.model if vector else None,
                                  vector.json() if vector else None, (time.perf_counter()-started)*1000)
        return result
