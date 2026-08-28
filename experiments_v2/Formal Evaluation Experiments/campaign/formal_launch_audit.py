#!/usr/bin/env python3
"""Independent offline audit of the final non-formal launch preparation."""
from __future__ import annotations
import argparse,json,subprocess
from pathlib import Path
from campaign_common import CAMPAIGN_DIR,FORMAL_RESULTS_DIR,ORDER_TXT_SHA256,REPO_ROOT,family_for_trial,load_json,load_sealed_order,sha256_file,write_json_exclusive
from campaign_journal import CampaignJournal
from formal_campaign_launcher import LAUNCH_GATE_PATH,REHEARSAL_ID,formal_cursor_snapshot
from runner_registry import load_runner_registry,registry_sha256,validate_registry_pins
def audit(gate_path=LAUNCH_GATE_PATH,run_dir=None):
 checks=[]
 def ck(n,o,d):checks.append({'check':n,'status':'PASS' if o else 'FAIL','details':d})
 try:
  gate=load_json(Path(gate_path));registry=load_runner_registry();pins=validate_registry_pins(registry);ck('five_adapters_pinned',pins['status']=='PASS',pins);order=load_sealed_order();ck('sealed_order',len(order)==len(set(order))==610 and gate.get('global_order_sha256')==ORDER_TXT_SHA256,{'count':len(order),'sha256':ORDER_TXT_SHA256});run=Path(run_dir or CAMPAIGN_DIR/'results/synthetic-validation'/REHEARSAL_ID);summary_path=run/'rehearsal_summary.json';manifest_path=run/'launcher_run_manifest.json';summary=load_json(summary_path);records=CampaignJournal(run/'suite-journal').read();ck('complete_pinned_adapter_rehearsal',summary.get('status')=='PASS' and len(records)==610 and summary.get('accounted_attempts')==610 and gate.get('pinned_adapter_rehearsal_id')==run.name and gate.get('pinned_adapter_rehearsal_summary_sha256')==sha256_file(summary_path) and gate.get('pinned_adapter_rehearsal_manifest_sha256')==sha256_file(manifest_path),summary);ids=[x['trial_id'] for x in records];ck('exact_order_no_missing_duplicate_replacement',ids==order and len(set(ids))==610 and all(x.get('replacement_attempt') is False for x in records),{'count':len(ids),'unique':len(set(ids))});ck('journal_chain',bool(records) and records[-1].get('record_hash')==gate.get('pinned_adapter_rehearsal_journal_tail_hash'),{'tail':records[-1]['record_hash']});ck('routing',all(x['experiment']==family_for_trial(x['trial_id']) for x in records),{});ck('artifact_hashes',all((run/x['artifact_path']).is_file() and sha256_file(run/x['artifact_path'])==x['artifact_sha256'] for x in records),{});ck('restart_failure_determinism',all(summary.get(x) is True for x in ('restart_resume','failure_retention','deterministic_replay')),summary)
  evidence_path=REPO_ROOT/gate['formal_restart_resume_evidence_path'];evidence=load_json(evidence_path);ck('isolated_formal_restart_resume',evidence.get('status')=='PASS' and evidence.get('formal_cursor_unchanged') is True and gate.get('formal_restart_resume_evidence_sha256')==sha256_file(evidence_path),evidence)
  provenance_path=REPO_ROOT/gate['campaign_provenance_path'];provenance=load_json(provenance_path);ck('campaign_provenance',provenance.get('status')=='PASS' and gate.get('campaign_provenance_sha256')==sha256_file(provenance_path),{'status':provenance.get('status'),'sha256':sha256_file(provenance_path)})
  launcher=CAMPAIGN_DIR/'formal_campaign_launcher.py';launcher_rel=launcher.relative_to(REPO_ROOT).as_posix();implementation=gate.get('global_launch_implementation_commit');committed=subprocess.run(['git','show',f'{implementation}:{launcher_rel}'],cwd=REPO_ROOT,check=True,capture_output=True).stdout;ck('launcher_implementation_pin',gate.get('launcher_source_sha256')==sha256_file(launcher) and committed==launcher.read_bytes(),{'commit':implementation,'sha256':sha256_file(launcher)})
  snap=formal_cursor_snapshot();ck('formal_output_absence',snap['suite_journal_record_count']==0 and not snap['files'],snap);ck('launch_gate_ready_pristine',gate.get('formal_campaign_status')=='READY_FOR_FORMAL_LAUNCH' and gate.get('formal_campaign_started') is False and gate.get('next_formal_position')==1 and gate.get('next_formal_trial_id')==order[0] and gate.get('accepted_formal_results_created')==0 and gate.get('formal_global_cursor_consumed') is False and gate.get('formal_suite_journal_record_count')==0,gate);ck('registry_hash',gate.get('runner_registry_sha256')==registry_sha256(registry),gate.get('runner_registry_sha256'));ck('governance',gate.get('sealed_files_unchanged') is True and gate.get('production_semantics_unchanged') is True and gate.get('formal_output_absence_status')=='PASS',{})
 except Exception as x:ck('internal_error',False,f'{type(x).__name__}: {x}')
 return {'audit_type':'formal_resume_safe_launch_preparation_audit_v2','status':'PASS' if all(x['status']=='PASS' for x in checks) else 'FAIL','checks':checks}
def main():
 p=argparse.ArgumentParser();p.add_argument('--gate',type=Path,default=LAUNCH_GATE_PATH);p.add_argument('--run-dir',type=Path);p.add_argument('--output',type=Path);a=p.parse_args();r=audit(a.gate,a.run_dir)
 if a.output:write_json_exclusive(a.output,r)
 else:print(json.dumps(r,indent=2,sort_keys=True))
 return r['status']!='PASS'
if __name__=='__main__':raise SystemExit(main())
