"""Launch-gate and real pinned-adapter integration tests (never formal mode)."""
from __future__ import annotations
from copy import deepcopy
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from campaign_common import CANONICAL_POLICY_SHA256,ORDER_TXT_SHA256,CampaignError,load_json,load_sealed_order,sha256_file,write_json_exclusive
from campaign_journal import CampaignExecutionLock
from formal_campaign_launcher import FormalCampaignLauncher
from pinned_adapter_loader import PinnedAdapterLoader
from runner_registry import formal_launch_gate,load_runner_registry,validate_registry_pins
class FormalLauncherTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.registry=load_runner_registry();cls.order=load_sealed_order();cls.loader=PinnedAdapterLoader(cls.registry)
 def setUp(self):self.temp=tempfile.TemporaryDirectory(prefix='formal-launch-test-');self.root=Path(self.temp.name)/'campaign/results/synthetic-validation'
 def tearDown(self):self.temp.cleanup()
 def launcher(self,run='test'):return FormalCampaignLauncher('rehearsal',run,self.root,FakeFormalAdapterLoader())
 def test_all_five_original_pins_remain_verifiable(self):self.assertEqual(validate_registry_pins(self.registry)['status'],'PASS')
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

class FakeFormalAdapterLoader:
 def __init__(self,statuses=()):self.statuses=list(statuses)
 def verify_all_checkouts(self):return {'status':'PASS'}
 def run_exact_trial(self,family,trial,context):
  out=Path(context['attempt_output_dir']);artifact=out/'attempt.json';status=self.statuses.pop(0) if self.statuses else context.get('failure_injection','success');accepted=context['execution_mode']=='formal'
  write_json_exclusive(artifact,{'record_type':'isolated_fake_formal_attempt_v1','dataset_class':'formal_evaluation' if accepted else 'synthetic_validation','accepted_formal_result':accepted,'trial_id':trial,'experiment':family,'global_position':context['global_trial_position'],'attempt_status':status,'replacement_attempt':False})
  return {'trial_id':trial,'experiment':family,'attempt_status':status,'artifact_path':str(artifact),'artifact_sha256':sha256_file(artifact)}

class FormalRestartResumeRegressionTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.registry=load_runner_registry();cls.order=load_sealed_order()
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(prefix='isolated-formal-resume-');self.root=Path(self.temp.name)/'formal';self.gate=Path(self.temp.name)/'gate.json'
  source=Path(__file__).resolve().parent/'formal_launch_gate_v1.json';write_json_exclusive(self.gate,load_json(source))
 def tearDown(self):self.temp.cleanup()
 def launcher(self,statuses=()):return FormalCampaignLauncher('formal',run_root=self.root,loader=FakeFormalAdapterLoader(statuses),gate_path=self.gate)
 def rewrite_manifest(self,transform):
  path=self.root/'launcher_run_manifest.json';path.chmod(0o644);value=load_json(path);transform(value);path.write_text(json.dumps(value,sort_keys=True,indent=2)+'\n',encoding='utf-8')
 def test_initialize_and_restart_before_first_retained_attempt(self):
  first=self.launcher();manifest=self.root/'launcher_run_manifest.json';self.assertTrue(manifest.is_file());digest=sha256_file(manifest)
  second=self.launcher();self.assertEqual(second.validate_state()['next_position'],1);self.assertEqual(sha256_file(manifest),digest);self.assertFalse(second.lock.exists())
 def test_existing_empty_formal_root_initializes_manifest(self):
  self.root.mkdir(parents=True);launcher=self.launcher();self.assertEqual(launcher.validate_state()['next_position'],1);self.assertTrue((self.root/'launcher_run_manifest.json').is_file())
 def test_retained_one_restart_dispatch_two_exact_prefix_and_immutable_manifest(self):
  first=self.launcher();manifest=self.root/'launcher_run_manifest.json';digest=sha256_file(manifest);first.dispatch_next()
  second=self.launcher();self.assertEqual(second.validate_state()['next_position'],2);second.dispatch_next();records=second.journal.read()
  self.assertEqual([x['global_position'] for x in records],[1,2]);self.assertEqual([x['trial_id'] for x in records],self.order[:2]);self.assertEqual(sha256_file(manifest),digest)
  with self.assertRaisesRegex(CampaignError,'required before position #3'):second.validate_state()
 def test_retained_failure_restart_advances_without_retry(self):
  first=self.launcher(('infrastructure_failure',));self.assertEqual(first.dispatch_next()['attempt_status'],'infrastructure_failure')
  second=self.launcher();self.assertEqual(second.validate_state()['next_position'],2);self.assertEqual(second.dispatch_next()['global_position'],2)
 def test_nonempty_root_without_manifest_fails_closed(self):
  self.root.mkdir(parents=True);write_json_exclusive(self.root/'unknown.json',{'unknown':True})
  with self.assertRaisesRegex(CampaignError,'unrecognized nonempty formal root'):self.launcher()
 def test_malformed_or_tampered_manifest_fails_closed(self):
  self.launcher();path=self.root/'launcher_run_manifest.json';path.chmod(0o644);path.write_text('{not-json',encoding='utf-8')
  with self.assertRaises(CampaignError):self.launcher()
 def test_manifest_provenance_mismatch_fails_closed(self):
  self.launcher();self.rewrite_manifest(lambda value:value.__setitem__('global_order_sha256','0'*64))
  with self.assertRaisesRegex(CampaignError,'provenance mismatch'):self.launcher()
 def test_launch_gate_identity_mismatch_fails_closed_on_resume(self):
  self.launcher();self.gate.chmod(0o644);gate=load_json(self.gate);gate['blockers']=['tampered'];self.gate.write_text(json.dumps(gate,sort_keys=True,indent=2)+'\n',encoding='utf-8')
  with self.assertRaisesRegex(CampaignError,'provenance mismatch'):self.launcher()
 def test_duplicate_or_replacement_after_resume_fails_closed(self):
  first=self.launcher();first.dispatch_next();second=self.launcher()
  with self.assertRaises(CampaignError):second.dispatch_next(self.order[0])
  journal=self.root/'suite-journal/000001-attempt.json';journal.chmod(0o644);record=load_json(journal);record['replacement_attempt']=True;journal.write_text(json.dumps(record,sort_keys=True,indent=2)+'\n',encoding='utf-8')
  with self.assertRaises(CampaignError):self.launcher()
if __name__=='__main__':unittest.main()
