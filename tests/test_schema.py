import unittest
import math
from jev_approval.schema import strict_json, Vector, ContractError, Envelope, probability, canonical
from jev_approval.config import Config
from dataclasses import replace
from .helpers import raw_response,envelope

class ContractTests(unittest.TestCase):
    def test_valid_response(self):self.assertEqual(Vector.parse(raw_response(),'jev-1.13.0').choices['risk'].choice,'low')
    def test_duplicate_json_keys(self):
        with self.assertRaises(ContractError):strict_json('{"decision":"deny","decision":"allow"}')
    def test_nonfinite_json(self):
        for x in ('NaN','Infinity','-Infinity'):
            with self.subTest(x=x),self.assertRaises(ContractError):strict_json('{"x":'+x+'}')
    def test_bool_is_not_probability(self):
        with self.assertRaises(ContractError):probability(True)
    def test_bad_probability_values(self):
        for value in (-.01,1.01,float('nan'),float('inf'),'0.9',None):
            with self.subTest(value=value),self.assertRaises(ContractError):probability(value)
    def test_missing_answer(self):
        raw=raw_response();del raw['answers']['risk']
        with self.assertRaises(ContractError):Vector.parse(raw,'jev-1.13.0')
    def test_extra_answer(self):
        raw=raw_response();raw['answers']['extra']={}
        with self.assertRaises(ContractError):Vector.parse(raw,'jev-1.13.0')
    def test_missing_confidence(self):
        raw=raw_response();del raw['answers']['risk']['confidence']
        with self.assertRaises(ContractError):Vector.parse(raw,'jev-1.13.0')
    def test_distribution_sum(self):
        raw=raw_response();raw['answers']['risk']['probabilities']['low']=.3
        with self.assertRaises(ContractError):Vector.parse(raw,'jev-1.13.0')
    def test_selection_not_argmax(self):
        raw=raw_response();raw['answers']['risk']['choice']='high'
        with self.assertRaises(ContractError):Vector.parse(raw,'jev-1.13.0')
    def test_wrong_primitive(self):
        raw=raw_response();raw['answers']['destructive']['type']='score'
        with self.assertRaises(ContractError):Vector.parse(raw,'jev-1.13.0')
    def test_invalid_usage(self):
        raw=raw_response();raw['usage']['input_tokens']=True
        with self.assertRaises(ContractError):Vector.parse(raw,'jev-1.13.0')
    def test_missing_host_guard(self):
        raw=envelope().json();del raw['guards']['mandatory_review']
        with self.assertRaises(ContractError):Envelope.parse(raw)
    def test_string_false_rejected(self):
        raw=envelope().json();raw['guards']['mandatory_review']='false'
        with self.assertRaises(ContractError):Envelope.parse(raw)
    def test_unknown_envelope_field(self):
        raw=envelope().json();raw['approved']=True
        with self.assertRaises(ContractError):Envelope.parse(raw)
    def test_model_alias_not_accepted(self):
        with self.assertRaises(ContractError):replace(Config(),model='jev-latest').validate()
    def test_arbitrary_provider_not_accepted(self):
        with self.assertRaises(ContractError):replace(Config(),endpoint='https://attacker.invalid').validate()
    def test_arbitrary_daemon_not_accepted(self):
        with self.assertRaises(ContractError):replace(Config(),daemon_url='http://example.org/review').validate()
    def test_unknown_fast_allow_tool(self):
        with self.assertRaises(ContractError):replace(Config(),fast_allow_tools=('write_stdin',)).validate()
    def test_canonical_json_is_order_independent(self):self.assertEqual(canonical({'b':2,'a':1}),canonical({'a':1,'b':2}))
