import hashlib
from pathlib import Path
import pytest
from e5_trial_registry import *
from e5_formal_adapter import FormalAdapterError,identity,run_exact_trial
from e5_formal_backend import build_runtime_spec
from e5_language_driver import classify_method_exception
from e5_physical_trial import completed_language_outcome
from location_allocate.formation_geometry import GeometryError
def ctx(t,root,**kw):
 i=identity();v={'execution_mode':'spec_rehearsal','dataset_class':'synthetic_validation','formal_launch_authorized':False,'trial_id':t,'global_trial_position':ORDER_PATH.read_text().splitlines().index(t)+1,'runner_commit':i['commit'],'runner_source_sha256':i['source_sha256'],'policy_sha256':POLICY_SHA256,'protocol_sha256':PROTOCOL_SHA256,'registry_sha256':REGISTRY_SHA256,'global_trial_order_sha256':ORDER_SHA256,'attempt_output_dir':str(root)};v.update(kw);return v
def test_population_and_exact_runtime_reconstruction():
 ids=registered_trial_ids();assert len(ids)==len(set(ids))==25
 for t in ids:
  s=build_exact_spec(t);r=build_runtime_spec(s);assert r==build_runtime_spec(build_exact_spec(t));assert r['exact_command']==s['exact_command'];assert hashlib.sha256(r['exact_command'].encode()).hexdigest()==r['exact_command_utf8_sha256'];assert not r['candidate_gt_used_as_input'];assert r['full_method_modes']==MODES
def test_rehearsal_duplicate_no_journal_and_labels(tmp_path):
 t=registered_trial_ids()[0];c=ctx(t,tmp_path/'a');d=run_exact_trial(t,c);assert not d['accepted_formal_result'];assert d['dataset_class']=='synthetic_validation';assert not list(tmp_path.rglob('*journal*'))
 with pytest.raises(FormalAdapterError):run_exact_trial(t,c)
@pytest.mark.parametrize('field,value',[('global_trial_position',611),('runner_commit','0'*40),('runner_source_sha256','0'*64),('policy_sha256','0'*64),('protocol_sha256','0'*64),('registry_sha256','0'*64),('global_trial_order_sha256','0'*64)])
def test_context_fail_closed(field,value,tmp_path):
 t=registered_trial_ids()[0]
 with pytest.raises(FormalAdapterError):run_exact_trial(t,ctx(t,tmp_path/'a',**{field:value}))
def test_wrong_family_and_formal_gate(tmp_path):
 t=registered_trial_ids()[0]
 with pytest.raises(Exception):run_exact_trial('E4B-AUTO-T__smooth__S54201',ctx(t,tmp_path/'x',trial_id='E4B-AUTO-T__smooth__S54201'))
 with pytest.raises(FormalAdapterError):run_exact_trial(t,ctx(t,tmp_path/'f',execution_mode='formal',dataset_class='formal_evaluation',formal_launch_authorized=False,launch_gate_status='READY_FOR_FORMAL_LAUNCH'))
def test_failure_injection_retained(tmp_path):
 t=registered_trial_ids()[0];assert run_exact_trial(t,ctx(t,tmp_path/'a',failure_injection='timeout'))['attempt_status']=='timeout'
def test_engineering_fixture_nonregistered_and_full_method():
 from e5_engineering_smoke import fixture
 f=fixture();assert f['trial_id'] not in registered_trial_ids();assert f['exact_command'] not in {x['exact_command'] for x in scenarios().values()};assert f['full_method_modes']==MODES;assert f['dataset_class']=='engineering_validation';assert not f['candidate_gt_used_as_input']
def test_px4_generator_uses_pinned_system_python(tmp_path):
 from e5_physical_trial import env
 e=env(1,tmp_path);assert e['PATH'].split(':')[0]=='/usr/bin'
def test_no_hidden_preview_or_retry_mode():
 source=Path(__file__).with_name('e5_formal_adapter.py').read_text();assert 'preview' not in source;assert "execution_mode')" in source
 driver=Path(__file__).with_name('e5_language_driver.py').read_text();assert "provider_request_attempts_logged" in driver;assert "finally:" in driver
def test_geometry_rejection_is_completed_method_outcome():
 result=classify_method_exception(GeometryError('workspace limit'))
 assert result=={'attempt_status':'method_failure','failure_stage':'resolution','mission_termination':'frozen_method_rejection'}
 assert completed_language_outcome(result)
 assert not completed_language_outcome({'attempt_status':'infrastructure_failure'})
