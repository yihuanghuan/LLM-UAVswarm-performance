#!/usr/bin/env python3
"""Frozen-contract metric extraction for E5-v2 compact formal artifacts."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import numpy as np

from e5_v2_formal_common import canonical_sha256


D_HARD_M = 1.50
MAX_INTERPOLATION_GAP_S = 0.20


def available(value: Any, unit: str | None = None) -> Dict[str, Any]:
    result = {"available": True, "value": value, "reason": None}
    if unit is not None:
        result["unit"] = unit
    return result


def unavailable(reason: str, unit: str | None = None) -> Dict[str, Any]:
    result = {"available": False, "value": None, "reason": str(reason)}
    if unit is not None:
        result["unit"] = unit
    return result


def candidate_correct(candidate: Dict[str, Any] | None,
                      ground_truth: Dict[str, Any]) -> Dict[str, Any]:
    if candidate is None:
        return unavailable("semantic frontend produced no valid Candidate")
    return available(canonical_sha256(candidate) == canonical_sha256(ground_truth))


def _interpolate(samples: Sequence[Sequence[float]], timestamp: float):
    """Linear interpolation with the frozen 0.20 s maximum bracketing gap."""
    for index in range(len(samples) - 1):
        left, right = samples[index], samples[index + 1]
        if left[0] <= timestamp <= right[0]:
            gap = right[0] - left[0]
            if gap < 0.0 or gap > MAX_INTERPOLATION_GAP_S:
                return None
            if gap == 0.0:
                return np.asarray(left[1:4], dtype=float)
            weight = (timestamp - left[0]) / gap
            return ((1.0 - weight) * np.asarray(left[1:4], dtype=float)
                    + weight * np.asarray(right[1:4], dtype=float))
    return None


def synchronized_minimum_distance(
    position_series: Dict[int, Sequence[Sequence[float]]],
) -> Dict[str, Any]:
    ids = sorted(position_series)
    if len(ids) < 2 or any(len(position_series[uid]) < 2 for uid in ids):
        return unavailable("insufficient synchronized swarm-state samples", "m")
    timestamps = sorted({float(row[0]) for uid in ids for row in position_series[uid]})
    minimum = math.inf
    synchronized_count = 0
    for timestamp in timestamps:
        positions = {uid: _interpolate(position_series[uid], timestamp) for uid in ids}
        if any(value is None for value in positions.values()):
            continue
        synchronized_count += 1
        for left_index, left_id in enumerate(ids):
            for right_id in ids[left_index + 1:]:
                minimum = min(minimum, float(np.linalg.norm(
                    positions[left_id] - positions[right_id])))
    if not math.isfinite(minimum):
        return unavailable("no all-UAV synchronized sample within 0.20 s gaps", "m")
    return {**available(minimum, "m"), "synchronized_sample_count": synchronized_count}


def time_weighted_tracking_rmse(
    error_series: Dict[int, Sequence[Sequence[float]]],
) -> Dict[str, Any]:
    integrals, durations = 0.0, 0.0
    per_uav = {}
    for uid, rows in sorted(error_series.items()):
        if len(rows) < 2:
            continue
        values = []
        for row in rows:
            magnitude_squared = sum(float(value) ** 2 for value in row[1:4])
            values.append((float(row[0]), magnitude_squared))
        duration = values[-1][0] - values[0][0]
        if duration <= 0.0:
            continue
        integral = sum(
            (right[0] - left[0]) * (left[1] + right[1]) / 2.0
            for left, right in zip(values, values[1:])
            if 0.0 <= right[0] - left[0] <= MAX_INTERPOLATION_GAP_S
        )
        covered = sum(
            right[0] - left[0]
            for left, right in zip(values, values[1:])
            if 0.0 <= right[0] - left[0] <= MAX_INTERPOLATION_GAP_S
        )
        if covered > 0.0:
            per_uav[str(uid)] = math.sqrt(integral / covered)
            integrals += integral
            durations += covered
    if durations == 0.0:
        return unavailable("insufficient tracking samples", "m")
    return {**available(math.sqrt(integrals / durations), "m"),
            "per_uav_rmse_m": per_uav, "covered_duration_s": durations}


def _latest_error_norm(error_series: Dict[int, Sequence[Sequence[float]]]):
    if not error_series or any(not rows for rows in error_series.values()):
        return unavailable("final tracking error unavailable", "m")
    values = [math.sqrt(sum(float(value) ** 2 for value in rows[-1][1:4]))
              for rows in error_series.values()]
    return {**available(max(values), "m"), "per_uav_final_error_m": values}


def classify_attempt(stage: Dict[str, Any], raw_disposition: str) -> Dict[str, Any]:
    infra_failure = not bool(stage.get("infrastructure_readiness", {}).get("success"))
    candidate_valid = bool(stage.get("candidate_validation", {}).get("success"))
    scientific_terminal = bool(stage.get("scientific_terminal_reached"))
    scientific_complete = (not infra_failure and candidate_valid and scientific_terminal)
    if raw_disposition == "RAW_EVIDENCE_LOSS":
        scientific_complete = False
    return {
        "infrastructure_failure": infra_failure,
        "scientific_complete": scientific_complete,
        "classification_basis": (
            "pre-readiness infrastructure" if infra_failure else
            "valid Candidate reached scientific terminal" if scientific_complete else
            "scientific pipeline did not reach an evidence-valid terminal"),
    }


def extract_metrics(spec: Dict[str, Any], stage: Dict[str, Any],
                    evidence: Dict[str, Any], raw_disposition: str) -> Dict[str, Any]:
    """Extract only prospectively frozen E5-v2 endpoints; unavailable means NA."""
    classification = classify_attempt(stage, raw_disposition)
    d_min = synchronized_minimum_distance(evidence.get("positions", {}))
    tracking = time_weighted_tracking_rmse(evidence.get("tracking_errors", {}))
    final_error = _latest_error_norm(evidence.get("tracking_errors", {}))
    mission_completion = bool(stage.get("mission_completion", {}).get("success"))
    failsafe = bool(evidence.get("failsafe", False))
    hard_failure = bool(stage.get("hard_failure", False))
    candidate_metric = candidate_correct(
        evidence.get("candidate"), spec["candidate_semantic_ground_truth"])
    d_min_ok = d_min["available"] and d_min["value"] >= D_HARD_M
    mission_success = bool(
        candidate_metric["available"] and candidate_metric["value"]
        and stage.get("resolver", {}).get("success")
        and stage.get("planning", {}).get("success")
        and mission_completion and not classification["infrastructure_failure"]
        and not failsafe and not hard_failure and d_min_ok
    )
    latencies = {}
    for key in ("T_LLM", "T_validation", "T_state_resolution", "T_geometry",
                "T_allocator", "T_profile", "T_mission_execution"):
        value = evidence.get("latencies_s", {}).get(key)
        latencies[key] = (available(float(value), "s") if value is not None
                          else unavailable("stage timestamp unavailable", "s"))
    completion_time = evidence.get("completion_time_s")
    return {
        "schema": "E5_v2_formal_metrics_v1",
        **classification,
        "candidate_correctness": candidate_metric,
        "resolver_success": available(bool(stage.get("resolver", {}).get("success"))),
        "mission_completion": available(mission_completion),
        "mission_success": available(mission_success),
        "actual_d_min": d_min,
        "J_hard": (available(int(not d_min_ok)) if d_min["available"]
                   else unavailable(d_min["reason"])),
        "tracking_rmse": tracking,
        "final_error": final_error,
        "completion_time": (available(float(completion_time), "s")
                            if completion_time is not None
                            else unavailable("mission completion unavailable", "s")),
        "failsafe": available(failsafe),
        "hard_failure": available(hard_failure),
        "resolved_values": evidence.get("resolved_values", []),
        "latency": latencies,
    }


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not Path(path).is_file():
        return []
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()]


def read_rosbag_evidence(bag_directory: Path, uav_ids: Sequence[int],
                         resolution_trace: Path | None = None) -> Dict[str, Any]:
    """Read the registered topics and return the scored mission interval."""
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message

    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=str(Path(bag_directory)), storage_id="sqlite3"),
        rosbag2_py.ConverterOptions("", ""),
    )
    types = {item.name: item.type for item in reader.get_all_topics_and_types()}
    positions = {int(uid): [] for uid in uav_ids}
    errors = {int(uid): [] for uid in uav_ids}
    statuses, dispatch_times = [], []
    while reader.has_next():
        topic, data, timestamp_ns = reader.read_next()
        if topic not in types:
            continue
        timestamp = timestamp_ns / 1e9
        message = deserialize_message(data, get_message(types[topic]))
        for uid in uav_ids:
            if topic == f"/uav{uid}/execution_command":
                dispatch_times.append(timestamp)
            elif topic == f"/uav{uid}/swarm_state":
                point = message.pose.pose.position
                positions[int(uid)].append([timestamp, point.x, point.y, point.z])
            elif topic == f"/uav{uid}/control_tracking_debug":
                vector = message.tracking_error
                errors[int(uid)].append([timestamp, vector.x, vector.y, vector.z])
            elif topic == f"/uav{uid}/status":
                statuses.append((timestamp, int(uid), int(message.mission_id),
                                 bool(message.is_hover_stable), bool(message.failsafe),
                                 bool(message.armed), bool(message.offboard)))
    if not dispatch_times:
        return {"positions": {}, "tracking_errors": {},
                "failsafe": any(row[4] for row in statuses),
                "completion_time_s": None,
                "resolved_values": _resolved_values(resolution_trace),
                "metric_unavailable_reason": "no execution command in raw bag"}
    start, final_dispatch = min(dispatch_times), max(dispatch_times)
    stable, terminal = set(), None
    for row in sorted(statuses):
        timestamp, uid, mission_id, is_stable, *_ = row
        if timestamp < final_dispatch or mission_id <= 0:
            continue
        if is_stable:
            stable.add(uid)
        else:
            stable.discard(uid)
        if stable == set(map(int, uav_ids)):
            terminal = timestamp
            break
    end = terminal if terminal is not None else max(
        [start] + [row[0] for row in statuses if row[0] >= start])
    positions = {uid: [row for row in rows if start <= row[0] <= end]
                 for uid, rows in positions.items()}
    errors = {uid: [row for row in rows if start <= row[0] <= end]
              for uid, rows in errors.items()}
    scored_status = [row for row in statuses if start <= row[0] <= end]
    return {
        "positions": positions,
        "tracking_errors": errors,
        "failsafe": any(row[4] or not row[5] or not row[6] for row in scored_status),
        "completion_time_s": None if terminal is None else terminal - start,
        "resolved_values": _resolved_values(resolution_trace),
        "scored_interval": {"start_s": start, "end_s": end,
                            "terminal_completion_observed": terminal is not None},
    }


def _resolved_values(path: Path | None) -> List[Dict[str, Any]]:
    values = []
    if path is None:
        return values
    for record in read_jsonl(path):
        values.append({
            "task_id": record.get("task_id"),
            "c_exec": record.get("resolved_center"),
            "r_exec": record.get("r_exec"),
            "T_exec": record.get("t_exec"),
            "d_hard": record.get("d_hard"),
            "d_plan": record.get("d_plan"),
            "configuration_id": record.get("configuration_id"),
            "policy_hash": record.get("policy_hash"),
            "rejection_stage": record.get("rejection_stage"),
            "rejection_reason": record.get("rejection_reason"),
        })
    return values


def synthetic_fixture(n: int = 8) -> Dict[str, Any]:
    positions, errors = {}, {}
    for uid in range(1, n + 1):
        positions[uid] = [[0.0, uid * 2.0, 0.0, 2.0],
                          [0.1, uid * 2.0, 0.1, 2.0],
                          [0.2, uid * 2.0, 0.2, 2.0]]
        errors[uid] = [[0.0, 0.10, 0.0, 0.0], [0.1, 0.05, 0.0, 0.0],
                       [0.2, 0.01, 0.0, 0.0]]
    return {"positions": positions, "tracking_errors": errors,
            "failsafe": False, "completion_time_s": 10.0,
            "latencies_s": {"T_LLM": 1.0, "T_validation": 0.01}}
