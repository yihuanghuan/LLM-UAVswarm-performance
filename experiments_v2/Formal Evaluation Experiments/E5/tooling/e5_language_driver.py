#!/usr/bin/env python3
"""Instrument, without replacing, the frozen Candidate parser/runtime path."""
from __future__ import annotations
import argparse,hashlib,json,signal,time
from pathlib import Path
def _slice(path,offset):
 p=Path(path)
 if not p.exists():return ''
 with p.open('rb') as f:f.seek(offset);return f.read().decode('utf-8',errors='replace')
def main():
 p=argparse.ArgumentParser();p.add_argument('--runtime-spec',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--result',type=Path,required=True);a=p.parse_args();s=json.loads(a.runtime_spec.read_text());a.output.mkdir(parents=True,exist_ok=True)
 command=s['exact_command'];assert hashlib.sha256(command.encode()).hexdigest()==s['exact_command_utf8_sha256'];assert not s.get('candidate_gt_used_as_input',False)
 import rclpy
 import location_allocate.paper_runtime as paper_runtime
 from location_allocate.location_allocate import UAVFormationNode
 from location_allocate.paper_candidate_parser import parse_candidate_mission
 from location_allocate.safety_aware_allocator import SafetyAwareTopologyAllocator
 repo=Path(__file__).resolve().parents[4];rawlog=repo/'logs/llm_raw_responses.jsonl';parselog=repo/'logs/llm_parse_log.csv';rawpos=rawlog.stat().st_size if rawlog.exists() else 0;parsepos=parselog.stat().st_size if parselog.exists() else 0;lat={'LLM_inference':0.0,'parse_validation':0.0,'snapshot_wait':0.0,'resolution':0.0,'allocation':0.0,'dispatch':0.0,'physical_execution':0.0};counts={'command_submission':1,'formal_command_retry':0}
 def timed(obj,name,key):
  original=getattr(obj,name)
  def wrapper(*x,**kw):
   t=time.monotonic()
   try:return original(*x,**kw)
   finally:lat[key]+=time.monotonic()-t
  setattr(obj,name,wrapper)
 for name in ('allocate_with_metrics','allocate_grouped'):timed(SafetyAwareTopologyAllocator,name,'allocation')
 timed(paper_runtime,'resolve_execution_task','resolution');timed(paper_runtime,'resolve_execution_parallel','resolution')
 out={'attempt_status':'infrastructure_failure','command_byte_identity':True,'candidate_gt_used_as_input':False,'latency_decomposition_s':lat,'counts':counts,'mission_timeout_s':s['mission_timeout_s']}
 rclpy.init();node=None
 try:
  node=UAVFormationNode();ids=tuple(s['uav_ids']);t=time.monotonic();pre=node.paper_runtime._await_dispatch_snapshot(ids);lat['snapshot_wait']+=time.monotonic()-t;out['fresh_state_before_language_submission']=set(pre.states)==set(ids)
  started=time.monotonic();payload=parse_candidate_mission(command,f'Available UAV IDs: {list(ids)}\nTotal available UAVs: {len(ids)}');parse_wall=time.monotonic()-started
  raw_append=_slice(rawlog,rawpos);parse_append=_slice(parselog,parsepos);(a.output/'llm_raw_responses.append.jsonl').write_text(raw_append);(a.output/'llm_parse_log.append.csv.fragment').write_text(parse_append);records=[]
  for line in raw_append.splitlines():
   try:records.append(json.loads(line))
   except json.JSONDecodeError:pass
  lat['LLM_inference']=sum(float(x.get('latency_ms',0))/1000 for x in records);lat['parse_validation']=max(0.0,parse_wall-lat['LLM_inference']);(a.output/'validated_candidate.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
  participants=node.paper_runtime._mission_participant_ids(payload);t=time.monotonic();snap=node.paper_runtime._await_dispatch_snapshot(participants);lat['snapshot_wait']+=time.monotonic()-t;node.paper_runtime.prime_dispatch_snapshot(participants,snap);out['fresh_state_before_runtime_dispatch']=set(snap.states)==set(participants)
  timed(node.paper_runtime,'_publish_commands','dispatch');runtime_started=time.monotonic()
  def alarm(_sig,_frame):raise TimeoutError(f"sealed mission timeout {s['mission_timeout_s']} s")
  old=signal.signal(signal.SIGALRM,alarm);signal.setitimer(signal.ITIMER_REAL,float(s['mission_timeout_s']))
  try:node.run_candidate_mission(payload)
  finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,old)
  runtime_wall=time.monotonic()-runtime_started;lat['resolution']=max(0.0,lat['resolution']-lat['allocation']);lat['physical_execution']=max(0.0,runtime_wall-lat['resolution']-lat['allocation']-lat['dispatch']);out.update({'attempt_status':'success','candidate_completed':True,'validated_candidate_retained':True,'llm_attempt_records':len(records),'runtime_wall_s':runtime_wall})
 except Exception as x:out['error']=f'{type(x).__name__}: {x}'
 finally:
  raw_append=_slice(rawlog,rawpos);parse_append=_slice(parselog,parsepos);(a.output/'llm_raw_responses.append.jsonl').write_text(raw_append);(a.output/'llm_parse_log.append.csv.fragment').write_text(parse_append);parse_lines=[x for x in parse_append.splitlines() if x and not x.startswith('command_id,')];out['provider_request_attempts_logged']=len(parse_lines);out['real_llm_invocation_attempted']=bool(parse_lines);out['latency_decomposition_s']=lat;a.result.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
  if node is not None:node.destroy_node()
  if rclpy.ok():rclpy.shutdown()
 return 0 if out['attempt_status']=='success' else 2
if __name__=='__main__':raise SystemExit(main())
