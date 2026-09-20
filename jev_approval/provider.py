"""Bounded, redirect-free HTTPS transport. No hidden retries on the approval path."""
from __future__ import annotations
from typing import Any, Protocol
import urllib.request
import urllib.error
from .schema import canonical, strict_json, ContractError
from .config import Config
from .questions import QUESTIONS

class Provider(Protocol):
    def evaluate(self, state: dict[str, Any]) -> dict[str, Any]: ...

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

class SystemOneProvider:
    def __init__(self, config: Config, api_key: str):
        config.validate()
        if not api_key or '\n' in api_key or '\r' in api_key:
            raise ContractError('api_key_missing_or_invalid')
        self.config, self.api_key = config, api_key
        # Do not silently send transcripts or credentials via ambient proxy settings.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def evaluate(self, state: dict[str, Any]) -> dict[str, Any]:
        if not self.config.allow_remote_context:
            raise ContractError('remote_context_not_authorized')
        payload = canonical({'model': self.config.model, 'state': state, 'questions': QUESTIONS})
        request = urllib.request.Request(self.config.endpoint, data=payload, method='POST', headers={
            'Authorization': 'Bearer ' + self.api_key,
            'Content-Type': 'application/json', 'Accept': 'application/json',
            'User-Agent': 'jev-codex-approval/0.1.0'})
        try:
            with self.opener.open(request, timeout=self.config.timeout_seconds) as response:
                data = response.read(self.config.max_response_bytes + 1)
                if len(data) > self.config.max_response_bytes:
                    raise ContractError('provider_response_too_large')
                raw = strict_json(data)
                if not isinstance(raw, dict):
                    raise ContractError('provider_response_not_object')
                return raw
        except urllib.error.HTTPError as exc:
            # Error bodies may contain the submitted state. Never surface them.
            exc.close()
            raise ContractError('provider_http_' + str(exc.code)) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ContractError('provider_unavailable') from None
