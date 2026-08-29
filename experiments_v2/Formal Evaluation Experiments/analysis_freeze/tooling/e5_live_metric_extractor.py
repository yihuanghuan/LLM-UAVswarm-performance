#!/usr/bin/env python3
"""Authoritative E5 end-to-end live-data attempt extractor."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from analysis_common import (EvidenceError, clip_series, file_inventory, metric_na,
                             metric_value)
from attempt_context import FORMAL_ROOT, result_envelope, terminal_classification, validate_attempt
from live_metric_helpers import (iapf_burden, pairwise_distance_metrics,
                                 swarm_position_series, tracking_rmse)
from rosbag_evidence import read_bag, records_for


RELEVANT = ("/execution_command", "/swarm_state", "/control_tracking_debug",
            "/iapf_debug", "/status", "/startup_event")


def authoritative_scenario(scenario_id: str) -> dict[str, Any]:
    registry = yaml.safe_load((FORMAL_ROOT / "E5/e5_end_to_end_registry_v1.yaml").read_text())
    matches = [item for item in registry["scenarios"] if item["scenario_id"] == scenario_id]
    if len(matches) != 1:
        raise EvidenceError(f"E5 registered scenario not uniquely found: {scenario_id}")
    return matches[0]


def terminal_contract(scenario: dict[str, Any]) -> tuple[set[int], dict[int, list[int]], float]:
    nodes = scenario["candidate_semantic_ground_truth"]["mission"]["nodes"]
    terminal = nodes[-1]
    if terminal["type"] == "task":
        tasks = [terminal["task"]]
    elif terminal["type"] == "parallel" and terminal.get("completion_mode") == "synchronized":
        tasks = terminal["tasks"]
    else:
        raise EvidenceError("unsupported or non-registered E5 terminal graph semantics")
    task_uavs = {int(task["task_id"]): [int(x) for x in task["U"]] for task in tasks}
    waits = []
    for task in tasks:
        q = task.get("q", {"mode": "direct"})
        waits.append(float(q.get("duration", 0.0)) if q.get("mode") == "hover-and-wait" else 0.0)
    if len(set(waits)) > 1:
        raise EvidenceError("synchronized terminal tasks have inconsistent registered waits")
    return set(task_uavs), task_uavs, waits[0]


def derive_physical_interval(records: list[Any], scenario: dict[str, Any]) -> dict[str, Any]:
    commands = records_for(records, "/execution_command")
    if not commands:
        return {"complete": False, "reason": "no physical execution-command publication"}
    mission_ids = sorted(set(int(record.message.mission_id) for record in commands))
    if len(mission_ids) != 1:
        raise EvidenceError("E5 attempt has ambiguous mission IDs")
    mission_id = mission_ids[0]
    start = min(record.timestamp for record in commands)
    terminal_task_ids, task_uavs, wait_s = terminal_contract(scenario)
    terminal_commands = [record for record in commands if int(record.message.task_id) in terminal_task_ids]
    required_uavs = sorted({uav for values in task_uavs.values() for uav in values})
    if {int(record.message.uav_id) for record in terminal_commands} != set(required_uavs):
        return {"complete": False, "reason": "terminal dispatch command set incomplete", "mission_id": mission_id,
                "start": start}
    terminal_dispatch = min(record.timestamp for record in terminal_commands)
    stable_entries = {}
    for uav_id in required_uavs:
        candidates = [record.timestamp for record in records_for(records, "/status", mission_id=mission_id, uav_id=uav_id)
                      if record.timestamp >= terminal_dispatch and bool(record.message.is_hover_stable)]
        if not candidates:
            return {"complete": False, "reason": f"terminal stable completion absent for UAV {uav_id}",
                    "mission_id": mission_id, "start": start}
        stable_entries[uav_id] = min(candidates)
    stable_group_end = max(stable_entries.values())
    end = stable_group_end + wait_s
    targets = {int(record.message.uav_id): [float(record.message.target_pos.x),
                                           float(record.message.target_pos.y),
                                           float(record.message.target_pos.z)]
               for record in terminal_commands}
    return {"complete": True, "mission_id": mission_id, "start": float(start), "end": float(end),
            "duration_s": float(end - start), "terminal_dispatch": float(terminal_dispatch),
            "terminal_task_ids": sorted(terminal_task_ids), "terminal_required_uav_ids": required_uavs,
            "stable_entry_by_uav": {str(k): v for k, v in stable_entries.items()},
            "registered_terminal_wait_s": wait_s, "final_targets": targets,
            "basis": "first execution-command through graph-derived synchronized terminal stable completion and wait"}


def _latencies(language: dict[str, Any], physical_complete: bool) -> dict[str, Any]:
    raw = language.get("latency_decomposition_s", {})
    mapping = {
        "llm_inference": "LLM_inference", "parse_validation": "parse_validation",
        "snapshot_wait": "snapshot_wait", "resolution": "resolution", "allocation": "allocation",
        "dispatch": "dispatch",
    }
    output = {}
    for metric, key in mapping.items():
        value = raw.get(key)
        output[metric] = metric_value(float(value), unit="s", semantics="stage service time") \
            if value is not None and float(value) >= 0.0 else metric_na("registered stage duration unavailable")
    if physical_complete and raw.get("physical_execution") is not None:
        output["physical_execution"] = metric_value(float(raw["physical_execution"]), unit="s",
            semantics="terminal completion minus first execution-command")
    else:
        output["physical_execution"] = metric_na("registered terminal mission completion absent")
    output["latency_components_additive"] = metric_value(False,
        note="stage service times may overlap physical mission wall clock")
    output["command_to_terminal_wall_clock"] = metric_na(
        "language-command submission timestamp is not retained as an authoritative absolute timestamp")
    return output


def extract(attempt_dir: Path, *, raw_inventory: dict[str, str] | None = None) -> dict[str, Any]:
    attempt_dir = Path(attempt_dir).resolve()
    manifest, spec, dependencies = validate_attempt(attempt_dir, "E5")
    scenario = authoritative_scenario(spec["scenario_id"])
    language_path = attempt_dir / "raw/language_result.json"
    language = json.loads(language_path.read_text()) if language_path.is_file() else {}
    metrics: dict[str, Any] = {
        "provider_status": metric_value(language.get("attempt_status") not in (None, "provider_failure"),
            provider_attempts=language.get("provider_request_attempts_logged"),
            frozen_command_retry_count=language.get("counts", {}).get("formal_command_retry"),
            error=language.get("error")),
        "parsing_resolution_status": metric_value(language.get("candidate_completed") is True,
            attempt_status=language.get("attempt_status"), failure_stage=language.get("failure_stage"),
            mission_termination=language.get("mission_termination")),
    }
    coverage: dict[str, Any] = {}
    bag_present = (attempt_dir / "raw/rosbag/metadata.yaml").is_file()
    records = read_bag(attempt_dir / "raw/rosbag", lambda topic: topic.endswith(RELEVANT)) if bag_present else []
    physical = derive_physical_interval(records, scenario) if records else {
        "complete": False, "reason": "rosbag absent"}
    interval = ({key: value for key, value in physical.items() if key not in ("complete", "final_targets")}
                if physical.get("complete") else None)
    metrics["latency_decomposition"] = _latencies(language, bool(physical.get("complete")))
    if physical.get("complete"):
        start, end, mission_id = float(physical["start"]), float(physical["end"]), int(physical["mission_id"])
        uav_ids = list(range(1, 9))
        distance, distance_cov = pairwise_distance_metrics(records, uav_ids, start, end)
        metrics.update(distance); coverage.update(distance_cov)
        tracking, tracking_cov = tracking_rmse(records, uav_ids, mission_id, start, end)
        metrics["tracking_RMSE"] = metric_value(tracking["swarm_equal_uav_pooled_rmse_m"], unit="m",
            per_uav=tracking["per_uav_m"], mean_diagnostic=tracking["mean_per_uav_rmse_m"],
            max_diagnostic=tracking["max_per_uav_rmse_m"], aggregation="equal-UAV pooled RMS")
        coverage["tracking_error"] = tracking_cov
        burden, burden_cov = iapf_burden(records, uav_ids, mission_id, start, end, aggregate="sum")
        metrics["iapf_activation_burden"] = metric_value(burden["swarm"]["activation_time_s"],
            unit="UAV-seconds", per_uav=burden["per_uav"], per_uav_mean=burden["per_uav_mean"])
        metrics["integral_delta_p_burden"] = metric_value(burden["swarm"]["integral_delta_p_m_s"],
            unit="m*s", per_uav=burden["per_uav"], per_uav_mean=burden["per_uav_mean"])
        metrics["integral_delta_a_burden"] = metric_value(burden["swarm"]["integral_delta_a_mps"],
            unit="m/s", per_uav=burden["per_uav"], per_uav_mean=burden["per_uav_mean"])
        coverage["iapf"] = burden_cov
        positions = swarm_position_series(records, uav_ids)
        errors = {}
        final_cov = {}
        for uav_id in uav_ids:
            clipped, cov = clip_series(positions[uav_id], start, end)
            target = np.asarray(physical["final_targets"][uav_id], dtype=float)
            errors[str(uav_id)] = float(np.linalg.norm(clipped.value[-1] - target))
            final_cov[str(uav_id)] = cov
        metrics["final_error"] = metric_value(float(np.mean(list(errors.values()))), unit="m",
            per_uav=errors, max_diagnostic=max(errors.values()), aggregation="mean per-UAV at terminal completion")
        coverage["final_position"] = final_cov
        status_records = records_for(records, "/status", mission_id=mission_id)
        hard_failure = any(bool(record.message.failsafe) for record in status_records)
        d_min = float(metrics["actual_d_min"]["value"])
        within_timeout = (end - start) <= float(spec["mission_timeout_s"])
        method_completed = language.get("attempt_status") == "success" and language.get("candidate_completed") is True
        success = method_completed and not hard_failure and d_min >= 1.5 and within_timeout
        metrics["mission_success"] = metric_value(success, denominator="all retained attempts",
            components={"registered_terminal_completion": True, "method_completed": method_completed,
                        "no_hard_failure": not hard_failure, "actual_d_min_at_least_d_hard": d_min >= 1.5,
                        "within_registered_timeout": within_timeout})
        analysis_status = "COMPLETE"
    else:
        reason = physical.get("reason", "registered terminal mission completion absent")
        for name in ("actual_d_min", "tracking_RMSE", "iapf_activation_burden",
                     "integral_delta_p_burden", "integral_delta_a_burden", "final_error"):
            metrics[name] = metric_na(reason)
        metrics["mission_success"] = metric_value(False, denominator="all retained attempts",
            components={"registered_terminal_completion": False,
                        "method_completed": language.get("attempt_status") == "success"})
        if records:
            commands = records_for(records, "/execution_command")
            if commands:
                last = max(record.timestamp for record in records)
                metrics["partial_physical_execution"] = {
                    "valid": False, "value": None, "reason": reason,
                    "partial_observed_value": last - min(r.timestamp for r in commands),
                    "partial_reason": reason}
        analysis_status = "PARTIAL_VALID_METRICS"
        coverage["physical_interval"] = physical
    return result_envelope(attempt_dir, "E5", Path(__file__), manifest, dependencies,
        scored_interval=interval, terminal_classification=terminal_classification(manifest),
        analysis_status=analysis_status, metrics=metrics, source_coverage=coverage,
        raw_inventory=raw_inventory if raw_inventory is not None else file_inventory(attempt_dir))


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("attempt_dir", type=Path); parser.add_argument("--output", type=Path)
    args = parser.parse_args(); result = extract(args.attempt_dir)
    text = json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
    if args.output: args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(text)
    else: print(text, end="")
    return 0


if __name__ == "__main__": raise SystemExit(main())
