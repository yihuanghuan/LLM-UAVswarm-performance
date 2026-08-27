from pathlib import Path
import tempfile
import pytest
from e3_provenance import validate
from e3_runner import run_exact_trial,SyntheticBackend
from e3_trial_registry import *

def test_population_and_hashes(): assert len(registered_trial_ids())==len(set(registered_trial_ids()))==360; assert sha256_file(PROTOCOL_PATH)==PROTOCOL_SHA256; assert sha256_file(REGISTRY_PATH)==REGISTRY_SHA256
def test_provenance(): assert validate()["status"]=="PASS"
@pytest.mark.parametrize("bad",["X", "E5-SIMPLE__Full_Method__S55101", "E3-A-01__P9_F1__S53101", "E3-A-01__P1_F1__S99999"])
def test_refusals(bad):
    with pytest.raises(E3Error): build_exact_spec(bad)
def test_duplicate_and_labels():
    with tempfile.TemporaryDirectory() as t:
        tid=registered_trial_ids()[0]; root=Path(t); d=run_exact_trial(tid,{"exact_trial_id":tid},root,SyntheticBackend()); assert d["experiment"]=="E3"
        with pytest.raises(E3Error): run_exact_trial(tid,{"exact_trial_id":tid},root,SyntheticBackend())
        a=__import__('json').loads((root/d['artifact_path']).read_text()); assert a['accepted_formal_result'] is False and a['mock_execution']['scientific_outcomes'] is None
def test_mapping_timing_disturbance_and_p0_ownership():
    for tid in registered_trial_ids():
        s=build_exact_spec(tid); c=s['condition']; assert s['assignment_mode']==CONDITION_MAPPING[c]['assignment_mode']; assert s['avoidance_mode']==CONDITION_MAPPING[c]['avoidance_mode']; assert s['staging']=={'stable_continuous_s':2.0,'scored':False}; assert s['scoring']['end_offset_s']==s['duration_s']+2; assert s['timeout_after_t0_s']==s['duration_s']+6; assert s['disturbance']['onset_s']==2 and s['disturbance']['duration_s']==1.5; assert s['disturbance']['zero_wrench_at_end']; assert (not c.startswith('P0')) or s['P0_fixed_target_ownership'] is False
def test_paired_invariants():
    base=None
    for c in CONDITIONS:
        s=build_exact_spec(f'E3-B-01__{c}__S53101'); frozen=(s['initial_positions_m'],s['ordered_targets_m'],s['seed'],s['duration_s'],s['invariants']['control_mode'],s['disturbance'])
        if base is None: base=frozen
        assert frozen==base
def test_deterministic_specs_and_no_formal_mode():
    tid=registered_trial_ids()[99]; assert build_exact_spec(tid)==build_exact_spec(tid); assert not (E3_DIR/'results'/'formal').exists()

