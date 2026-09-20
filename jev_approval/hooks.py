"""Read-only compatibility adapter. Never grants permission from incomplete hook inputs."""
from __future__ import annotations
from typing import Any
from uuid import uuid4
from .schema import Envelope, ContractError

def hook_envelope(raw: Any) -> Envelope:
    if not isinstance(raw, dict) or raw.get('hook_event_name') != 'PermissionRequest':
        raise ContractError('unsupported_hook_event')
    if not isinstance(raw.get('tool_name'), str) or not isinstance(raw.get('tool_input'), dict):
        raise ContractError('invalid_hook_payload')
    return Envelope.parse({
        'schema_version': 1, 'request_id': str(uuid4()), 'source': 'codex-hook',
        'action': {'tool': raw['tool_name'], 'arguments': raw['tool_input']},
        'context': {'policy': {}, 'messages': [], 'authorization_revision': 'unavailable'},
        'guards': {'context_complete': False, 'mandatory_review': True,
                   'fresh_review': True, 'retry': False, 'escalated': False,
                   'cancelled': False, 'authorization_current': False}})

def permission_output(decision: dict) -> dict:
    # This compatibility adapter intentionally abstains. The native adapter supplies
    # authenticated host context and enforces freshness; the hook wire contract does not.
    return {}
