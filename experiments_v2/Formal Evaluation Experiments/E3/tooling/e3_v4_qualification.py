#!/usr/bin/env python3
"""Fail-closed, feedback-off-only E3-v4 candidate qualification harness."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import yaml

from e3_formal_backend import build_runtime_spec, execute_registered_trial
from e3_trial_registry import POLICY_PATH, canonical_sha256, sha256_file
from e3_v4_qualification_metrics import extract as extract_metrics

TOOLING_DIR = Path(__file__).resolve().parent
E3_DIR = TOOLING_DIR.parent
REPO_ROOT = E3_DIR.parents[2]
GRID_PATH = E3_DIR / "E3_v4_candidate_disturbance_grid.yaml"
SEEDS_PATH = E3_DIR / "E3_v4_qualification_seeds.yaml"
OLD_REGISTRY_PATH = E3_DIR / "e3_factorial_registry_v3.yaml"
DEFAULT_OUTPUT = E3_DIR / "results" / "qualification" / "raw"
ALLOWED = {
    "P0_F0": {"assignment_mode": "distance_hungarian", "avoidance_mode": "off"},
    "P1_F0": {"assignment_mode": "safety_aware", "avoidance_mode": "off"},
}
NOTICE = "NOT_FORMAL_RESULT"


class QualificationError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise QualificationError(f"expected mapping: {path}")
    return value


def validate_condition(condition: str) -> dict[str, str]:
    if condition not in ALLOWED:
        raise QualificationError(
            f"qualification permits only P0_F0/P1_F0; feedback-on refused: {condition}"
        )
    return ALLOWED[condition]


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()


def build_candidate_spec(candidate_id: str, condition: str, seed: int) -> dict[str, Any]:
    mapping = validate_condition(condition)
    grid, seeds = load_yaml(GRID_PATH), load_yaml(SEEDS_PATH)
    if grid.get("status") != "FROZEN_BEFORE_NEW_PHYSICAL_QUALIFICATION":
        raise QualificationError("candidate grid is not frozen")
    if seeds.get("status") != "FROZEN_FOR_QUALIFICATION_ONLY":
        raise QualificationError("qualification seed registry is not frozen")
    if int(seed) not in [int(value) for value in seeds["seeds"]]:
        raise QualificationError(f"unregistered qualification seed: {seed}")
    if candidate_id not in grid["candidates"]:
        raise QualificationError(f"unknown candidate: {candidate_id}")
    candidate = grid["candidates"][candidate_id]
    if candidate.get("disposition") != "PHYSICAL":
        raise QualificationError(
            f"candidate is not executable: {candidate.get('disposition')}"
        )
    geometry = grid["geometries"][candidate["geometry"]]
    scenario = str(candidate["scenario_id"])
    family = "B_residual_execution_risk" if scenario.startswith("E3-B") else "C_mixed_risk"
    duration = float(geometry["duration_s"])
    trial_id = f"E3V4Q-{candidate_id}__{condition}__S{int(seed)}"
    spec = {
        "spec_type": "E3_v4_qualification_execution_spec_v1",
        "fixture_class": "E3_v4_qualification_candidate",
        "dataset_class": "calibration_pilot",
        "accepted_formal_result": False,
        "result_notice": NOTICE,
        "trial_id": trial_id,
        "candidate_id": candidate_id,
        "experiment": "E3-v4-qualification",
        "scenario_id": scenario,
        "condition": condition,
        "seed": int(seed),
        "family": family,
        "input_level": "frozen allocator target set plus executable task fields; no LLM call",
        "uav_ids": [int(value) for value in geometry["uav_ids"]],
        "initial_positions_m": geometry["initial_positions_m"],
        "ordered_targets_m": geometry["ordered_targets_m"],
        "duration_s": duration,
        "staging": {"stable_continuous_s": 2.0, "scored": False},
        "scoring": {"t0": "interaction_execution_command_timestamp",
                    "end_offset_s": duration + 2.0},
        "timeout_after_t0_s": duration + 6.0,
        "assignment_mode": mapping["assignment_mode"],
        "avoidance_mode": mapping["avoidance_mode"],
        "invariants": {
            "style": "normal", "safety_s": 1.0, "q": {"mode": "direct"},
            "lfs_runtime_mode": "candidate_v2", "control_mode": "ladrc_acceleration",
            "policy": "lfs_policy.paper_current.yaml",
        },
        "disturbance": {
            "mechanism": "ROS 2 gazebo_plugins GazeboRosForce model plugin plus experiment-only e3_wrench_driver.py",
            "model_overlay": "../environment/patches/iris_gazebo_ros_force_v1.patch",
            "link": "base_link", "force_frame": "world",
            "waveform": "rectangular constant force", "torque": [0.0, 0.0, 0.0],
            "timing_basis": "/clock elapsed from /e3/disturbance_arm received at t0",
            "affected_uavs": [int(value) for value in candidate["affected_uavs"]],
            "vectors_N": candidate["vectors_N"],
            "magnitude_N_per_uav": float(candidate["magnitude_N_per_uav"]),
            "onset_s": float(candidate["onset_s"]),
            "duration_s": float(candidate["duration_s"]),
            "zero_wrench_at_end": True, "random_component": None,
            "loaded_for_zero_force_family_A": True,
        },
        "metric_log_schema": {
            "primary_metrics": ["actual_d_min", "predicted_d_min", "hard_risk_events",
                "hard_risk_exposure_duration", "mission_success", "iapf_activation_time",
                "integral_delta_p", "integral_delta_a", "trajectory_deviation"],
            "raw_required": ["clock", "execution_command_t0", "per_uav_position_3d",
                "per_uav_nominal_reference", "per_uav_safe_reference", "iapf_active",
                "iapf_delta_p", "iapf_delta_a", "allocator_prediction", "completion_events",
                "hard_failures", "wrench_commands"],
        },
    }
    spec["registered_input_hash"] = canonical_sha256({
        "grid_sha256": sha256_file(GRID_PATH), "candidate": candidate,
        "geometry": geometry, "condition": condition, "seed": int(seed),
    })
    spec["resolved_execution_spec_hash"] = canonical_sha256(spec)
    return spec


def _write_exclusive(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o444)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def execute(candidate_id: str, condition: str, seed: int, output_root: Path) -> dict[str, Any]:
    spec = build_candidate_spec(candidate_id, condition, seed)
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    attempt_dir = output_root / spec["trial_id"]
    if attempt_dir.exists():
        raise QualificationError(f"refusing to overwrite retained pilot: {attempt_dir}")
    lock_path = output_root / ".qualification.lock"
    with lock_path.open("a+", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise QualificationError("another physical qualification attempt is active") from exc
        attempt_dir.mkdir()
        raw_dir = attempt_dir / "raw"
        started = datetime.now(timezone.utc).isoformat()
        error = None
        try:
            physical = execute_registered_trial(spec, raw_dir)
            metrics = extract_metrics(raw_dir)
            _write_exclusive(attempt_dir / "qualification_metrics.json", metrics)
            status = str(physical.get("attempt_status", "infrastructure_failure"))
        except Exception as exc:
            status = "infrastructure_failure"
            error = f"{type(exc).__name__}: {exc}"
            metrics = None
        provenance = {
            "parent_commit": "d55ba9e3faddcc258a2b0985f6db821f8efcabfb",
            "qualification_commit": git("rev-parse", "HEAD"),
            "branch": git("branch", "--show-current"),
            "production_baseline": "6cf402debf23851b1eff3edc6f3ab49eae7127c4",
            "policy_sha256": sha256_file(POLICY_PATH),
            "old_E3_v3_registry_sha256": sha256_file(OLD_REGISTRY_PATH),
            "candidate_grid_sha256": sha256_file(GRID_PATH),
            "qualification_seeds_sha256": sha256_file(SEEDS_PATH),
        }
        manifest = {
            "schema": "E3_v4_qualification_attempt_v1",
            "dataset_class": "calibration_pilot",
            "accepted_formal_result": False,
            "result_notice": NOTICE,
            "formal_cursor_consumed": False,
            "trial_id": spec["trial_id"],
            "candidate_id": candidate_id, "scenario_id": spec["scenario_id"],
            "condition": condition, "feedback": "F0", "seed": int(seed),
            "attempt_status": status, "error": error,
            "started_utc": started, "finished_utc": datetime.now(timezone.utc).isoformat(),
            "execution_spec": spec, "metrics": metrics, "provenance": provenance,
        }
        _write_exclusive(attempt_dir / "attempt.json", manifest)
        return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--condition", required=True, choices=tuple(ALLOWED))
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--dry-run-spec", action="store_true")
    args = parser.parse_args()
    if args.dry_run_spec:
        value = build_runtime_spec(build_candidate_spec(args.candidate, args.condition, args.seed))
    else:
        value = execute(args.candidate, args.condition, args.seed, args.output_root)
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if value.get("attempt_status", "success") == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
