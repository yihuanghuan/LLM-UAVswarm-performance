#!/usr/bin/env python3
"""Fail-closed provenance for the pinned-adapter global launch branch."""
from __future__ import annotations
import argparse,hashlib,json,subprocess
from pathlib import Path
from campaign_common import BASELINE_COMMIT,BASELINE_TAG,CAMPAIGN_DIR,CAMPAIGN_MANIFEST_PATH,CANONICAL_POLICY_SHA256,FORMAL_RESULTS_DIR,GLOBAL_REGISTRY_PATH,GLOBAL_REGISTRY_SHA256,ORDER_TXT_PATH,ORDER_TXT_SHA256,ORDER_YAML_PATH,ORDER_YAML_SHA256,POLICY_PATH,PREFLIGHT_PATH,PREFLIGHT_SHA256,REPO_ROOT,SOURCE_PREFLIGHT_COMMIT,family_for_trial,load_json,load_sealed_order,sha256_file,source_hashes,utc_now,write_json_exclusive
from runner_registry import load_runner_registry,registry_sha256,validate_registry_pins
INFRASTRUCTURE_HEAD='d2edd0cfef87b4485a35a8b762733fe702e63396';INFRASTRUCTURE_SOURCE='c50aeb6d821a644a0ea0d48c40a1e7b471f9cd2b';BRANCH='formal/global-campaign-launch-v1'
SEALED=('experiments_v2/Formal Evaluation Experiments/formal_preflight_v1.yaml','experiments_v2/Formal Evaluation Experiments/e2_e5_scenario_seed_registry_v1.yaml','experiments_v2/Formal Evaluation Experiments/simulation_trial_order_v1.yaml','experiments_v2/Formal Evaluation Experiments/simulation_trial_order_v1.txt')
def git(*a,binary=False):return subprocess.run(['git',*a],cwd=REPO_ROOT,check=True,capture_output=True,text=not binary).stdout
def _formal_root_state(order):
 if not FORMAL_RESULTS_DIR.exists() or not any(FORMAL_RESULTS_DIR.iterdir()):return True,{'phase':'prelaunch','retained_count':0}
 manifest=FORMAL_RESULTS_DIR/'launcher_run_manifest.json';journal_dir=FORMAL_RESULTS_DIR/'suite-journal';envelopes=FORMAL_RESULTS_DIR/'attempt-artifacts';adapter_dirs=FORMAL_RESULTS_DIR/'adapter-attempts'
 if not manifest.is_file():return False,{'error':'started formal root lacks launcher manifest'}
 records=[]
 try:
  for pos,path in enumerate(sorted(journal_dir.glob('*-attempt.json')),1):
   r=load_json(path);trial=order[pos-1];family=family_for_trial(trial);envelope=envelopes/f'{pos:06d}-attempt.json'
   if (r.get('global_position'),r.get('trial_id'),r.get('experiment'))!=(pos,trial,family):return False,{'error':f'journal prefix mismatch at {pos}'}
   if not envelope.is_file() or sha256_file(envelope)!=r.get('artifact_sha256'):return False,{'error':f'envelope mismatch at {pos}'}
   a=load_json(envelope);underlying=FORMAL_RESULTS_DIR/a['adapter_artifact_path']
   if not underlying.is_file() or sha256_file(underlying)!=a.get('adapter_artifact_sha256'):return False,{'error':f'adapter artifact mismatch at {pos}'}
   records.append(r)
 except Exception as x:return False,{'error':f'{type(x).__name__}: {x}'}
 envelope_count=len(list(envelopes.glob('*-attempt.json'))) if envelopes.exists() else 0;adapter_count=len([p for p in adapter_dirs.iterdir() if p.is_dir()]) if adapter_dirs.exists() else 0
 ok=len(records)==envelope_count==adapter_count
 return ok,{'phase':'started','retained_count':len(records),'envelope_count':envelope_count,'adapter_attempt_count':adapter_count,'exact_sealed_prefix':ok}
def validate_provenance(raise_on_failure=True):
 checks=[]
 def ck(name,ok,details):checks.append({'check':name,'status':'PASS' if ok else 'FAIL','details':details})
 try:
  head=str(git('rev-parse','HEAD')).strip();branch=str(git('branch','--show-current')).strip();base_ok=subprocess.run(['git','merge-base','--is-ancestor',INFRASTRUCTURE_HEAD,'HEAD'],cwd=REPO_ROOT).returncode==0;ck('launch_branch_exact_base',branch==BRANCH and base_ok,{'branch':branch,'base':INFRASTRUCTURE_HEAD,'head':head});ck('validated_infrastructure_source_retained',subprocess.run(['git','merge-base','--is-ancestor',INFRASTRUCTURE_SOURCE,'HEAD'],cwd=REPO_ROOT).returncode==0,INFRASTRUCTURE_SOURCE);ck('baseline',str(git('rev-parse',f'{BASELINE_TAG}^{{}}')).strip()==BASELINE_COMMIT,BASELINE_COMMIT)
  sealed={};ok=True
  for rel in SEALED:
   cur=(REPO_ROOT/rel).read_bytes();approved=git('show',f'{SOURCE_PREFLIGHT_COMMIT}:{rel}',binary=True);same=cur==approved;ok &= same;sealed[rel]={'sha256':hashlib.sha256(cur).hexdigest(),'byte_identical':same}
  ck('sealed_files_unchanged',ok,sealed);order=load_sealed_order();ck('sealed_610_order',len(order)==len(set(order))==610,{'count':len(order),'first':order[0],'sha256':sha256_file(ORDER_TXT_PATH)});ck('policy_unchanged',sha256_file(POLICY_PATH)==CANONICAL_POLICY_SHA256,sha256_file(POLICY_PATH));pins=validate_registry_pins();ck('five_adapter_pins',pins['status']=='PASS',pins)
  manifest=load_json(CAMPAIGN_MANIFEST_PATH);ck('machine_manifest_ready_for_launch',manifest.get('current_formal_campaign_status')=='READY_FOR_FORMAL_LAUNCH' and manifest.get('formal_campaign_started') is False and manifest.get('accepted_formal_result') is False,manifest)
  formal_ok,formal_details=_formal_root_state(order);ck('formal_root_is_absent_or_valid_retained_prefix',formal_ok,formal_details)
  changed=str(git('diff','--name-only',INFRASTRUCTURE_HEAD)).splitlines()+str(git('ls-files','--others','--exclude-standard')).splitlines();prefix=CAMPAIGN_DIR.relative_to(REPO_ROOT).as_posix()+'/';bad=sorted(set(x for x in changed if not x.startswith(prefix)));ck('launch_changes_confined_to_campaign',not bad,bad)
 except Exception as x:head='UNKNOWN';registry={};ck('internal_error',False,f'{type(x).__name__}: {x}')
 registry=load_runner_registry() if head!='UNKNOWN' else {};sources=[p for p in CAMPAIGN_DIR.iterdir() if p.is_file() and p.suffix in {'.py','.json','.md'} and p!=CAMPAIGN_DIR/'formal_launch_gate_v1.json']
 report={'manifest_type':'E2_E5_global_launch_provenance_v1','generated_at_utc':utc_now(),'dataset_class':'engineering_validation','accepted_formal_result':False,'result_notice':'NOT_FORMAL_RESULT','status':'PASS' if all(x['status']=='PASS' for x in checks) else 'FAIL','campaign_infrastructure_commit':head,'global_infrastructure_source_commit':INFRASTRUCTURE_SOURCE,'global_infrastructure_rehearsal_head':INFRASTRUCTURE_HEAD,'campaign_infrastructure_source_hashes':source_hashes(sources),'runner_registry_sha256':registry_sha256(registry) if registry else None,'sealed_hashes':{'preflight_sha256':PREFLIGHT_SHA256,'policy_sha256':CANONICAL_POLICY_SHA256,'global_registry_sha256':GLOBAL_REGISTRY_SHA256,'order_yaml_sha256':ORDER_YAML_SHA256,'order_txt_sha256':ORDER_TXT_SHA256},'checks':checks}
 if report['status']!='PASS' and raise_on_failure:raise RuntimeError(json.dumps(report,sort_keys=True))
 return report
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path);a=p.parse_args();r=validate_provenance(False)
 if a.output:write_json_exclusive(a.output,r)
 else:print(json.dumps(r,indent=2,sort_keys=True))
 return r['status']!='PASS'
if __name__=='__main__':raise SystemExit(main())
