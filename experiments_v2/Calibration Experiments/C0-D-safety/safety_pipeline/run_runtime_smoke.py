#!/usr/bin/env python3
"""The three preregistered C0-D cold-start integration smokes."""
from __future__ import annotations
import csv, json, os, signal, subprocess, tempfile, time
from pathlib import Path
import yaml

PIPELINE=Path(__file__).resolve().parent; REPO=PIPELINE.parents[3]; WORKSPACE=REPO.parents[1]
RESULTS=PIPELINE.parent/"results"/"C0-D_safety_policy_freeze"; PX4=Path("/home/yihuang/PX4-Autopilot")
PYTHON=WORKSPACE/"llm_env/bin/python"; READY=REPO/"experiments-legacy/system_8uav/scripts/wait_swarm_ready.py"
CASES=[("compact_s1",1.0,"Have UAVs 1 through 8 form a line with compact qualitative scale centered at [0, 12, 3] with automatic duration, using normal motion and safety factor 1.0."),
       ("crossing_prone_s1",1.0,"Have UAVs 1 through 8 form a circle with normal qualitative scale centered at [0, 12, 3] with automatic duration, using normal motion and safety factor 1.0."),
       ("normal_spacious_smax",2.0,"Have UAVs 1 through 8 form a line with spacious qualitative scale centered at [0, 12, 3] with automatic duration, using normal motion and safety factor 2.0.")]
def start(cmd, log, cwd=None):
    stream=log.open("w"); return subprocess.Popen(cmd,cwd=cwd,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True),stream
def stop(p):
    if p and p.poll() is None:
        os.killpg(p.pid,signal.SIGINT)
        try:p.wait(25)
        except subprocess.TimeoutExpired: os.killpg(p.pid,signal.SIGKILL);p.wait(10)
def main():
    RESULTS.mkdir(parents=True,exist_ok=True); rows=[]
    base=yaml.safe_load((REPO/"lfs_policy/config/lfs_policy.paper_current.yaml").read_text())
    with tempfile.TemporaryDirectory(prefix="c0d-policy-") as temp:
      policy=Path(temp)/"candidate.yaml";policy.write_text(yaml.safe_dump(base,sort_keys=False))
      for name,s,command in CASES:
        out=RESULTS/"runtime_raw"/name;out.mkdir(parents=True,exist_ok=False);procs=[];logs=[];failure="";text=""
        try:
          p,l=start(["MicroXRCEAgent","udp4","-p","8888"],out/"agent.log");procs.append(p);logs.append(l)
          p,l=start(["bash",str(PX4/"Tools/simulation/gazebo-classic/sitl_multiple_run.sh"),"-n","8","-m","iris"],out/"sitl.log",PX4);procs.append(p);logs.append(l);time.sleep(18)
          if p.poll() is not None:raise RuntimeError("PX4/Gazebo exited during startup")
          p,l=start(["ros2","launch","ladrc_controller","swarm_launch.py","uav_ids:=[1,2,3,4,5,6,7,8]","control_mode:=ladrc_acceleration",f"lfs_policy_file:={policy}"],out/"controllers.log",WORKSPACE);procs.append(p);logs.append(l)
          ready=subprocess.run([str(PYTHON),str(READY),"--uav-ids","1,2,3,4,5,6,7,8","--timeout","150"],cwd=REPO,text=True,capture_output=True,timeout=165);(out/"readiness.log").write_text(ready.stdout+ready.stderr)
          if ready.returncode:raise RuntimeError("readiness gate failed")
          job=subprocess.run([str(PYTHON),str(REPO/"experiments_v2/Calibration Experiments/C0-C-geometry-scale/geometry_scale_pipeline/candidate_owned_prewarm.py"),"--uav-ids","1,2,3,4,5,6,7,8","--policy",str(policy),"--command",command],cwd=REPO,text=True,capture_output=True,timeout=300);text=job.stdout+job.stderr;(out/"scheduler.log").write_text(text)
          if job.returncode or '"candidate_completed": true' not in text:raise RuntimeError("Candidate mission did not complete")
        except Exception as e: failure=f"{type(e).__name__}: {e}"
        finally:
          for p in reversed(procs):stop(p)
          for l in logs:l.close()
        rows.append({"attempt":name,"uav_count":8,"s":s,"candidate_completed":not bool(failure),"workspace_rejection":"workspace" in text.lower(),"freshness_failure":"stale" in text.lower(),"integration_result":"PASS" if not failure else "FAIL","failure_reason":failure,"raw_log_dir":str(out.relative_to(RESULTS))})
    with (RESULTS/"runtime_smoke_metrics.csv").open("w",newline="") as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    if any(r["integration_result"]!="PASS" for r in rows):raise SystemExit("C0-D smoke failure recorded")
if __name__=="__main__":main()
