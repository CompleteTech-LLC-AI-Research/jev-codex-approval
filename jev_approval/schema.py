"""Strict wire contracts: no absent value is interpreted as permission."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from hashlib import sha256
import json
import math
from typing import Any

MAX_INPUT_BYTES = 262_144
class ContractError(ValueError):
    pass

def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in pairs:
        if k in out:
            raise ContractError("duplicate_json_key")
        out[k] = v
    return out

def strict_json(data: bytes | str) -> Any:
    if len(data.encode('utf-8') if isinstance(data, str) else data) > MAX_INPUT_BYTES:
        raise ContractError('input_too_large')
    try:
        return json.loads(data, object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ContractError('nonfinite_json')))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ContractError('invalid_json') from exc

def canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False,
                          sort_keys=True, separators=(',', ':')).encode('utf-8')
    except (ValueError, TypeError, RecursionError) as exc:
        raise ContractError('not_json') from exc

def digest(value: Any) -> str:
    return sha256(canonical(value)).hexdigest()

def probability(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError('probability_not_numeric')
    value = float(value)
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ContractError('probability_out_of_range')
    return value

CHOICES = {
    'risk': ('low', 'medium', 'high', 'critical', 'unknown'),
    'authorization': ('explicit', 'within_task', 'absent', 'unknown'),
    'evidence': ('sufficient', 'needs_investigation', 'unreliable'),
    'compliance': ('compliant', 'violation', 'uncertain'),
}
HAZARDS = ('destructive', 'sensitive_egress', 'credential_probing',
           'persistent_weakening', 'scope_excess', 'prompt_injection')

@dataclass(frozen=True)
class ChoiceAnswer:
    choice: str
    probabilities: dict[str, float]
    confidence: float

@dataclass(frozen=True)
class Vector:
    model: str
    choices: dict[str, ChoiceAnswer]
    hazards: dict[str, float]
    usage: dict[str, int]

    @classmethod
    def parse(cls, raw: Any, expected_model: str) -> 'Vector':
        if not isinstance(raw, dict) or raw.get('model') != expected_model:
            raise ContractError('model_mismatch')
        answers = raw.get('answers')
        if not isinstance(answers, dict) or set(answers) != set(CHOICES) | set(HAZARDS):
            raise ContractError('answer_keys_mismatch')
        choices = {}
        for key, labels in CHOICES.items():
            answer = answers[key]
            if not isinstance(answer, dict) or answer.get('type') != 'choice':
                raise ContractError('choice_type_mismatch')
            probs = answer.get('probabilities')
            if not isinstance(probs, dict) or set(probs) != set(labels):
                raise ContractError('choice_labels_mismatch')
            probs = {label: probability(value) for label, value in probs.items()}
            if abs(sum(probs.values()) - 1) > 0.001:
                raise ContractError('probabilities_do_not_sum_to_one')
            selected = answer.get('choice')
            if selected not in labels or probs[selected] + 1e-8 < max(probs.values()):
                raise ContractError('choice_not_argmax')
            choices[key] = ChoiceAnswer(selected, probs, probability(answer.get('confidence')))
        hazards = {}
        for key in HAZARDS:
            answer = answers[key]
            if not isinstance(answer, dict) or answer.get('type') != 'noul':
                raise ContractError('noul_type_mismatch')
            hazards[key] = probability(answer.get('noul'))
        usage = raw.get('usage')
        if not isinstance(usage, dict):
            raise ContractError('usage_missing')
        for key in ('input_tokens', 'output_tokens'):
            if type(usage.get(key)) is not int or usage[key] < 0:
                raise ContractError('invalid_usage')
        return cls(expected_model, choices, hazards, dict(usage))

    def json(self) -> dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class Envelope:
    request_id: str
    source: str
    action: dict[str, Any]
    context: dict[str, Any]
    guards: dict[str, bool]

    @classmethod
    def parse(cls, raw: Any) -> 'Envelope':
        if not isinstance(raw, dict) or type(raw.get('schema_version')) is not int or raw['schema_version'] != 1:
            raise ContractError('schema_version_mismatch')
        if set(raw) != {'schema_version', 'request_id', 'source', 'action', 'context', 'guards'}:
            raise ContractError('envelope_keys_mismatch')
        request_id = raw.get('request_id')
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128 or any(ord(c) < 32 for c in request_id):
            raise ContractError('invalid_request_id')
        source = raw.get('source')
        if source not in ('codex-native', 'codex-hook', 'offline-evaluation'):
            raise ContractError('invalid_source')
        action, context, guards = raw.get('action'), raw.get('context'), raw.get('guards')
        if not isinstance(action, dict) or not isinstance(context, dict) or not isinstance(guards, dict):
            raise ContractError('invalid_envelope_sections')
        required = {'context_complete', 'mandatory_review', 'fresh_review', 'retry',
                    'escalated', 'cancelled', 'authorization_current'}
        if set(guards) != required or any(type(v) is not bool for v in guards.values()):
            raise ContractError('invalid_guards')
        if not isinstance(action.get('tool'), str):
            raise ContractError('action_tool_missing')
        if not isinstance(context.get('policy'), dict) or not isinstance(context.get('messages'), list):
            raise ContractError('context_policy_or_messages_missing')
        if not isinstance(context.get('authorization_revision'), str):
            raise ContractError('authorization_revision_missing')
        canonical(raw)
        return cls(request_id, source, action, context, guards)

    def json(self) -> dict[str, Any]:
        return {'schema_version': 1, **asdict(self)}

    @property
    def policy_hash(self) -> str:
        return digest(self.context['policy'])

    @property
    def snapshot_hash(self) -> str:
        # Request id is deliberately included: no cross-request permission reuse.
        return digest(self.json())
