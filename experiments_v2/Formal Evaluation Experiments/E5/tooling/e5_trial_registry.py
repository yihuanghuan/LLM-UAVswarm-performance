from __future__ import annotations
import hashlib,json,re
from pathlib import Path
import yaml
TOOLING_DIR=Path(__file__).resolve().parent; E5_DIR=TOOLING_DIR.parent; FORMAL_DIR=E5_DIR.parent; REPO_ROOT=FORMAL_DIR.parents[1]
PROTOCOL_PATH=FORMAL_DIR/'protocols/E5_protocol_v1.yaml'; REGISTRY_PATH=E5_DIR/'e5_end_to_end_registry_v1.yaml'; GLOBAL_REGISTRY_PATH=FORMAL_DIR/'e2_e5_scenario_seed_registry_v1.yaml'; ORDER_PATH=FORMAL_DIR/'simulation_trial_order_v1.txt'; POLICY_PATH=REPO_ROOT/'lfs_policy/config/lfs_policy.paper_current.yaml'; LLM_MANIFEST_PATH=FORMAL_DIR/'llm_runtime_manifest_v1.yaml'
PROTOCOL_SHA256='116002154cd2395b6a9f55d7c1aae6e0a2c42440f0ceaa827a1a8cb02828319c'; REGISTRY_SHA256='9bb6bc9b46b5211c50c8f2e29bd434235424beb2bb0fc36ec857a3298d89511e'; GLOBAL_REGISTRY_SHA256='90313d33793940489edde631d397564378ae54fe3cfddf438e4a895d6132254d'; ORDER_SHA256='db28bf8d734e1f206987519e91ff27c67b2d9ab2971aeb68c4e13735762f1dce'; POLICY_SHA256='6b47d27f4253d7311e79ea51f6dd1cf0d0182e6df24374a94abae0aa6a135858'; LLM_MANIFEST_SHA256='2760697ad2230e335f7955f67b2cac2f4b6d44487743ef760ac6754cb12a3a14'
MODES={'lfs_runtime_mode':'candidate_v2','assignment_mode':'safety_aware','control_mode':'ladrc_acceleration','avoidance_mode':'iapf_dual'}
RE_TRIAL=re.compile(r'^(E5-(?:SIMPLE|REL-QUAL|SEQUENTIAL|PARALLEL|MIXED-HIGH))__Full_Method__S(\d+)$')
class E5Error(RuntimeError): pass
def sha256_file(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def canonical(v): return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def canonical_sha256(v): return hashlib.sha256(canonical(v)).hexdigest()
def ly(p):
 v=yaml.safe_load(Path(p).read_text());
 if not isinstance(v,dict): raise E5Error(f'expected mapping: {p}')
 return v
def load_registry():
 expected=[(PROTOCOL_PATH,PROTOCOL_SHA256),(REGISTRY_PATH,REGISTRY_SHA256),(GLOBAL_REGISTRY_PATH,GLOBAL_REGISTRY_SHA256),(ORDER_PATH,ORDER_SHA256),(POLICY_PATH,POLICY_SHA256),(LLM_MANIFEST_PATH,LLM_MANIFEST_SHA256)]
 for p,h in expected:
  if sha256_file(p)!=h: raise E5Error(f'sealed hash mismatch: {p}: {sha256_file(p)} != {h}')
 r=ly(REGISTRY_PATH)
 if r.get('status')!='SEALED': raise E5Error('E5 registry not sealed')
 if {k:r['full_method'][k] for k in MODES}!=MODES: raise E5Error('Full Method modes mismatch')
 return r
def scenarios(r=None):
 x={s['scenario_id']:s for s in (r or load_registry())['scenarios']}
 if len(x)!=5: raise E5Error('expected five unique scenarios')
 return x
def registered_trial_ids(r=None):
 r=r or load_registry(); ids=[f"{s['scenario_id']}__Full_Method__S{seed}" for s in r['scenarios'] for seed in r['seeds']]; order=ORDER_PATH.read_text().splitlines(); f=[x for x in order if x.startswith('E5-')]
 if len(ids)!=len(set(ids)) or len(ids)!=25 or set(ids)!=set(f) or any(order.count(x)!=1 for x in ids): raise E5Error('population/global order mismatch')
 return ids
def parse_trial_id(t,r=None):
 m=RE_TRIAL.fullmatch(str(t))
 if not m:
  if str(t).startswith(('E2-','E3-','E4A-','E4B-')): raise E5Error('wrong family')
  raise E5Error('malformed/unregistered E5 trial')
 sid,ss=m.groups(); r=r or load_registry(); seed=int(ss)
 if sid not in scenarios(r): raise E5Error('unregistered scenario')
 if seed not in r['seeds']: raise E5Error('unregistered seed')
 return {'scenario_id':sid,'condition':'Full_Method','seed':seed}
def mission_graph_contract(s):
 sid=s['scenario_id']; nodes=s['candidate_semantic_ground_truth']['mission']['nodes']; contract={'node_types':[n['type'] for n in nodes],'task_count':sum(1 if n['type']=='task' else len(n['tasks']) for n in nodes)}
 if sid=='E5-SEQUENTIAL': contract.update({'transition':'task_1_TRAJECTORY_completion','not_stable_hover_completion':True,'task_1_q':'continuous'})
 if sid in {'E5-PARALLEL','E5-MIXED-HIGH'}:
  parallel=next(n for n in nodes if n['type']=='parallel'); contract.update({'parallel_completion_mode':parallel['completion_mode'],'synchronized':parallel['completion_mode']=='synchronized','parallel_task_ids':[t['task_id'] for t in parallel['tasks']]})
 if sid=='E5-MIXED-HIGH': contract['transition']='task_1_TRAJECTORY_completion_to_parallel_group'
 return contract
def build_exact_spec(t,r=None):
 r=r or load_registry(); i=parse_trial_id(t,r); s=scenarios(r)[i['scenario_id']]; llm=ly(LLM_MANIFEST_PATH); command=s['exact_command']
 spec={'spec_type':'E5_exact_execution_spec_v1','trial_id':t,'experiment':'E5',**i,'cold_start_required':True,'cold_start_spawn_m':r['common']['cold_start_spawn_m'],'readiness_gate':{'required_uav_count':8,'uav_ids':r['common']['availability'],'all_px4_ready':True,'armed_offboard':True,'frozen_fresh_state_predicate':True,'before_command_submission':True},'full_method_modes':MODES,'exact_command':command,'exact_command_utf8_sha256':hashlib.sha256(command.encode()).hexdigest(),'command_source':'sealed_registry_exact_command','candidate_semantic_ground_truth':{'usage':'audit_and_scoring_only_not_runtime_input','value':s['candidate_semantic_ground_truth']},'mission_graph':mission_graph_contract(s),'completion_mode':s['completion_mode'],'mission_timeout_s':float(s['mission_timeout_s']),'frozen_language_runtime':{'model':llm['provider']['exact_model_name'],'prompt_version':llm['prompt']['prompt_version'],'system_prompt_sha256':llm['prompt']['system_prompt_sha256'],'few_shot_sha256':llm['prompt']['few_shot_sha256'],'schema_sha256':llm['schema']['sha256'],'temperature':llm['decoding']['temperature'],'top_p':llm['decoding']['top_p'],'max_tokens':llm['decoding']['max_tokens'],'response_format':llm['decoding']['response_format'],'candidate_gt_used_as_input':False},'success_contract':{'denominator':'all retained attempts','predicates':r['common']['success_common'],'d_hard_m':1.5,'retry_or_replacement_allowed':False},'metric_log_schema':{'primary_metrics':['all_attempt_mission_success','tracking_RMSE','final_error','actual_d_min','iapf_burden','latency_decomposition'],'latency_components':['LLM_inference','parse_validation','snapshot_wait','resolution','allocation','dispatch','physical_execution'],'raw_required':['raw_llm_request_response_metadata','candidate_validation','state_snapshots','resolution_trace','assignment_trace','dispatch_events','task_completion_events','per_uav_measured_position_3d','nominal_reference','safe_reference','iapf_active','iapf_delta_p','iapf_delta_a','hard_failures','px4_readiness']}}
 spec['registered_input_hash']=canonical_sha256({'scenario':s,'seed':i['seed'],'condition':'Full_Method'}); spec['resolved_execution_spec_hash']=canonical_sha256(spec); return spec
