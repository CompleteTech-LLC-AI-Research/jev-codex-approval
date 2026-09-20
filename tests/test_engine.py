import unittest
from dataclasses import replace
from copy import deepcopy
from jev_approval.engine import Engine, CircuitBreaker
from jev_approval.schema import Envelope, HAZARDS
from .helpers import envelope, raw_response, FakeProvider, config, audit_noop

class EngineTests(unittest.TestCase):
    def result(self,env=None,provider=None,cfg=None,audit=audit_noop):
        env=env or envelope()
        provider=provider or FakeProvider()
        return Engine(cfg or config(env),provider,audit).review(env)
    def test_low_risk_allow(self):
        r=self.result();self.assertEqual(r.decision,'allow');self.assertEqual(r.candidate,'allow')
    def test_shadow_never_approves(self):
        r=self.result(cfg=replace(config(),mode='shadow'));self.assertEqual(r.decision,'defer');self.assertEqual(r.candidate,'allow')
    def test_off_never_calls_provider(self):
        p=FakeProvider();r=self.result(provider=p,cfg=replace(config(),mode='off'));self.assertEqual(p.calls,0)
    def test_no_remote_consent(self):
        p=FakeProvider();r=self.result(provider=p,cfg=replace(config(),allow_remote_context=False));self.assertEqual(p.calls,0)
    def test_each_host_guard_forces_original_review(self):
        for key,value in {'context_complete':False,'mandatory_review':True,'fresh_review':True,
                          'retry':True,'escalated':True,'cancelled':True,'authorization_current':False}.items():
            with self.subTest(key=key):
                raw=envelope().json();raw['guards'][key]=value;env=Envelope.parse(raw);p=FakeProvider()
                r=self.result(env,p);self.assertEqual(r.decision,'defer');self.assertEqual(p.calls,0)
    def test_hook_cannot_upgrade_host_authority(self):
        env=replace(envelope(),source='codex-hook');p=FakeProvider();r=self.result(env,p)
        self.assertEqual(r.decision,'defer');self.assertEqual(p.calls,0)
    def test_evaluation_cannot_grant_live_permission(self):
        r=self.result(replace(envelope(),source='offline-evaluation'));self.assertEqual(r.decision,'defer')
    def test_policy_pin_required(self):
        r=self.result(cfg=replace(config(),approved_policy_hashes=()));self.assertEqual(r.reason,'policy_or_question_set_not_approved')
    def test_question_pin_required(self):
        r=self.result(cfg=replace(config(),approved_question_hash=''));self.assertEqual(r.decision,'defer')
    def test_model_drift(self):
        raw=raw_response();raw['model']='jev-9.0.0';r=self.result(provider=FakeProvider(raw));self.assertEqual(r.decision,'defer')
    def test_low_confidence(self):
        raw=raw_response();raw['answers']['risk']['confidence']=.5
        self.assertEqual(self.result(provider=FakeProvider(raw)).reason,'low_confidence')
    def test_low_selected_probability(self):
        raw=raw_response();raw['answers']['risk']['probabilities'].update(low=.98,medium=.02)
        self.assertEqual(self.result(provider=FakeProvider(raw)).decision,'defer')
    def test_each_hazard_prevents_allow(self):
        for key in HAZARDS:
            with self.subTest(key=key):
                raw=raw_response();raw['answers'][key]['noul']=.2
                self.assertEqual(self.result(provider=FakeProvider(raw)).reason,'hazard_requires_guardian')
    def test_high_risk_not_automatic_deny(self):
        raw=raw_response({'risk':'high'})
        self.assertEqual(self.result(provider=FakeProvider(raw)).decision,'defer')
    def test_unknown_authorization(self):
        raw=raw_response({'authorization':'unknown'});self.assertEqual(self.result(provider=FakeProvider(raw)).decision,'defer')
    def test_needs_investigation(self):
        raw=raw_response({'evidence':'needs_investigation'});self.assertEqual(self.result(provider=FakeProvider(raw)).decision,'defer')
    def test_fast_deny_requires_opt_in(self):
        raw=raw_response({'risk':'high','authorization':'absent','compliance':'violation'})
        self.assertEqual(self.result(provider=FakeProvider(raw)).decision,'defer')
    def test_clear_policy_deny(self):
        raw=raw_response({'risk':'high','authorization':'absent','compliance':'violation'})
        self.assertEqual(self.result(provider=FakeProvider(raw),cfg=replace(config(),enable_fast_deny=True)).decision,'deny')
    def test_unconfigured_action_category(self):
        env=replace(envelope(),action={'tool':'mcp_tool_call','arguments':{}})
        self.assertEqual(self.result(env).decision,'defer')
    def test_oversize_does_not_silently_truncate(self):
        raw=envelope().json();raw['context']['messages']=[{'text':'x'*25000}];env=Envelope.parse(raw);p=FakeProvider()
        self.assertEqual(self.result(env,p).reason,'state_too_large');self.assertEqual(p.calls,0)
    def test_multimedia_deferred(self):
        raw=envelope().json();raw['context']['messages']=[{'type':'input_image','image_url':'private'}]
        self.assertEqual(self.result(Envelope.parse(raw)).reason,'unsupported_media')
    def test_secret_not_sent(self):
        raw=envelope().json();raw['action']['command']=['echo','api_key=abcdefghijklmnopqrstuvwxyz'];p=FakeProvider()
        self.assertEqual(self.result(Envelope.parse(raw),p).reason,'possible_secret_no_egress');self.assertEqual(p.calls,0)
    def test_provider_failure(self):
        r=self.result(provider=FakeProvider(failure=True));self.assertEqual(r.decision,'defer');self.assertNotIn('traceback',str(r.json()))
    def test_audit_failure_prevents_allow(self):
        def fail(*_):raise OSError()
        self.assertEqual(self.result(audit=fail).reason,'audit_unavailable')
    def test_audit_is_data_minimal(self):
        records=[];self.result(audit=lambda _,r:records.append(r))
        text=str(records);self.assertNotIn('/workspace',text);self.assertNotIn('Show the current',text)
    def test_circuit_breaker(self):
        p=FakeProvider(failure=True);engine=Engine(config(),p,audit_noop)
        for _ in range(3):engine.review(envelope())
        self.assertEqual(engine.review(envelope()).reason,'circuit_open');self.assertEqual(p.calls,3)
    def test_binding_changes_with_action_and_revision(self):
        a=envelope();raw=a.json();raw['context']['authorization_revision']='revision-2';b=Envelope.parse(raw)
        self.assertNotEqual(a.snapshot_hash,b.snapshot_hash)
        raw=a.json();raw['action']['command']=['rm','data'];self.assertNotEqual(a.snapshot_hash,Envelope.parse(raw).snapshot_hash)
