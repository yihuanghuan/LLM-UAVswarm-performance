import json,tempfile
from pathlib import Path
import pytest
from e4a_provenance import validate
from e4a_runner import run_exact_trial,SyntheticBackend
from e4a_trial_registry import *
def test_population_hashes_provenance(): assert len(registered_trial_ids())==len(set(registered_trial_ids()))==45; assert sha256_file(PROTOCOL_PATH)==PROTOCOL_SHA256; assert sha256_file(REGISTRY_PATH)==REGISTRY_SHA256; assert validate()['status']=='PASS'
@pytest.mark.parametrize('bad',['X','E4B-AUTO-T__smooth__S54201','E4A-HORIZONTAL__fast__S54101','E4A-HORIZONTAL__smooth__S99999'])
def test_refusals(bad):
 with pytest.raises(E4AError): build_exact_spec(bad)
def test_duplicate_synthetic_labels_no_formal():
 with tempfile.TemporaryDirectory() as t:
  tid=registered_trial_ids()[0]; d=run_exact_trial(tid,{'exact_trial_id':tid},Path(t),SyntheticBackend()); a=json.loads((Path(t)/d['artifact_path']).read_text()); assert a['accepted_formal_result'] is False and a['mock_execution']['scientific_outcomes'] is None
  with pytest.raises(E4AError): run_exact_trial(tid,{'exact_trial_id':tid},Path(t),SyntheticBackend())
 assert not (E4_DIR/'results'/'formal').exists()
def test_exact_registered_values_and_isolation():
 expected={'E4A-HORIZONTAL':([0.,4.,0.],4.0),'E4A-VERTICAL':([0.,0.,3.],3.5),'E4A-DIAGONAL-3D':([3.,4.,2.],4.0)}
 for sid,(disp,t) in expected.items():
  for seed in load_registry()['E4_A']['seeds']:
   ss=[build_exact_spec(f'{sid}__{style}__S{seed}') for style in STYLES]; assert all(s['displacement_m']==disp and s['requested_T']['value_s']==t and s['T_exec_requirement_s']==t for s in ss); assert len({canonical_sha256(isolation_projection(s)) for s in ss})==1; assert len({canonical_sha256(s['nominal_reference']) for s in ss})==1; assert [s['motion_style'] for s in ss]==list(STYLES); assert len({s['legitimate_style_profile']['style_gain'] for s in ss})==3
def test_deterministic_reconstruction():
 for tid in registered_trial_ids(): assert build_exact_spec(tid)==build_exact_spec(tid)

