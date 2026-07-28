#!/usr/bin/env python3
"""Deterministic metrics used by the experiment 08 analysis pipeline."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence

import numpy as np


@dataclass(frozen=True)
class PairMetrics:
    uav_a: int
    uav_b: int
    minimum_distance: float
    collision_event_count: int
    violation_sample_count: int
    violation_event_count: int
    risk_exposure_time: float
    risk_integral: float


def read_csv(path: Path, required: Iterable[str]) -> List[Dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or [])
        missing = set(required) - fields
        if missing:
            raise ValueError(f"{path} missing fields: {sorted(missing)}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"{path} has no rows")
    return rows


def finite_float(value: object, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite, got {value}")
    return result


def event_count(mask: Sequence[bool]) -> int:
    values = np.asarray(mask, dtype=bool)
    if values.size == 0:
        return 0
    return int(values[0]) + int(np.count_nonzero(values[1:] & ~values[:-1]))


def integrate_mask(time: np.ndarray, mask: np.ndarray) -> float:
    if len(time) < 2:
        return 0.0
    return float(np.sum(np.diff(time) * mask[:-1].astype(float)))


def risk_integral(
    time: Sequence[float], distance: Sequence[float], threshold: float
) -> float:
    time_np = np.asarray(time, dtype=float)
    distance_np = np.asarray(distance, dtype=float)
    if len(time_np) != len(distance_np):
        raise ValueError("time and distance lengths differ")
    risk = np.maximum(0.0, threshold - distance_np) ** 2
    return float(np.trapz(risk, time_np)) if len(time_np) > 1 else 0.0


def resample_odometry(
    rows: Sequence[Mapping[str, object]],
    sample_hz: float,
    max_gap: float,
) -> tuple[np.ndarray, Dict[int, np.ndarray]]:
    if sample_hz <= 0.0 or max_gap <= 0.0:
        raise ValueError("sample_hz and max_gap must be positive")
    by_uav: Dict[int, List[tuple[float, float, float, float]]] = {}
    for row_number, row in enumerate(rows, start=2):
        timestamp = finite_float(row["timestamp"], f"timestamp row {row_number}")
        uav_id_value = finite_float(row["uav_id"], f"uav_id row {row_number}")
        if not uav_id_value.is_integer():
            raise ValueError("uav_id must be an integer")
        values = (
            timestamp,
            finite_float(row["x"], "x"),
            finite_float(row["y"], "y"),
            finite_float(row["z"], "z"),
        )
        by_uav.setdefault(int(uav_id_value), []).append(values)
    if len(by_uav) < 2:
        raise ValueError("at least two UAVs are required")

    prepared: Dict[int, np.ndarray] = {}
    for uav_id, samples in by_uav.items():
        data = np.asarray(sorted(samples), dtype=float)
        unique_time, unique_index = np.unique(data[:, 0], return_index=True)
        data = data[unique_index]
        if len(data) < 2:
            raise ValueError(f"UAV {uav_id} has fewer than two samples")
        gaps = np.diff(unique_time)
        if np.any(gaps > max_gap + 1e-12):
            raise ValueError(
                f"UAV {uav_id} odometry gap {gaps.max():.6f}s exceeds {max_gap}s"
            )
        prepared[uav_id] = data

    start = max(data[0, 0] for data in prepared.values())
    end = min(data[-1, 0] for data in prepared.values())
    if end <= start:
        raise ValueError("UAV odometry has no overlapping time interval")
    step = 1.0 / sample_hz
    timeline = np.arange(start, end + step * 0.25, step)
    if len(timeline) < 2:
        raise ValueError("overlapping interval is too short")
    positions = {
        uav_id: np.column_stack([
            np.interp(timeline, data[:, 0], data[:, axis])
            for axis in (1, 2, 3)
        ])
        for uav_id, data in prepared.items()
    }
    return timeline, positions


def pair_metrics(
    timeline: np.ndarray,
    positions: Mapping[int, np.ndarray],
    d_collision: float,
    d_violation: float,
) -> tuple[List[PairMetrics], Dict[tuple[int, int], np.ndarray]]:
    if not 0.0 < d_collision < d_violation:
        raise ValueError("thresholds must satisfy 0 < d_collision < d_violation")
    results: List[PairMetrics] = []
    distances: Dict[tuple[int, int], np.ndarray] = {}
    for uav_a, uav_b in combinations(sorted(positions), 2):
        series = np.linalg.norm(positions[uav_a] - positions[uav_b], axis=1)
        if not np.all(np.isfinite(series)):
            raise ValueError("non-finite pairwise distance")
        collision = series < d_collision
        violation = series < d_violation
        distances[(uav_a, uav_b)] = series
        results.append(PairMetrics(
            uav_a=uav_a,
            uav_b=uav_b,
            minimum_distance=float(series.min()),
            collision_event_count=event_count(collision),
            violation_sample_count=int(np.count_nonzero(violation)),
            violation_event_count=event_count(violation),
            risk_exposure_time=integrate_mask(timeline, violation),
            risk_integral=risk_integral(timeline, series, d_violation),
        ))
    return results, distances


def debug_metrics(rows: Sequence[Mapping[str, object]]) -> Dict[str, float | int]:
    if not rows:
        return {
            "iapf_activation_time": 0.0,
            "iapf_activation_ratio": 0.0,
            "mean_repulsion_norm": 0.0,
            "max_repulsion_norm": 0.0,
            "position_saturation_ratio": 0.0,
            "acceleration_saturation_ratio": 0.0,
            "peak_acceleration_setpoint": 0.0,
            "integrated_squared_acceleration": 0.0,
        }
    by_time: Dict[float, List[Mapping[str, object]]] = {}
    raw_norms: List[float] = []
    acceleration_norms: Dict[float, List[float]] = {}
    for row in rows:
        timestamp = finite_float(row["timestamp"], "debug timestamp")
        by_time.setdefault(timestamp, []).append(row)
        raw_norm = math.sqrt(sum(
            finite_float(row[f"raw_repulsion_{axis}"], "raw repulsion") ** 2
            for axis in "xyz"))
        if str(row["iapf_active"]).lower() in ("1", "true"):
            raw_norms.append(raw_norm)
        acceleration_norms.setdefault(timestamp, []).append(math.sqrt(sum(
            finite_float(row[f"modulated_acceleration_{axis}"], "acceleration") ** 2
            for axis in "xyz")))
    times = np.asarray(sorted(by_time), dtype=float)
    active = np.asarray([
        any(str(row["iapf_active"]).lower() in ("1", "true")
            for row in by_time[timestamp])
        for timestamp in times
    ])
    activation_time = integrate_mask(times, active)
    mission_time = float(times[-1] - times[0]) if len(times) > 1 else 0.0
    position_saturated = sum(
        str(row["position_saturated"]).lower() in ("1", "true")
        for row in rows)
    acceleration_saturated = sum(
        str(row["acceleration_saturated"]).lower() in ("1", "true")
        for row in rows)
    accel_time = np.asarray(sorted(acceleration_norms), dtype=float)
    accel_series = np.asarray([
        max(acceleration_norms[timestamp]) for timestamp in accel_time
    ])
    return {
        "iapf_activation_time": activation_time,
        "iapf_activation_ratio": (
            activation_time / mission_time if mission_time > 0.0 else 0.0),
        "mean_repulsion_norm": (
            float(np.mean(raw_norms)) if raw_norms else 0.0),
        "max_repulsion_norm": max(raw_norms, default=0.0),
        "position_saturation_ratio": position_saturated / len(rows),
        "acceleration_saturation_ratio": acceleration_saturated / len(rows),
        "peak_acceleration_setpoint": (
            float(accel_series.max()) if len(accel_series) else 0.0),
        "integrated_squared_acceleration": (
            float(np.trapz(accel_series ** 2, accel_time))
            if len(accel_time) > 1 else 0.0),
    }


def trajectory_metrics(
    timeline: np.ndarray,
    positions: Mapping[int, np.ndarray],
    debug_rows: Sequence[Mapping[str, object]],
) -> Dict[str, float]:
    deviations: List[float] = []
    actual_path = 0.0
    nominal_path = 0.0
    for position in positions.values():
        actual_path += float(np.linalg.norm(np.diff(position, axis=0), axis=1).sum())
    by_uav: Dict[int, List[Mapping[str, object]]] = {}
    for row in debug_rows:
        by_uav.setdefault(int(row["uav_id"]), []).append(row)
    for uav_id, rows in by_uav.items():
        if uav_id not in positions:
            continue
        rows = sorted(rows, key=lambda row: float(row["timestamp"]))
        debug_time = np.asarray([float(row["timestamp"]) for row in rows])
        nominal = np.asarray([
            [float(row[f"nominal_ref_{axis}"]) for axis in "xyz"]
            for row in rows])
        mask = (debug_time >= timeline[0]) & (debug_time <= timeline[-1])
        debug_time = debug_time[mask]
        nominal = nominal[mask]
        if len(debug_time) < 2:
            continue
        actual = np.column_stack([
            np.interp(debug_time, timeline, positions[uav_id][:, axis])
            for axis in range(3)])
        deviations.extend(np.linalg.norm(actual - nominal, axis=1).tolist())
        nominal_path += float(
            np.linalg.norm(np.diff(nominal, axis=0), axis=1).sum())
    return {
        "mean_trajectory_deviation": (
            float(np.mean(deviations)) if deviations else math.nan),
        "max_trajectory_deviation": max(deviations, default=math.nan),
        "actual_path_length": actual_path,
        "nominal_path_length": nominal_path,
        "path_length_ratio": (
            actual_path / nominal_path if nominal_path > 0.0 else math.nan),
    }


def outcome_metrics(
    trial_dir: Path,
    timeline: np.ndarray,
    positions: Mapping[int, np.ndarray],
    debug_rows: Sequence[Mapping[str, object]],
    final_tolerance: float,
    stall_distance: float,
    stall_speed: float,
    stall_duration: float,
) -> Dict[str, float | int]:
    assignment_rows = read_csv(
        trial_dir / "assignment.csv",
        {"uav_id", "target_x", "target_y", "target_z"})
    targets = {
        int(row["uav_id"]): np.asarray([
            float(row["target_x"]), float(row["target_y"]),
            float(row["target_z"])])
        for row in assignment_rows
    }
    final_errors = {
        uav_id: float(np.linalg.norm(position[-1] - targets[uav_id]))
        for uav_id, position in positions.items()
    }
    stall_events = 0
    for uav_id, position in positions.items():
        speed = np.linalg.norm(
            np.gradient(position, timeline, axis=0), axis=1)
        target_distance = np.linalg.norm(position - targets[uav_id], axis=1)
        condition = (target_distance > stall_distance) & (speed < stall_speed)
        minimum_samples = max(
            1, int(math.ceil(stall_duration / np.median(np.diff(timeline)))))
        start = 0
        while start < len(condition):
            if not condition[start]:
                start += 1
                continue
            end = start
            while end < len(condition) and condition[end]:
                end += 1
            if end - start >= minimum_samples:
                stall_events += 1
            start = end

    recovery = 0.0
    active_times = [
        float(row["timestamp"]) for row in debug_rows
        if str(row["iapf_active"]).lower() in ("1", "true")]
    if active_times:
        event_path = trial_dir / "mission_events.csv"
        recovery = math.nan
        if event_path.is_file():
            events = read_csv(event_path, {"timestamp", "event", "uav_id"})
            last_active = max(active_times)
            stable_by_uav: Dict[int, float] = {}
            for row in events:
                if row["event"] == "hover_stable":
                    timestamp = float(row["timestamp"])
                    if timestamp >= last_active:
                        stable_by_uav[int(row["uav_id"])] = timestamp
            if set(stable_by_uav) >= set(positions):
                recovery = max(stable_by_uav.values()) - last_active
    return {
        "recovery_time": recovery,
        "stall_event_count": stall_events,
        "safe_completion_ratio": (
            sum(error <= final_tolerance for error in final_errors.values())
            / len(final_errors)),
        "final_formation_error": float(np.mean(list(final_errors.values()))),
    }


def analyze_trial(trial_dir: Path) -> tuple[List[PairMetrics], Dict[str, object]]:
    metadata_path = trial_dir / "run_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    thresholds = metadata["safety_thresholds"]
    analysis = metadata["analysis"]
    odom_rows = read_csv(
        trial_dir / "odom.csv", {"timestamp", "uav_id", "x", "y", "z"})
    timeline, positions = resample_odometry(
        odom_rows, float(analysis["sample_hz"]), float(analysis["max_odom_gap"]))
    pairs, distance_series = pair_metrics(
        timeline, positions, float(thresholds["d_collision"]),
        float(thresholds["d_violation"]))
    debug_path = trial_dir / "iapf_debug.csv"
    debug_rows = read_csv(debug_path, {
        "timestamp", "uav_id", "iapf_active",
        "raw_repulsion_x", "raw_repulsion_y", "raw_repulsion_z",
        "position_saturated", "acceleration_saturated",
        "nominal_ref_x", "nominal_ref_y", "nominal_ref_z",
        "modulated_acceleration_x", "modulated_acceleration_y",
        "modulated_acceleration_z",
    }) if debug_path.is_file() and debug_path.stat().st_size else []
    closest = min(pairs, key=lambda pair: pair.minimum_distance)
    min_over_time = np.min(np.stack(list(distance_series.values())), axis=0)
    summary: Dict[str, object] = {
        "experiment_id": metadata["experiment_id"],
        "batch_id": metadata["batch_id"],
        "phase": metadata.get("phase", "unspecified"),
        "scenario": metadata["scenario"],
        "method": metadata["method"],
        "trial": metadata["trial"],
        "seed": metadata["seed"],
        "minimum_inter_agent_distance": closest.minimum_distance,
        "mean_min_distance": float(min_over_time.mean()),
        "closest_pair": f"{closest.uav_a}-{closest.uav_b}",
        "collision_event_count": sum(
            pair.collision_event_count for pair in pairs),
        "violation_sample_count": sum(
            pair.violation_sample_count for pair in pairs),
        "violation_event_count": sum(
            pair.violation_event_count for pair in pairs),
        "risk_exposure_time": sum(
            pair.risk_exposure_time for pair in pairs),
        "risk_integral": sum(pair.risk_integral for pair in pairs),
    }
    summary.update(debug_metrics(debug_rows))
    summary.update(trajectory_metrics(timeline, positions, debug_rows))
    summary.update(outcome_metrics(
        trial_dir, timeline, positions, debug_rows,
        float(analysis.get("final_position_tolerance", 0.30)),
        float(analysis.get("stall_distance", 0.50)),
        float(analysis.get("stall_speed", 0.15)),
        float(analysis.get("stall_duration", 2.0))))
    outcome = metadata.get("outcome", {})
    summary["mission_success"] = bool(
        summary["collision_event_count"] == 0 and outcome.get("hover_stable", False)
        and not outcome.get("timed_out", False)
        and not outcome.get("px4_failsafe", False)
        and not outcome.get("node_crash", False)
        and summary["safe_completion_ratio"] == 1.0)
    if summary["mission_success"]:
        summary["failure_reason"] = "none"
    elif summary["collision_event_count"]:
        summary["failure_reason"] = "collision"
    elif summary["stall_event_count"] and outcome.get(
            "failure_reason") in ("unknown", "timeout"):
        summary["failure_reason"] = "stall"
    else:
        summary["failure_reason"] = outcome.get("failure_reason", "unknown")
    return pairs, summary


def write_dict_rows(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    if not rows:
        raise ValueError("cannot write an empty CSV")
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: List[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
