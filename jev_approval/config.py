from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import os
import re
import stat
import tomllib
from .schema import ContractError, probability

@dataclass(frozen=True)
class Config:
    mode: str = 'shadow'
    model: str = 'jev-1.13.0'
    allow_remote_context: bool = False
    endpoint: str = 'https://api.typesafe.ai/v1/systemone'
    timeout_seconds: float = 1.0
    max_state_bytes: int = 24_000
    max_response_bytes: int = 64_000
    min_confidence: float = 0.98
    min_probability: float = 0.995
    max_hazard: float = 0.005
    deny_confidence: float = 0.99
    deny_probability: float = 0.999
    fast_allow_tools: tuple[str, ...] = ()
    enable_fast_deny: bool = False
    approved_policy_hashes: tuple[str, ...] = ()
    approved_question_hash: str = ''
    audit_path: str = ''
    require_audit: bool = True
    breaker_failures: int = 3
    breaker_seconds: float = 15.0
    daemon_url: str = ''
    daemon_token_env: str = 'JEV_APPROVAL_TOKEN'

    @classmethod
    def load(cls, path: str | Path) -> 'Config':
        path = Path(path).expanduser()
        if not path.is_absolute():
            raise ContractError('config_path_must_be_absolute')
        st = path.lstat()
        if not stat.S_ISREG(st.st_mode) or path.is_symlink():
            raise ContractError('config_must_be_regular_nonsymlink')
        if os.name == 'posix' and (st.st_mode & 0o022 or st.st_uid not in (0, os.getuid())):
            raise ContractError('config_permissions_unsafe')
        with path.open('rb') as f:
            data = tomllib.load(f)
        known = set(cls.__dataclass_fields__)
        if set(data) - known:
            raise ContractError('unknown_configuration_key')
        for key in ('fast_allow_tools', 'approved_policy_hashes'):
            if key in data:
                if not isinstance(data[key], list) or not all(isinstance(x, str) for x in data[key]):
                    raise ContractError('configuration_list_expected')
                data[key] = tuple(data[key])
        cfg = cls(**data)
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if self.mode not in ('off', 'shadow', 'enforce'):
            raise ContractError('unknown_mode')
        if not re.fullmatch(r'jev-\d+\.\d+\.\d+', self.model):
            raise ContractError('versioned_model_required')
        if self.endpoint != 'https://api.typesafe.ai/v1/systemone':
            raise ContractError('provider_endpoint_not_allowed')
        for name in ('allow_remote_context', 'enable_fast_deny', 'require_audit'):
            if type(getattr(self, name)) is not bool:
                raise ContractError('configuration_boolean_expected')
        for name in ('min_confidence', 'min_probability', 'max_hazard', 'deny_confidence', 'deny_probability'):
            probability(getattr(self, name))
        for name, low, high in (('timeout_seconds', .05, 10), ('breaker_seconds', .1, 3600)):
            value = getattr(self, name)
            if type(value) not in (float, int) or not low <= value <= high:
                raise ContractError('invalid_configuration_range')
        for name, low, high in (('max_state_bytes', 512, 48_000), ('max_response_bytes', 1024, 262144), ('breaker_failures', 1, 100)):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ContractError('invalid_configuration_range')
        if set(self.fast_allow_tools) - {'exec_command', 'apply_patch'}:
            raise ContractError('unsupported_fast_allow_tool')
        for h in self.approved_policy_hashes:
            if not re.fullmatch('[0-9a-f]{64}', h):
                raise ContractError('invalid_policy_hash')
        if self.approved_question_hash and not re.fullmatch('[0-9a-f]{64}', self.approved_question_hash):
            raise ContractError('invalid_question_hash')
        if self.daemon_url and self.daemon_url != 'http://127.0.0.1:8766/review':
            raise ContractError('daemon_endpoint_not_allowed')
        if not re.fullmatch('[A-Z_][A-Z0-9_]*', self.daemon_token_env):
            raise ContractError('invalid_token_environment_name')
        if self.audit_path and not Path(self.audit_path).expanduser().is_absolute():
            raise ContractError('audit_path_must_be_absolute')
