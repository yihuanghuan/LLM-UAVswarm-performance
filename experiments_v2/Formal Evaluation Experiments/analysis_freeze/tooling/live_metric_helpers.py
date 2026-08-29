#!/usr/bin/env python3
"""Signal extraction helpers shared by E3/E4/E5 live extractors."""

from __future__ import annotations

from itertools import combinations
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from analysis_common import (EvidenceError, Series, below_threshold_metrics, clip_series,
                             metric_na, metric_value, normalize_series, synchronized_grid,
                             time_weighted_rms, trapezoidal_integral, vector_norm,
                             zero_order_hold_duration)
from rosbag_evidence import BagRecord, point, records_for, vector


def command_time(records: Iterable[BagRecord], mission_id: int, *, first: bool = True,
                 task_ids: set[int] | None = None) -> float:
    commands = records_for(records, "/execution_command", mission_id=mission_id)
    if task_ids is not None:
        commands = [record for record in commands if int(record.message.task_id) in task_ids]
    if not commands:
        raise EvidenceError(f"no execution-command publication for mission {mission_id}")
    values = [record.timestamp for record in commands]
    return float(min(values) if first else max(values))


def swarm_position_series(records: Iterable[BagRecord], uav_ids: Iterable[int]) -> dict[int, Series]:
    output = {}
    for uav_id in uav_ids:
        subset = records_for(records, "/swarm_state", uav_id=uav_id)
        # nav_msgs/Odometry does not carry uav_id; identify it by topic.
        subset = [r for r in records if r.topic == f"/uav{uav_id}/swarm_state"]
        output[uav_id] = normalize_series(
            [r.timestamp for r in subset], [point(r.message.pose.pose.position) for r in subset])
    return output


def pairwise_distance_metrics(records: Iterable[BagRecord], uav_ids: list[int], start: float, end: float,
                              d_hard: float | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    series = swarm_position_series(records, uav_ids)
    grid, positions, coverage = synchronized_grid(series, start, end)
    distances: dict[str, np.ndarray] = {}
    minimum = math.inf
    minimum_pair = None
    minimum_time = None
    per_pair_minimum = {}
    for first, second in combinations(sorted(uav_ids), 2):
        key = f"{first}-{second}"
        values = np.linalg.norm(positions[first] - positions[second], axis=1)
        distances[key] = values
        index = int(np.argmin(values))
        value = float(values[index])
        per_pair_minimum[key] = {"distance_m": value, "timestamp": float(grid[index])}
        if value < minimum or (value == minimum and (minimum_pair is None or key < minimum_pair)):
            minimum, minimum_pair, minimum_time = value, key, float(grid[index])
    output = {
        "actual_d_min": metric_value(minimum, unit="m", pair=minimum_pair,
                                     timestamp=minimum_time, per_pair=per_pair_minimum),
    }
    if d_hard is not None:
        risk = below_threshold_metrics(grid, distances, d_hard)
        output.update({
            "hard_risk_event_count": metric_value(risk.pop("hard_risk_event_count"), threshold_m=d_hard),
            "hard_risk_exposure_duration": metric_value(
                risk.pop("hard_risk_exposure_duration"), unit="pair-seconds", threshold_m=d_hard),
            "any_pair_hard_risk_duration": metric_value(
                risk.pop("any_pair_hard_risk_duration"), unit="s", threshold_m=d_hard),
            "hard_risk_pair_diagnostics": risk["pair_diagnostics"],
        })
    return output, {"swarm_position": coverage, "synchronization_grid_sample_count": int(grid.size)}


def tracking_series(records: Iterable[BagRecord], uav_id: int, mission_id: int,
                    field: str) -> Series:
    # Include the immediately preceding sample so the publication-time t0 boundary
    # is bracketed before the controller callback changes mission_id.
    subset = records_for(records, "/control_tracking_debug", uav_id=uav_id)
    getter = point if field.endswith("position") else vector
    return normalize_series([r.timestamp for r in subset], [getter(getattr(r.message, field)) for r in subset])


def iapf_series(records: Iterable[BagRecord], uav_id: int, mission_id: int,
                field: str) -> Series:
    subset = records_for(records, "/iapf_debug", uav_id=uav_id)
    return normalize_series([r.timestamp for r in subset], [vector(getattr(r.message, field)) for r in subset])


def iapf_burden(records: Iterable[BagRecord], uav_ids: list[int], mission_id: int,
                start: float, end: float, *, aggregate: str) -> tuple[dict[str, Any], dict[str, Any]]:
    per_uav: dict[str, Any] = {}
    coverage: dict[str, Any] = {}
    for uav_id in uav_ids:
        debug = records_for(records, "/iapf_debug", uav_id=uav_id)
        active, active_cov = zero_order_hold_duration(
            [r.timestamp for r in debug], [bool(r.message.iapf_active) for r in debug], start, end)
        delta_p, p_cov = clip_series(iapf_series(records, uav_id, mission_id, "position_offset"), start, end)
        delta_a, a_cov = clip_series(iapf_series(records, uav_id, mission_id, "acceleration_offset"), start, end)
        per_uav[str(uav_id)] = {
            "activation_time_s": active,
            "integral_delta_p_m_s": trapezoidal_integral(delta_p.t, vector_norm(delta_p.value)),
            "integral_delta_a_mps": trapezoidal_integral(delta_a.t, vector_norm(delta_a.value)),
        }
        coverage[str(uav_id)] = {"iapf_active": active_cov, "delta_p": p_cov, "delta_a": a_cov}
    keys = ("activation_time_s", "integral_delta_p_m_s", "integral_delta_a_mps")
    reducer = np.sum if aggregate == "sum" else np.mean
    swarm = {key: float(reducer([values[key] for values in per_uav.values()])) for key in keys}
    means = {key: float(np.mean([values[key] for values in per_uav.values()])) for key in keys}
    return {"per_uav": per_uav, "swarm": swarm, "per_uav_mean": means,
            "aggregation": aggregate}, coverage


def deviation_metrics(records: Iterable[BagRecord], uav_ids: list[int], mission_id: int,
                      start: float, end: float) -> tuple[dict[str, Any], dict[str, Any]]:
    per_uav = {}; coverage = {}
    for uav_id in uav_ids:
        nominal, nom_cov = clip_series(tracking_series(records, uav_id, mission_id, "nominal_position"), start, end)
        safe, safe_cov = clip_series(tracking_series(records, uav_id, mission_id, "safe_position"), start, end)
        grid = np.unique(np.concatenate((nominal.t, safe.t)))
        from analysis_common import interpolate_series
        difference = interpolate_series(safe, grid) - interpolate_series(nominal, grid)
        magnitude = vector_norm(difference)
        per_uav[str(uav_id)] = {
            "integral_m_s": trapezoidal_integral(grid, magnitude),
            "rms_m": time_weighted_rms(grid, magnitude),
        }
        coverage[str(uav_id)] = {"nominal": nom_cov, "safe": safe_cov}
    return {
        "per_uav": per_uav,
        "swarm_sum_integral_m_s": float(sum(v["integral_m_s"] for v in per_uav.values())),
        "swarm_equal_uav_pooled_rms_m": math.sqrt(float(np.mean([v["rms_m"] ** 2 for v in per_uav.values()]))),
    }, coverage


def tracking_rmse(records: Iterable[BagRecord], uav_ids: list[int], mission_id: int,
                  start: float, end: float) -> tuple[dict[str, Any], dict[str, Any]]:
    per_uav = {}; coverage = {}
    for uav_id in uav_ids:
        subset = records_for(records, "/control_tracking_debug", uav_id=uav_id)
        error = normalize_series([r.timestamp for r in subset], [vector(r.message.tracking_error) for r in subset])
        clipped, cov = clip_series(error, start, end)
        per_uav[str(uav_id)] = time_weighted_rms(clipped.t, vector_norm(clipped.value))
        coverage[str(uav_id)] = cov
    values = list(per_uav.values())
    return {
        "per_uav_m": per_uav,
        "swarm_equal_uav_pooled_rmse_m": math.sqrt(float(np.mean(np.square(values)))),
        "mean_per_uav_rmse_m": float(np.mean(values)),
        "max_per_uav_rmse_m": float(np.max(values)),
    }, coverage
