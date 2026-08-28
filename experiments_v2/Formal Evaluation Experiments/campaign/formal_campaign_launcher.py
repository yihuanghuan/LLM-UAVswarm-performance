#!/usr/bin/env python3
"""Formal-capable suite launcher; this module does not authorize starting #1."""
from __future__ import annotations
from collections import Counter
import argparse,json
from pathlib import Path
from campaign_common import ATTEMPT_STATUSES,BASELINE_COMMIT,BASELINE_TAG,CAMPAIGN_DIR,CANONICAL_POLICY_SHA256,FORMAL_RESULTS_DIR,NOT_FORMAL_RESULT,ORDER_TXT_SHA256,SOURCE_PREFLIGHT_COMMIT,SYNTHETIC_RESULTS_DIR,CampaignError,family_for_trial,load_json,load_sealed_order,sha256_file,write_json_exclusive
from campaign_journal import CampaignExecutionLock,CampaignJournal
from pinned_adapter_loader import PinnedAdapterLoader
from runner_registry import formal_launch_gate,load_runner_registry,registry_sha256
LAUNCH_GATE_PATH=CAMPAIGN_DIR/'formal_launch_gate_v1.json'
REHEARSAL_ID='final-pinned-adapter-rehearsal-v1-20260828'
def formal_cursor_snapshot(root=FORMAL_RESULTS_DIR):
 root=Path(root)
 if not root.exists():return {'exists':False,'suite_journal_record_count':0,'files':[]}
 files=[{'path':p.relative_to(root).as_posix(),'sha256':sha256_file(p)} for p in sorted(root.rglob('*')) if p.is_file()]
 journal=list((root/'suite-journal').glob('*-attempt.json')) if (root/'suite-journal').exists() else []
 return {'exists':True,'suite_journal_record_count':len(journal),'files':files}
class FormalCampaignLauncher:
 def __init__(self,mode='rehearsal',run_id=REHEARSAL_ID,run_root=None,loader=None,gate_path=LAUNCH_GATE_PATH):
  if mode not in {'rehearsal','formal'}:raise CampaignError('unsupported launcher mode')
  self.mode=mode;self.order=load_sealed_order();self.registry=load_runner_registry();ready,blockers=formal_launch_gate(self.registry)
  if not ready:raise CampaignError(f'runner pin gate closed: {blockers}')
  self.loader=loader or PinnedAdapterLoader(self.registry);checkouts=self.loader.verify_all_checkouts()
  if checkouts['status']!='PASS':raise CampaignError('adapter checkout verification failed')
  self.gate_path=Path(gate_path)
  if mode=='formal':
   gate=load_json(self.gate_path)
   if gate.get('formal_campaign_status')!='READY_FOR_FORMAL_LAUNCH' or gate.get('formal_campaign_started') is not False:raise CampaignError('formal launch gate is not READY_FOR_FORMAL_LAUNCH')
   if gate.get('next_formal_position')!=1 or gate.get('formal_suite_journal_record_count')!=0:raise CampaignError('formal launch gate cursor is not pristine')
   self.run_dir=Path(run_root or FORMAL_RESULTS_DIR)
  else:
   if '/' in run_id or run_id in {'','.','..'}:raise CampaignError('invalid rehearsal run id')
   self.run_dir=Path(run_root or SYNTHETIC_RESULTS_DIR)/run_id
  self.journal=CampaignJournal(self.run_dir/'suite-journal');self.envelopes=self.run_dir/'attempt-artifacts';self.adapter_attempts=self.run_dir/'adapter-attempts';self.lock=self.run_dir/'.formal-campaign-execution.lock';self._records=[];self._initialize()
 def _initialize(self):
  manifest=self.run_dir/'launcher_run_manifest.json'
  if self.mode=='rehearsal':
   if not self.run_dir.exists():
    self.run_dir.mkdir(parents=True);write_json_exclusive(manifest,{'manifest_type':'pinned_adapter_campaign_rehearsal_v1','dataset_class':'synthetic_validation','accepted_formal_result':False,'result_notice':NOT_FORMAL_RESULT,'formal_cursor_consumed':False,'formal_cursor_state_before':formal_cursor_snapshot(),'global_order_count':610,'global_order_sha256':ORDER_TXT_SHA256,'runner_registry_sha256':registry_sha256(self.registry),'adapter_kind':'actual_pinned_entrypoints_spec_mode'})
   elif not manifest.is_file():raise CampaignError('existing rehearsal root lacks manifest')
  elif self.run_dir.exists() and not manifest.exists():
   # A future formal root is allowed only when it is completely empty.
   if any(self.run_dir.iterdir()):raise CampaignError('unrecognized nonempty formal root')
  self.validate_state()
 def reject_selector(self,selector):raise CampaignError(f'forbidden selector {selector!r}; only global next is allowed')
 def validate_state(self):
  if not self.run_dir.exists():records=[]
  else:
   temps=list(self.run_dir.rglob('*.tmp-*'))
   if temps:raise CampaignError('partial temporary artifact requires recovery')
   records=self.journal.read()
  if len(records)>610:raise CampaignError('journal exceeds sealed order')
  for pos,r in enumerate(records,1):
   trial=self.order[pos-1];family=family_for_trial(trial);expected=f'attempt-artifacts/{pos:06d}-attempt.json'
   if (r.get('global_position'),r.get('trial_id'),r.get('experiment'))!=(pos,trial,family):raise CampaignError(f'journal is not exact sealed prefix at {pos}')
   if r.get('artifact_path')!=expected or r.get('replacement_attempt') is not False:raise CampaignError(f'journal artifact/replacement mismatch at {pos}')
   artifact=self.run_dir/expected
   if not artifact.is_file() or sha256_file(artifact)!=r.get('artifact_sha256'):raise CampaignError(f'artifact missing/hash mismatch at {pos}')
   a=load_json(artifact)
   if (a.get('global_position'),a.get('trial_id'),a.get('experiment'),a.get('attempt_status'))!=(pos,trial,family,r.get('attempt_status')):raise CampaignError(f'artifact identity mismatch at {pos}')
   accepted=self.mode=='formal'
   if a.get('accepted_formal_result') is not accepted or a.get('replacement_attempt') is not False:raise CampaignError(f'artifact formal/replacement label mismatch at {pos}')
   underlying=self.run_dir/a['adapter_artifact_path']
   if not underlying.is_file() or sha256_file(underlying)!=a['adapter_artifact_sha256']:raise CampaignError(f'underlying adapter artifact mismatch at {pos}')
  if self.run_dir.exists():
   envelopes=sorted(self.envelopes.glob('*-attempt.json')) if self.envelopes.exists() else [];dirs=sorted(x for x in self.adapter_attempts.iterdir() if x.is_dir()) if self.adapter_attempts.exists() else []
   if len(envelopes)!=len(records) or len(dirs)!=len(records):raise CampaignError('orphan adapter/envelope artifact requires audited recovery')
  self._records=records;return {'retained_count':len(records),'next_position':len(records)+1 if len(records)<610 else None,'complete':len(records)==610,'status_counts':dict(Counter(x['attempt_status'] for x in records))}
 def _adapter_context(self,family,trial,pos,out,failure_injection=None):
  e=self.registry['runners'][family];formal=self.mode=='formal';c={'execution_mode':'formal' if formal else 'spec_rehearsal','dataset_class':'formal_evaluation' if formal else 'synthetic_validation','formal_launch_authorized':formal,'launch_gate_status':'READY_FOR_FORMAL_LAUNCH' if formal else 'REHEARSAL_ONLY','trial_id':trial,'global_trial_position':pos,'runner_commit':e['adapter_commit'],'runner_source_sha256':e['adapter_source_sha256'],'policy_sha256':CANONICAL_POLICY_SHA256,'protocol_sha256':e['protocol_sha256'],'registry_sha256':e['registry_sha256'],'global_trial_order_sha256':ORDER_TXT_SHA256,'attempt_output_dir':str(out)}
  if failure_injection and not formal:c['failure_injection']=failure_injection
  return c
 def dispatch_next(self,requested_trial_id=None,failure_injection=None):
  with CampaignExecutionLock(self.lock):
   state=self.validate_state();pos=state['next_position']
   if pos is None:raise CampaignError('campaign complete')
   trial=self.order[pos-1]
   if requested_trial_id is not None and requested_trial_id!=trial:raise CampaignError(f'requested trial is not global next: {requested_trial_id} != {trial}')
   family=family_for_trial(trial);out=self.adapter_attempts/f'{pos:06d}';envelope=self.envelopes/f'{pos:06d}-attempt.json'
   if out.exists() or envelope.exists():raise CampaignError('orphan/duplicate output exists')
   descriptor=self.loader.run_exact_trial(family,trial,self._adapter_context(family,trial,pos,out,failure_injection));adapter_path=Path(descriptor['artifact_path']).resolve()
   if descriptor.get('trial_id')!=trial or descriptor.get('experiment')!=family or descriptor.get('attempt_status') not in ATTEMPT_STATUSES:raise CampaignError('adapter descriptor identity/status mismatch')
   if not adapter_path.is_file() or sha256_file(adapter_path)!=descriptor.get('artifact_sha256'):raise CampaignError('adapter artifact not durable/hash matched')
   try:relative=adapter_path.relative_to(self.run_dir.resolve()).as_posix()
   except ValueError as x:raise CampaignError('adapter artifact escaped campaign root') from x
   accepted=self.mode=='formal';payload={'record_type':'global_pinned_adapter_attempt_envelope_v1','dataset_class':'formal_evaluation' if accepted else 'synthetic_validation','accepted_formal_result':accepted,'result_notice':None if accepted else NOT_FORMAL_RESULT,'global_position':pos,'trial_id':trial,'experiment':family,'attempt_status':descriptor['attempt_status'],'replacement_attempt':False,'adapter_artifact_path':relative,'adapter_artifact_sha256':descriptor['artifact_sha256'],'adapter_pin':self.registry['runners'][family],'failure_injection_classification':'synthetic_infrastructure_semantics_only' if failure_injection else None}
   write_json_exclusive(envelope,payload);eh=sha256_file(envelope);record=self.journal.append({'record_type':'global_formal_suite_journal_attempt_v1' if accepted else 'global_pinned_rehearsal_suite_journal_attempt_v1','dataset_class':payload['dataset_class'],'accepted_formal_result':accepted,'result_notice':payload['result_notice'],'global_position':pos,'trial_id':trial,'experiment':family,'attempt_status':descriptor['attempt_status'],'replacement_attempt':False,'artifact_path':envelope.relative_to(self.run_dir).as_posix(),'artifact_sha256':eh,'adapter_commit':self.registry['runners'][family]['adapter_commit'],'adapter_source_sha256':self.registry['runners'][family]['adapter_source_sha256']},prior_records=self._records);self._records=[*self._records,record];return record
def main():
 p=argparse.ArgumentParser();p.add_argument('--rehearsal',action='store_true');p.add_argument('--formal',action='store_true');p.add_argument('--run-id',default=REHEARSAL_ID);p.add_argument('--trial-id');p.add_argument('--selector');a=p.parse_args()
 if a.formal==a.rehearsal:raise SystemExit('select exactly one of --rehearsal/--formal')
 launcher=FormalCampaignLauncher('formal' if a.formal else 'rehearsal',a.run_id)
 if a.selector:launcher.reject_selector(a.selector)
 print(json.dumps(launcher.dispatch_next(a.trial_id),indent=2,sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
