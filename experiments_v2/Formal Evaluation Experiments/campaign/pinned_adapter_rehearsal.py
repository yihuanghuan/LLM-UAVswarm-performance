#!/usr/bin/env python3
"""Complete 610-order rehearsal through the actual five pinned entrypoints."""
from __future__ import annotations
from collections import Counter
import argparse,json,tempfile
from pathlib import Path
from campaign_common import NOT_FORMAL_RESULT,family_for_trial,load_sealed_order,write_json_exclusive
from formal_campaign_launcher import FormalCampaignLauncher,REHEARSAL_ID,formal_cursor_snapshot
def injected(pos):
 if pos%131==0:return 'timeout'
 if pos%97==0:return 'method_failure'
 return None
def trace(launcher):return [{'global_position':x['global_position'],'trial_id':x['trial_id'],'experiment':x['experiment'],'attempt_status':x['attempt_status']} for x in launcher.journal.read()]
def run(root=None,run_id=REHEARSAL_ID,restart_at=137):
 l=FormalCampaignLauncher('rehearsal',run_id,root);restarted=False
 while True:
  state=l.validate_state()
  if state['complete']:break
  pos=state['next_position'];l.dispatch_next(failure_injection=injected(pos))
  if pos==restart_at:
   l=FormalCampaignLauncher('rehearsal',run_id,root);restarted=l.validate_state()['next_position']==restart_at+1
 primary=trace(l);order=load_sealed_order();expected=[{'global_position':i,'trial_id':t,'experiment':family_for_trial(t),'attempt_status':injected(i) or 'success'} for i,t in enumerate(order,1)]
 with tempfile.TemporaryDirectory(prefix='pinned-adapter-replay-') as td:
  other=FormalCampaignLauncher('rehearsal','deterministic-replay',Path(td)/'campaign/results/synthetic-validation')
  while not other.validate_state()['complete']:
   pos=other.validate_state()['next_position'];other.dispatch_next(failure_injection=injected(pos))
  replay=trace(other)
 summary={'manifest_type':'complete_610_pinned_adapter_rehearsal_v1','dataset_class':'synthetic_validation','accepted_formal_result':False,'result_notice':NOT_FORMAL_RESULT,'status':'PASS' if primary==expected==replay and restarted else 'FAIL','accounted_attempts':len(primary),'unique_trials':len({x['trial_id'] for x in primary}),'exact_order':primary==expected,'correct_routing':all(x['experiment']==family_for_trial(x['trial_id']) for x in primary),'restart_resume':restarted,'failure_retention':any(x['attempt_status']!='success' for x in primary),'deterministic_replay':primary==replay,'status_counts':dict(Counter(x['attempt_status'] for x in primary)),'formal_cursor_state_after':formal_cursor_snapshot()};write_json_exclusive(l.run_dir/'rehearsal_summary.json',summary);return l,summary
def main():
 p=argparse.ArgumentParser();p.add_argument('--run-id',default=REHEARSAL_ID);a=p.parse_args();l,s=run(run_id=a.run_id);print(json.dumps(s,indent=2,sort_keys=True));return s['status']!='PASS'
if __name__=='__main__':raise SystemExit(main())
