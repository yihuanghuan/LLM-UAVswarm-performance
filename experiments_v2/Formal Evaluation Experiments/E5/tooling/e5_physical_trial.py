#!/usr/bin/env python3
"""One cold E5 Full-Method physical execution; no retry/campaign authority."""
from __future__ import annotations
import argparse,hashlib,json,os,signal,subprocess,time
from pathlib import Path
from e5_runtime_provenance import collect_runtime_provenance,runtime_provenance_gate
WORK=Path('/home/yihuang/learning/LLM_swarm_ws');PX4=Path('/home/yihuang/PX4-Autopilot-formal-v1');INSTALL=WORK/'formal_install_v1/setup.bash';PY=WORK/'llm_env/bin/python';POLICY=WORK/'formal_install_v1/lfs_policy/share/lfs_policy/config/lfs_policy.paper_current.yaml';REPO=Path(__file__).resolve().parents[4];READY=REPO/'experiments-legacy/system_8uav/scripts/wait_swarm_ready.py'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def completed_language_outcome(language):return language.get('attempt_status') in {'success','method_failure'}
def env(seed,output):
 raw=subprocess.check_output(['bash','-lc',f'source /opt/ros/humble/setup.bash && source {INSTALL} && env -0']);e={a.decode():b.decode() for x in raw.split(b'\0') if b'=' in x for a,b in [x.split(b'=',1)]};e.update({'ROS_DOMAIN_ID':'45','RMW_IMPLEMENTATION':'rmw_fastrtps_cpp','FORMAL_GAZEBO_SEED':str(seed),'ROS_HOME':str(output/'ros_home'),'PYTHONPATH':str(REPO/'location_allocate')+':'+str(REPO/'lfs_policy')+':'+e.get('PYTHONPATH','')});e['PATH']='/usr/bin:/bin:'+e.get('PATH','');e['GAZEBO_PLUGIN_PATH']='/opt/ros/humble/lib:'+e.get('GAZEBO_PLUGIN_PATH','');return e
def start(cmd,path,cwd=None,e=None):f=path.open('w');p=subprocess.Popen(cmd,cwd=cwd,env=e,stdout=f,stderr=subprocess.STDOUT,start_new_session=True);return p,f
def stop(p):
 if not p or p.poll() is not None:return
 os.killpg(p.pid,signal.SIGINT)
 try:p.wait(25)
 except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGTERM);p.wait(10)
def clean():
 for sig in ('INT','TERM'):
  for pat in ('(^|/)px4( |$)','(^|/)gzserver( |$)','MicroXRCEAgent','ladrc_position_controller_node','location_allocate'):subprocess.run(['pkill',f'-{sig}','-f',pat],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  time.sleep(2)
def orchestrate(s,output,result):
 output=Path(output).resolve();result=Path(result).resolve();output.mkdir(parents=True,exist_ok=True);e=env(s['seed'],output);ids=s['uav_ids'];procs=[];logs=[];out={'attempt_status':'infrastructure_failure','fixture_class':s.get('fixture_class','registered_formal_spec'),'dataset_class':s.get('dataset_class','formal_evaluation'),'retry_performed':False,'cold_start':True,'full_method_modes':s['full_method_modes'],'accepted_formal_result':s.get('dataset_class')=='formal_evaluation'}
 try:
  clean()
  for cmd,name,cwd in [(['MicroXRCEAgent','udp4','-p','8888'],'agent',None),(['bash',str(PX4/'Tools/simulation/gazebo-classic/sitl_multiple_run.sh'),'-n','8','-m','iris','-w','empty'],'sitl',PX4)]:p,f=start(cmd,output/f'{name}.log',cwd,e);procs.append(p);logs.append(f)
  time.sleep(24);p,f=start(['ros2','launch','ladrc_controller','swarm_launch.py','uav_ids:=[1,2,3,4,5,6,7,8]','control_mode:=ladrc_acceleration','avoidance_mode:=iapf_dual',f'lfs_policy_file:={POLICY}'],output/'controllers.log',WORK,e);procs.append(p);logs.append(f)
  ready=subprocess.run([str(PY),str(READY),'--uav-ids','1,2,3,4,5,6,7,8','--timeout','180'],cwd=WORK,env=e,text=True,capture_output=True,timeout=195);(output/'readiness.log').write_text(ready.stdout+ready.stderr)
  if ready.returncode:raise RuntimeError('8/8 readiness failed')
  topics=['/clock']
  for i in ids:topics += [f'/uav{i}/status',f'/uav{i}/startup_event',f'/uav{i}/swarm_state',f'/uav{i}/execution_command',f'/uav{i}/trajectory_metrics',f'/uav{i}/control_adaptation',f'/uav{i}/control_tracking_debug',f'/uav{i}/iapf_debug',f'/px4_{i}/fmu/out/vehicle_status']
  p,f=start(['ros2','bag','record','-o',str(output/'rosbag'),*topics],output/'rosbag.log',WORK,e);procs.append(p);logs.append(f);time.sleep(3)
  rp=collect_runtime_provenance(REPO,e,ids);(output/'runtime_provenance.json').write_text(json.dumps(rp,indent=2,sort_keys=True)+'\n')
  if not runtime_provenance_gate(rp):raise RuntimeError('installed runtime provenance gate failed')
  lr=output/'language_result.json';run=subprocess.run([str(PY),str(Path(__file__).with_name('e5_language_driver.py')),'--runtime-spec',str(output/'runtime_spec.json'),'--output',str(output),'--result',str(lr)],cwd=REPO,env=e,text=True,capture_output=True,timeout=float(s['mission_timeout_s'])+150);(output/'language_driver.log').write_text(run.stdout+run.stderr)
  if not lr.exists():raise RuntimeError('language result missing')
  language=json.loads(lr.read_text())
  if not completed_language_outcome(language):raise RuntimeError(f"language path failed: {language.get('error','unknown')}")
  out.update({'attempt_status':'success','scientific_outcome':language.get('attempt_status'),'method_failure_stage':language.get('failure_stage'),'method_failure_reason':language.get('error'),'language_result':'language_result.json','runtime_provenance':'runtime_provenance.json','raw_evidence':{'rosbag':'rosbag','controllers':'controllers.log','llm_raw':'llm_raw_responses.append.jsonl','llm_parse':'llm_parse_log.append.csv.fragment','candidate':'validated_candidate.json','resolution_trace':'ros_home/candidate_resolution_trace.jsonl'}})
 except Exception as x:out['error']=f'{type(x).__name__}: {x}'
 finally:
  for p in reversed(procs):stop(p)
  for f in logs:f.close()
  result.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
 return 0 if out['attempt_status']=='success' else 2
def main():
 p=argparse.ArgumentParser();p.add_argument('--runtime-spec',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--result',type=Path,required=True);a=p.parse_args();s=json.loads(a.runtime_spec.read_text());(a.output/'runtime_spec.json').write_text(a.runtime_spec.read_text());return orchestrate(s,a.output,a.result)
if __name__=='__main__':raise SystemExit(main())
