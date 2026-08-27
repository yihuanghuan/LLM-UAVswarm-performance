#!/usr/bin/env python3
"""E3 exact-trial adapter core and synthetic population validation."""
from __future__ import annotations
import argparse, hashlib, json, subprocess
from pathlib import Path
from typing import Any, Dict
from e3_journal import E3Journal, write_artifact
from e3_provenance import validate
from e3_scorer import validate_artifact
from e3_trial_registry import *

DATASET="synthetic_validation"; NOTICE="NOT_FORMAL_RESULT"
RESULTS=E3_DIR/"results"/"synthetic-validation"

class SyntheticBackend:
    def execute_exact_spec(self,spec):
        return {"backend":"E3_synthetic_contract_backend_v1","validation_status":"SPEC_VALIDATED","scientific_outcomes":None,"launch_spec_validated":True}

def runner_source_hash(): return sha256_file(Path(__file__))

def run_exact_trial(trial_id: str, campaign_context: Dict[str,Any], output_root: Path, backend=None):
    provenance=validate()
    if provenance["status"]!="PASS": raise E3Error("provenance gate failed")
    spec=build_exact_spec(trial_id)
    if campaign_context.get("exact_trial_id")!=trial_id: raise E3Error("campaign context exact trial mismatch")
    output_root=Path(output_root)
    artifact_path=output_root/"artifacts"/trial_id/"attempt.json"
    if artifact_path.exists(): raise E3Error(f"duplicate retained attempt: {trial_id}")
    mock=(backend or SyntheticBackend()).execute_exact_spec(spec)
    artifact={"record_type":"E3_synthetic_attempt_v1","dataset_class":DATASET,"accepted_formal_result":False,"result_notice":NOTICE,"trial_id":trial_id,"experiment":"E3","scenario_id":spec["scenario_id"],"condition":spec["condition"],"seed":spec["seed"],"registered_input_hash":spec["registered_input_hash"],"resolved_execution_spec_hash":spec["resolved_execution_spec_hash"],"runner":{"branch":provenance["runner_branch"],"commit":provenance["runner_commit"],"entrypoint":"experiments_v2/Formal Evaluation Experiments/E3/tooling/e3_runner.py","source_sha256":runner_source_hash()},"protocol_sha256":PROTOCOL_SHA256,"registry_sha256":REGISTRY_SHA256,"policy_sha256":POLICY_SHA256,"validation_status":"SPEC_VALIDATED","execution_spec":spec,"mock_execution":mock}
    validate_artifact(artifact); write_artifact(artifact_path,artifact)
    digest=sha256_file(artifact_path)
    record=E3Journal(output_root/"journal").append({"trial_id":trial_id,"experiment":"E3","scenario_id":spec["scenario_id"],"condition":spec["condition"],"seed":spec["seed"],"artifact_path":artifact_path.relative_to(output_root).as_posix(),"artifact_sha256":digest,"validation_status":"SPEC_VALIDATED","dataset_class":DATASET,"accepted_formal_result":False,"result_notice":NOTICE})
    return {"trial_id":trial_id,"experiment":"E3","attempt_status":"success","artifact_path":record["artifact_path"],"artifact_sha256":digest,"runner_commit":provenance["runner_commit"],"runner_source_sha256":runner_source_hash()}

def run_population(run_id):
    root=RESULTS/run_id
    if root.exists(): raise E3Error(f"run exists: {root}")
    root.mkdir(parents=True)
    write_artifact(root/"run_manifest.json",{"run_id":run_id,"dataset_class":DATASET,"accepted_formal_result":False,"result_notice":NOTICE,"local_enumeration_is_formal_order":False,"notice":"LOCAL SYNTHETIC ENUMERATION IS NOT FORMAL DATA-COLLECTION ORDER."})
    for trial_id in registered_trial_ids(): run_exact_trial(trial_id,{"exact_trial_id":trial_id},root,SyntheticBackend())
    from e3_audit import audit_run
    report=audit_run(root); write_artifact(root/"audit.json",report)
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("--synthetic-validation",action="store_true",required=True); p.add_argument("--run-id",required=True); a=p.parse_args()
    result=run_population(a.run_id); print(json.dumps(result,indent=2,sort_keys=True)); raise SystemExit(result["status"]!="PASS")

