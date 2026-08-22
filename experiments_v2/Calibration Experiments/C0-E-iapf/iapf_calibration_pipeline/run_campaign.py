#!/usr/bin/env python3
"""Minimal, reproducible C0-E runtime calibration campaign.

Each invocation is a cold-start production Candidate dispatch trial.  The
runner never replaces a trial directory and retains startup/mission failures
as first-class rows.  It intentionally does not implement avoidance or
trajectory equations: PX4/Gazebo, LADRC and candidate_dispatch are used
unchanged.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, os, signal, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
import yaml

PIPE = Path(__file__).resolve().parent
REPO = PIPE.parents[3]
WORKSPACE = REPO.parents[1]
RESULTS = PIPE.parent / "results" / "C0-E_iapf_freeze"
PX4 = Path("/home/yihuang/PX4-Autopilot")
PYTHON = WORKSPACE / "llm_env/bin/python"
READY = REPO / "experiments-legacy/system_8uav/scripts/wait_swarm_ready.py"

# Independent diagnostic calibration scenes.  Commands are deterministic
# specifications (Candidate parser temperature is fixed at production 0).
SCENES = {
 "S1": {"ids":"1,2,3,4,5,6,7,8", "command":"Have UAVs 1 through 8 form a line with compact qualitative scale centered at [0, 12, 3] with automatic duration, using normal motion and safety factor {s}.", "family":"head-on"},
 "S2": {"ids":"1,2,3,4,5,6,7,8", "command":"Have UAVs 1 through 8 form a circle with normal qualitative scale centered at [0, 12, 3] with automatic duration, using normal motion and safety factor {s}.", "family":"offset-crossing"},
 "S3": {"ids":"1,2,3,4,5,6,7,8", "command":"Have UAVs 1 through 8 form a vertical line with normal qualitative scale centered at [0, 12, 5] with automatic duration, using normal motion and safety factor {s}.", "family":"vertical-crossing"},
 "S4": {"ids":"1,2,3,4,5,6,7,8", "command":"Have UAVs 1 through 8 form a circle with compact qualitative scale centered at [0, 12, 3] with automatic duration, using normal motion and safety factor {s}.", "family":"dense"},
 "S5": {"ids":"1,2,3,4,5,6,7,8", "command":"Have UAVs 1 through 8 form a line with spacious qualitative scale centered at [0, 12, 3] with automatic duration, using normal motion and safety factor {s}.", "family":"already-separating"},
}

def sha(path):
 h=hashlib.sha256(); h.update(Path(path).read_bytes()); return h.hexdigest()
def stop(p):
 if p and p.poll() is None:
  os.killpg(p.pid, signal.SIGINT)
  try: p.wait(25)
  except subprocess.TimeoutExpired: os.killpg(p.pid, signal.SIGKILL); p.wait(10)
def ros_env():
 out=subprocess.check_output(['bash','-lc',f'source /opt/ros/humble/setup.bash && source {WORKSPACE}/install/setup.bash && env -0'])
 return {x.split(b'=',1)[0].decode():x.split(b'=',1)[1].decode() for x in out.split(b'\0') if b'=' in x}
def start(cmd, log, cwd=None, env=None):
 f=log.open("w"); return subprocess.Popen(cmd,cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True),f
def topics(ids):
 out=[]
 for u in ids.split(','):
  out += [f"/uav{u}/iapf_debug",f"/uav{u}/control_tracking_debug",f"/uav{u}/trajectory_metrics",f"/uav{u}/status",f"/uav{u}/swarm_state"]
 return out
def main():
 p=argparse.ArgumentParser(); p.add_argument('--stage',required=True); p.add_argument('--candidate',required=True); p.add_argument('--policy',type=Path,required=True); p.add_argument('--scene',choices=SCENES,required=True); p.add_argument('--s',type=float,required=True); p.add_argument('--cold-start',type=int,default=1); p.add_argument('--root',type=Path,default=RESULTS/'runtime_raw'); a=p.parse_args()
 a.policy=a.policy.resolve(); spec=SCENES[a.scene]; trial=f"{a.stage}_{a.candidate}_{a.scene}_s{a.s:g}_cold{a.cold_start}_{int(time.time())}"; d=a.root/trial; d.mkdir(parents=True,exist_ok=False); env=ros_env()
 policy=yaml.safe_load(a.policy.read_text()); alpha=float(policy.get('iapf_runtime',{}).get('filter_alpha',.20)); ids=spec['ids']; command=spec['command'].format(s=f"{a.s:.1f}")
 manifest={"trial_id":trial,"stage":a.stage,"candidate":a.candidate,"scene":a.scene,"scene_family":spec['family'],"s":a.s,"cold_start":a.cold_start,"seed":"c0e-screen-20260822","control_mode":"ladrc_acceleration","dispatch":"location_allocate.candidate_dispatch","policy":str(a.policy),"policy_sha256":sha(a.policy),"iapf_filter_alpha":alpha,"command":command,"spawn":"standard_8_uav_line","started_utc":datetime.now(timezone.utc).isoformat(),"result":"FAIL","failure_reason":""}
 ps=[]; logs=[]; bag=None
 try:
  q,l=start(['MicroXRCEAgent','udp4','-p','8888'],d/'agent.log',env=env); ps+=[q];logs+=[l]
  q,l=start(['bash',str(PX4/'Tools/simulation/gazebo-classic/sitl_multiple_run.sh'),'-n','8','-m','iris'],d/'sitl.log',PX4,env);ps+=[q];logs+=[l];time.sleep(18)
  if q.poll() is not None: raise RuntimeError('PX4/Gazebo exited during startup')
  q,l=start(['ros2','launch','ladrc_controller','swarm_launch.py',f'uav_ids:=[{ids}]','control_mode:=ladrc_acceleration',f'lfs_policy_file:={a.policy}',f'iapf_filter_alpha:={alpha:.2f}'],d/'controllers.log',WORKSPACE,env);ps+=[q];logs+=[l]
  r=subprocess.run([str(PYTHON),str(READY),'--uav-ids',ids,'--timeout','120'],cwd=REPO,env=env,text=True,capture_output=True,timeout=135); (d/'readiness.log').write_text(r.stdout+r.stderr)
  if r.returncode: raise RuntimeError('readiness gate failed')
  bag,bl=start(['ros2','bag','record','-o',str(d/'rosbag'),*topics(ids)],d/'rosbag.log',REPO,env); logs+=[bl]; time.sleep(1)
  j=subprocess.run([str(PYTHON),'-m','location_allocate.candidate_dispatch','--uav-ids',ids,'--policy',str(a.policy),'--command',command],cwd=REPO,env=env,text=True,capture_output=True,timeout=300); (d/'scheduler.log').write_text(j.stdout+j.stderr)
  if j.returncode or '"candidate_completed": true' not in j.stdout: raise RuntimeError('Candidate mission did not complete')
  manifest['result']='PASS'
 except Exception as e: manifest['failure_reason']=f'{type(e).__name__}: {e}'
 finally:
  stop(bag)
  for q in reversed(ps): stop(q)
  for l in logs: l.close()
  manifest['finished_utc']=datetime.now(timezone.utc).isoformat(); (d/'manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
 # A raw bag is retained for all completed trials.  Mission/runtime evidence
 # is recorded immediately; debug metrics are summarized offline in a stable CSV.
 row={k:manifest[k] for k in ('trial_id','stage','candidate','scene','scene_family','s','cold_start','control_mode','dispatch','iapf_filter_alpha','result','failure_reason','policy_sha256')}; row['raw_dir']=str(d.relative_to(RESULTS)); print(json.dumps(row,sort_keys=True)); return 0 if manifest['result']=='PASS' else 2
if __name__=='__main__': raise SystemExit(main())
