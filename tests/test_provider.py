import io
import json
import unittest
import urllib.error
from dataclasses import replace
from unittest.mock import patch
from jev_approval.provider import SystemOneProvider
from jev_approval.config import Config
from jev_approval.schema import ContractError, canonical
from jev_approval.cli import run_review
from jev_approval.daemon import remote_review
from jev_approval.engine import Engine
from .helpers import config, envelope, raw_response, FakeProvider, audit_noop

class Opener:
    def __init__(self, data=None, error=None):
        self.data,self.error,self.calls,self.request,self.timeout=data,error,0,None,None
    def open(self, request, timeout):
        self.calls+=1;self.request=request;self.timeout=timeout
        if self.error:raise self.error
        return io.BytesIO(self.data)

class ProviderTests(unittest.TestCase):
    def test_documented_request_contract(self):
        cfg=config();p=SystemOneProvider(cfg,'synthetic-key-for-tests')
        transport=Opener(canonical(raw_response()));p.opener=transport
        state={'action':envelope().action,'context':envelope().context}
        p.evaluate(state)
        body=json.loads(transport.request.data)
        self.assertEqual(set(body),{'model','state','questions'})
        self.assertEqual(len(body['questions']),10)
        self.assertEqual(transport.request.full_url,'https://api.typesafe.ai/v1/systemone')
        self.assertEqual(transport.timeout,cfg.timeout_seconds)
    def test_provider_rejects_absent_key(self):
        with self.assertRaises(ContractError):SystemOneProvider(config(),'')
    def test_provider_rejects_key_header_injection(self):
        with self.assertRaises(ContractError):SystemOneProvider(config(),'x\nAnother: header')
    def test_provider_consent_guard(self):
        p=SystemOneProvider(replace(config(),allow_remote_context=False),'synthetic-key')
        transport=Opener(canonical(raw_response()));p.opener=transport
        with self.assertRaises(ContractError):p.evaluate({})
        self.assertEqual(transport.calls,0)
    def test_provider_oversized_response(self):
        p=SystemOneProvider(replace(config(),max_response_bytes=1024),'synthetic-key')
        p.opener=Opener(b'x'*1025)
        with self.assertRaises(ContractError):p.evaluate({})
    def test_rate_limit_no_hidden_retry(self):
        p=SystemOneProvider(config(),'synthetic-key')
        error=urllib.error.HTTPError('https://api.typesafe.ai/v1/systemone',429,'rate limit',{},io.BytesIO(b'PRIVATE_ERROR_BODY'))
        transport=Opener(error=error);p.opener=transport
        with self.assertRaises(ContractError) as ctx:p.evaluate({})
        self.assertEqual(transport.calls,1);self.assertNotIn('PRIVATE_ERROR_BODY',str(ctx.exception))
    def test_daemon_not_contacted_without_client_consent(self):
        cfg=replace(config(),allow_remote_context=False,daemon_url='http://127.0.0.1:8766/review')
        with patch('jev_approval.cli.remote_review') as remote:
            answer=run_review(envelope().json(),cfg)
        remote.assert_not_called();self.assertEqual(answer['decision'],'defer')
    def test_daemon_not_contacted_in_off_mode(self):
        cfg=replace(config(),mode='off',daemon_url='http://127.0.0.1:8766/review')
        with patch('jev_approval.cli.remote_review') as remote:
            answer=run_review(envelope().json(),cfg)
        remote.assert_not_called();self.assertEqual(answer['decision'],'defer')
    def test_daemon_request_binding_checked(self):
        answer=Engine(config(),FakeProvider(),audit_noop).review(envelope()).json()
        answer['snapshot_hash']='wrong'
        cfg=replace(config(),daemon_url='http://127.0.0.1:8766/review')
        with patch.dict('os.environ',{'JEV_APPROVAL_TOKEN':'x'*40}),patch('jev_approval.daemon.urllib.request.build_opener',return_value=Opener(canonical(answer))):
            with self.assertRaises(ContractError):remote_review(envelope(),cfg)
    def test_daemon_cannot_widen_client_tool_scope(self):
        answer=Engine(config(),FakeProvider(),audit_noop).review(envelope()).json()
        cfg=replace(config(),fast_allow_tools=(),daemon_url='http://127.0.0.1:8766/review')
        with patch.dict('os.environ',{'JEV_APPROVAL_TOKEN':'x'*40}),patch('jev_approval.daemon.urllib.request.build_opener',return_value=Opener(canonical(answer))):
            self.assertEqual(remote_review(envelope(),cfg)['decision'],'defer')
    def test_daemon_cannot_bypass_client_policy_pin(self):
        answer=Engine(config(),FakeProvider(),audit_noop).review(envelope()).json()
        cfg=replace(config(),approved_policy_hashes=(),daemon_url='http://127.0.0.1:8766/review')
        with patch.dict('os.environ',{'JEV_APPROVAL_TOKEN':'x'*40}),patch('jev_approval.daemon.urllib.request.build_opener',return_value=Opener(canonical(answer))):
            self.assertEqual(remote_review(envelope(),cfg)['decision'],'defer')
