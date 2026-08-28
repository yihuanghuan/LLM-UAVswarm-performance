#!/usr/bin/env python3
"""Run one registered formal-equivalent trial without campaign authority."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import traceback
from typing import Any, Dict, Iterable

import yaml


HERE = Path(__file__).resolve()
DEMO_ROOT = HERE.parents[1]
HOST_REPO = HERE.parents[4]
WORKSPACE = HOST_REPO.parent
MATRIX_PATH = DEMO_ROOT / "demo_matrix_v1.json"
CAMPAIGN_ROOT = WORKSPACE / "global_campaign_launch/experiments_v2/Formal Evaluation Experiments/campaign/results/formal"
CAMPAIGN_BASELINE = DEMO_ROOT / "campaign_v1_integrity_baseline.json"
NOTICE = "NOT_FORMAL_RESULT"

FAMILIES = {
    "E2": (WORKSPACE / "e2_adapter_worktree", "experiments_v2/Formal Evaluation Experiments/E2/tooling"),
    "E3": (WORKSPACE / "e3_adapter_worktree", "experiments_v2/Formal Evaluation Experiments/E3/tooling"),
    "E4A": (WORKSPACE / "e4a_adapter_worktree", "experiments_v2/Formal Evaluation Experiments/E4/tooling_e4a"),
    "E4B": (WORKSPACE / "e4b_adapter_worktree", "experiments_v2/Formal Evaluation Experiments/E4/tooling_e4b"),
    "E5": (WORKSPACE / "e5_adapter_worktree", "experiments_v2/Formal Evaluation Experiments/E5/tooling"),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_exclusive(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise RuntimeError(f"refusing to overwrite retained artifact: {path}")
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
    with temporary.open("xb") as stream:
        stream.write(canonical(value))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def campaign_snapshot() -> Dict[str, Any]:
    files = {}
    for path in sorted(item for item in CAMPAIGN_ROOT.rglob("*") if item.is_file()):
        files[path.relative_to(CAMPAIGN_ROOT).as_posix()] = sha256_file(path)
    journal = sorted((CAMPAIGN_ROOT / "suite-journal").glob("*.json"))
    records = [json.loads(path.read_text()) for path in journal]
    accepted = sum(item.get("accepted_formal_result") is True for item in records)
    checks = {
        "journal_exactly_1_and_2": [path.name for path in journal] == [
            "000001-attempt.json", "000002-attempt.json"
        ],
        "accepted_formal_attempt_count_is_2": accepted == 2,
        "no_000003_anywhere": not any("000003" in path for path in files),
        "launcher_commit_unchanged": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=WORKSPACE / "global_campaign_launch", text=True,
        ).strip() == "8c532288c8b5c47a20da954caad4f717cdc92ddb",
    }
    return {
        "snapshot_type": "Campaign_v1_byte_integrity_v1",
        "captured_utc": utc_now(),
        "campaign_root": str(CAMPAIGN_ROOT),
        "checks": checks,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "journal_record_count": len(records),
        "accepted_formal_attempt_count": accepted,
        "files": files,
        "files_manifest_sha256": hashlib.sha256(canonical(files)).hexdigest(),
        "launcher_manifest_sha256": files.get("launcher_run_manifest.json"),
    }


def initialize_campaign_guard() -> Dict[str, Any]:
    snapshot = campaign_snapshot()
    if snapshot["status"] != "PASS":
        raise RuntimeError(f"Campaign v1 baseline is not intact: {snapshot['checks']}")
    write_exclusive(CAMPAIGN_BASELINE, snapshot)
    return snapshot


def assert_campaign_guard() -> Dict[str, Any]:
    if not CAMPAIGN_BASELINE.exists():
        raise RuntimeError("Campaign v1 baseline has not been initialized")
    baseline = json.loads(CAMPAIGN_BASELINE.read_text())
    current = campaign_snapshot()
    if current["status"] != "PASS" or current["files"] != baseline["files"]:
        raise RuntimeError("CRITICAL: Campaign v1 changed after demo baseline capture")
    return current


def matrix() -> Dict[str, Any]:
    return json.loads(MATRIX_PATH.read_text())


def git_identity(repo: Path) -> Dict[str, str]:
    return {
        "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=repo, text=True).strip(),
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
        "status_porcelain": subprocess.check_output(["git", "status", "--short"], cwd=repo, text=True),
    }


def _activate(family: str) -> Path:
    repo, relative = FAMILIES[family]
    tooling = repo / relative
    for value in (tooling, repo / "location_allocate", repo / "lfs_policy"):
        sys.path.insert(0, str(value))
    os.chdir(repo)
    return repo


def _run_e2(trial_id: str, raw: Path) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    from e2_formal_adapter import _registered_spec
    from e2_common import POLICY_PATH, global_order_positions, load_scenario_registry
    from e2_provenance import validate_provenance
    from e2_runner import build_attempt_record
    from location_allocate.policy_adapter import load_runtime_policy
    spec = _registered_spec(trial_id)
    provenance = validate_provenance()
    backend = build_attempt_record(
        trial_id, load_scenario_registry(), load_runtime_policy(POLICY_PATH)[1],
        provenance, global_order_positions()[trial_id], 1,
    )
    write_exclusive(raw / "offline_resolution_trace.json", backend)
    return spec, backend, provenance


def _run_live(family: str, trial_id: str, raw: Path) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    if family == "E3":
        from e3_trial_registry import build_exact_spec
        from e3_formal_backend import execute_registered_trial
        from e3_formal_adapter import adapter_identity
        spec = build_exact_spec(trial_id)
        static = {"status": "PASS", "adapter_identity": adapter_identity()}
    elif family == "E4A":
        from e4a_trial_registry import build_exact_spec
        from e4a_formal_backend import execute_registered_trial
        from e4a_provenance import validate
        spec = build_exact_spec(trial_id); static = validate()
    elif family == "E4B":
        from e4b_trial_registry import build_exact_spec
        from e4b_formal_backend import execute_registered_trial
        from e4b_provenance import validate
        spec = build_exact_spec(trial_id); static = validate()
    elif family == "E5":
        from e5_trial_registry import build_exact_spec
        from e5_formal_backend import execute_registered_trial
        from e5_provenance import validate
        spec = build_exact_spec(trial_id); static = validate()
    else:
        raise ValueError(family)
    if static.get("status") != "PASS":
        raise RuntimeError(f"static provenance failed: {static}")
    spec = dict(spec)
    spec["dataset_class"] = "engineering_validation"
    backend = execute_registered_trial(spec, raw)
    return spec, backend, static


def bag_counts(raw: Path) -> Dict[str, int]:
    metadata = raw / "rosbag/metadata.yaml"
    if not metadata.exists():
        return {}
    value = yaml.safe_load(metadata.read_text()) or {}
    topics = value.get("rosbag2_bagfile_information", {}).get("topics_with_message_count", [])
    return {item["topic_metadata"]["name"]: int(item["message_count"]) for item in topics}


def _all_topics(counts: Dict[str, int], ids: Iterable[int], template: str,
                minimum: int = 1) -> bool:
    return all(counts.get(template.format(uid=uid), 0) >= minimum for uid in ids)


def _evidence(name: str, produced: bool, source: str, timestamp: str,
              support: bool | None = None, notes: str | None = None) -> Dict[str, Any]:
    return {
        "required_raw_field": name,
        "produced": bool(produced),
        "authoritative_source": source,
        "timestamp_basis": timestamp,
        "supports_deterministic_metric_extraction": bool(produced if support is None else support),
        "notes": notes,
    }


def raw_audit(family: str, spec: Dict[str, Any], raw: Path) -> Dict[str, Any]:
    counts = bag_counts(raw)
    ids = [int(value) for value in spec.get("uav_ids", [1, 2, 3, 4])]
    fields = []
    if family == "E2":
        trace = raw / "offline_resolution_trace.json"
        for name in ("parse-time availability and state reference", "execution snapshot epoch and state",
                     "Candidate and Executable c/r/T", "correction and rejection reason",
                     "configuration ID and policy hash"):
            fields.append(_evidence(name, trace.exists(), "offline_resolution_trace.json",
                                    "registered snapshot epochs / deterministic offline trace"))
    elif family == "E3":
        disturbance = spec["disturbance"]
        affected = [int(value) for value in disturbance["affected_uavs"]]
        wrench_ok = (raw / "wrench.log").exists() and (
            not affected or all(counts.get(f"/e3_force/mavlink_{uid + 1}/wrench", 0) > 0 for uid in affected)
        )
        fields = [
            _evidence("clock", counts.get("/clock", 0) > 0, "rosbag:/clock", "ROS simulation time"),
            _evidence("execution_command_t0", _all_topics(counts, ids, "/uav{uid}/execution_command", 2), "rosbag execution commands + phase results", "ROS header stamp and retained monotonic t0"),
            _evidence("per_uav_position_3d", _all_topics(counts, ids, "/px4_{uid}/fmu/out/vehicle_odometry"), "rosbag PX4 vehicle_odometry", "PX4/ROS message stamp"),
            _evidence("per_uav_nominal_reference", _all_topics(counts, ids, "/uav{uid}/control_tracking_debug"), "rosbag ControlTrackingDebug.nominal_position", "ROS header stamp"),
            _evidence("per_uav_safe_reference", _all_topics(counts, ids, "/uav{uid}/control_tracking_debug"), "rosbag ControlTrackingDebug.safe_position", "ROS header stamp"),
            _evidence("iapf_active", _all_topics(counts, ids, "/uav{uid}/iapf_debug"), "rosbag IAPFDebug.iapf_active", "ROS header stamp"),
            _evidence("iapf_delta_p", _all_topics(counts, ids, "/uav{uid}/iapf_debug"), "rosbag IAPFDebug.position_offset", "ROS header stamp"),
            _evidence("iapf_delta_a", _all_topics(counts, ids, "/uav{uid}/iapf_debug"), "rosbag IAPFDebug.acceleration_offset", "ROS header stamp"),
            _evidence("allocator_prediction", (raw / "runtime_spec.json").exists(), "runtime_spec allocator metrics", "pre-dispatch deterministic resolution"),
            _evidence("completion_events", _all_topics(counts, ids, "/uav{uid}/startup_event"), "rosbag StartupEvent + phase results", "ROS header stamp"),
            _evidence("hard_failures", _all_topics(counts, ids, "/uav{uid}/status"), "rosbag UAVStatus failsafe/startup state", "ROS header stamp"),
            _evidence("wrench_commands", wrench_ok, "wrench.log and registered wrench rosbag topics", "ROS /clock after disturbance arm", notes="zero-disturbance trials are evidenced by empty affected_uavs plus retained driver log"),
        ]
    elif family == "E4A":
        tracking = _all_topics(counts, ids, "/uav{uid}/control_tracking_debug")
        fields = [
            _evidence("clock", counts.get("/clock", 0) > 0, "rosbag:/clock", "ROS simulation time"),
            _evidence("commanded_ladrc_acceleration_3d", tracking, "rosbag ControlTrackingDebug.ladrc_output", "ROS header stamp"),
            _evidence("safe_reference_position_3d", tracking, "rosbag ControlTrackingDebug.safe_position", "ROS header stamp"),
            _evidence("measured_position_3d", tracking, "rosbag ControlTrackingDebug.actual_position", "ROS header stamp"),
            _evidence("trajectory_completion", _all_topics(counts, ids, "/uav{uid}/trajectory_metrics"), "rosbag TrajectoryMetrics.is_finished", "ROS header stamp"),
            _evidence("stable_hover_entry", _all_topics(counts, ids, "/uav{uid}/status"), "rosbag UAVStatus stability_state", "ROS header stamp"),
        ]
    elif family == "E4B":
        runtime_path = raw / "runtime_spec.json"
        runtime = json.loads(runtime_path.read_text()) if runtime_path.exists() else {}
        iapf = _all_topics(counts, ids, "/uav{uid}/iapf_debug")
        mapping = {
            "requested_T": bool(runtime.get("requested_T")),
            "T_min_terms_v_a_j": runtime.get("timing_feasibility_evidence") is not None or spec["scenario_id"] == "E4B-SAFETY-ACTIVE",
            "T_exec": "duration_s" in runtime,
            "assignment_mode": "assignment_mode" in runtime,
            "avoidance_mode": "avoidance_mode" in runtime,
            "d_hard": "d_hard" in runtime.get("resolved_safety", {}),
            "d_plan": "d_plan" in runtime.get("resolved_safety", {}),
            "safety_mapping": bool(runtime.get("authority_evidence", {}).get("safety_contract")),
            "execution_profile_limits": bool(runtime.get("profiles")),
            "omega_limits": bool(runtime.get("profiles")),
            "controller_saturation_predicate": iapf,
            "iapf_events": iapf,
            "assignment_trace": bool(runtime.get("allocator_diagnostics")),
            "authority_decision_trace": bool(runtime.get("authority_evidence", {}).get("deterministic_checks")),
        }
        fields = [_evidence(name, value,
                            "runtime_spec.json" if name not in {"controller_saturation_predicate", "iapf_events"} else "rosbag IAPFDebug saturation/event fields",
                            "pre-dispatch deterministic trace" if name not in {"controller_saturation_predicate", "iapf_events"} else "ROS header stamp")
                  for name, value in mapping.items()]
    elif family == "E5":
        tracking = _all_topics(counts, ids, "/uav{uid}/control_tracking_debug")
        iapf = _all_topics(counts, ids, "/uav{uid}/iapf_debug")
        resolution = raw / "ros_home/candidate_resolution_trace.jsonl"
        language_path = raw / "language_result.json"
        language = json.loads(language_path.read_text()) if language_path.exists() else {}
        method_terminated_before_dispatch = (
            language.get("attempt_status") == "method_failure"
            and language.get("mission_termination") == "frozen_method_rejection"
            and bool(language.get("failure_stage"))
        )
        dispatch_topics = _all_topics(counts, ids, "/uav{uid}/execution_command")
        completion_topics = _all_topics(counts, ids, "/uav{uid}/trajectory_metrics")
        dispatch_source = (
            "language_result.json retained zero-dispatch method termination"
            if method_terminated_before_dispatch else "rosbag UAVExecutionCommand"
        )
        completion_source = (
            "language_result.json retained pre-dispatch mission termination"
            if method_terminated_before_dispatch else "rosbag TrajectoryMetrics + UAVStatus"
        )
        fields = [
            _evidence("raw_llm_request_response_metadata", (raw / "llm_raw_responses.append.jsonl").exists() and (raw / "llm_raw_responses.append.jsonl").stat().st_size > 0, "provider append log", "provider wall timestamp/latency"),
            _evidence("candidate_validation", (raw / "validated_candidate.json").exists(), "validated_candidate.json", "post-provider parse/validation"),
            _evidence("state_snapshots", _all_topics(counts, ids, "/uav{uid}/swarm_state") and resolution.exists(), "rosbag SwarmState + resolution trace snapshot timestamps", "ROS/source/receive timestamps"),
            _evidence("resolution_trace", resolution.exists() and resolution.stat().st_size > 0, "candidate_resolution_trace.jsonl", "snapshot epoch"),
            _evidence("assignment_trace", resolution.exists() and resolution.stat().st_size > 0, "candidate_resolution_trace.jsonl assignment metrics", "pre-dispatch snapshot epoch"),
            _evidence("dispatch_events", dispatch_topics or method_terminated_before_dispatch, dispatch_source, "ROS header stamp or retained method-termination wall timestamp", notes="zero dispatch is expected only for an explicitly classified pre-dispatch frozen-method rejection" if method_terminated_before_dispatch else None),
            _evidence("task_completion_events", completion_topics or method_terminated_before_dispatch, completion_source, "ROS header stamp or retained method-termination wall timestamp", notes="pre-dispatch method termination is the terminal event" if method_terminated_before_dispatch else None),
            _evidence("per_uav_measured_position_3d", tracking, "rosbag ControlTrackingDebug.actual_position", "ROS header stamp"),
            _evidence("nominal_reference", tracking, "rosbag ControlTrackingDebug.nominal_position", "ROS header stamp"),
            _evidence("safe_reference", tracking, "rosbag ControlTrackingDebug.safe_position", "ROS header stamp"),
            _evidence("iapf_active", iapf, "rosbag IAPFDebug.iapf_active", "ROS header stamp"),
            _evidence("iapf_delta_p", iapf, "rosbag IAPFDebug.position_offset", "ROS header stamp"),
            _evidence("iapf_delta_a", iapf, "rosbag IAPFDebug.acceleration_offset", "ROS header stamp"),
            _evidence("hard_failures", _all_topics(counts, ids, "/uav{uid}/status"), "rosbag UAVStatus failsafe/startup state", "ROS header stamp"),
            _evidence("px4_readiness", (raw / "readiness.log").exists() and _all_topics(counts, ids, "/px4_{uid}/fmu/out/vehicle_status"), "readiness log + rosbag PX4 VehicleStatus", "ROS/PX4 timestamps"),
        ]
    complete = bool(fields) and all(item["produced"] and item["supports_deterministic_metric_extraction"] for item in fields)
    return {
        "sealed_raw_requirement_count": len(fields),
        "complete": complete,
        "rosbag_metadata_present": (raw / "rosbag/metadata.yaml").exists() if family != "E2" else None,
        "rosbag_topic_message_counts": counts,
        "requirements": fields,
    }


def orphan_snapshot() -> Dict[str, Any]:
    patterns = ("MicroXRCEAgent", "gzserver", "gzclient", "ladrc_position_controller_node",
                "/build/px4_sitl_default/bin/px4", "ros2 bag record")
    completed = subprocess.run(["ps", "-eo", "pid=,ppid=,stat=,args="], text=True, capture_output=True)
    matches = [line.strip() for line in completed.stdout.splitlines()
               if any(pattern in line for pattern in patterns)
               and "runtime_demo.py" not in line]
    return {"status": "PASS" if not matches else "FAIL", "matching_processes": matches}


def scientific_classification(family: str, spec: Dict[str, Any], backend: Dict[str, Any],
                              raw: Path) -> Dict[str, Any]:
    if family == "E2":
        return {"classification": "frozen_offline_method_outcome", "metric_flags": backend.get("metric_flags")}
    if family == "E4B" and spec.get("scenario_id") == "E4B-INFEASIBLE-EXPLICIT-T":
        runtime_path = raw / "runtime_spec.json"
        runtime = json.loads(runtime_path.read_text()) if runtime_path.exists() else {}
        t_exec, t_min = runtime.get("duration_s"), runtime.get("T_min_s")
        return {"classification": "expected_frozen_feasibility_correction",
                "T_exec_s": t_exec, "T_min_s": t_min,
                "correction_contract_pass": t_exec is not None and t_min is not None and t_exec >= t_min}
    if family == "E5" and (raw / "language_result.json").exists():
        language = json.loads((raw / "language_result.json").read_text())
        if language.get("attempt_status") == "method_failure":
            return {
                "classification": "frozen_method_failure",
                "failure_stage": language.get("failure_stage"),
                "termination": language.get("mission_termination"),
                "reason": language.get("error"),
            }
    return {"classification": "not_scored_analysis_freeze_pending",
            "backend_terminal_status": backend.get("attempt_status")}


def run_demo(entry: Dict[str, Any]) -> Dict[str, Any]:
    assert_campaign_guard()
    family = entry["family"]
    repo = _activate(family)
    output = DEMO_ROOT / family / entry["demo_instance_id"]
    output.mkdir(parents=True, exist_ok=False)
    raw = output / "raw"; raw.mkdir()
    started = utc_now(); spec = {}; backend = {}; static = {}
    exception = None
    try:
        if family == "E2":
            spec, backend, static = _run_e2(entry["trial_id"], raw)
        else:
            spec, backend, static = _run_live(family, entry["trial_id"], raw)
    except Exception as exc:
        exception = {"type": type(exc).__name__, "message": str(exc),
                     "traceback": traceback.format_exc()}
        backend = backend or {"attempt_status": "infrastructure_failure", "error": str(exc)}
    audit = raw_audit(family, spec, raw) if spec else {"complete": False, "requirements": [], "error": "spec unavailable"}
    runtime_provenance_path = raw / "runtime_provenance.json"
    runtime_provenance = json.loads(runtime_provenance_path.read_text()) if runtime_provenance_path.exists() else None
    orphan = orphan_snapshot()
    campaign_after = assert_campaign_guard()
    backend_status = backend.get("attempt_status", "success" if family == "E2" and exception is None else "infrastructure_failure")
    provenance_pass = static.get("status") == "PASS" and (
        family == "E2" or runtime_provenance is not None and runtime_provenance.get("status") == "PASS"
    )
    infrastructure_pass = (
        exception is None and backend_status == "success" and audit["complete"]
        and provenance_pass and orphan["status"] == "PASS"
    )
    manifest = {
        "manifest_type": "formal_equivalent_runtime_demo_v1",
        "demo_instance_id": entry["demo_instance_id"],
        "registered_trial_id": entry["trial_id"],
        "family": family,
        "runtime_class": entry["runtime_class"],
        "matrix_role": entry.get("matrix_role", "primary"),
        "rerun_of": entry.get("rerun_of"),
        "rerun_reason": entry.get("rerun_reason"),
        "dataset_class": "engineering_validation",
        "accepted_formal_result": False,
        "result_notice": NOTICE,
        "formal_cursor_consumed": False,
        "campaign_attempt_envelope_created": False,
        "formal_suite_journal_mutated": False,
        "execution_mode": "formal_equivalent_live_backend" if family != "E2" else "formal_equivalent_offline_backend",
        "same_backend_as_formal_adapter": True,
        "physical_execution_performed": family != "E2" and (raw / "physical_result.json").exists(),
        "cold_start": family != "E2",
        "started_utc": started,
        "finished_utc": utc_now(),
        "source_worktree": str(repo),
        "source_identity": git_identity(repo),
        "execution_spec": spec,
        "static_provenance": static,
        "runtime_provenance": runtime_provenance,
        "backend_result": backend,
        "raw_evidence_audit": audit,
        "process_cleanup": orphan,
        "infrastructure_status": "PASS" if infrastructure_pass else "FAIL",
        "scientific_outcome": scientific_classification(family, spec, backend, raw),
        "exception": exception,
        "campaign_v1_postcheck": {
            "status": campaign_after["status"],
            "files_manifest_sha256": campaign_after["files_manifest_sha256"],
            "accepted_formal_attempt_count": campaign_after["accepted_formal_attempt_count"],
        },
    }
    write_exclusive(output / "demo_manifest.json", manifest)
    return manifest


def _artifact_inventory(demo_directory: Path) -> Dict[str, Any]:
    files = []
    for path in sorted(item for item in demo_directory.rglob("*") if item.is_file()):
        relative = path.relative_to(DEMO_ROOT).as_posix()
        files.append({"path": relative, "size_bytes": path.stat().st_size,
                      "sha256": sha256_file(path)})
    return {
        "artifact_count": len(files),
        "rosbag_paths": [item for item in files if "/raw/rosbag/" in item["path"]],
        "log_paths": [item for item in files if item["path"].endswith(".log")],
        "all_artifacts": files,
        "inventory_sha256": hashlib.sha256(canonical(files)).hexdigest(),
    }


def _discovery_summary(manifest: Dict[str, Any]) -> Dict[str, Any]:
    dynamic = (manifest.get("runtime_provenance") or {}).get("dynamic_runtime_checks", {})
    selected = {
        str(uid): observation.get("selected_observation_sequence")
        for uid, observation in dynamic.items()
        if isinstance(observation, dict) and "selected_observation_sequence" in observation
    }
    bounds = {
        str(uid): observation.get("stabilization_bounds")
        for uid, observation in dynamic.items()
        if isinstance(observation, dict) and observation.get("stabilization_bounds")
    }
    return {
        "selected_observation_sequence_by_controller": selected,
        "maximum_selected_observation_sequence": max(selected.values(), default=None),
        "stabilization_bounds_by_controller": bounds,
    }


def _completion_record(entry: Dict[str, Any], manifest: Dict[str, Any],
                       manifest_path: Path) -> Dict[str, Any]:
    spec = manifest.get("execution_spec", {})
    runtime_provenance = manifest.get("runtime_provenance") or {}
    return {
        "family": entry["family"],
        "registered_trial_id": entry["trial_id"],
        "demo_instance_id": entry["demo_instance_id"],
        "matrix_role": entry.get("matrix_role", "primary"),
        "rerun_of": entry.get("rerun_of"),
        "rerun_reason": entry.get("rerun_reason"),
        "runtime_class": entry["runtime_class"],
        "scenario": spec.get("scenario_id"),
        "condition_or_style": spec.get("condition", spec.get("style")),
        "seed": spec.get("seed"),
        "authoritative_identity": {
            "E3_protocol_version": entry.get("protocol_version"),
            "E3_protocol_sha256": (
                "2eea03e2bb33aa1c10c1ae104b965f909690f00c8caee4446291faf2c9893013"
                if entry["family"] == "E3" else None
            ),
            "E3_registry_sha256": (
                "b56344c6cd257e99851523d640d9a89d6def994884877e2303d8fab836e0faf2"
                if entry["family"] == "E3" else None
            ),
            "registered_input_hash": spec.get("registered_input_hash"),
            "resolved_execution_spec_hash": spec.get("resolved_execution_spec_hash"),
        },
        "adapter_tooling_identity": manifest.get("source_identity"),
        "frozen_policy": runtime_provenance.get("installed_policy"),
        "numeric_runtime_environment": {
            "python": platform.python_version(),
            "python_executable": sys.executable,
            "numpy": __import__("numpy").__version__,
            "scipy": __import__("scipy").__version__,
            "ros_distro": os.environ.get("ROS_DISTRO"),
        },
        "dataset_class": manifest.get("dataset_class"),
        "accepted_formal_result": manifest.get("accepted_formal_result"),
        "result_notice": manifest.get("result_notice"),
        "formal_cursor_consumed": manifest.get("formal_cursor_consumed"),
        "physical_execution_performed": manifest.get("physical_execution_performed"),
        "cold_start": manifest.get("cold_start"),
        "static_provenance_result": manifest.get("static_provenance", {}).get("status", "NOT_RECORDED"),
        "runtime_provenance_result": runtime_provenance.get(
            "status", "NOT_APPLICABLE" if entry["family"] == "E2" else "NOT_COMPLETED"
        ),
        "provenance_result": (
            manifest.get("static_provenance", {}).get("status", "NOT_RECORDED")
            if entry["family"] == "E2"
            else runtime_provenance.get("status", "NOT_COMPLETED")
        ),
        "infrastructure_status": manifest.get("infrastructure_status"),
        "scientific_outcome": manifest.get("scientific_outcome"),
        "raw_evidence_status": "COMPLETE" if manifest.get("raw_evidence_audit", {}).get("complete") else "INCOMPLETE",
        "raw_requirement_count": manifest.get("raw_evidence_audit", {}).get("sealed_raw_requirement_count"),
        "discovery": _discovery_summary(manifest),
        "teardown_status": manifest.get("process_cleanup", {}).get("status"),
        "manifest_path": manifest_path.relative_to(DEMO_ROOT).as_posix(),
        "manifest_sha256": sha256_file(manifest_path),
        "artifacts": _artifact_inventory(manifest_path.parent),
    }


def aggregate() -> Dict[str, Any]:
    plan = matrix()
    planned = plan["demos"]
    primary_planned = [item for item in planned if item.get("matrix_role", "primary") == "primary"]
    manifest_paths = sorted(DEMO_ROOT.glob("E*/**/demo_manifest.json"))
    all_by_id = {
        json.loads(path.read_text())["demo_instance_id"]: (json.loads(path.read_text()), path)
        for path in manifest_paths
    }
    plan_ids = {item["demo_instance_id"] for item in planned}
    missing = [item["demo_instance_id"] for item in planned if item["demo_instance_id"] not in all_by_id]
    records = [
        _completion_record(item, *all_by_id[item["demo_instance_id"]])
        for item in planned if item["demo_instance_id"] in all_by_id
    ]
    by_family = {}
    for family in FAMILIES:
        family_plan = [item for item in planned if item["family"] == family]
        family_primary = [item for item in family_plan if item.get("matrix_role", "primary") == "primary"]
        family_diagnostic = [item for item in family_plan if item.get("matrix_role") == "diagnostic_rerun"]
        selected = [item for item in records if item["family"] == family]
        selected_primary = [item for item in selected if item["matrix_role"] == "primary"]
        selected_diagnostic = [item for item in selected if item["matrix_role"] == "diagnostic_rerun"]
        resolved, unresolved = [], []
        for entry in family_primary:
            candidates = [item for item in selected if item["registered_trial_id"] == entry["trial_id"]]
            destination = resolved if any(
                item["infrastructure_status"] == "PASS"
                and item["raw_evidence_status"] == "COMPLETE"
                for item in candidates
            ) else unresolved
            destination.append(entry["trial_id"])
        selected_sequences = [
            sequence
            for item in selected if item["infrastructure_status"] == "PASS"
            for sequence in item["discovery"]["selected_observation_sequence_by_controller"].values()
        ]
        by_family[family] = {
            "planned_primary": len(family_primary),
            "primary_completed": len(selected_primary),
            "primary_infrastructure_pass": sum(item["infrastructure_status"] == "PASS" for item in selected_primary),
            "primary_infrastructure_fail_retained": sum(item["infrastructure_status"] != "PASS" for item in selected_primary),
            "diagnostic_reruns_planned": len(family_diagnostic),
            "diagnostic_reruns_completed": len(selected_diagnostic),
            "diagnostic_infrastructure_pass": sum(item["infrastructure_status"] == "PASS" for item in selected_diagnostic),
            "diagnostic_infrastructure_fail": sum(item["infrastructure_status"] != "PASS" for item in selected_diagnostic),
            "registered_paths_resolved": len(resolved),
            "resolved_trial_ids": resolved,
            "unresolved_trial_ids": unresolved,
            "cold_starts": sum(bool(item["cold_start"]) for item in selected),
            "raw_complete_attempts": sum(item["raw_evidence_status"] == "COMPLETE" for item in selected),
            "provenance_pass_attempts": sum(item["provenance_result"] == "PASS" for item in selected),
            "cleanup_pass_attempts": sum(item["teardown_status"] == "PASS" for item in selected),
            "discovery_selected_observation_histogram": {
                str(sequence): selected_sequences.count(sequence)
                for sequence in sorted(set(selected_sequences))
            },
            "maximum_discovery_selected_observation": max(selected_sequences, default=None),
            "demo_instance_ids": [item["demo_instance_id"] for item in selected],
        }
    current_phase = [item for item in primary_planned if item["family"] in {"E3", "E4A", "E4B", "E5"}]
    result = {
        "matrix_id": plan["matrix_id"],
        "generated_utc": utc_now(),
        "dataset_class": "engineering_validation",
        "accepted_formal_result": False,
        "result_notice": NOTICE,
        "formal_cursor_consumed": False,
        "planned_count": len(primary_planned),
        "current_phase_planned_primary_count": len(current_phase),
        "diagnostic_rerun_plan_count": len(planned) - len(primary_planned),
        "completed_planned_attempt_count": len(records),
        "missing_planned_demo_instance_ids": missing,
        "historical_evidence_excluded": sorted(set(all_by_id) - plan_ids),
        "by_family": by_family,
        "demo_records": records,
        "campaign_v1_integrity": assert_campaign_guard(),
    }
    target = DEMO_ROOT / "formal_equivalent_demo_matrix.json"
    temporary = target.with_suffix(".json.tmp")
    temporary.write_bytes(canonical(result)); os.replace(temporary, target)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--initialize-campaign-guard", action="store_true")
    group.add_argument("--run-instance")
    group.add_argument("--aggregate", action="store_true")
    group.add_argument("--show-plan", action="store_true")
    args = parser.parse_args()
    if args.initialize_campaign_guard:
        value = initialize_campaign_guard()
    elif args.show_plan:
        value = matrix()
    elif args.aggregate:
        value = aggregate()
    else:
        entries = [item for item in matrix()["demos"] if item["demo_instance_id"] == args.run_instance]
        if len(entries) != 1:
            raise SystemExit(f"unknown or duplicate demo instance: {args.run_instance}")
        value = run_demo(entries[0])
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0 if value.get("infrastructure_status", value.get("status", "PASS")) == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
