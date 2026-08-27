#!/usr/bin/env python3
import argparse,json
from pathlib import Path
from e4b_journal import Journal,write_json
from e4b_provenance import validate
from e4b_scorer import validate_artifact
from e4b_trial_registry import *
RESULTS=E4_DIR/'results'/'synthetic-validation-e4b'
class SyntheticBackend:
 def execute_exact_spec(self,s): return {'backend':'E4B_synthetic_contract_backend_v1','validation_status':'SPEC_VALIDATED','scientific_outcomes':None,'physical_safety_active_executed':False}
def run_exact_trial(t,ctx,root,backend=None):
 p=validate();
 if p['status']!='PASS': raise E4BError('provenance failed')
 s=build_exact_spec(t)
 if ctx.get('exact_trial_id')!=t: raise E4BError('context mismatch')
 root=Path(root); ap=root/'artifacts'/t/'attempt.json'
 if ap.exists(): raise E4BError('duplicate retained attempt')
 mock=(backend or SyntheticBackend()).execute_exact_spec(s); a={'record_type':'E4B_synthetic_attempt_v1','dataset_class':'synthetic_validation','accepted_formal_result':False,'result_notice':'NOT_FORMAL_RESULT','trial_id':t,'experiment':'E4B','scenario_id':s['scenario_id'],'style':s['style'],'seed':s['seed'],'registered_input_hash':s['registered_input_hash'],'resolved_execution_spec_hash':s['resolved_execution_spec_hash'],'runner':{'branch':p['runner_branch'],'commit':p['runner_commit'],'entrypoint':'experiments_v2/Formal Evaluation Experiments/E4/tooling_e4b/e4b_runner.py','source_sha256':sha256_file(__file__)},'protocol_sha256':PROTOCOL_SHA256,'registry_sha256':REGISTRY_SHA256,'policy_sha256':POLICY_SHA256,'validation_status':'SPEC_VALIDATED','execution_spec':s,'mock_execution':mock}; a['authority_validation']=validate_artifact(a); write_json(ap,a); h=sha256_file(ap); r=Journal(root/'journal').append({'trial_id':t,'experiment':'E4B','scenario_id':s['scenario_id'],'style':s['style'],'seed':s['seed'],'artifact_path':ap.relative_to(root).as_posix(),'artifact_sha256':h,'dataset_class':'synthetic_validation','accepted_formal_result':False,'result_notice':'NOT_FORMAL_RESULT','validation_status':'SPEC_VALIDATED'}); return {'trial_id':t,'experiment':'E4B','attempt_status':'success','artifact_path':r['artifact_path'],'artifact_sha256':h,'runner_commit':p['runner_commit'],'runner_source_sha256':sha256_file(__file__)}
def run_population(run_id):
 root=RESULTS/run_id
 if root.exists(): raise E4BError('run exists')
 root.mkdir(parents=True); write_json(root/'run_manifest.json',{'run_id':run_id,'dataset_class':'synthetic_validation','accepted_formal_result':False,'result_notice':'NOT_FORMAL_RESULT','notice':'LOCAL SYNTHETIC ENUMERATION IS NOT FORMAL DATA-COLLECTION ORDER.'})
 for t in registered_trial_ids(): run_exact_trial(t,{'exact_trial_id':t},root,SyntheticBackend())
 from e4b_audit import audit_run
 a=audit_run(root); write_json(root/'audit.json',a); return a
if __name__=='__main__':
 p=argparse.ArgumentParser(); p.add_argument('--synthetic-validation',action='store_true',required=True); p.add_argument('--run-id',required=True); x=p.parse_args(); r=run_population(x.run_id); print(json.dumps(r,indent=2)); raise SystemExit(r['status']!='PASS')

