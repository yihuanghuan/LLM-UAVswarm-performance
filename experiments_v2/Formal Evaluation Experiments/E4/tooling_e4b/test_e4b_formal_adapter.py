from pathlib import Path
import pytest
from e4b_trial_registry import *
from e4b_formal_adapter import FormalAdapterError,identity,run_exact_trial
from e4b_formal_backend import build_runtime_spec
def ctx(t,root,**kw):
 i=identity();v={'execution_mode':'spec_rehearsal','dataset_class':'synthetic_validation','formal_launch_authorized':False,'trial_id':t,'global_trial_position':ORDER_PATH.read_text().splitlines().index(t)+1,'runner_commit':i['commit'],'runner_source_sha256':i['source_sha256'],'policy_sha256':POLICY_SHA256,'protocol_sha256':PROTOCOL_SHA256,'registry_sha256':REGISTRY_SHA256,'global_trial_order_sha256':ORDER_SHA256,'attempt_output_dir':str(root)};v.update(kw);return v
def test_population_and_runtime_reconstruction():
 ids=registered_trial_ids();assert len(ids)==len(set(ids))==60
 for t in ids:
  r=build_runtime_spec(build_exact_spec(t));assert r==build_runtime_spec(build_exact_spec(t));assert len(r['authority_evidence']['predicates'])==6
  if r['T_min_s'] is not None:assert r['duration_s']>=r['T_min_s']-TOLERANCE
def test_rehearsal_duplicate_no_journal_and_labels(tmp_path):
 t=registered_trial_ids()[0];c=ctx(t,tmp_path/'a');d=run_exact_trial(t,c);assert not d['accepted_formal_result'];assert d['dataset_class']=='synthetic_validation';assert not list(tmp_path.rglob('*journal*'))
 with pytest.raises(FormalAdapterError):run_exact_trial(t,c)
@pytest.mark.parametrize('field,value',[('global_trial_position',611),('runner_commit','0'*40),('runner_source_sha256','0'*64),('policy_sha256','0'*64),('protocol_sha256','0'*64),('registry_sha256','0'*64),('global_trial_order_sha256','0'*64)])
def test_context_fail_closed(field,value,tmp_path):
 t=registered_trial_ids()[0]
 with pytest.raises(FormalAdapterError):run_exact_trial(t,ctx(t,tmp_path/'a',**{field:value}))
def test_wrong_family_and_formal_gate(tmp_path):
 t=registered_trial_ids()[0]
 with pytest.raises(Exception):run_exact_trial('E4A-HORIZONTAL__smooth__S54101',ctx(t,tmp_path/'x',trial_id='E4A-HORIZONTAL__smooth__S54101'))
 with pytest.raises(FormalAdapterError):run_exact_trial(t,ctx(t,tmp_path/'f',execution_mode='formal',dataset_class='formal_evaluation',formal_launch_authorized=False,launch_gate_status='READY_FOR_FORMAL_LAUNCH'))
def test_failure_injection_retained(tmp_path):
 t=registered_trial_ids()[0];assert run_exact_trial(t,ctx(t,tmp_path/'a',failure_injection='timeout'))['attempt_status']=='timeout'
def test_engineering_fixture_is_not_registered():
 from e4b_engineering_smoke import fixture
 f=fixture();assert f['trial_id'] not in registered_trial_ids();r=build_runtime_spec(f);assert r['fixture_class']=='non_registered_engineering_fixture';assert r['dataset_class']=='engineering_validation'
