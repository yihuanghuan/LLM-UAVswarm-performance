import json,tempfile,hashlib
from pathlib import Path
import pytest
from e5_audit import graph_ok
from e5_provenance import validate
from e5_runner import run_exact_trial,SyntheticBackend
from e5_trial_registry import *
def test_population_hashes_provenance(): assert len(registered_trial_ids())==len(set(registered_trial_ids()))==25; assert sha256_file(PROTOCOL_PATH)==PROTOCOL_SHA256; assert sha256_file(REGISTRY_PATH)==REGISTRY_SHA256; assert validate()['status']=='PASS'
@pytest.mark.parametrize('bad',['X','E3-A-01__P1_F1__S53101','E5-SIMPLE__Baseline__S55101','E5-SIMPLE__Full_Method__S99999'])
def test_refusals(bad):
 with pytest.raises(E5Error): build_exact_spec(bad)
def test_duplicate_synthetic_no_llm_formal():
 with tempfile.TemporaryDirectory() as t:
  tid=registered_trial_ids()[0]; d=run_exact_trial(tid,{'exact_trial_id':tid},Path(t),SyntheticBackend()); a=json.loads((Path(t)/d['artifact_path']).read_text()); assert a['accepted_formal_result'] is False and not a['mock_execution']['llm_called'] and a['mock_execution']['scientific_outcomes'] is None
  with pytest.raises(E5Error): run_exact_trial(tid,{'exact_trial_id':tid},Path(t),SyntheticBackend())
 assert not (E5_DIR/'results'/'formal').exists()
def test_exact_command_identity_and_gt_not_input():
 reg=scenarios()
 for tid in registered_trial_ids():
  s=build_exact_spec(tid); assert s['exact_command']==reg[s['scenario_id']]['exact_command']; assert hashlib.sha256(s['exact_command'].encode()).hexdigest()==s['exact_command_utf8_sha256']; assert not s['frozen_language_runtime']['candidate_gt_used_as_input']; assert s['candidate_semantic_ground_truth']['usage']=='audit_and_scoring_only_not_runtime_input'
def test_cold_start_readiness_modes_timeout_denominator():
 for tid in registered_trial_ids():
  s=build_exact_spec(tid); assert s['cold_start_required']; assert s['readiness_gate']=={'required_uav_count':8,'uav_ids':[1,2,3,4,5,6,7,8],'all_px4_ready':True,'armed_offboard':True,'frozen_fresh_state_predicate':True,'before_command_submission':True}; assert s['full_method_modes']==MODES; assert s['mission_timeout_s']==float(scenarios()[s['scenario_id']]['mission_timeout_s']); assert s['success_contract']['denominator']=='all retained attempts'; assert not s['success_contract']['retry_or_replacement_allowed']
def test_exact_mission_graph_semantics():
 for tid in registered_trial_ids(): assert graph_ok(build_exact_spec(tid))
 seq=build_exact_spec('E5-SEQUENTIAL__Full_Method__S55101'); assert seq['mission_graph']['transition']=='task_1_TRAJECTORY_completion' and seq['mission_graph']['not_stable_hover_completion']
 par=build_exact_spec('E5-PARALLEL__Full_Method__S55101'); assert par['mission_graph']['synchronized']
 mixed=build_exact_spec('E5-MIXED-HIGH__Full_Method__S55101'); assert mixed['mission_graph']['synchronized'] and mixed['mission_graph']['transition']=='task_1_TRAJECTORY_completion_to_parallel_group'
def test_deterministic_reconstruction():
 for tid in registered_trial_ids(): assert build_exact_spec(tid)==build_exact_spec(tid)

