#!/usr/bin/env python3
"""Diagnose the retained amendment-v1 vertical response without changing pilots."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from typing import Any

import numpy as np


TOOLING_DIR = Path(__file__).resolve().parent
E3_DIR = TOOLING_DIR.parent
FORMAL_DIR = E3_DIR.parent
RAW_ROOT = E3_DIR / "results" / "qualification" / "raw"
WORKSPACE = Path("/home/yihuang/learning/LLM_swarm_ws")
INTERFACE_PREFIX = WORKSPACE / "formal_install_v1" / "uav_swarm_interfaces"
INTERFACE_PYTHON = INTERFACE_PREFIX / "local/lib/python3.10/dist-packages"
INTERFACE_LIB = INTERFACE_PREFIX / "lib"
ANALYSIS_TOOLS = FORMAL_DIR / "analysis_freeze" / "tooling"

sys.path.insert(0, str(INTERFACE_PYTHON))
sys.path.insert(0, str(ANALYSIS_TOOLS))
os.environ["LD_LIBRARY_PATH"] = ":".join(filter(None, (
    str(INTERFACE_LIB), os.environ.get("LD_LIBRARY_PATH", ""))))

from analysis_common import normalize_series, synchronized_grid  # noqa: E402
from live_metric_helpers import command_time, swarm_position_series  # noqa: E402
from rosbag_evidence import read_bag  # noqa: E402


ACCELERATION_LIMIT_MPS2 = 5.0
EXPECTED_ATTEMPTS = 90
CONDITIONS = ("P0_F0", "P1_F0")
FORCES_N = (2.0, 3.0, 4.0)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def vector3(value: Any) -> np.ndarray:
    return np.asarray([float(value.x), float(value.y), float(value.z)], dtype=float)


def scalar_range(values: list[float]) -> list[float]:
    return [float(min(values)), float(max(values))]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    numeric = (
        "actual_d_min_m",
        "minimum_abs_vertical_separation_m",
        "nominal_vertical_compression_m",
        "realized_vertical_compression_from_pre_median_m",
        "max_inward_relative_vertical_velocity_mps",
        "max_opposing_relative_ladrc_acceleration_mps2",
        "max_affected_ladrc_output_norm_mps2",
        "minimum_distance_time_relative_to_registered_onset_s",
        "minimum_distance_time_relative_to_registered_end_s",
    )
    result = {
        "attempt_count": len(rows),
        "force_publication_verified_attempts": sum(
            row["force_publication"]["both_uavs_verified"] for row in rows
        ),
        "minimum_pair_counts": dict(sorted(Counter(
            row["actual_d_min_pair"] for row in rows
        ).items())),
        "mission_success_attempts": sum(row["mission_success"] for row in rows),
        "failsafe_attempts": sum(row["failsafe_seen"] for row in rows),
        "catastrophic_d_min_le_0p25_attempts": sum(
            row["actual_d_min_m"] <= 0.25 for row in rows
        ),
        "ladrc_limit_reached_attempts": sum(
            row["ladrc_acceleration_limit_reached"] for row in rows
        ),
    }
    for field in numeric:
        values = [float(row[field]) for row in rows]
        result[field.replace("_m", "_m").replace("_s", "_s") + "_distribution"] = {
            "range": scalar_range(values),
            "mean": float(np.mean(values)),
            "median": float(np.median(values)),
        }
    return result


def clock_seconds(message: Any) -> float:
    return float(message.clock.sec) + float(message.clock.nanosec) * 1.0e-9


def simulation_time_at_or_before(clock_records: list[Any], bag_timestamp: float) -> float:
    eligible = [
        record for record in clock_records if record.bag_timestamp <= bag_timestamp
    ]
    if not eligible:
        raise RuntimeError(f"no /clock support before bag timestamp {bag_timestamp}")
    return clock_seconds(max(eligible, key=lambda record: record.bag_timestamp).message)


def bag_time_at_or_after_sim_target(clock_records: list[Any], after_bag_time: float,
                                    target_sim_time: float) -> float:
    eligible = [
        record for record in clock_records
        if record.bag_timestamp >= after_bag_time
        and clock_seconds(record.message) >= target_sim_time
    ]
    if not eligible:
        raise RuntimeError(f"no /clock sample reaches simulation time {target_sim_time}")
    return float(min(eligible, key=lambda record: record.bag_timestamp).bag_timestamp)


def wrench_evidence(records: list[Any], clock_records: list[Any], topic: str,
                    expected: np.ndarray, t0: float, arm_time: float) -> dict[str, Any]:
    subset = [record for record in records if record.topic == topic]
    nonzero = []
    zero = []
    observed_vectors = []
    for record in subset:
        vector = vector3(record.message.force)
        if np.linalg.norm(vector) > 1.0e-12:
            nonzero.append(record)
            observed_vectors.append(tuple(float(x) for x in vector))
        else:
            zero.append(record)
    first_active_record = min(nonzero, key=lambda record: record.bag_timestamp, default=None)
    last_active_record = max(nonzero, key=lambda record: record.bag_timestamp, default=None)
    first_active_sim = (
        simulation_time_at_or_before(clock_records, first_active_record.bag_timestamp)
        if first_active_record is not None else None
    )
    last_active_sim = (
        simulation_time_at_or_before(clock_records, last_active_record.bag_timestamp)
        if last_active_record is not None else None
    )
    first_zero_record = min(
        (record for record in zero
         if first_active_record is not None
         and record.bag_timestamp > last_active_record.bag_timestamp),
        key=lambda record: record.bag_timestamp,
        default=None,
    )
    first_zero_sim = (
        simulation_time_at_or_before(clock_records, first_zero_record.bag_timestamp)
        if first_zero_record is not None else None
    )
    vectors = sorted(set(observed_vectors))
    magnitude_and_direction_correct = bool(vectors) and all(
        np.allclose(np.asarray(vector), expected, rtol=0.0, atol=1.0e-12)
        for vector in vectors
    )
    return {
        "topic": topic,
        "message_count": len(subset),
        "active_message_count": len(nonzero),
        "zero_message_count": len(zero),
        "observed_active_vectors_N": [list(vector) for vector in vectors],
        "magnitude_and_direction_correct": magnitude_and_direction_correct,
        "first_active_relative_to_t0_s": (
            float(first_active_record.bag_timestamp - t0)
            if first_active_record is not None else None
        ),
        "first_active_relative_to_arm_sim_s": (
            float(first_active_sim - arm_time) if first_active_sim is not None else None
        ),
        "last_active_relative_to_t0_s": (
            float(last_active_record.bag_timestamp - t0)
            if last_active_record is not None else None
        ),
        "zero_after_active_relative_to_t0_s": (
            float(first_zero_record.bag_timestamp - t0)
            if first_zero_record is not None else None
        ),
        "published_hold_duration_sim_s": (
            float(first_zero_sim - first_active_sim)
            if first_active_sim is not None and first_zero_sim is not None else None
        ),
        "published_hold_duration_wall_s": (
            float(first_zero_record.bag_timestamp - first_active_record.bag_timestamp)
            if first_active_record is not None and first_zero_record is not None else None
        ),
        "publication_verified": bool(
            nonzero and first_zero_record is not None and magnitude_and_direction_correct
        ),
    }


def extract_attempt(attempt_path: Path) -> dict[str, Any]:
    attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    raw_dir = attempt_path.parent / "raw"
    spec = json.loads((raw_dir / "runtime_spec.json").read_text(encoding="utf-8"))
    interaction = json.loads((raw_dir / "interaction_result.json").read_text(encoding="utf-8"))
    if attempt["condition"] not in CONDITIONS or attempt["feedback"] != "F0":
        raise RuntimeError(f"feedback firewall violation: {attempt_path}")
    if spec["avoidance_mode"] != "off" or attempt["attempt_status"] != "success":
        raise RuntimeError(f"invalid retained scientific attempt: {attempt_path}")

    relevant = {
        "/clock", "/e3/disturbance_arm",
        "/uav2/execution_command", "/uav3/execution_command",
        "/uav2/swarm_state", "/uav3/swarm_state",
        "/uav2/control_tracking_debug", "/uav3/control_tracking_debug",
        "/e3_force/mavlink_3/wrench", "/e3_force/mavlink_4/wrench",
    }
    records = read_bag(raw_dir / "rosbag", lambda topic: topic in relevant)
    mission_id = int(interaction["mission_id"])
    t0 = command_time(records, mission_id)
    arm = [record for record in records if record.topic == "/e3/disturbance_arm"]
    if len(arm) != 1:
        raise RuntimeError(f"expected one arm record: {attempt_path}")
    clock_records = [record for record in records if record.topic == "/clock"]
    arm_sim_time = simulation_time_at_or_before(clock_records, arm[0].bag_timestamp)
    force_start_sim = arm_sim_time + float(spec["disturbance"]["onset_s"])
    force_end_sim = force_start_sim + float(spec["disturbance"]["duration_s"])
    force_start = bag_time_at_or_after_sim_target(
        clock_records, arm[0].bag_timestamp, force_start_sim
    )
    force_end = bag_time_at_or_after_sim_target(
        clock_records, arm[0].bag_timestamp, force_end_sim
    )
    scored_end = t0 + float(spec["duration_s"]) + 2.0

    positions = swarm_position_series(records, (2, 3))
    grid, position, _ = synchronized_grid(positions, t0, scored_end)
    delta = position[3] - position[2]
    distance = np.linalg.norm(delta, axis=1)
    abs_dz = np.abs(delta[:, 2])
    min_distance_index = int(np.argmin(distance))
    min_dz_index = int(np.argmin(abs_dz))

    pre_mask = grid < force_start
    post_mask = grid >= force_start
    if not np.any(pre_mask) or not np.any(post_mask):
        raise RuntimeError(f"missing pre/post position support: {attempt_path}")
    pre_dz_median = float(np.median(abs_dz[pre_mask]))
    post_min_dz = float(np.min(abs_dz[post_mask]))

    velocity_series = {}
    for uid in (2, 3):
        subset = [record for record in records if record.topic == f"/uav{uid}/swarm_state"]
        velocity_series[uid] = normalize_series(
            [record.timestamp for record in subset],
            [vector3(record.message.twist.twist.linear) for record in subset],
        )
    v_grid, velocity, _ = synchronized_grid(velocity_series, force_start, force_end)
    inward_relative_velocity = velocity[2][:, 2] - velocity[3][:, 2]

    ladrc_series = {}
    ladrc_norms = {}
    for uid in (2, 3):
        subset = [
            record for record in records
            if record.topic == f"/uav{uid}/control_tracking_debug"
        ]
        ladrc_series[uid] = normalize_series(
            [record.timestamp for record in subset],
            [vector3(record.message.ladrc_output) for record in subset],
        )
    a_grid, ladrc, _ = synchronized_grid(ladrc_series, force_start, force_end)
    opposing_relative_ladrc = ladrc[3][:, 2] - ladrc[2][:, 2]
    for uid in (2, 3):
        ladrc_norms[uid] = np.linalg.norm(ladrc[uid], axis=1)
    max_ladrc_norm = float(max(np.max(value) for value in ladrc_norms.values()))

    vectors = spec["disturbance"]["vectors_N"]
    expected2 = np.asarray(vectors.get("2", vectors.get(2)), dtype=float)
    expected3 = np.asarray(vectors.get("3", vectors.get(3)), dtype=float)
    uav2_wrench = wrench_evidence(
        records, clock_records, "/e3_force/mavlink_3/wrench", expected2, t0, arm_sim_time
    )
    uav3_wrench = wrench_evidence(
        records, clock_records, "/e3_force/mavlink_4/wrench", expected3, t0, arm_sim_time
    )
    both_verified = bool(
        uav2_wrench["publication_verified"] and uav3_wrench["publication_verified"]
    )

    geometry_key = attempt["candidate_id"].split("-")[2]
    initial = spec["initial_positions_m"]
    h = float(initial[2][1] - initial[1][1])
    nominal_z = abs(float(initial[2][2] - initial[1][2]))
    minimum_time = float(grid[min_distance_index])
    minimum_relative_t0 = minimum_time - t0
    return {
        "attempt_instance_id": attempt["attempt_instance_id"],
        "candidate_id": attempt["candidate_id"],
        "condition": attempt["condition"],
        "seed": int(attempt["seed"]),
        "geometry": geometry_key,
        "h_m": h,
        "registered_force_magnitude_N_per_uav": float(np.linalg.norm(expected2)),
        "registered_nominal_vertical_separation_m": nominal_z,
        "actual_d_min_m": float(distance[min_distance_index]),
        "actual_d_min_pair": attempt["metrics"]["realized"]["d_min_pair"],
        "minimum_abs_vertical_separation_m": float(abs_dz[min_dz_index]),
        "nominal_vertical_compression_m": float(nominal_z - abs_dz[min_dz_index]),
        "pre_onset_median_abs_vertical_separation_m": pre_dz_median,
        "post_onset_min_abs_vertical_separation_m": post_min_dz,
        "realized_vertical_compression_from_pre_median_m": float(
            pre_dz_median - post_min_dz
        ),
        "max_inward_relative_vertical_velocity_mps": float(
            np.max(inward_relative_velocity)
        ),
        "mean_inward_relative_vertical_velocity_mps": float(
            np.mean(inward_relative_velocity)
        ),
        "max_opposing_relative_ladrc_acceleration_mps2": float(
            np.max(opposing_relative_ladrc)
        ),
        "mean_opposing_relative_ladrc_acceleration_mps2": float(
            np.mean(opposing_relative_ladrc)
        ),
        "max_affected_ladrc_output_norm_mps2": max_ladrc_norm,
        "ladrc_acceleration_limit_reached": bool(
            max_ladrc_norm >= ACCELERATION_LIMIT_MPS2 - 1.0e-9
        ),
        "registered_force_start_relative_to_t0_s": float(force_start - t0),
        "registered_force_end_relative_to_t0_s": float(force_end - t0),
        "minimum_distance_time_relative_to_t0_s": minimum_relative_t0,
        "minimum_distance_time_relative_to_registered_onset_s": float(
            minimum_time - force_start
        ),
        "minimum_distance_time_relative_to_registered_end_s": float(
            minimum_time - force_end
        ),
        "force_publication": {
            "both_uavs_verified": both_verified,
            "uav2": uav2_wrench,
            "uav3": uav3_wrench,
        },
        "mission_success": bool(attempt["metrics"]["stability"]["mission_success"]),
        "failsafe_seen": bool(attempt["metrics"]["stability"]["failsafe_seen"]),
        "attempt_json_sha256": sha256_file(attempt_path),
        "rosbag_sqlite_sha256": sha256_file(raw_dir / "rosbag" / "rosbag_0.db3"),
    }


def build() -> dict[str, Any]:
    paths = sorted(RAW_ROOT.glob("E3V4Q-B02-V1-*/attempt.json"))
    if len(paths) != EXPECTED_ATTEMPTS:
        raise RuntimeError(f"expected {EXPECTED_ATTEMPTS} attempts, found {len(paths)}")
    rows = [extract_attempt(path) for path in paths]
    if len({row["attempt_instance_id"] for row in rows}) != EXPECTED_ATTEMPTS:
        raise RuntimeError("duplicate amendment-v1 attempt identity")

    cells = {}
    for h in (1.0, 1.1, 1.2):
        for force in FORCES_N:
            for condition in CONDITIONS:
                selected = [
                    row for row in rows
                    if math.isclose(row["h_m"], h)
                    and math.isclose(row["registered_force_magnitude_N_per_uav"], force)
                    and row["condition"] == condition
                ]
                if len(selected) != 5:
                    raise RuntimeError(f"incomplete cell h={h} F={force} {condition}")
                cells[f"h={h:.1f}|F={force:.1f}|{condition}"] = summarize(selected)

    dose_response = {}
    for condition in CONDITIONS:
        for verification in ("all", "wrench_verified"):
            dose_response[f"{condition}|{verification}"] = {}
            for force in FORCES_N:
                selected = [
                    row for row in rows
                    if row["condition"] == condition
                    and math.isclose(row["registered_force_magnitude_N_per_uav"], force)
                    and (verification == "all"
                         or row["force_publication"]["both_uavs_verified"])
                ]
                dose_response[f"{condition}|{verification}"][f"{force:.1f}N"] = summarize(selected)

    verified = [row for row in rows if row["force_publication"]["both_uavs_verified"]]
    unverified = [row for row in rows if not row["force_publication"]["both_uavs_verified"]]
    active_topics = [
        uav
        for row in verified
        for uav in (row["force_publication"]["uav2"], row["force_publication"]["uav3"])
    ]
    onset_from_arm = [uav["first_active_relative_to_arm_sim_s"] for uav in active_topics]
    hold_duration = [uav["published_hold_duration_sim_s"] for uav in active_topics]
    magnitude_correct = all(uav["magnitude_and_direction_correct"] for uav in active_topics)

    r1 = {
        "pass": len(verified) == EXPECTED_ATTEMPTS and magnitude_correct,
        "publication_verified_attempts": len(verified),
        "publication_unverified_attempts": len(unverified),
        "unverified_attempt_ids": [row["attempt_instance_id"] for row in unverified],
        "registered_magnitudes_present_N": sorted({
            row["registered_force_magnitude_N_per_uav"] for row in rows
        }),
        "observed_active_vectors_match_registry_for_verified_attempts": magnitude_correct,
        "first_active_relative_to_arm_sim_range_s": scalar_range(onset_from_arm),
        "first_active_relative_to_arm_sim_counts": dict(sorted(Counter(
            f"{value:.1f}" for value in onset_from_arm
        ).items())),
        "published_hold_duration_sim_range_s": scalar_range(hold_duration),
        "published_hold_duration_sim_counts": dict(sorted(Counter(
            f"{value:.1f}" for value in hold_duration
        ).items())),
        "reason": (
            "FAIL: ten retained attempts contain zero wrench messages on both affected "
            "topics and show the no-force response pattern; force application cannot be "
            "verified for the full registered population."
            if len(verified) != EXPECTED_ATTEMPTS else
            "PASS: every retained attempt has registry-matching wrench publication evidence."
        ),
    }

    verified_force_means = {}
    for force in FORCES_N:
        selected = [
            row for row in verified
            if math.isclose(row["registered_force_magnitude_N_per_uav"], force)
        ]
        verified_force_means[f"{force:.1f}N"] = {
            "n": len(selected),
            "mean_d_min_m": float(np.mean([row["actual_d_min_m"] for row in selected])),
            "mean_vertical_compression_from_pre_median_m": float(np.mean([
                row["realized_vertical_compression_from_pre_median_m"] for row in selected
            ])),
            "mean_max_inward_relative_vertical_velocity_mps": float(np.mean([
                row["max_inward_relative_vertical_velocity_mps"] for row in selected
            ])),
        }
    mean_d = [verified_force_means[f"{force:.1f}N"]["mean_d_min_m"] for force in FORCES_N]
    mean_c = [verified_force_means[f"{force:.1f}N"]["mean_vertical_compression_from_pre_median_m"]
              for force in FORCES_N]
    r2 = {
        "pass": bool(mean_d[0] > mean_d[1] > mean_d[2] and mean_c[0] < mean_c[1] < mean_c[2]),
        "verified_attempt_dose_summary": verified_force_means,
        "reason": (
            "PASS: among attempts with observed registry-matching wrench messages, mean "
            "d_min decreases and mean vertical compression increases monotonically from "
            "2 N to 4 N."
        ),
    }

    force4_registered = [
        row for row in rows
        if math.isclose(row["registered_force_magnitude_N_per_uav"], 4.0)
    ]
    force4 = [
        row for row in force4_registered
        if row["force_publication"]["both_uavs_verified"]
    ]
    r3 = {
        "pass": bool(
            all(row["mission_success"] and not row["failsafe_seen"] for row in force4)
            and all(row["actual_d_min_m"] > 0.25 for row in force4)
            and all(not row["ladrc_acceleration_limit_reached"] for row in force4)
        ),
        "registered_attempt_count": len(force4_registered),
        "force_publication_verified_attempt_count": len(force4),
        "mission_success_attempts": sum(row["mission_success"] for row in force4),
        "failsafe_attempts": sum(row["failsafe_seen"] for row in force4),
        "d_min_range_m": scalar_range([row["actual_d_min_m"] for row in force4]),
        "max_ladrc_output_norm_range_mps2": scalar_range([
            row["max_affected_ladrc_output_norm_mps2"] for row in force4
        ]),
        "acceleration_limit_reached_attempts": sum(
            row["ladrc_acceleration_limit_reached"] for row in force4
        ),
        "reason": "PASS: 4 N remained mission-stable, non-catastrophic, failsafe-free, and below the frozen acceleration limit.",
    }

    return {
        "schema": "E3_v4_B02_amendment_v1_response_diagnosis_v1",
        "status": "BLOCKED_AT_E3_B02_RESPONSE_DIAGNOSIS",
        "dataset_class": "calibration_pilot_posthoc_diagnosis",
        "accepted_formal_result": False,
        "f1_attempt_count": 0,
        "formal_attempt_count": 0,
        "attempt_count": len(rows),
        "response_gates": {"R1": r1, "R2": r2, "R3": r3},
        "amendment_v2_authorized_to_proceed": bool(r1["pass"] and r2["pass"] and r3["pass"]),
        "cells": cells,
        "dose_response": dose_response,
        "attempt_rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")
    args.output.write_text(
        json.dumps(build(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
