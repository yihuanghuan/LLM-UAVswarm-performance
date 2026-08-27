"""Delegate one exact E5 cold-start Full-Method execution."""
from __future__ import annotations
import json,subprocess,sys
from pathlib import Path
from e5_trial_registry import REPO_ROOT,canonical_sha256
def build_runtime_spec(s):
 r={'runtime_spec_type':'E5_registered_full_method_runtime_v1','fixture_class':s.get('fixture_class','registered_formal_spec'),'dataset_class':s.get('dataset_class','formal_evaluation'),'trial_id':s['trial_id'],'seed':s['seed'],'scenario_id':s['scenario_id'],'uav_ids':s['readiness_gate']['uav_ids'],'cold_start_spawn_m':s['cold_start_spawn_m'],'cold_start_required':True,'readiness_gate':s['readiness_gate'],'full_method_modes':s['full_method_modes'],'exact_command':s['exact_command'],'exact_command_utf8_sha256':s['exact_command_utf8_sha256'],'command_source':s['command_source'],'candidate_gt_used_as_input':False,'mission_graph':s['mission_graph'],'mission_timeout_s':s['mission_timeout_s'],'frozen_language_runtime':s['frozen_language_runtime'],'metric_log_schema':s['metric_log_schema']};r['runtime_spec_sha256']=canonical_sha256(r);return r
def execute_registered_trial(s,raw):
 raw=Path(raw);raw.mkdir(parents=True,exist_ok=True);spec=build_runtime_spec(s);p=raw/'runtime_spec.json';p.write_text(json.dumps(spec,ensure_ascii=False,indent=2,sort_keys=True)+'\n');result=raw/'physical_result.json';run=subprocess.run([sys.executable,str(Path(__file__).with_name('e5_physical_trial.py')),'--runtime-spec',str(p),'--output',str(raw),'--result',str(result)],cwd=REPO_ROOT,text=True,capture_output=True,timeout=600);(raw/'harness.stdout.log').write_text(run.stdout);(raw/'harness.stderr.log').write_text(run.stderr)
 if not result.exists():raise RuntimeError('physical result missing')
 value=json.loads(result.read_text());value['harness_returncode']=run.returncode;return value
