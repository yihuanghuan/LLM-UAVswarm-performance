from pathlib import Path
import pytest
from e2_common import CANONICAL_POLICY_SHA256,ORDER_TXT_PATH,registered_trial_ids
from e2_formal_adapter import *
from e2_formal_adapter import _registered_spec
def ctx(t,root,**kw):
 i=identity(); v={'execution_mode':'spec_rehearsal','dataset_class':'synthetic_validation','formal_launch_authorized':False,'trial_id':t,'global_trial_position':ORDER_TXT_PATH.read_text().splitlines().index(t)+1,'runner_commit':i['commit'],'runner_source_sha256':i['source_sha256'],'policy_sha256':CANONICAL_POLICY_SHA256,'protocol_sha256':PROTOCOL_SHA256,'registry_sha256':REGISTRY_SHA256,'global_trial_order_sha256':ORDER_SHA256,'attempt_output_dir':str(root)};v.update(kw);return v
def test_population_and_deterministic_spec():
 ids=registered_trial_ids(); assert len(ids)==len(set(ids))==120; assert [_registered_spec(t) for t in ids]==[_registered_spec(t) for t in ids]
def test_nonformal_retention_and_no_journal(tmp_path):
 t=registered_trial_ids()[0];d=run_exact_trial(t,ctx(t,tmp_path/'a'));assert not d['accepted_formal_result'];assert not list(tmp_path.rglob('*journal*'))
def test_duplicate_refused(tmp_path):
 t=registered_trial_ids()[0];c=ctx(t,tmp_path/'a');run_exact_trial(t,c)
 with pytest.raises(E2FormalAdapterError):run_exact_trial(t,c)
@pytest.mark.parametrize('field,value',[('global_trial_position',611),('runner_commit','0'*40),('runner_source_sha256','0'*64),('policy_sha256','0'*64),('protocol_sha256','0'*64),('registry_sha256','0'*64),('global_trial_order_sha256','0'*64)])
def test_context_mismatch(field,value,tmp_path):
 t=registered_trial_ids()[0]
 with pytest.raises(E2FormalAdapterError):run_exact_trial(t,ctx(t,tmp_path/'a',**{field:value}))
def test_unknown_wrong_family_and_formal_gate(tmp_path):
 t=registered_trial_ids()[0]
 for bad in ('garbage','E3-A-01__P1_F1__S31001'):
  with pytest.raises(Exception):run_exact_trial(bad,ctx(t,tmp_path/bad.replace('/','_'),trial_id=bad))
 with pytest.raises(E2FormalAdapterError):run_exact_trial(t,ctx(t,tmp_path/'formal',execution_mode='formal',dataset_class='formal_evaluation',formal_launch_authorized=False,launch_gate_status='READY_FOR_FORMAL_LAUNCH'))
 assert not (tmp_path/'formal').exists()
def test_failure_retained(tmp_path):
 t=registered_trial_ids()[0];d=run_exact_trial(t,ctx(t,tmp_path/'a',failure_injection='method_failure'));assert d['attempt_status']=='method_failure'
