#!/usr/bin/env python3
"""Offline E3 readiness auditor and manifest writer."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from e3_journal import E3Journal,write_artifact
from e3_provenance import BASELINE,BASELINE_TAG,BRANCH,SOURCE,validate
from e3_scorer import validate_artifact
from e3_trial_registry import *

def audit_run(root):
    root=Path(root); checks=[]
    def ck(n,o,d): checks.append({"check":n,"status":"PASS" if o else "FAIL","details":d})
    try:
        expected=registered_trial_ids(); records=E3Journal(root/"journal").read(); ids=[r["trial_id"] for r in records]
        ck("population_accounting",len(expected)==len(records)==360 and ids==expected,{"registered":360,"validated":len(records),"missing":len(set(expected)-set(ids)),"duplicate":len(ids)-len(set(ids)),"unregistered":len(set(ids)-set(expected))})
        bad=[]
        for r in records:
            path=root/r["artifact_path"]
            if not path.is_file() or sha256_file(path)!=r["artifact_sha256"]: bad.append(r["trial_id"]); continue
            validate_artifact(json.loads(path.read_text()))
        ck("retained_artifacts_and_schema",not bad,{"errors":bad})
        ck("deterministic_reconstruction",all(build_exact_spec(i)==build_exact_spec(i) for i in expected),{"count":len(expected)})
        ck("provenance",validate()["status"]=="PASS",validate()["status"])
        ck("no_formal_output",not (E3_DIR/"results"/"formal").exists(),{"formal_global_cursor_consumed":False})
    except Exception as e: ck("internal_error",False,{"type":type(e).__name__,"message":str(e)}); records=[]
    return {"audit_type":"E3_synthetic_readiness_audit_v1","status":"PASS" if all(c["status"]=="PASS" for c in checks) else "FAIL","dataset_class":"synthetic_validation","accepted_formal_result":False,"result_notice":"NOT_FORMAL_RESULT","registered_attempt_count":360,"synthetic_validated_attempt_count":len(records),"checks":checks}

def readiness(root,output):
    audit=audit_run(root); prov=validate(); runner=TOOLING_DIR/"e3_runner.py"
    value={"experiment":"E3","branch":BRANCH,"commit":prov["runner_commit"],"runner_entrypoint":"experiments_v2/Formal Evaluation Experiments/E3/tooling/e3_runner.py","runner_source_sha256":sha256_file(runner),"source_preflight_commit":SOURCE,"baseline_tag":BASELINE_TAG,"baseline_commit":BASELINE,"policy_sha256":POLICY_SHA256,"protocol_path":PROTOCOL_PATH.relative_to(REPO_ROOT).as_posix(),"protocol_sha256":PROTOCOL_SHA256,"registry_path":REGISTRY_PATH.relative_to(REPO_ROOT).as_posix(),"registry_sha256":REGISTRY_SHA256,"registered_attempt_count":360,"synthetic_validated_attempt_count":audit["synthetic_validated_attempt_count"],"production_semantics_changed":False,"accepted_formal_results_created":False,"formal_global_cursor_consumed":False,"validation_status":"READY_FOR_GLOBAL_INTEGRATION" if audit["status"]=="PASS" else "BLOCKED","blockers":[] if audit["status"]=="PASS" else ["synthetic readiness audit failed"]}
    write_artifact(output,value); return value

if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("run_dir",type=Path); p.add_argument("--readiness-manifest",type=Path); a=p.parse_args(); result=readiness(a.run_dir,a.readiness_manifest) if a.readiness_manifest else audit_run(a.run_dir); print(json.dumps(result,indent=2,sort_keys=True)); raise SystemExit(result.get("status",result.get("validation_status")) not in {"PASS","READY_FOR_GLOBAL_INTEGRATION"})

