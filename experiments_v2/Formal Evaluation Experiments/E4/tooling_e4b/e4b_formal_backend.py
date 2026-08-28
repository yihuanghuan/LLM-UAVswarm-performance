"""Construct frozen E4B allocation/profiles and delegate one exact execution."""
from __future__ import annotations
from dataclasses import asdict
import json,subprocess,sys
from pathlib import Path
from e4b_trial_registry import REPO_ROOT,POLICY_PATH,canonical_sha256
from e4b_scorer import validate_authority
def build_runtime_spec(s):
 for p in (REPO_ROOT/'location_allocate',REPO_ROOT/'lfs_policy'):
  if str(p) not in sys.path:sys.path.insert(0,str(p))
 from location_allocate.execution_profile_compiler import compile_execution_profiles
 from location_allocate.lfs_types import ExecutableLFS
 from location_allocate.policy_adapter import load_runtime_policy
 policy=load_runtime_policy(POLICY_PATH)[1];ids=sorted(int(x) for x in s['initial_positions_m']);initial=[[float(value) for value in s['initial_positions_m'][i]] for i in ids];ordered=[[float(value) for value in s['ordered_targets_m'][i]] for i in ids];duration=float(s['expected_T_exec_s'] if s['expected_T_exec_s'] is not None else s['requested_T']['value_s']);safety=policy.resolve_safety(1.0);allocator=policy.allocator_factory(safety.d_hard,safety.d_plan);targets,metrics=allocator.allocate_mode_with_metrics(initial,ordered,duration,s['assignment_mode'])
 exe=ExecutableLFS(uav_ids=tuple(ids),formation={'type':'E4B_exact_registered_targets'},center=(0.,0.,0.),radius=0.,duration=duration,motion_style=s['style'],safety_factor=1.0,trigger_semantics={'mode':'direct'});profiles=compile_execution_profiles(exe,initial,targets,policy.profile,safety.soft_iapf)
 r={'runtime_spec_type':'E4B_registered_physical_runtime_v1','fixture_class':s.get('fixture_class','registered_formal_spec'),'dataset_class':s.get('dataset_class','formal_evaluation'),'trial_id':s['trial_id'],'seed':s['seed'],'scenario_id':s['scenario_id'],'uav_ids':ids,'initial_positions_m':initial,'ordered_targets_m':ordered,'assigned_targets_m':targets,'requested_T':s['requested_T'],'T_min_s':s.get('T_min_s'),'duration_s':duration,'style':s['style'],'safety_s':1.0,'assignment_mode':s['assignment_mode'],'avoidance_mode':s['avoidance_mode'],'profiles':[asdict(x) for x in profiles],'allocation_metrics':asdict(metrics),'allocator_diagnostics':allocator.metrics_dict(),'resolved_safety':asdict(safety),'timing_feasibility_evidence':s.get('timing_feasibility_evidence'),'authority_evidence':{'deterministic_checks':validate_authority(s),'hierarchy':s['authority_hierarchy'],'predicates':s['authority_predicates'],'frozen_motion_limits':s['frozen_motion_limits'],'controller_hard_clamps':s['controller_hard_clamps'],'safety_contract':s['safety_contract']},'metric_log_schema':s['metric_log_schema']};r['runtime_spec_sha256']=canonical_sha256(r);return r
def execute_registered_trial(s,raw):
 raw=Path(raw);raw.mkdir(parents=True,exist_ok=True);spec=build_runtime_spec(s);p=raw/'runtime_spec.json';p.write_text(json.dumps(spec,indent=2,sort_keys=True)+'\n');result=raw/'physical_result.json';run=subprocess.run([sys.executable,str(Path(__file__).with_name('e4b_physical_trial.py')),'--runtime-spec',str(p),'--output',str(raw),'--result',str(result)],cwd=REPO_ROOT,text=True,capture_output=True,timeout=420);(raw/'harness.stdout.log').write_text(run.stdout);(raw/'harness.stderr.log').write_text(run.stderr)
 if not result.exists():raise RuntimeError('physical result missing')
 value=json.loads(result.read_text());value['harness_returncode']=run.returncode;return value
