#!/usr/bin/env python3
"""E3 fail-closed provenance gate."""

from __future__ import annotations
import hashlib, json, subprocess
from pathlib import Path
from typing import Any, Dict
from e3_trial_registry import *

SOURCE = "36dba68c6b16681ec98500b49c5a83095de4b634"
BASELINE_TAG = "paper-final-sim-v3"
BASELINE = "6cf402debf23851b1eff3edc6f3ab49eae7127c4"
BRANCH = "formal/E3-planning-feedback-safety-v1"
ALLOWED_BRANCHES = {
    BRANCH,
    "formal/E3-formal-adapter-v1",
    "formal/E3-formal-adapter-case-c-v1",
    "formal/E3-protocol-feasibility-correction-v2",
}
PRODUCTION = [
 "location_allocate/location_allocate/safety_aware_allocator.py",
 "location_allocate/location_allocate/location_allocate.py",
 "lfs_policy/config/lfs_policy.paper_current.yaml",
 "experiments_v2/Formal Evaluation Experiments/harness/e3_wrench_driver.py",
 "experiments_v2/Formal Evaluation Experiments/environment/patches/iris_gazebo_ros_force_v1.patch",
]

def git(*args: str, binary=False):
    return subprocess.run(["git",*args],cwd=REPO_ROOT,check=True,capture_output=True,text=not binary).stdout

def validate() -> Dict[str, Any]:
    checks=[]
    def ck(name, ok, details): checks.append({"check":name,"status":"PASS" if ok else "FAIL","details":details})
    try:
        head=git("rev-parse","HEAD").strip(); branch=git("branch","--show-current").strip()
        ck("source_ancestry", subprocess.run(["git","merge-base","--is-ancestor",SOURCE,"HEAD"],cwd=REPO_ROOT).returncode==0,{"head":head})
        ck("branch",branch in ALLOWED_BRANCHES,branch)
        ck("baseline",git("rev-parse",f"{BASELINE_TAG}^{{}}").strip()==BASELINE,BASELINE)
        load_registry(); registered_trial_ids()
        ck("sealed_hashes",True,{"protocol":PROTOCOL_SHA256,"registry":REGISTRY_SHA256,"global_registry":GLOBAL_REGISTRY_SHA256,"order":ORDER_SHA256,"policy":POLICY_SHA256})
        details={}; ok=True
        for rel in PRODUCTION:
            current=(REPO_ROOT/rel).read_bytes(); approved=git("show",f"{SOURCE}:{rel}",binary=True)
            same=current==approved; ok &= same; details[rel]={"sha256":hashlib.sha256(current).hexdigest(),"byte_identical":same}
        ck("production_sources_byte_identical",ok,details)
        changed=git("diff","--name-only",SOURCE).splitlines()+git("ls-files","--others","--exclude-standard").splitlines()
        allowed_roots=(
            "experiments_v2/Formal Evaluation Experiments/E3/",
            "experiments_v2/Formal Evaluation Experiments/formal_equivalent_demos/",
        )
        allowed_files={
            "experiments_v2/Formal Evaluation Experiments/protocols/E3_protocol_v2.yaml",
            # Review-only scientific correction candidate.  Its presence is
            # allowed, but e3_trial_registry continues to resolve and hash-gate
            # the SEALED v2 protocol/registry until a separate human freeze.
            "experiments_v2/Formal Evaluation Experiments/protocols/E3_protocol_v3_candidate.yaml",
        }
        bad=sorted({p for p in changed if not p.startswith(allowed_roots) and p not in allowed_files})
        ck("changes_experiment_only",not bad,{"prohibited":bad})
    except Exception as exc: ck("internal_error",False,{"type":type(exc).__name__,"message":str(exc)}); head="UNKNOWN"
    return {"manifest_type":"E3_provenance_v2","status":"PASS" if all(c["status"]=="PASS" for c in checks) else "FAIL","runner_branch":branch if 'branch' in locals() else BRANCH,"runner_commit":head,"checks":checks}

if __name__ == "__main__":
    report=validate(); print(json.dumps(report,indent=2,sort_keys=True)); raise SystemExit(report["status"]!="PASS")
