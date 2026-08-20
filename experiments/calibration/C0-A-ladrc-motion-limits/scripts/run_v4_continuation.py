#!/usr/bin/env python3
"""Execute bounded C0-A-v4 continuation and stop at the first failed stage."""
import argparse, json, subprocess, sys
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parents[1]; REPO=ROOT.parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from run_trial import ros_environment
PYTHON=ROOT.parents[2].parents[1]/'llm_env/bin/python'
RUN=ROOT/'scripts/run_trial.py'; EXTRACT=ROOT/'scripts/extract_metrics.py'
SCHEDULE=ROOT/'trial_order_v4.json'; CONFIG=ROOT/'configs/c0a_prereg_v4.json'
def now(): return datetime.now(timezone.utc).isoformat()
def load(p): return json.loads(Path(p).read_text())
def save(p,d): Path(p).write_text(json.dumps(d,indent=2,sort_keys=True)+'\n')
def groups(root, stage):
 out=defaultdict(list)
 for p in Path(root,'raw').glob('C0A-v4-*/metrics.json'):
  m=load(p)
  if m.get('stage')==stage: out[m['candidate_id']].append((m,load(p.parent/'manifest.json'),load(p.parent/'trial_spec.json')))
 return out
def score(items):
 u=[uav for trial,_,_ in items for uav in trial.get('per_uav',[])]
 if not u: return (float('inf'),)*4
 return (max(x.get('post_trajectory_rms_m',float('inf')) for x in u),max(max(x.get('post_trajectory_peak_to_peak_per_axis_m',[float('inf')])) for x in u),max(x.get('post_trajectory_last_first_rms_ratio',float('inf')) for x in u),max(x.get('tracking_rmse_m',float('inf')) for x in u))
def select(root, stage, expected, state):
 gs=groups(root,stage); passing=[(k,v) for k,v in gs.items() if len(v)==expected and all(x[0].get('hard_pass') for x in v)]
 if not passing: state['campaign_status']='NO_ACCEPTABLE_CONFIGURATION'; return None
 if stage=='A1_CONFIRMATION':
  win=sorted(passing,key=lambda kv:score(kv[1]))[0]; concrete=state['a1_confirmation_mapping'][win[0]]; state['a1_winner_id']=concrete; state['a1_winner']=state['a1_candidates'][concrete]
 elif stage=='A2_SCREENING':
  win=sorted(passing,key=lambda kv:(-sum(kv[1][0][2]['resolved_candidate_parameters'][k] for k in ('v_limit','a_limit','j_limit')),score(kv[1])))[0]; state['a2_confirmation_mapping']={'A2-RANK-01':win[0],'A2-RANK-02':sorted(passing,key=lambda kv:(-sum(kv[1][0][2]['resolved_candidate_parameters'][k] for k in ('v_limit','a_limit','j_limit')),score(kv[1])))[1][0]}; state['a2_candidates']={k:v[0][2]['resolved_candidate_parameters'] for k,v in gs.items()}; state['a2_survivors']=[k for k,_ in passing]
 elif stage=='A2_CONFIRMATION':
  win=sorted(passing,key=lambda kv:score(kv[1]))[0]; concrete=state['a2_confirmation_mapping'][win[0]]; state['a2_winner_id']=concrete; state['a2_winner']=state['a2_candidates'][concrete]
 else: win=passing[0]
 return win[0]
def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--artifact-root',type=Path,required=True); args=ap.parse_args(); root=args.artifact_root.resolve(); root.mkdir(parents=True,exist_ok=True)
 state_path=root/'campaign_state_v4.json'; old=load(root/'campaign_state.json'); state=load(state_path) if state_path.exists() else {**old,'protocol_version':'C0-A-prereg-v4','campaign_status':'RUNNING','formal_trials_executed':0,'completed_stages':[],'failures':[],'a1_confirmation_mapping':{'A1-RANK-01':'A1-OC067-OO117','A1-RANK-02':'A1-OC067-OO100','A1-RANK-03':'A1-OC067-OO083'},'a1_candidates':old['a1_candidates'],'artifact_root':str(root)}
 schedule=load(SCHEDULE)['entries']; save(state_path,state)
 for stage,expected in [('A1_CONFIRMATION',18),('A2_SCREENING',5),('A2_CONFIRMATION',15),('A3_VALIDATION',9),('SCALE_VALIDATION',9)]:
  if stage in state['completed_stages']: continue
  for e in [x for x in schedule if x['stage']==stage]:
   d=root/'raw'/e['trial_id']; mp=d/'metrics.json'
   if mp.exists(): continue
   cmd=[str(PYTHON),str(RUN),'--trial-id',e['trial_id'],'--state',str(state_path),'--artifact-root',str(root),'--schedule',str(SCHEDULE),'--config',str(CONFIG)]
   r=subprocess.run(cmd,cwd=REPO,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT) if not d.exists() else subprocess.CompletedProcess(cmd,0,'existing trial directory retained')
   (root/'logs').mkdir(exist_ok=True); (root/'logs/v4_trials.jsonl').open('a').write(json.dumps({'trial_id':e['trial_id'],'returncode':r.returncode,'output':r.stdout})+'\n')
   if not mp.exists():
    ex=subprocess.run([str(PYTHON),str(EXTRACT),str(d)],cwd=REPO,env=ros_environment(),text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    if ex.returncode!=0: raise SystemExit(ex.stdout)
   if not mp.exists(): raise SystemExit(r.stdout)
   m=load(mp); state['formal_trials_executed']+=1; state['last_trial_id']=e['trial_id']; state['updated_utc']=now(); state.setdefault('failures',[]); state['failures'] += [] if m.get('hard_pass') else [{'trial_id':e['trial_id'],'hard_failures':m.get('hard_failures',[])}]; save(state_path,state)
  win=select(root,stage,expected,state); save(root/'metrics'/f'{stage.lower()}_v4_selection.json',{'stage':stage,'winner':win,'status':state['campaign_status']});
  if state['campaign_status']!='RUNNING': save(state_path,state); break
  state['completed_stages'].append(stage); save(state_path,state)
 print(json.dumps({'status':state['campaign_status'],'completed':state['formal_trials_executed'],'stages':state['completed_stages'],'a1_winner':state.get('a1_winner_id'),'a2_winner':state.get('a2_winner_id')},sort_keys=True))
if __name__=='__main__': main()
