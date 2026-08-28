#!/usr/bin/env python3
"""One cold E4A direct-command physical execution; no retry/campaign authority."""
from __future__ import annotations
import argparse,hashlib,json,os,signal,subprocess,sys,time
from pathlib import Path
from types import SimpleNamespace
from e4a_runtime_provenance import collect_runtime_provenance,runtime_provenance_gate
WORK=Path('/home/yihuang/learning/LLM_swarm_ws');PX4=Path('/home/yihuang/PX4-Autopilot-formal-v1');INSTALL=WORK/'formal_install_v1/setup.bash';PY=WORK/'llm_env/bin/python';POLICY=WORK/'formal_install_v1/lfs_policy/share/lfs_policy/config/lfs_policy.paper_current.yaml';REPO=Path(__file__).resolve().parents[4];READY=REPO/'experiments-legacy/system_8uav/scripts/wait_swarm_ready.py'
def env(seed):
 raw=subprocess.check_output(['bash','-lc',f'source /opt/ros/humble/setup.bash && source {INSTALL} && env -0']);e={a.decode():b.decode() for x in raw.split(b'\0') if b'=' in x for a,b in [x.split(b'=',1)]};e.update({'ROS_DOMAIN_ID':'43','RMW_IMPLEMENTATION':'rmw_fastrtps_cpp','FORMAL_GAZEBO_SEED':str(seed)});e['GAZEBO_PLUGIN_PATH']='/opt/ros/humble/lib:'+e.get('GAZEBO_PLUGIN_PATH','');return e
def start(cmd,path,cwd=None,e=None):f=path.open('w');p=subprocess.Popen(cmd,cwd=cwd,env=e,stdout=f,stderr=subprocess.STDOUT,start_new_session=True);return p,f
def stop(p):
 if not p or p.poll() is not None:return
 os.killpg(p.pid,signal.SIGINT)
 try:p.wait(20)
 except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGTERM);p.wait(8)
def clean():
 for sig in ('INT','TERM'):
  for pat in ('(^|/)px4( |$)','(^|/)gzserver( |$)','MicroXRCEAgent','ladrc_position_controller_node'):subprocess.run(['pkill',f'-{sig}','-f',pat],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  time.sleep(2)
def endpoint_ok(node,topic,uid):
 eps=node.get_subscriptions_info_by_topic(topic);return any(x.node_name=='ladrc_position_controller' and x.node_namespace==f'/uav{uid}' for x in eps) and any(x.node_name=='rosbag2_recorder' for x in eps)
def direct(spec,phase,result):
 sys.path[:0]=[str(REPO/'location_allocate'),str(REPO/'lfs_policy')];import rclpy
 from rclpy.node import Node
 from uav_swarm_interfaces.msg import UAVExecutionCommand,UAVStatus,StartupEvent
 from location_allocate.execution_command_builder import build_task_command_batch
 from location_allocate.lfs_types import ExecutableLFS,ExecutionProfile
 ids=spec['uav_ids'];targets=spec['initial_positions_m'] if phase=='stage' else spec['assigned_targets_m'];duration=6.0 if phase=='stage' else spec['duration_s'];mission=int(hashlib.sha256((spec['trial_id']+phase).encode()).hexdigest()[:8],16) or 1
 profiles=[]
 for x in spec['profiles']:
  v=dict(x);v['duration']=duration;v['omega_c']=tuple(v['omega_c']);v['omega_o']=tuple(v['omega_o']);profiles.append(ExecutionProfile(**v))
 class D(Node):
  def __init__(self):
   super().__init__('e4a_exact_command_driver');self.status={};self.events={i:[] for i in ids};self.pubs={i:self.create_publisher(UAVExecutionCommand,f'/uav{i}/execution_command',10) for i in ids};self.sub=[]
   for i in ids:
    self.sub.append(self.create_subscription(UAVStatus,f'/uav{i}/status',lambda m,u=i:self.status.__setitem__(u,m),20));self.sub.append(self.create_subscription(StartupEvent,f'/uav{i}/startup_event',lambda m,u=i:self.events[u].append(m.event) if int(m.mission_id)==mission else None,20))
  def commands(self):
   e=ExecutableLFS(uav_ids=tuple(ids),formation={'type':'E4A_exact_targets'},center=(0.,0.,0.),radius=0.,duration=duration,motion_style=spec['style'],safety_factor=spec['safety_s'],trigger_semantics={'mode':'direct'});r=SimpleNamespace(executable_lfs=e,assigned_targets=tuple(tuple(x) for x in targets),profiles=tuple(profiles));return build_task_command_batch(r,mission,1,1,self.get_clock().now().to_msg())
 rclpy.init();n=D();out={'phase':phase,'success':False,'mission_id':mission,'publish_count':{str(i):0 for i in ids}};stable=None
 try:
  deadline=time.monotonic()+20
  while time.monotonic()<deadline:
   rclpy.spin_once(n,timeout_sec=.05)
   if all(endpoint_ok(n,f'/uav{i}/execution_command',i) for i in ids):break
  if not all(endpoint_ok(n,f'/uav{i}/execution_command',i) for i in ids):raise RuntimeError('controller/recorder endpoint missing')
  commands=n.commands();out['command_payload']=[{'uav_id':int(c.uav_id),'mission_id':int(c.mission_id),'target':[c.target_pos.x,c.target_pos.y,c.target_pos.z],'style':c.profile.style,'duration':c.profile.duration,'configuration_id':c.profile.configuration_id} for c in commands]
  t0=time.monotonic();out['execution_command_t0_monotonic']=t0
  for c in commands:n.pubs[int(c.uav_id)].publish(c);out['publish_count'][str(c.uav_id)]+=1
  deadline=t0+(36 if phase=='stage' else duration+6)
  while time.monotonic()<deadline:
   rclpy.spin_once(n,timeout_sec=.02);ok=all(i in n.status and int(n.status[i].mission_id)==mission and n.status[i].is_hover_stable for i in ids);stable=(stable or time.monotonic()) if ok else None
   if phase=='stage' and stable and time.monotonic()-stable>=2:out['success']=True;break
   if phase=='interaction' and time.monotonic()>=t0+duration+2:out['success']=True;break
  out['events']=n.events;out['acceptance']=all('command_accepted' in n.events[i] for i in ids);out['stable_continuous_s']=time.monotonic()-stable if stable else 0.;out['termination_reason']='SUCCESS' if out['success'] else 'TIMEOUT'
 except Exception as x:out['error']=f'{type(x).__name__}: {x}';out['termination_reason']='DRIVER_FAILURE'
 finally:Path(result).write_text(json.dumps(out,indent=2,sort_keys=True)+'\n');n.destroy_node();rclpy.shutdown()
 return 0 if out['success'] else 2
def orchestrate(spec,output,result):
 output=Path(output).resolve();result=Path(result).resolve();output.mkdir(parents=True,exist_ok=True);e=env(spec['seed']);ids=spec['uav_ids'];procs=[];logs=[];out={'attempt_status':'infrastructure_failure','fixture_class':spec.get('fixture_class','registered_formal_spec'),'dataset_class':spec.get('dataset_class','formal_evaluation'),'retry_performed':False,'cold_start':True}
 try:
  clean()
  for cmd,name,cwd in [(['MicroXRCEAgent','udp4','-p','8888'],'agent',None),(['bash',str(PX4/'Tools/simulation/gazebo-classic/sitl_multiple_run.sh'),'-n',str(len(ids)),'-m','iris','-w','empty'],'sitl',PX4)]:p,f=start(cmd,output/f'{name}.log',cwd,e);procs.append(p);logs.append(f)
  time.sleep(20);p,f=start(['ros2','launch','ladrc_controller','swarm_launch.py',f"uav_ids:=[{','.join(map(str,ids))}]",'control_mode:=ladrc_acceleration','avoidance_mode:=iapf_dual',f'lfs_policy_file:={POLICY}'],output/'controllers.log',WORK,e);procs.append(p);logs.append(f)
  ready=subprocess.run([str(PY),str(READY),'--uav-ids',','.join(map(str,ids)),'--timeout','150'],cwd=WORK,env=e,text=True,capture_output=True,timeout=165);(output/'readiness.log').write_text(ready.stdout+ready.stderr)
  if ready.returncode:raise RuntimeError('readiness failed')
  topics=['/clock']
  for i in ids:topics += [f'/uav{i}/status',f'/uav{i}/startup_event',f'/uav{i}/execution_command',f'/uav{i}/trajectory_metrics',f'/uav{i}/control_adaptation',f'/uav{i}/control_tracking_debug',f'/uav{i}/iapf_debug',f'/px4_{i}/fmu/out/vehicle_status']
  p,f=start(['ros2','bag','record','-o',str(output/'rosbag'),*topics],output/'rosbag.log',WORK,e);procs.append(p);logs.append(f);time.sleep(2)
  provenance=collect_runtime_provenance(REPO,e,ids);(output/'runtime_provenance.json').write_text(json.dumps(provenance,indent=2,sort_keys=True)+'\n')
  if not runtime_provenance_gate(provenance):raise RuntimeError('installed runtime provenance gate failed')
  for phase in ('stage','interaction'):
   rr=output/f'{phase}_result.json';run=subprocess.run([str(PY),str(Path(__file__).resolve()),'--direct','--runtime-spec',str(output/'runtime_spec.json'),'--phase',phase,'--result',str(rr)],cwd=WORK,env=e,text=True,capture_output=True,timeout=120);(output/f'{phase}.log').write_text(run.stdout+run.stderr)
   if run.returncode:raise RuntimeError(f'{phase} failed')
  out['attempt_status']='success';out['raw_evidence']={'rosbag':'rosbag','staging':'stage_result.json','interaction':'interaction_result.json','controllers':'controllers.log','runtime_provenance':'runtime_provenance.json'}
 except Exception as x:out['error']=f'{type(x).__name__}: {x}'
 finally:
  for p in reversed(procs):stop(p)
  for f in logs:f.close()
  Path(result).write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
 return 0 if out['attempt_status']=='success' else 2
def main():
 p=argparse.ArgumentParser();p.add_argument('--runtime-spec',type=Path,required=True);p.add_argument('--output',type=Path);p.add_argument('--result',type=Path,required=True);p.add_argument('--direct',action='store_true');p.add_argument('--phase');a=p.parse_args();s=json.loads(a.runtime_spec.read_text())
 if a.direct:return direct(s,a.phase,a.result)
 (a.output/'runtime_spec.json').write_text(a.runtime_spec.read_text());return orchestrate(s,a.output,a.result)
if __name__=='__main__':raise SystemExit(main())
