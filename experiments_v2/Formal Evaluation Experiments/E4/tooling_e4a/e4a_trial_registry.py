from __future__ import annotations
import hashlib,json,re
from pathlib import Path
from typing import Any,Dict,List
import yaml
TOOLING_DIR=Path(__file__).resolve().parent; E4_DIR=TOOLING_DIR.parent; FORMAL_DIR=E4_DIR.parent; REPO_ROOT=FORMAL_DIR.parents[1]
PROTOCOL_PATH=FORMAL_DIR/'protocols'/'E4_protocol_v1.yaml'; REGISTRY_PATH=E4_DIR/'e4_motion_style_registry_v1.yaml'; GLOBAL_REGISTRY_PATH=FORMAL_DIR/'e2_e5_scenario_seed_registry_v1.yaml'; ORDER_PATH=FORMAL_DIR/'simulation_trial_order_v1.txt'; POLICY_PATH=REPO_ROOT/'lfs_policy/config/lfs_policy.paper_current.yaml'; STYLE_POLICY_PATH=REPO_ROOT/'experiments_v2/Calibration Experiments/C0-F-motion-style/results/C0-F_motion_style_freeze/frozen_motion_style_policy.yaml'
PROTOCOL_SHA256='5a7eeb923aebcfb068827c6513a37e856dc8d6f05166a4b84775b33572bd83d0'; REGISTRY_SHA256='48779a6667759955dd7dab2d8509f61a5439cca51a4bf98fcb48b6d17c499f95'; GLOBAL_REGISTRY_SHA256='90313d33793940489edde631d397564378ae54fe3cfddf438e4a895d6132254d'; ORDER_SHA256='db28bf8d734e1f206987519e91ff27c67b2d9ab2971aeb68c4e13735762f1dce'; POLICY_SHA256='6b47d27f4253d7311e79ea51f6dd1cf0d0182e6df24374a94abae0aa6a135858'; STYLE_POLICY_SHA256='43f1a9f4a5eee0e23b9b002946f40335a287cee206551f18aaceea91dba4c9a2'
STYLES=('smooth','normal','aggressive'); RE_TRIAL=re.compile(r'^(E4A-(?:HORIZONTAL|VERTICAL|DIAGONAL-3D))__(smooth|normal|aggressive)__S(\d+)$')
class E4AError(RuntimeError): pass
def sha256_file(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def canonical(v): return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def canonical_sha256(v): return hashlib.sha256(canonical(v)).hexdigest()
def load_yaml(p):
 v=yaml.safe_load(Path(p).read_text());
 if not isinstance(v,dict): raise E4AError(f'expected mapping: {p}')
 return v
def load_registry():
 for p,h in [(PROTOCOL_PATH,PROTOCOL_SHA256),(REGISTRY_PATH,REGISTRY_SHA256),(GLOBAL_REGISTRY_PATH,GLOBAL_REGISTRY_SHA256),(ORDER_PATH,ORDER_SHA256),(POLICY_PATH,POLICY_SHA256),(STYLE_POLICY_PATH,STYLE_POLICY_SHA256)]:
  if sha256_file(p)!=h: raise E4AError(f'sealed hash mismatch: {p}')
 r=load_yaml(REGISTRY_PATH)
 if r.get('status')!='SEALED' or r['E4_A'].get('status')!='SEALED': raise E4AError('E4A registry not sealed')
 return r
def scenarios(r=None):
 r=r or load_registry(); x={s['scenario_id']:s for s in r['E4_A']['scenarios']}
 if len(x)!=3: raise E4AError('expected 3 E4A scenarios')
 return x
def registered_trial_ids(r=None):
 r=r or load_registry(); ids=[f"{s['scenario_id']}__{style}__S{seed}" for s in r['E4_A']['scenarios'] for style in STYLES for seed in r['E4_A']['seeds']]
 order=ORDER_PATH.read_text().splitlines(); filtered=[x for x in order if x.startswith('E4A-')]
 if len(ids)!=len(set(ids)) or len(ids)!=45 or set(ids)!=set(filtered) or any(order.count(x)!=1 for x in ids): raise E4AError('E4A population/global order mismatch')
 return ids
def parse_trial_id(t,r=None):
 m=RE_TRIAL.fullmatch(str(t))
 if not m:
  if str(t).startswith(('E2-','E3-','E4B-','E5-')): raise E4AError(f'wrong family: {t}')
  raise E4AError(f'malformed/unregistered E4A trial: {t}')
 sid,style,seed_s=m.groups(); r=r or load_registry(); seed=int(seed_s)
 if sid not in scenarios(r): raise E4AError(f'unregistered scenario: {sid}')
 if style not in STYLES: raise E4AError(f'unregistered style: {style}')
 if seed not in r['E4_A']['seeds']: raise E4AError(f'unregistered seed: {seed}')
 return {'scenario_id':sid,'style':style,'seed':seed}
def build_exact_spec(t,r=None):
 r=r or load_registry(); i=parse_trial_id(t,r); s=scenarios(r)[i['scenario_id']]; common=r['common']; profiles=load_yaml(STYLE_POLICY_PATH); duration=float(s['explicit_T_s'])
 spec={'spec_type':'E4A_exact_execution_spec_v1','trial_id':t,'experiment':'E4A',**i,'uav_ids':common['uav_ids'],'availability':common['availability'],'initial_positions_m':common['initial_positions_m'],'assigned_targets_m':s['assigned_targets_m'],'displacement_m':s['displacement_m'],'requested_T':{'mode':'explicit','value_s':duration},'T_exec_requirement_s':duration,'safety_s':float(common['safety_s']),'q':common['q'],'seed_pairing':i['seed'],'nominal_reference':{'polynomial':'frozen Minimum-Jerk reference','p0':common['initial_positions_m'],'targets':s['assigned_targets_m'],'duration_s':duration,'style_may_regenerate_or_retime':False},'frozen_feasibility_terms_s':s['frozen_feasibility_terms_s'],'motion_style':i['style'],'legitimate_style_profile':{'style':i['style'],'style_gain':profiles['style_gains'][i['style']],'task_adaptation':profiles['task_adaptation'],'task_gain':profiles['task_gain'],'smoothing_alpha':profiles['smoothing_alpha']},'metric_log_schema':{'primary_metrics':['settling_time','control_effort','acceleration_response','tracking_RMSE'],'acceleration_response_components':['peak','RMS','rise_time'],'control_effort_definition':'time integral norm commanded LADRC acceleration','tracking_RMSE_definition':'safe reference vs measured 3-D position','raw_required':['clock','commanded_ladrc_acceleration_3d','safe_reference_position_3d','measured_position_3d','trajectory_completion','stable_hover_entry']}}
 spec['registered_input_hash']=canonical_sha256({'scenario':s,'style':i['style'],'seed':i['seed']}); spec['resolved_execution_spec_hash']=canonical_sha256(spec); return spec
def isolation_projection(spec):
 return {k:v for k,v in spec.items() if k not in {'trial_id','style','motion_style','legitimate_style_profile','registered_input_hash','resolved_execution_spec_hash'}}

