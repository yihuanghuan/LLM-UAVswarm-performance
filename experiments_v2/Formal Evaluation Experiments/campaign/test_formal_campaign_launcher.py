"""Launch-gate and real pinned-adapter integration tests (never formal mode)."""
from __future__ import annotations
from copy import deepcopy
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from campaign_common import CANONICAL_POLICY_SHA256,ORDER_TXT_SHA256,CampaignError,load_sealed_order,write_json_exclusive
from campaign_journal import CampaignExecutionLock
from formal_campaign_launcher import FormalCampaignLauncher
from pinned_adapter_loader import PinnedAdapterLoader
from runner_registry import formal_launch_gate,load_runner_registry,validate_registry_pins
class FormalLauncherTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.registry=load_runner_registry();cls.order=load_sealed_order();cls.loader=PinnedAdapterLoader(cls.registry)
 def setUp(self):self.temp=tempfile.TemporaryDirectory(prefix='formal-launch-test-');self.root=Path(self.temp.name)/'campaign/results/synthetic-validation'
 def tearDown(self):self.temp.cleanup()
 def launcher(self,run='test'):return FormalCampaignLauncher('rehearsal',run,self.root,self.loader)
 def test_all_five_real_entrypoints_verify(self):self.assertEqual(self.loader.verify_all_checkouts()['status'],'PASS')
 def test_registry_refuses_unpinned_and_pin_hash_mismatches(self):
  for mutation in ('unpinned','source','commit','protocol','registry'):
   r=deepcopy(self.registry);e=r['runners']['E2']
   if mutation=='unpinned':e['adapter_commit']=None
   elif mutation=='source':e['adapter_source_sha256']='0'*64
   elif mutation=='commit':e['adapter_commit']='0'*40
   elif mutation=='protocol':e['protocol_sha256']='0'*64
   else:e['registry_sha256']='0'*64
   self.assertFalse(formal_launch_gate(r)[0],mutation)
 def test_context_hashes_fail_closed_in_actual_adapter(self):
  t=self.order[0];e=self.registry['runners']['E2'];base={'execution_mode':'spec_rehearsal','dataset_class':'synthetic_validation','formal_launch_authorized':False,'trial_id':t,'global_trial_position':1,'runner_commit':e['adapter_commit'],'runner_source_sha256':e['adapter_source_sha256'],'policy_sha256':CANONICAL_POLICY_SHA256,'protocol_sha256':e['protocol_sha256'],'registry_sha256':e['registry_sha256'],'global_trial_order_sha256':ORDER_TXT_SHA256,'attempt_output_dir':str(Path(self.temp.name)/'attempt')}
  for field in ('policy_sha256','protocol_sha256','registry_sha256','global_trial_order_sha256'):
   c=dict(base);c[field]='0'*64
   with self.assertRaises(Exception):self.loader.run_exact_trial('E2',t,c)
 def test_requested_selector_future_previous_replacement_seed_refused(self):
  l=self.launcher()
  for requested in (self.order[1],self.order[0].replace('S52105','S99999')):
   with self.assertRaises(CampaignError):l.dispatch_next(requested)
  with self.assertRaises(CampaignError):l.reject_selector('next E2')
  l.dispatch_next()
  with self.assertRaises(CampaignError):l.dispatch_next(self.order[0])
  self.assertEqual(l.validate_state()['next_position'],2)
 def test_success_and_failure_retained_advance_restart_and_duplicate(self):
  l=self.launcher();r=l.dispatch_next();self.assertEqual(r['attempt_status'],'success');self.assertEqual(l.validate_state()['next_position'],2)
  l=self.launcher();r=l.dispatch_next(failure_injection='method_failure');self.assertEqual(r['attempt_status'],'method_failure');self.assertEqual(l.validate_state()['next_position'],3)
  with self.assertRaises(CampaignError):l.dispatch_next(self.order[1])
 def test_concurrent_launcher_refused(self):
  l=self.launcher()
  with CampaignExecutionLock(l.lock):
   with self.assertRaises(CampaignError):l.dispatch_next()
 def test_formal_gate_not_ready_refused_without_formal_output(self):
  gate=Path(self.temp.name)/'gate.json';write_json_exclusive(gate,{'formal_campaign_status':'NOT_READY','formal_campaign_started':False,'next_formal_position':1,'formal_suite_journal_record_count':0})
  root=Path(self.temp.name)/'isolated-formal'
  with self.assertRaises(CampaignError):FormalCampaignLauncher('formal',run_root=root,loader=self.loader,gate_path=gate)
  self.assertFalse(root.exists())
 def test_production_hash_mismatch_fails_provenance(self):
  import campaign_provenance
  with patch.object(campaign_provenance,'CANONICAL_POLICY_SHA256','0'*64):self.assertEqual(campaign_provenance.validate_provenance(False)['status'],'FAIL')
if __name__=='__main__':unittest.main()
