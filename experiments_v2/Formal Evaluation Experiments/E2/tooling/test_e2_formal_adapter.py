from copy import deepcopy
import json
from pathlib import Path
import pytest
from e2_common import (CANONICAL_POLICY_SHA256, ORDER_TXT_PATH, POLICY_PATH,
                       load_scenario_registry, registered_trial_ids)
from e2_formal_adapter import *
from e2_formal_adapter import (_assert_formal_backend_record, _formalize_backend_record,
                               _registered_spec)
from e2_provenance import validate_provenance
from e2_runner import build_attempt_record
from location_allocate.policy_adapter import load_runtime_policy
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

def synthetic_backend_record():
 t=registered_trial_ids()[0]
 return build_attempt_record(t,load_scenario_registry(),load_runtime_policy(POLICY_PATH)[1],validate_provenance(),ORDER_TXT_PATH.read_text().splitlines().index(t)+1,1)

def test_original_synthetic_runner_classification_unchanged():
 record=synthetic_backend_record()
 assert record['dataset_class']=='synthetic_validation'
 assert record['accepted_formal_result'] is False
 assert record['result_notice']=='NOT_FORMAL_RESULT'

def test_formal_backend_normalization():
 record=_formalize_backend_record(synthetic_backend_record())
 _assert_formal_backend_record(record)
 assert record['dataset_class']=='formal_evaluation'
 assert record['accepted_formal_result'] is True
 assert record['result_notice'] is None

def test_formal_normalization_changes_only_classification_fields():
 original=synthetic_backend_record(); formalized=_formalize_backend_record(deepcopy(original))
 same=lambda left,right:json.dumps(left,sort_keys=True,separators=(',',':'))==json.dumps(right,sort_keys=True,separators=(',',':'))
 changed={key for key in original if not same(original[key],formalized[key])}
 assert changed=={'dataset_class','accepted_formal_result','result_notice'}
 for key in set(original)-changed:
  assert same(original[key],formalized[key])
 assert original['replay']['deterministic_payload_hash']==formalized['replay']['deterministic_payload_hash']

def test_formal_backend_classification_fails_closed(monkeypatch,tmp_path):
 t=registered_trial_ids()[0]; bad=synthetic_backend_record()
 monkeypatch.setattr('e2_formal_adapter._formal_backend',lambda _trial,_position:bad)
 c=ctx(t,tmp_path/'formal',execution_mode='formal',dataset_class='formal_evaluation',formal_launch_authorized=True,launch_gate_status='READY_FOR_FORMAL_LAUNCH')
 result=run_exact_trial(t,c)
 assert result['attempt_status']=='infrastructure_failure'
 assert not (tmp_path/'formal'/'raw'/'offline_resolution_trace.json').exists()
