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
import re
import subprocess
import sys
from typing import Any

import yaml

from e3_formal_backend import build_runtime_spec, execute_registered_trial
from e3_trial_registry import POLICY_PATH, canonical_sha256, sha256_file

TOOLING_DIR = Path(__file__).resolve().parent
E3_DIR = TOOLING_DIR.parent
REPO_ROOT = E3_DIR.parents[2]
GRID_PATH = E3_DIR / "E3_v4_candidate_disturbance_grid.yaml"
SEEDS_PATH = E3_DIR / "E3_v4_qualification_seeds.yaml"
AMENDMENT_GRID_PATH = E3_DIR / "E3_v4_B02_amendment_v1_grid.yaml"
HOLDOUT_SEEDS_PATH = E3_DIR / "E3_v4_B02_holdout_qualification_seeds.yaml"
AMENDMENT_SELECTION_PATH = E3_DIR / "E3_v4_B02_amendment_screening_selection.yaml"
OLD_REGISTRY_PATH = E3_DIR / "e3_factorial_registry_v3.yaml"
DEFAULT_OUTPUT = E3_DIR / "results" / "qualification" / "raw"
ALLOWED = {
    "P0_F0": {"assignment_mode": "distance_hungarian", "avoidance_mode": "off"},
    "P1_F0": {"assignment_mode": "safety_aware", "avoidance_mode": "off"},
}
NOTICE = "NOT_FORMAL_RESULT"
METRICS_TOOL = TOOLING_DIR / "e3_v4_qualification_metrics.py"
INTERFACE_PREFIX = Path(
    "/home/yihuang/learning/LLM_swarm_ws/formal_install_v1/uav_swarm_interfaces"
)


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


def _resolve_registration(candidate_id: str, seed: int) -> dict[str, Any]:
    """Resolve either the original grid or the versioned B-02 amendment."""
    if candidate_id.startswith("B02-V1-"):
        grid = load_yaml(AMENDMENT_GRID_PATH)
        if grid.get("status") != "FROZEN_BEFORE_AMENDMENT_V1_PHYSICAL_QUALIFICATION":
            raise QualificationError("B-02 amendment grid is not frozen")
        if candidate_id not in grid["candidates"]:
            raise QualificationError(f"unknown amendment candidate: {candidate_id}")
        screen = [int(value) for value in load_yaml(SEEDS_PATH)["seeds"]]
        holdout = [int(value) for value in load_yaml(HOLDOUT_SEEDS_PATH)["seeds"]]
        if int(seed) in screen:
            seed_role = "screening"
            seed_registry_path = SEEDS_PATH
        elif int(seed) in holdout:
            seed_role = "holdout"
            seed_registry_path = HOLDOUT_SEEDS_PATH
            if not AMENDMENT_SELECTION_PATH.is_file():
                raise QualificationError(
                    "holdout execution refused before committed screening selection freeze"
                )
            selection = load_yaml(AMENDMENT_SELECTION_PATH)
            if (selection.get("status") != "FROZEN_BEFORE_HOLDOUT_EXECUTION"
                    or selection.get("selected_candidate_id") != candidate_id):
                raise QualificationError(
                    "holdout execution is restricted to the frozen selected candidate"
                )
        else:
            raise QualificationError(f"unregistered amendment qualification seed: {seed}")
        compact = grid["candidates"][candidate_id]
        profile = grid["disturbance_profiles"][compact["profile"]]
        candidate = {
            "scenario_id": grid["scenario_id"],
            "geometry": compact["geometry"],
            "affected_uavs": [2, 3],
            "vectors_N": {
                2: [0.0, 0.0, float(profile["magnitude_N_per_uav"])],
                3: [0.0, 0.0, -float(profile["magnitude_N_per_uav"])],
            },
            "magnitude_N_per_uav": float(profile["magnitude_N_per_uav"]),
            "onset_s": float(grid["onset_s"]),
            "duration_s": float(profile["duration_s"]),
            "disposition": "PHYSICAL",
            "amendment_profile": compact["profile"],
        }
        return {
            "grid": grid,
            "candidate": candidate,
            "geometry": grid["geometries"][compact["geometry"]],
            "grid_path": AMENDMENT_GRID_PATH,
            "seed_registry_path": seed_registry_path,
            "seed_role": seed_role,
            "amendment": "B02_v1",
        }

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
    return {
        "grid": grid,
        "candidate": candidate,
        "geometry": grid["geometries"][candidate["geometry"]],
        "grid_path": GRID_PATH,
        "seed_registry_path": SEEDS_PATH,
        "seed_role": "legacy_screening",
        "amendment": None,
    }


def build_candidate_spec(candidate_id: str, condition: str, seed: int) -> dict[str, Any]:
    mapping = validate_condition(condition)
    registration = _resolve_registration(candidate_id, seed)
    candidate = registration["candidate"]
    if candidate.get("disposition") != "PHYSICAL":
        raise QualificationError(
            f"candidate is not executable: {candidate.get('disposition')}"
        )
    geometry = registration["geometry"]
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
        "qualification_amendment": registration["amendment"],
        "qualification_seed_role": registration["seed_role"],
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
        "grid_sha256": sha256_file(registration["grid_path"]), "candidate": candidate,
        "geometry": geometry, "condition": condition, "seed": int(seed),
        "seed_registry_sha256": sha256_file(registration["seed_registry_path"]),
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


def _metrics_environment() -> dict[str, str]:
    """Return an environment that resolves only the sealed formal interfaces."""
    python_path = INTERFACE_PREFIX / "local/lib/python3.10/dist-packages"
    library_path = INTERFACE_PREFIX / "lib"
    if not python_path.is_dir() or not library_path.is_dir():
        raise QualificationError(
            f"sealed interface overlay is unavailable: {INTERFACE_PREFIX}"
        )
    env = os.environ.copy()
    env["PYTHONPATH"] = ":".join(filter(None, (
        str(python_path), env.get("PYTHONPATH", ""))))
    env["LD_LIBRARY_PATH"] = ":".join(filter(None, (
        str(library_path), env.get("LD_LIBRARY_PATH", ""))))
    return env


def _extract_metrics_in_sealed_overlay(raw_dir: Path, output_path: Path) -> dict[str, Any]:
    subprocess.run(
        [sys.executable, str(METRICS_TOOL), str(raw_dir), "--output", str(output_path)],
        cwd=REPO_ROOT,
        env=_metrics_environment(),
        check=True,
    )
    return json.loads(output_path.read_text(encoding="utf-8"))


def execute(candidate_id: str, condition: str, seed: int, output_root: Path,
            retry_suffix: str | None = None) -> dict[str, Any]:
    spec = build_candidate_spec(candidate_id, condition, seed)
    if retry_suffix is not None and not re.fullmatch(r"r[1-9][0-9]*", retry_suffix):
        raise QualificationError("retry suffix must match r[1-9][0-9]*")
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    attempt_instance_id = spec["trial_id"] + (
        f"__retry-{retry_suffix}" if retry_suffix is not None else ""
    )
    attempt_dir = output_root / attempt_instance_id
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
            metrics = _extract_metrics_in_sealed_overlay(
                raw_dir, attempt_dir / "qualification_metrics.json"
            )
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
            "candidate_grid_sha256": (
                sha256_file(AMENDMENT_GRID_PATH)
                if spec["qualification_amendment"] == "B02_v1"
                else sha256_file(GRID_PATH)
            ),
            "base_candidate_grid_sha256": sha256_file(GRID_PATH),
            "B02_amendment_grid_sha256": (
                sha256_file(AMENDMENT_GRID_PATH)
                if spec["qualification_amendment"] == "B02_v1" else None
            ),
            "qualification_seeds_sha256": (
                sha256_file(HOLDOUT_SEEDS_PATH)
                if spec["qualification_seed_role"] == "holdout"
                else sha256_file(SEEDS_PATH)
            ),
            "qualification_seed_role": spec["qualification_seed_role"],
        }
        manifest = {
            "schema": "E3_v4_qualification_attempt_v1",
            "dataset_class": "calibration_pilot",
            "accepted_formal_result": False,
            "result_notice": NOTICE,
            "formal_cursor_consumed": False,
            "trial_id": spec["trial_id"],
            "attempt_instance_id": attempt_instance_id,
            "retry_of": spec["trial_id"] if retry_suffix is not None else None,
            "retry_suffix": retry_suffix,
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
    parser.add_argument("--retry-suffix")
    parser.add_argument("--dry-run-spec", action="store_true")
    args = parser.parse_args()
    if args.dry_run_spec:
        value = build_runtime_spec(build_candidate_spec(args.candidate, args.condition, args.seed))
    else:
        value = execute(args.candidate, args.condition, args.seed, args.output_root,
                        retry_suffix=args.retry_suffix)
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if value.get("attempt_status", "success") == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
