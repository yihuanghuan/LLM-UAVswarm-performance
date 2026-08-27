#!/usr/bin/env python3
import argparse,json,hashlib
from pathlib import Path
from e5_journal import Journal,write_json
from e5_provenance import *
from e5_scorer import validate_artifact
from e5_trial_registry import *
def graph_ok(s):
 sid=s['scenario_id']; g=s['mission_graph']
 if sid=='E5-SEQUENTIAL': return g.get('transition')=='task_1_TRAJECTORY_completion' and g.get('not_stable_hover_completion') is True and g.get('task_1_q')=='continuous'
 if sid=='E5-PARALLEL': return g.get('synchronized') is True and g.get('parallel_task_ids')==[1,2]
 if sid=='E5-MIXED-HIGH': return g.get('synchronized') is True and g.get('transition')=='task_1_TRAJECTORY_completion_to_parallel_group' and g.get('parallel_task_ids')==[2,3]
 return True
def audit_run(root):
 root=Path(root); cs=[]
 def ck(n,o,d): cs.append({'check':n,'status':'PASS' if o else 'FAIL','details':d})
 try:
  exp=registered_trial_ids(); rs=Journal(root/'journal').read(); ids=[r['trial_id'] for r in rs]; ck('population',ids==exp and len(ids)==25,{'registered':25,'validated':len(ids),'missing':len(set(exp)-set(ids)),'duplicate':len(ids)-len(set(ids)),'unregistered':len(set(ids)-set(exp))}); bad=[]; commands=True; graphs=True; readiness=True; modes=True
  reg=scenarios()
  for r in rs:
   p=root/r['artifact_path']
   if not p.is_file() or sha256_file(p)!=r['artifact_sha256']: bad.append(r['trial_id']); continue
   a=json.loads(p.read_text()); validate_artifact(a); s=a['execution_spec']; commands &= s['exact_command']==reg[s['scenario_id']]['exact_command'] and hashlib.sha256(s['exact_command'].encode()).hexdigest()==s['exact_command_utf8_sha256']; graphs &= graph_ok(s); readiness &= s['cold_start_required'] and s['readiness_gate']['required_uav_count']==8 and s['readiness_gate']['before_command_submission']; modes &= s['full_method_modes']==MODES
  ck('artifacts_schema',not bad,bad); ck('exact_command_identity',commands,25); ck('mission_graphs',graphs,25); ck('cold_start_readiness',readiness,25); ck('full_method_only',modes,25); ck('deterministic',all(build_exact_spec(i)==build_exact_spec(i) for i in exp),25); ck('provenance',validate()['status']=='PASS',validate()['status']); manifest=json.loads((root/'run_manifest.json').read_text()); ck('no_llm_gazebo_formal',manifest.get('llm_calls')==0 and manifest.get('gazebo_px4_runs')==0 and not (E5_DIR/'results'/'formal').exists(),manifest)
 except Exception as e: ck('internal_error',False,str(e)); rs=[]
 return {'audit_type':'E5_synthetic_readiness_audit_v1','status':'PASS' if all(c['status']=='PASS' for c in cs) else 'FAIL','dataset_class':'synthetic_validation','accepted_formal_result':False,'result_notice':'NOT_FORMAL_RESULT','registered_attempt_count':25,'synthetic_validated_attempt_count':len(rs),'checks':cs}
def readiness(root,out):
 a=audit_run(root); p=validate(); v={'experiment':'E5','branch':BRANCH,'commit':p['runner_commit'],'runner_entrypoint':'experiments_v2/Formal Evaluation Experiments/E5/tooling/e5_runner.py','runner_source_sha256':sha256_file(TOOLING_DIR/'e5_runner.py'),'source_preflight_commit':SOURCE,'baseline_tag':BASELINE_TAG,'baseline_commit':BASELINE,'policy_sha256':POLICY_SHA256,'protocol_path':PROTOCOL_PATH.relative_to(REPO_ROOT).as_posix(),'protocol_sha256':PROTOCOL_SHA256,'registry_path':REGISTRY_PATH.relative_to(REPO_ROOT).as_posix(),'registry_sha256':REGISTRY_SHA256,'registered_attempt_count':25,'synthetic_validated_attempt_count':a['synthetic_validated_attempt_count'],'production_semantics_changed':False,'accepted_formal_results_created':False,'formal_global_cursor_consumed':False,'validation_status':'READY_FOR_GLOBAL_INTEGRATION' if a['status']=='PASS' else 'BLOCKED','blockers':[] if a['status']=='PASS' else ['audit failed']}; write_json(out,v); return v
if __name__=='__main__':
 p=argparse.ArgumentParser(); p.add_argument('run_dir',type=Path); p.add_argument('--readiness-manifest',type=Path); x=p.parse_args(); r=readiness(x.run_dir,x.readiness_manifest) if x.readiness_manifest else audit_run(x.run_dir); print(json.dumps(r,ensure_ascii=False,indent=2)); raise SystemExit(r.get('status',r.get('validation_status')) not in {'PASS','READY_FOR_GLOBAL_INTEGRATION'})

