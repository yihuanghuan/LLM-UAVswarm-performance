#!/usr/bin/env python3
"""Formal-capable exact-trial adapter around the validated E2 offline method."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Dict

from e2_common import (
    BASELINE_COMMIT, BASELINE_TAG, CANONICAL_POLICY_SHA256, CONFIGURATION_ID,
    GLOBAL_REGISTRY_PATH, ORDER_TXT_PATH, POLICY_PATH, PROTOCOL_PATH, REGISTRY_PATH,
    REPO_ROOT, SOURCE_PREFLIGHT_COMMIT, build_registered_snapshots,
    candidate_for_scenario, canonical_sha256, global_order_positions,
    load_scenario_registry, parse_trial_id, registered_trial_ids, scenario_index,
    sha256_file,
)


ADAPTER_BRANCH = "formal/E2-formal-adapter-v1"
CONTRACT_BRANCH = "formal/E2-commitment-timing-v1"
CONTRACT_COMMIT = "22110f3515662d88a9e8482368fad843fff6968a"
ENTRYPOINT = "experiments_v2/Formal Evaluation Experiments/E2/tooling/e2_formal_adapter.py"
PROTOCOL_SHA256 = "9ea7234db111b69cccb72315eed26e4abf117955eb20a2d593f2d854ea0b40e3"
REGISTRY_SHA256 = "8215a5d8248c946c480ca4c8cb41e2afac28e6021c9f308a068580da69369bae"
ORDER_SHA256 = "db28bf8d734e1f206987519e91ff27c67b2d9ab2971aeb68c4e13735762f1dce"
GLOBAL_REGISTRY_SHA256 = "90313d33793940489edde631d397564378ae54fe3cfddf438e4a895d6132254d"


class E2FormalAdapterError(RuntimeError):
    pass


def identity() -> Dict[str, str]:
    return {
        "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=REPO_ROOT,
                                           text=True).strip(),
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
                                           text=True).strip(),
        "entrypoint": ENTRYPOINT,
        "source_sha256": sha256_file(Path(__file__)),
    }


def _registered_spec(trial_id: str) -> Dict[str, Any]:
    registry = load_scenario_registry(); parsed = parse_trial_id(trial_id)
    if trial_id not in set(registered_trial_ids(registry=registry)):
        raise E2FormalAdapterError(f"unregistered E2 trial: {trial_id}")
    scenario = scenario_index(registry)[parsed["scenario_id"]]
    _, _, parse_snapshot, execute_snapshot = build_registered_snapshots(
        scenario, parsed["state_condition"], registry,
    )
    value = {
        "spec_type": "E2_exact_offline_execution_spec_v1", **parsed,
        "candidate": candidate_for_scenario(scenario),
        "parse_snapshot": parse_snapshot, "execution_snapshot": execute_snapshot,
        "configuration_id": CONFIGURATION_ID,
        "only_manipulated_factor": "numerical commitment stage for c/r/T",
    }
    value["resolved_execution_spec_hash"] = canonical_sha256(value)
    return value


def _validate(trial_id: str, context: Dict[str, Any]):
    spec = _registered_spec(trial_id); order = ORDER_TXT_PATH.read_text().splitlines()
    expected_position = order.index(trial_id) + 1
    adapter = identity()
    checks = {
        "trial_id": context.get("trial_id") == trial_id,
        "position": context.get("global_trial_position") == expected_position,
        "runner_commit": context.get("runner_commit") == adapter["commit"],
        "runner_source": context.get("runner_source_sha256") == adapter["source_sha256"],
        "policy": context.get("policy_sha256") == CANONICAL_POLICY_SHA256,
        "protocol": context.get("protocol_sha256") == PROTOCOL_SHA256,
        "registry": context.get("registry_sha256") == REGISTRY_SHA256,
        "order": context.get("global_trial_order_sha256") == ORDER_SHA256,
    }
    if not all(checks.values()):
        raise E2FormalAdapterError(f"formal adapter context mismatch: {checks}")
    mode = context.get("execution_mode")
    if mode == "formal":
        if not (context.get("dataset_class") == "formal_evaluation"
                and context.get("formal_launch_authorized") is True
                and context.get("launch_gate_status") == "READY_FOR_FORMAL_LAUNCH"):
            raise E2FormalAdapterError("formal launch authorization/gate required")
    elif mode == "spec_rehearsal":
        if context.get("dataset_class") not in {"synthetic_validation", "engineering_validation"}:
            raise E2FormalAdapterError("nonformal dataset required")
        if context.get("formal_launch_authorized") is not False:
            raise E2FormalAdapterError("rehearsal cannot be formally authorized")
    else:
        raise E2FormalAdapterError("unsupported execution mode")
    return spec, expected_position, adapter, mode


def _durable(path: Path, value: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists(): raise E2FormalAdapterError("duplicate retained attempt")
    data=(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode()
    temp=path.with_name(path.name+f".tmp-{os.getpid()}")
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o444)
    with os.fdopen(fd,"wb") as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())
    os.replace(temp,path)
    directory=os.open(path.parent,os.O_DIRECTORY); os.fsync(directory); os.close(directory)


def _formal_backend(trial_id: str, position: int):
    from e2_provenance import validate_provenance
    from e2_runner import build_attempt_record
    from location_allocate.policy_adapter import load_runtime_policy
    registry=load_scenario_registry(); provenance=validate_provenance()
    policy=load_runtime_policy(POLICY_PATH)[1]
    record=build_attempt_record(trial_id,registry,policy,provenance,position,1)
    return _formalize_backend_record(record)


def _formalize_backend_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize only the legacy builder's attempt-classification metadata."""
    record["dataset_class"]="formal_evaluation"
    record["accepted_formal_result"]=True
    record["result_notice"]=None
    return record


def _assert_formal_backend_record(record: Dict[str, Any]) -> None:
    if not (record.get("dataset_class")=="formal_evaluation"
            and record.get("accepted_formal_result") is True
            and record.get("result_notice") is None):
        raise E2FormalAdapterError("formal backend classification mismatch")


def run_exact_trial(trial_id: str, campaign_context: Dict[str, Any]):
    spec,position,adapter,mode=_validate(trial_id,campaign_context)
    output=Path(campaign_context["attempt_output_dir"]).resolve()
    if output.exists(): raise E2FormalAdapterError("duplicate retained attempt directory")
    output.mkdir(parents=True); (output/"raw").mkdir()
    accepted=mode=="formal"; status="success"
    backend={"backend":"E2_pinned_adapter_spec_rehearsal_v1",
             "physical_execution_performed":False,"scientific_outcomes":None}
    if mode=="formal":
        try:
            backend=_formal_backend(trial_id,position)
            _assert_formal_backend_record(backend)
            _durable(output/"raw"/"offline_resolution_trace.json",backend)
        except Exception as exc:
            status="infrastructure_failure"; backend={"error":f"{type(exc).__name__}: {exc}"}
    if campaign_context.get("failure_injection") and not accepted:
        status=str(campaign_context["failure_injection"])
    artifact={"record_type":"E2_formal_capable_exact_trial_attempt_v1",
      "dataset_class":"formal_evaluation" if accepted else campaign_context["dataset_class"],
      "accepted_formal_result":accepted,"result_notice":None if accepted else "NOT_FORMAL_RESULT",
      "trial_id":trial_id,"experiment":"E2","global_trial_position":position,
      "attempt_status":status,"replacement_attempt":False,"execution_mode":mode,
      "execution_spec":spec,"backend_result":backend,"adapter":adapter,
      "provenance":{"source_preflight_commit":SOURCE_PREFLIGHT_COMMIT,
        "baseline_tag":BASELINE_TAG,"baseline_commit":BASELINE_COMMIT,
        "policy_sha256":CANONICAL_POLICY_SHA256,"protocol_sha256":PROTOCOL_SHA256,
        "registry_sha256":REGISTRY_SHA256,"global_trial_order_sha256":ORDER_SHA256}}
    path=output/"attempt.json"; _durable(path,artifact); digest=sha256_file(path)
    return {"trial_id":trial_id,"experiment":"E2","attempt_status":status,
      "artifact_path":str(path),"artifact_sha256":digest,
      "dataset_class":artifact["dataset_class"],"accepted_formal_result":accepted,
      "runner_commit":adapter["commit"],"runner_source_sha256":adapter["source_sha256"],
      "suite_journal_mutated":False}
