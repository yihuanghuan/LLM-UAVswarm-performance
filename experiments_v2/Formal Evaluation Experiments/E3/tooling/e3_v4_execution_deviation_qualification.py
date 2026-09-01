#!/usr/bin/env python3
"""Append-only, F0-only qualification for E3-v4 execution deviations."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

import yaml

from e3_formal_backend import build_runtime_spec
from e3_trial_registry import POLICY_PATH, canonical_sha256, sha256_file

TOOLING_DIR = Path(__file__).resolve().parent
E3_DIR = TOOLING_DIR.parent
REPO_ROOT = E3_DIR.parents[2]
GRID_PATH = E3_DIR / "E3_v4_family_B_execution_deviation_grid.yaml"
SEEDS_PATH = E3_DIR / "E3_v4_qualification_seeds.yaml"
OLD_REGISTRY_PATH = E3_DIR / "e3_factorial_registry_v3.yaml"
HARNESS = TOOLING_DIR / "e3_v4_execution_deviation_trial.py"
METRICS = TOOLING_DIR / "e3_v4_execution_deviation_metrics.py"
DEFAULT_OUTPUT = E3_DIR / "results" / "qualification" / "execution_deviation_raw"
INTERFACE_PREFIX = Path(
    "/home/yihuang/learning/LLM_swarm_ws/formal_install_v1/uav_swarm_interfaces"
)
ALLOWED = {
    "P0_F0": {"assignment_mode": "distance_hungarian", "avoidance_mode": "off"},
    "P1_F0": {"assignment_mode": "safety_aware", "avoidance_mode": "off"},
}
NOTICE = "NOT_FORMAL_RESULT"


class QualificationError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise QualificationError(f"expected mapping: {path}")
    return value


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()


def validate_registration(candidate_id: str, condition: str, seed: int):
    if condition not in ALLOWED:
        raise QualificationError("Family-B qualification is sealed to P0_F0/P1_F0")
    grid = load_yaml(GRID_PATH)
    seeds = load_yaml(SEEDS_PATH)
    if grid.get("status") != "FROZEN_BEFORE_PHYSICAL_SCREENING":
        raise QualificationError("execution-deviation grid is not frozen")
    if grid.get("F1_permitted") is not False:
        raise QualificationError("grid does not fail closed against F1")
    if grid.get("formal_execution_permitted") is not False:
        raise QualificationError("grid does not fail closed against formal execution")
    if candidate_id not in grid["candidates"]:
        raise QualificationError(f"unregistered candidate: {candidate_id}")
    registered_seeds = [int(value) for value in grid["qualification_population"]["seeds"]]
    if int(seed) not in registered_seeds:
        raise QualificationError(f"unregistered qualification seed: {seed}")
    if registered_seeds != [int(value) for value in seeds["seeds"]]:
        raise QualificationError("grid seed list differs from qualification registry")
    dirty = git("status", "--porcelain", "--", str(GRID_PATH.relative_to(REPO_ROOT)))
    if dirty:
        raise QualificationError("physical execution refused for uncommitted grid")
    prereg_commit = git(
        "log", "-1", "--format=%H", "--", str(GRID_PATH.relative_to(REPO_ROOT))
    )
    if not prereg_commit:
        raise QualificationError("physical execution refused before grid commit")
    return grid, grid["candidates"][candidate_id], prereg_commit


def build_candidate_spec(candidate_id: str, condition: str, seed: int) -> dict[str, Any]:
    grid, candidate, prereg_commit = validate_registration(candidate_id, condition, seed)
    geometry = grid["geometries"][candidate["geometry"]]
    mapping = ALLOWED[condition]
    manipulation: dict[str, Any]
    if candidate["mechanism"] == "command_delay":
        manipulation = {
            "type": "command_delay",
            "affected_uavs": [int(value) for value in candidate["affected_uavs"]],
            "reference_uavs": [int(value) for value in candidate["reference_uavs"]],
            "delay_s": float(candidate["delay_s"]),
            "timing_basis": "ROS simulation time and execution-command header stamps",
            "random_component": None,
        }
    elif candidate["mechanism"] == "reference_deviation":
        manipulation = {
            "type": "reference_deviation",
            "affected_uav": int(candidate["affected_uav"]),
            "intended_pair": [int(value) for value in candidate["intended_pair"]],
            "start_s": float(candidate["start_s"]),
            "duration_s": float(candidate["duration_s"]),
            "offset_m": [float(value) for value in candidate["offset_m"]],
            "endpoint_semantics": (
                "counterfactual registered nominal reference at reset time plus offset"
            ),
            "reset_semantics": "new validated command to original committed target",
            "timing_basis": "ROS simulation time and execution-command header stamps",
            "random_component": None,
        }
    else:
        raise QualificationError(f"unknown mechanism: {candidate['mechanism']}")
    duration = float(geometry["duration_s"])
    trial_id = f"E3V4B-{candidate_id}__{condition}__S{int(seed)}"
    spec = {
        "spec_type": "E3_v4_execution_deviation_qualification_spec_v1",
        "fixture_class": "E3_v4_execution_deviation_candidate",
        "dataset_class": "calibration_pilot",
        "accepted_formal_result": False,
        "result_notice": NOTICE,
        "formal_cursor_consumed": False,
        "trial_id": trial_id,
        "candidate_id": candidate_id,
        "scenario_id": candidate["scenario_id"],
        "condition": condition,
        "seed": int(seed),
        "family": "B_residual_execution_risk",
        "uav_ids": [int(value) for value in geometry["uav_ids"]],
        "initial_positions_m": geometry["initial_positions_m"],
        "ordered_targets_m": geometry["ordered_targets_m"],
        "duration_s": duration,
        "staging": {"stable_continuous_s": 2.0, "scored": False},
        "scoring": {
            "t0": "first nominal interaction execution-command header timestamp",
            "end_offset_s": duration + 2.0,
        },
        "timeout_after_t0_s": duration + 6.0,
        "assignment_mode": mapping["assignment_mode"],
        "avoidance_mode": mapping["avoidance_mode"],
        "invariants": {
            "style": "normal", "safety_s": 1.0, "q": {"mode": "direct"},
            "lfs_runtime_mode": "candidate_v2",
            "control_mode": "ladrc_acceleration",
            "policy": "lfs_policy.paper_current.yaml",
        },
        "disturbance": manipulation,
        "manipulation": manipulation,
        "intended_pair": [int(value) for value in geometry["intended_pair"]],
        "delivery_tolerances": grid["delivery_tolerances"],
        "preregistration_commit": prereg_commit,
        "metric_log_schema": {
            "primary_metrics": [
                "actual_d_min", "predicted_d_min", "hard_risk_events",
                "hard_risk_exposure_duration", "mission_success",
                "intended_pair_attribution", "manipulation_delivery",
            ],
            "raw_required": [
                "clock", "execution_commands", "startup_events",
                "per_uav_position_3d", "per_uav_nominal_reference",
                "hard_failures", "manipulation_event_ledger",
            ],
        },
    }
    spec["registered_input_hash"] = canonical_sha256({
        "grid_sha256": sha256_file(GRID_PATH),
        "seed_registry_sha256": sha256_file(SEEDS_PATH),
        "candidate": candidate,
        "geometry": geometry,
        "condition": condition,
        "seed": int(seed),
    })
    spec["resolved_execution_spec_hash"] = canonical_sha256(spec)
    return spec


def build_deviation_runtime_spec(spec: dict[str, Any]) -> dict[str, Any]:
    runtime = build_runtime_spec(spec)
    runtime.update({
        "spec_type": spec["spec_type"],
        "candidate_id": spec["candidate_id"],
        "scenario_id": spec["scenario_id"],
        "condition": spec["condition"],
        "manipulation": spec["manipulation"],
        "intended_pair": spec["intended_pair"],
        "delivery_tolerances": spec["delivery_tolerances"],
        "preregistration_commit": spec["preregistration_commit"],
        "registered_input_hash": spec["registered_input_hash"],
        "accepted_formal_result": False,
        "formal_cursor_consumed": False,
        "result_notice": NOTICE,
    })
    runtime["runtime_spec_sha256"] = canonical_sha256(runtime)
    return runtime


def _metrics_environment() -> dict[str, str]:
    python_path = INTERFACE_PREFIX / "local/lib/python3.10/dist-packages"
    library_path = INTERFACE_PREFIX / "lib"
    if not python_path.is_dir() or not library_path.is_dir():
        raise QualificationError("sealed formal message interface is unavailable")
    env = os.environ.copy()
    env["PYTHONPATH"] = ":".join(filter(None, (str(python_path), env.get("PYTHONPATH", ""))))
    env["LD_LIBRARY_PATH"] = ":".join(filter(None, (str(library_path), env.get("LD_LIBRARY_PATH", ""))))
    return env


def write_exclusive(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def execute(
    candidate_id: str, condition: str, seed: int, output_root: Path,
    retry_suffix: str | None = None,
) -> dict[str, Any]:
    spec = build_candidate_spec(candidate_id, condition, seed)
    return execute_spec(
        spec, output_root, retry_suffix, grid_path=GRID_PATH,
        seeds_path=SEEDS_PATH,
    )


def execute_spec(
    spec: dict[str, Any], output_root: Path,
    retry_suffix: str | None = None, *, grid_path: Path = GRID_PATH,
    seeds_path: Path = SEEDS_PATH,
) -> dict[str, Any]:
    """Execute an already validated B/C qualification spec append-only."""
    candidate_id = str(spec["candidate_id"])
    condition = str(spec["condition"])
    seed = int(spec["seed"])
    runtime = build_deviation_runtime_spec(spec)
    if retry_suffix is not None and not re.fullmatch(r"r[1-9][0-9]*", retry_suffix):
        raise QualificationError("retry suffix must match r[1-9][0-9]*")
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    attempt_instance = spec["trial_id"] + (
        f"__retry-{retry_suffix}" if retry_suffix else ""
    )
    attempt_dir = output_root / attempt_instance
    if attempt_dir.exists():
        raise QualificationError(f"refusing to overwrite attempt: {attempt_dir}")
    lock_path = output_root / ".qualification.lock"
    with lock_path.open("a+", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise QualificationError("another qualification attempt is active") from exc
        attempt_dir.mkdir()
        raw_dir = attempt_dir / "raw"
        raw_dir.mkdir()
        runtime_path = raw_dir / "runtime_spec.json"
        runtime_path.write_text(
            json.dumps(runtime, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        physical_path = raw_dir / "physical_result.json"
        started = datetime.now(timezone.utc).isoformat()
        status = "infrastructure_failure"
        error = None
        metrics = None
        try:
            run = subprocess.run(
                [sys.executable, str(HARNESS), "--runtime-spec", str(runtime_path),
                 "--output", str(raw_dir), "--result", str(physical_path)],
                cwd=REPO_ROOT, text=True, capture_output=True,
                timeout=float(runtime["timeout_after_t0_s"]) + 300.0,
            )
            (raw_dir / "harness.stdout.log").write_text(run.stdout, encoding="utf-8")
            (raw_dir / "harness.stderr.log").write_text(run.stderr, encoding="utf-8")
            if not physical_path.exists():
                raise RuntimeError("physical harness did not retain a result")
            physical = json.loads(physical_path.read_text(encoding="utf-8"))
            status = str(physical.get("attempt_status", "infrastructure_failure"))
            if status != "success":
                error = str(physical.get("error", "physical harness failed"))
            else:
                metrics_path = attempt_dir / "qualification_metrics.json"
                metric_run = subprocess.run(
                    [sys.executable, str(METRICS), str(raw_dir), "--output", str(metrics_path)],
                    cwd=REPO_ROOT, env=_metrics_environment(), text=True,
                    capture_output=True,
                )
                (attempt_dir / "metrics.stdout.log").write_text(
                    metric_run.stdout + metric_run.stderr, encoding="utf-8"
                )
                if metric_run.returncode:
                    status = "infrastructure_failure"
                    raise RuntimeError("fail-closed manipulation/metric extraction failed")
                metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
                if not metrics["manipulation_delivery"]["verified"]:
                    status = "infrastructure_failure"
                    raise RuntimeError("manipulation delivery was not verified")
        except subprocess.TimeoutExpired as exc:
            status = "timeout"
            error = str(exc)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        manifest = {
            "schema": "E3_v4_execution_deviation_attempt_v1",
            "dataset_class": "calibration_pilot",
            "accepted_formal_result": False,
            "formal_cursor_consumed": False,
            "result_notice": NOTICE,
            "trial_id": spec["trial_id"],
            "attempt_instance_id": attempt_instance,
            "retry_of": spec["trial_id"] if retry_suffix else None,
            "retry_suffix": retry_suffix,
            "candidate_id": candidate_id,
            "condition": condition,
            "feedback": "F0",
            "seed": int(seed),
            "attempt_status": status,
            "error": error,
            "started_utc": started,
            "finished_utc": datetime.now(timezone.utc).isoformat(),
            "execution_spec": spec,
            "runtime_spec_sha256": runtime["runtime_spec_sha256"],
            "metrics": metrics,
            "provenance": {
                "branch": git("branch", "--show-current"),
                "qualification_commit": git("rev-parse", "HEAD"),
                "preregistration_commit": spec["preregistration_commit"],
                "grid_sha256": sha256_file(grid_path),
                "qualification_seeds_sha256": sha256_file(seeds_path),
                "policy_sha256": sha256_file(POLICY_PATH),
                "old_E3_v3_registry_sha256": sha256_file(OLD_REGISTRY_PATH),
                "production_baseline": "6cf402debf23851b1eff3edc6f3ab49eae7127c4",
            },
        }
        write_exclusive(attempt_dir / "attempt.json", manifest)
        return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--condition", required=True)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--retry-suffix")
    parser.add_argument("--dry-run-spec", action="store_true")
    args = parser.parse_args()
    if args.dry_run_spec:
        value = build_deviation_runtime_spec(
            build_candidate_spec(args.candidate, args.condition, args.seed)
        )
    else:
        value = execute(
            args.candidate, args.condition, args.seed, args.output_root,
            args.retry_suffix,
        )
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if value.get("attempt_status", "success") == "success" else 2


if __name__ == "__main__":
    raise SystemExit(main())
