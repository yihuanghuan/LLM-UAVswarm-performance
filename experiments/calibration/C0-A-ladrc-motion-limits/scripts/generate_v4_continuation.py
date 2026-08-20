#!/usr/bin/env python3
"""Generate the bounded post-start C0-A-v4 continuation schedule."""
import json, random
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
entries=[]; idx=0
def add(stage, candidate_id, scenario, disp, seed, rep, params, mult=1.15):
 global idx
 idx+=1
 entries.append({'schedule_index':idx,'trial_id':f'C0A-v4-{stage}-{candidate_id}-{scenario}-{disp}-S{seed}-R{rep}','stage':stage,'candidate_id':candidate_id,'candidate_parameters':params,'scenario_id':scenario,'signed_displacement_id':disp,'seed':seed,'repetition':rep,'duration_condition':{'kind':'T_MIN_MULTIPLIER','value':mult},'activation':{'type':'V4_CONTINUATION'}})
motions=[('C0A-S-HX-3','POS_X_3'),('C0A-S-HX-3','NEG_X_3'),('C0A-S-HY-3','POS_Y_3'),('C0A-S-VU-2','POS_Z_2'),('C0A-S-VD-1','NEG_Z_1'),('C0A-S-DIAG-1','POS_X2_Y2_Z1')]
for rank in range(1,4):
 for scenario,disp in motions:
  for seed in [44001,44002,44003]: add('A1_CONFIRMATION',f'A1-RANK-{rank:02d}',scenario,disp,seed,1,{'candidate_ref':f'A1-RANK-{rank:02d}'},1.25)
packages=[[3.,3.,6.],[4.,4.,8.],[5.,5.,10.],[4.,3.,8.],[5.,4.,8.],[5.,4.,10.]]
for pi,pkg in enumerate(packages,1):
 for scenario,disp in motions[:2]+motions[3:5]+[motions[5]]: add('A2_SCREENING',f'A2-PKG-{pi:02d}',scenario,disp,45001,1,{'v_limit':pkg[0],'a_limit':pkg[1],'j_limit':pkg[2],'minimum_duration':.5},1.15)
for rank in range(1,3):
 for scenario,disp in motions[:2]+motions[3:5]+[motions[5]]:
  for seed in [45002,45003,45004]: add('A2_CONFIRMATION',f'A2-RANK-{rank:02d}',scenario,disp,seed,1,{'candidate_ref':f'A2-RANK-{rank:02d}'},1.15)
for scenario,disp in motions[:3]:
 for seed in [45011,45012,45013]: add('A3_VALIDATION','A3-GUARD-01',scenario,disp,seed,1,{'omega_lower_multiplier':.75,'omega_upper_multiplier':1.25,'motion_clamp_multiplier':1.0},1.25)
for scenario in ['C0A-M-1','C0A-M-4','C0A-M-8']:
 for seed in [46001,46002,46003]: add('SCALE_VALIDATION','SCALE-FINAL',scenario,'POS_X_8',seed,1,{},1.25)
random.Random(44999).shuffle(entries)
out={'protocol_version':'C0-A-prereg-v4','ordering_seed':44999,'entries':entries,'entry_count':len(entries)}
(ROOT/'trial_order_v4.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({'entry_count':len(entries),'by_stage':{s:sum(e['stage']==s for e in entries) for s in sorted(set(e['stage'] for e in entries))}},sort_keys=True))
