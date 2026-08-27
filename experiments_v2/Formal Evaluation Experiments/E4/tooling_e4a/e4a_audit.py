#!/usr/bin/env python3
import argparse,json
from pathlib import Path
from e4a_journal import Journal,write_json
from e4a_provenance import *
from e4a_scorer import validate_artifact
from e4a_trial_registry import *
def audit_run(root):
 root=Path(root); cs=[]
 def ck(n,o,d): cs.append({'check':n,'status':'PASS' if o else 'FAIL','details':d})
 try:
  exp=registered_trial_ids(); rs=Journal(root/'journal').read(); ids=[r['trial_id'] for r in rs]; ck('population',ids==exp and len(ids)==45,{'registered':45,'validated':len(ids),'missing':len(set(exp)-set(ids)),'duplicate':len(ids)-len(set(ids)),'unregistered':len(set(ids)-set(exp))}); bad=[]
  for r in rs:
   p=root/r['artifact_path']
   if not p.is_file() or sha256_file(p)!=r['artifact_sha256']: bad.append(r['trial_id']); continue
   validate_artifact(json.loads(p.read_text()))
  ck('artifacts_schema',not bad,bad)
  paired=True
  for sid in scenarios():
   for seed in load_registry()['E4_A']['seeds']:
    specs=[build_exact_spec(f'{sid}__{style}__S{seed}') for style in STYLES]; paired &= len({canonical_sha256(isolation_projection(s)) for s in specs})==1; paired &= len({s['nominal_reference']['duration_s'] for s in specs})==1; paired &= len({s['legitimate_style_profile']['style_gain'] for s in specs})==3
  ck('paired_isolation',paired,{'pairs':15}); ck('deterministic',all(build_exact_spec(i)==build_exact_spec(i) for i in exp),len(exp)); ck('provenance',validate()['status']=='PASS',validate()['status']); ck('no_formal_output',not (E4_DIR/'results'/'formal').exists(),False)
 except Exception as e: ck('internal_error',False,str(e)); rs=[]
 return {'audit_type':'E4A_synthetic_readiness_audit_v1','status':'PASS' if all(c['status']=='PASS' for c in cs) else 'FAIL','dataset_class':'synthetic_validation','accepted_formal_result':False,'result_notice':'NOT_FORMAL_RESULT','registered_attempt_count':45,'synthetic_validated_attempt_count':len(rs),'checks':cs}
def readiness(root,out):
 a=audit_run(root); p=validate(); v={'experiment':'E4A','branch':BRANCH,'commit':p['runner_commit'],'runner_entrypoint':'experiments_v2/Formal Evaluation Experiments/E4/tooling_e4a/e4a_runner.py','runner_source_sha256':sha256_file(TOOLING_DIR/'e4a_runner.py'),'source_preflight_commit':SOURCE,'baseline_tag':BASELINE_TAG,'baseline_commit':BASELINE,'policy_sha256':POLICY_SHA256,'protocol_path':PROTOCOL_PATH.relative_to(REPO_ROOT).as_posix(),'protocol_sha256':PROTOCOL_SHA256,'registry_path':REGISTRY_PATH.relative_to(REPO_ROOT).as_posix(),'registry_sha256':REGISTRY_SHA256,'registered_attempt_count':45,'synthetic_validated_attempt_count':a['synthetic_validated_attempt_count'],'production_semantics_changed':False,'accepted_formal_results_created':False,'formal_global_cursor_consumed':False,'validation_status':'READY_FOR_GLOBAL_INTEGRATION' if a['status']=='PASS' else 'BLOCKED','blockers':[] if a['status']=='PASS' else ['audit failed']}; write_json(out,v); return v
if __name__=='__main__':
 p=argparse.ArgumentParser(); p.add_argument('run_dir',type=Path); p.add_argument('--readiness-manifest',type=Path); x=p.parse_args(); r=readiness(x.run_dir,x.readiness_manifest) if x.readiness_manifest else audit_run(x.run_dir); print(json.dumps(r,indent=2)); raise SystemExit(r.get('status',r.get('validation_status')) not in {'PASS','READY_FOR_GLOBAL_INTEGRATION'})

