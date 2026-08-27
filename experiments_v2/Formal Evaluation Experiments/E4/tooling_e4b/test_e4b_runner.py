import json,tempfile
from pathlib import Path
import pytest
from e4b_provenance import validate
from e4b_runner import run_exact_trial,SyntheticBackend
from e4b_scorer import validate_authority
from e4b_trial_registry import *
def test_population_hashes_provenance(): assert len(registered_trial_ids())==len(set(registered_trial_ids()))==60; assert sha256_file(PROTOCOL_PATH)==PROTOCOL_SHA256; assert sha256_file(REGISTRY_PATH)==REGISTRY_SHA256; assert validate()['status']=='PASS'
@pytest.mark.parametrize('bad',['X','E4A-HORIZONTAL__smooth__S54101','E4B-AUTO-T__fast__S54201','E4B-AUTO-T__smooth__S99999'])
def test_refusals(bad):
 with pytest.raises(E4BError): build_exact_spec(bad)
def test_duplicate_labels_no_physical_or_formal():
 with tempfile.TemporaryDirectory() as t:
  tid=registered_trial_ids()[0]; d=run_exact_trial(tid,{'exact_trial_id':tid},Path(t),SyntheticBackend()); a=json.loads((Path(t)/d['artifact_path']).read_text()); assert a['accepted_formal_result'] is False and not a['mock_execution']['physical_safety_active_executed']
  with pytest.raises(E4BError): run_exact_trial(tid,{'exact_trial_id':tid},Path(t),SyntheticBackend())
 assert not (E4_DIR/'results'/'formal').exists()
def test_all_authority_predicates_represented():
 ids={p['id'] for p in PREDICATES}; assert len(ids)==6
 for t in registered_trial_ids(): assert {x['predicate_id'] for x in validate_authority(build_exact_spec(t))}==ids
def test_exact_t_fields_and_tolerance():
 v=deterministic_policy_values(); assert abs(v['T_min_s']-2.8844991406148166)<=TOLERANCE
 for st,expected in {'smooth':3.7498488827992618,'normal':3.317174011707039,'aggressive':3.1729490546762986}.items(): assert abs(v['auto_T_exec_s'][st]-expected)<=TOLERANCE
 for st in STYLES: assert build_exact_spec(f'E4B-FEASIBLE-EXPLICIT-T__{st}__S54201')['expected_T_exec_s']==4.0; assert build_exact_spec(f'E4B-INFEASIBLE-EXPLICIT-T__{st}__S54201')['expected_T_exec_s']>=v['T_min_s']-TOLERANCE
def test_hard_limits_safety_and_determinism():
 for t in registered_trial_ids():
  s=build_exact_spec(t); assert s['frozen_motion_limits']=={'velocity_mps':5.0,'acceleration_mps2':5.0,'jerk_mps3':10.0}; assert s['safety_contract']['d_hard']==1.5; assert s==build_exact_spec(t)

