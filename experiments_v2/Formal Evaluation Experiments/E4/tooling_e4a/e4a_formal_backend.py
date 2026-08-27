"""Construct frozen E4A profiles and delegate one exact physical execution."""
from __future__ import annotations
from dataclasses import asdict
import json,subprocess,sys
from pathlib import Path
from types import SimpleNamespace
from e4a_trial_registry import REPO_ROOT,POLICY_PATH,canonical_sha256
def build_runtime_spec(s):
 for p in (REPO_ROOT/'location_allocate',REPO_ROOT/'lfs_policy'):
  if str(p) not in sys.path:sys.path.insert(0,str(p))
 from location_allocate.execution_profile_compiler import compile_execution_profiles
 from location_allocate.lfs_types import ExecutableLFS
 from location_allocate.policy_adapter import load_runtime_policy
 policy=load_runtime_policy(POLICY_PATH)[1];ids=[int(x) for x in s['uav_ids']];initial=[s['initial_positions_m'][i] for i in ids];targets=[s['assigned_targets_m'][i] for i in ids];duration=float(s['T_exec_requirement_s'])
 exe=ExecutableLFS(uav_ids=tuple(ids),formation={'type':'E4A_exact_registered_targets'},center=(0.,0.,0.),radius=0.,duration=duration,motion_style=s['style'],safety_factor=float(s['safety_s']),trigger_semantics=s['q']); profiles=compile_execution_profiles(exe,initial,targets,policy.profile,policy.resolve_safety(float(s['safety_s'])).soft_iapf)
 r={'runtime_spec_type':'E4A_registered_physical_runtime_v1','fixture_class':s.get('fixture_class','registered_formal_spec'),'dataset_class':s.get('dataset_class','formal_evaluation'),'trial_id':s['trial_id'],'seed':s['seed'],'uav_ids':ids,'initial_positions_m':initial,'assigned_targets_m':targets,'duration_s':duration,'style':s['style'],'safety_s':s['safety_s'],'profiles':[asdict(x) for x in profiles],'nominal_reference':s['nominal_reference'],'metric_log_schema':s['metric_log_schema']};r['runtime_spec_sha256']=canonical_sha256(r);return r
def execute_registered_trial(s,raw):
 raw=Path(raw);raw.mkdir(parents=True,exist_ok=True);spec=build_runtime_spec(s);p=raw/'runtime_spec.json';p.write_text(json.dumps(spec,indent=2,sort_keys=True)+'\n');result=raw/'physical_result.json';run=subprocess.run([sys.executable,str(Path(__file__).with_name('e4a_physical_trial.py')),'--runtime-spec',str(p),'--output',str(raw),'--result',str(result)],cwd=REPO_ROOT,text=True,capture_output=True,timeout=420);(raw/'harness.stdout.log').write_text(run.stdout);(raw/'harness.stderr.log').write_text(run.stderr)
 if not result.exists():raise RuntimeError('physical result missing')
 value=json.loads(result.read_text());value['harness_returncode']=run.returncode;return value
