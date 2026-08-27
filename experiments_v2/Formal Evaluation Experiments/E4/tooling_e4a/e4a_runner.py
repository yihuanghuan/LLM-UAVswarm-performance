#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from e4a_journal import Journal,write_json
from e4a_provenance import validate
from e4a_scorer import validate_artifact
from e4a_trial_registry import *
RESULTS=E4_DIR/'results'/'synthetic-validation-e4a'
class SyntheticBackend:
 def execute_exact_spec(self,s): return {'backend':'E4A_synthetic_contract_backend_v1','validation_status':'SPEC_VALIDATED','scientific_outcomes':None,'nominal_reference_hash':canonical_sha256(s['nominal_reference'])}
def run_exact_trial(trial_id,campaign_context,output_root,backend=None):
 p=validate();
 if p['status']!='PASS': raise E4AError('provenance failed')
 s=build_exact_spec(trial_id)
 if campaign_context.get('exact_trial_id')!=trial_id: raise E4AError('exact trial context mismatch')
 root=Path(output_root); ap=root/'artifacts'/trial_id/'attempt.json'
 if ap.exists(): raise E4AError('duplicate retained attempt')
 mock=(backend or SyntheticBackend()).execute_exact_spec(s); a={'record_type':'E4A_synthetic_attempt_v1','dataset_class':'synthetic_validation','accepted_formal_result':False,'result_notice':'NOT_FORMAL_RESULT','trial_id':trial_id,'experiment':'E4A','scenario_id':s['scenario_id'],'style':s['style'],'seed':s['seed'],'registered_input_hash':s['registered_input_hash'],'resolved_execution_spec_hash':s['resolved_execution_spec_hash'],'runner':{'branch':p['runner_branch'],'commit':p['runner_commit'],'entrypoint':'experiments_v2/Formal Evaluation Experiments/E4/tooling_e4a/e4a_runner.py','source_sha256':sha256_file(__file__)},'protocol_sha256':PROTOCOL_SHA256,'registry_sha256':REGISTRY_SHA256,'policy_sha256':POLICY_SHA256,'validation_status':'SPEC_VALIDATED','execution_spec':s,'mock_execution':mock}; validate_artifact(a); write_json(ap,a); h=sha256_file(ap); r=Journal(root/'journal').append({'trial_id':trial_id,'experiment':'E4A','scenario_id':s['scenario_id'],'style':s['style'],'seed':s['seed'],'artifact_path':ap.relative_to(root).as_posix(),'artifact_sha256':h,'dataset_class':'synthetic_validation','accepted_formal_result':False,'result_notice':'NOT_FORMAL_RESULT','validation_status':'SPEC_VALIDATED'}); return {'trial_id':trial_id,'experiment':'E4A','attempt_status':'success','artifact_path':r['artifact_path'],'artifact_sha256':h,'runner_commit':p['runner_commit'],'runner_source_sha256':sha256_file(__file__)}
def run_population(run_id):
 root=RESULTS/run_id
 if root.exists(): raise E4AError('run exists')
 root.mkdir(parents=True); write_json(root/'run_manifest.json',{'run_id':run_id,'dataset_class':'synthetic_validation','accepted_formal_result':False,'result_notice':'NOT_FORMAL_RESULT','notice':'LOCAL SYNTHETIC ENUMERATION IS NOT FORMAL DATA-COLLECTION ORDER.'})
 for tid in registered_trial_ids(): run_exact_trial(tid,{'exact_trial_id':tid},root,SyntheticBackend())
 from e4a_audit import audit_run
 a=audit_run(root); write_json(root/'audit.json',a); return a
if __name__=='__main__':
 p=argparse.ArgumentParser(); p.add_argument('--synthetic-validation',action='store_true',required=True); p.add_argument('--run-id',required=True); x=p.parse_args(); r=run_population(x.run_id); print(json.dumps(r,indent=2)); raise SystemExit(r['status']!='PASS')

