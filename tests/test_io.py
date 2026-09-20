from pathlib import Path
from dataclasses import replace
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from jev_approval.audit import append_record
from jev_approval.config import Config
from jev_approval.daemon import ApprovalServer
from jev_approval.engine import Engine
from jev_approval.schema import ContractError, canonical
from .helpers import envelope,config,FakeProvider,audit_noop
ROOT=Path(__file__).resolve().parents[1]

class IOTests(unittest.TestCase):
    def test_private_audit_write(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'audit.jsonl';append_record(str(p),{'decision':'defer'})
            self.assertEqual(json.loads(p.read_text())['decision'],'defer')
            if os.name=='posix':self.assertEqual(p.stat().st_mode&0o777,0o600)
    @unittest.skipUnless(os.name=='posix','POSIX permissions')
    def test_public_audit_file_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'a';p.touch();p.chmod(0o644)
            with self.assertRaises(ContractError):append_record(str(p),{})
    @unittest.skipUnless(os.name=='posix','POSIX symlinks')
    def test_audit_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'target';p.touch();p.chmod(0o600);link=Path(t)/'link';link.symlink_to(p)
            with self.assertRaises(OSError):append_record(str(link),{})
    def test_config_load(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'c.toml';p.write_text('mode="off"\n');p.chmod(0o600)
            self.assertEqual(Config.load(p).mode,'off')
    def test_config_typo_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'c.toml';p.write_text('mod="enforce"\n');p.chmod(0o600)
            with self.assertRaises(ContractError):Config.load(p)
    @unittest.skipUnless(os.name=='posix','POSIX permissions')
    def test_writable_config_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'c.toml';p.write_text('mode="off"');p.chmod(0o666)
            with self.assertRaises(ContractError):Config.load(p)
    def test_native_bad_json_returns_defer(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'c.toml';p.write_text('mode="off"');p.chmod(0o600)
            r=subprocess.run([sys.executable,'-I',str(ROOT/'scripts/launcher.py'),'native','--config',str(p)],
                input='{bad',text=True,capture_output=True,check=True)
            self.assertEqual(json.loads(r.stdout)['decision'],'defer')
    def test_hook_output_never_allows(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'c.toml';p.write_text('mode="off"');p.chmod(0o600)
            r=subprocess.run([sys.executable,'-I',str(ROOT/'scripts/launcher.py'),'hook','--config',str(p)],
                input='{}',text=True,capture_output=True,check=True)
            self.assertEqual(json.loads(r.stdout),{})
    def test_daemon_rejects_external_bind(self):
        with self.assertRaises(ContractError):ApprovalServer(('0.0.0.0',0),Engine(config(),FakeProvider(),audit_noop),'x'*40)
    def test_daemon_rejects_weak_token(self):
        with self.assertRaises(ContractError):ApprovalServer(('127.0.0.1',0),Engine(config(),FakeProvider(),audit_noop),'short')
    def test_daemon_auth_and_bound_roundtrip(self):
        s=ApprovalServer(('127.0.0.1',0),Engine(config(),FakeProvider(),audit_noop),'x'*40)
        thread=threading.Thread(target=s.serve_forever,daemon=True);thread.start()
        try:
            url='http://127.0.0.1:'+str(s.server_address[1])+'/review'
            request=urllib.request.Request(url,data=canonical(envelope().json()),headers={'Content-Type':'application/json'})
            with self.assertRaises(urllib.error.HTTPError) as ctx:urllib.request.urlopen(request,timeout=2)
            self.assertEqual(ctx.exception.code,401);ctx.exception.close()
            request.add_header('Authorization','Bearer '+'x'*40)
            with urllib.request.urlopen(request,timeout=2) as response:result=json.load(response)
            self.assertEqual(result['decision'],'allow');self.assertEqual(result['request_id'],envelope().request_id)
        finally:
            s.shutdown();s.server_close();thread.join(timeout=2)
    def test_native_patcher_preserves_original_validation(self):
        spec=importlib.util.spec_from_file_location('install_native',ROOT/'scripts/install_native.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        sample='pub(in crate::guardian) struct PreparedApproval {\n}\n            PreparedApproval {\n}\n'+module.OLD_CALL+'\n// ORIGINAL_FRESHNESS_VALIDATION\n'
        updated=module.transform('guardian/review_request.rs',sample)
        self.assertIn('ORIGINAL_FRESHNESS_VALIDATION',updated)
        self.assertIn('run_guardian_review_session_before_deadline',updated)
        self.assertIn('jev_review_id: review_id.to_owned()',updated)
    def test_native_patcher_refuses_changed_anchor(self):
        spec=importlib.util.spec_from_file_location('install_native',ROOT/'scripts/install_native.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with self.assertRaises(ValueError):module.transform('guardian/mod.rs','// unexpected source\n')
