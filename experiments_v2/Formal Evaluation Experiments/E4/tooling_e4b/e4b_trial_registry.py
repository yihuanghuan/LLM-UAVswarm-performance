from __future__ import annotations
import hashlib,json,re,sys
from pathlib import Path
import yaml
TOOLING_DIR=Path(__file__).resolve().parent; E4_DIR=TOOLING_DIR.parent; FORMAL_DIR=E4_DIR.parent; REPO_ROOT=FORMAL_DIR.parents[1]
PROTOCOL_PATH=FORMAL_DIR/'protocols/E4_protocol_v1.yaml'; REGISTRY_PATH=E4_DIR/'e4_motion_style_registry_v1.yaml'; GLOBAL_REGISTRY_PATH=FORMAL_DIR/'e2_e5_scenario_seed_registry_v1.yaml'; ORDER_PATH=FORMAL_DIR/'simulation_trial_order_v1.txt'; POLICY_PATH=REPO_ROOT/'lfs_policy/config/lfs_policy.paper_current.yaml'
PROTOCOL_SHA256='5a7eeb923aebcfb068827c6513a37e856dc8d6f05166a4b84775b33572bd83d0'; REGISTRY_SHA256='48779a6667759955dd7dab2d8509f61a5439cca51a4bf98fcb48b6d17c499f95'; GLOBAL_REGISTRY_SHA256='90313d33793940489edde631d397564378ae54fe3cfddf438e4a895d6132254d'; ORDER_SHA256='db28bf8d734e1f206987519e91ff27c67b2d9ab2971aeb68c4e13735762f1dce'; POLICY_SHA256='6b47d27f4253d7311e79ea51f6dd1cf0d0182e6df24374a94abae0aa6a135858'
STYLES=('smooth','normal','aggressive'); RE_TRIAL=re.compile(r'^(E4B-(?:FEASIBLE-EXPLICIT-T|INFEASIBLE-EXPLICIT-T|AUTO-T|SAFETY-ACTIVE))__(smooth|normal|aggressive)__S(\d+)$'); TOLERANCE=1e-9
PREDICATES=[
 {'id':'feasible_explicit_T_style_override','text':'feasible explicit T changed as a function of style','mode':'deterministic_policy'},
 {'id':'infeasible_T_or_vaj_bypass','text':'infeasible T accepted below frozen T_min or any v/a/j feasibility condition bypassed','mode':'deterministic_policy'},
 {'id':'auto_T_below_T_min','text':'auto T resolved below frozen T_min','mode':'deterministic_policy'},
 {'id':'style_safety_override','text':'style changed or disabled d_hard, d_plan ownership, safety mapping, assignment safety, or feedback safety','mode':'launch_and_event_schema'},
 {'id':'profile_or_clamp_exceeded','text':'execution profile exceeded frozen velocity, acceleration, jerk, omega limits, or physical controller hard clamps','mode':'policy_and_event_schema'},
 {'id':'priority_above_style_changed','text':'style changed any priority above soft motion-style preference','mode':'decision_trace_schema'},
]
class E4BError(RuntimeError): pass
def sha256_file(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def canonical(v): return json.dumps(v,sort_keys=True,separators=(',',':')).encode()
def canonical_sha256(v): return hashlib.sha256(canonical(v)).hexdigest()
def ly(p):
 v=yaml.safe_load(Path(p).read_text());
 if not isinstance(v,dict): raise E4BError('expected mapping')
 return v
def load_registry():
 for p,h in [(PROTOCOL_PATH,PROTOCOL_SHA256),(REGISTRY_PATH,REGISTRY_SHA256),(GLOBAL_REGISTRY_PATH,GLOBAL_REGISTRY_SHA256),(ORDER_PATH,ORDER_SHA256),(POLICY_PATH,POLICY_SHA256)]:
  if sha256_file(p)!=h: raise E4BError(f'hash mismatch: {p}')
 r=ly(REGISTRY_PATH)
 if r['E4_B']['status']!='SEALED': raise E4BError('registry not sealed')
 return r
def scenarios(r=None): return {s['scenario_id']:s for s in (r or load_registry())['E4_B']['scenarios']}
def registered_trial_ids(r=None):
 r=r or load_registry(); ids=[f"{s['scenario_id']}__{st}__S{seed}" for s in r['E4_B']['scenarios'] for st in STYLES for seed in r['E4_B']['seeds']]; order=ORDER_PATH.read_text().splitlines(); f=[x for x in order if x.startswith('E4B-')]
 if len(ids)!=len(set(ids)) or len(ids)!=60 or set(ids)!=set(f) or any(order.count(x)!=1 for x in ids): raise E4BError('population/global order mismatch')
 return ids
def parse_trial_id(t,r=None):
 m=RE_TRIAL.fullmatch(str(t))
 if not m:
  if str(t).startswith(('E2-','E3-','E4A-','E5-')): raise E4BError('wrong family')
  raise E4BError('malformed/unregistered E4B trial')
 sid,st,ss=m.groups(); r=r or load_registry(); seed=int(ss)
 if sid not in scenarios(r): raise E4BError('unregistered scenario')
 if st not in STYLES: raise E4BError('unregistered style')
 if seed not in r['E4_B']['seeds']: raise E4BError('unregistered seed')
 return {'scenario_id':sid,'style':st,'seed':seed}
def deterministic_policy_values(distance=4.0):
 source=str(REPO_ROOT/'location_allocate')
 if source not in sys.path: sys.path.insert(0,source)
 from location_allocate.motion_limits import MotionLimits
 from location_allocate.timing_resolution import ConfiguredMinimumJerkTimingPolicy
 p=ConfiguredMinimumJerkTimingPolicy(MotionLimits(5.,5.,10.),.5,{'smooth':1.3,'normal':1.15,'aggressive':1.1},'paper-current-v11-c0-f-frozen'); tmin=p.feasible_duration(distance)
 return {'T_min_s':tmin,'auto_T_exec_s':{st:p.auto_duration(distance,st) for st in STYLES}}
def build_exact_spec(t,r=None):
 r=r or load_registry(); i=parse_trial_id(t,r); s=scenarios(r)[i['scenario_id']]; common=r['common']; policy=ly(POLICY_PATH); source=s.get('geometry_source'); horizontal={x['scenario_id']:x for x in r['E4_A']['scenarios']}['E4A-HORIZONTAL']; initial=s.get('initial_positions_m',common['initial_positions_m']); targets=s.get('ordered_targets_m',horizontal['assigned_targets_m']); expected=None
 if i['scenario_id']=='E4B-FEASIBLE-EXPLICIT-T': expected=4.0
 elif i['scenario_id']=='E4B-INFEASIBLE-EXPLICIT-T': expected=float(s['T_min_s'])
 elif i['scenario_id']=='E4B-AUTO-T': expected=float(s['expected_T_exec_s'][i['style']])
 requested=s['requested_T'] if 'requested_T' in s else {'mode':'explicit','value_s':float(s['requested_T_s'])}
 spec={'spec_type':'E4B_exact_execution_spec_v1','trial_id':t,'experiment':'E4B',**i,'initial_positions_m':initial,'ordered_targets_m':targets,'requested_T':requested,'T_min_s':s.get('T_min_s'),'expected_T_exec_s':expected,'assignment_mode':s.get('assignment_mode','safety_aware'),'avoidance_mode':s.get('avoidance_mode','iapf_dual'),'safety_contract':{'d_hard':policy['safety']['d_hard'],'d_plan_ownership':'frozen safety mapping/allocator','mapping_type':policy['safety']['mapping_type'],'style_may_change':False},'timing_feasibility_evidence':horizontal.get('frozen_feasibility_terms_s') if source=='E4A-HORIZONTAL' else None,'authority_hierarchy':r['E4_B']['authority_hierarchy'],'comparison_tolerance':TOLERANCE,'frozen_motion_limits':r['E4_B']['motion_limit_contract']['frozen_limits'],'controller_hard_clamps':policy['controller_hard_clamps'],'authority_predicates':PREDICATES,'metric_log_schema':{'primary_metrics':['unauthorized_override_count','Priority_Preservation_Rate'],'denominator':'all retained E4-B attempts','raw_required':['requested_T','T_min_terms_v_a_j','T_exec','assignment_mode','avoidance_mode','d_hard','d_plan','safety_mapping','execution_profile_limits','omega_limits','controller_saturation_predicate','iapf_events','assignment_trace','authority_decision_trace'],'predicate_ids':[p['id'] for p in PREDICATES]},'physical_safety_active_outcome_execution':'PROHIBITED_IN_PREPARATION' if i['scenario_id']=='E4B-SAFETY-ACTIVE' else 'NOT_APPLICABLE'}
 spec['registered_input_hash']=canonical_sha256({'scenario':s,'style':i['style'],'seed':i['seed']}); spec['resolved_execution_spec_hash']=canonical_sha256(spec); return spec
