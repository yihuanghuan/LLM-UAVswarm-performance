#!/usr/bin/env python3
"""Run one C0-A trial through the repository's existing PX4/Gazebo path."""
from __future__ import annotations

import argparse
import json
import math
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[3]
OLD_C0A = ROOT.parent / "legacy_campaign"
VENV = REPO.parents[1] / "llm_env" / "bin" / "python"


def ros_environment():
    """Match the sourced environment used by the established C0-A runner."""
    command = (
        "source /opt/ros/humble/setup.bash && "
        f"source {REPO.parents[1]}/install/setup.bash && env -0"
    )
    result = subprocess.run(["bash", "-lc", command], check=True, stdout=subprocess.PIPE)
    return {
        key.decode(): value.decode()
        for item in result.stdout.split(b"\0") if b"=" in item
        for key, value in [item.split(b"=", 1)]
    }


def minimum_duration(distance, limits):
    return max(
        1.875 * distance / limits["velocity"],
        math.sqrt((10.0 / math.sqrt(3.0)) * distance / limits["acceleration"]),
        (60.0 * distance / limits["jerk"]) ** (1.0 / 3.0),
        0.5,
    )


def write_compatibility_inputs(spec, runtime_root):
    """Adapt one new-plan trial to the pre-existing C0-A run_trial contract."""
    trial = spec["trial"]
    limits = spec["motion_limits"]
    displacement = [float(value) for value in trial["displacement"]]
    distance = math.sqrt(sum(value * value for value in displacement))
    t_min = minimum_duration(distance, limits)
    old_config = json.loads((OLD_C0A / "configs" / "c0a_prereg_v3.json").read_text())
    old_config["single_uav_cases"]["C0A_RUNTIME:CASE"] = displacement
    config_path = runtime_root / "runtime_config.json"
    config_path.write_text(json.dumps(old_config, indent=2) + "\n")
    parameters = {
        "omega_c": spec["ladrc"]["omega_c"],
        "omega_o": spec["ladrc"]["omega_o"],
        "v_limit": float(limits["velocity"]),
        "a_limit": float(limits["acceleration"]),
        "j_limit": float(limits["jerk"]),
        "minimum_duration": 0.5,
    }
    entry = {
        "trial_id": trial["trial_id"], "stage": "A1_SCREENING",
        "candidate_id": "runtime", "scenario_id": "C0A_RUNTIME",
        "signed_displacement_id": "CASE", "candidate_parameters": parameters,
        "seed": int(trial["seed"]), "repetition": int(trial["repetition"]),
        "duration_condition": {"id": "C0A_RUNTIME_DURATION", "value": float(trial["duration_s"]) / t_min},
    }
    schedule_path = runtime_root / "runtime_schedule.json"
    schedule_path.write_text(json.dumps({"entries": [entry]}, indent=2) + "\n")
    state_path = runtime_root / "runtime_state.json"
    state_path.write_text("{}\n")
    return schedule_path, config_path, state_path


def normalized_metrics(runtime_metrics, failure_reason, spec_limits):
    row = runtime_metrics.get("per_uav", [{}])[0] if runtime_metrics.get("per_uav") else {}
    failures = runtime_metrics.get("hard_failures", [])
    reason = failure_reason or ";".join(failures)
    velocity_peak = row.get("measured_peak_velocity_mps")
    acceleration_peak = row.get("measured_peak_acceleration_mps2")
    jerk_peak = row.get("measured_peak_jerk_mps3")
    return {
        "success": bool(row.get("mission_success", False)) and not failure_reason,
        "failure_reason": reason,
        "tracking_rmse": row.get("tracking_rmse_m"),
        "tracking_rmse_m": row.get("tracking_rmse_m"),
        "final_error": row.get("final_error_m"),
        "final_position_error_m": row.get("final_error_m"),
        "max_position_error_m": row.get("maximum_tracking_error_m"),
        "settling_time_s": row.get("settling_time_s"),
        "peak_velocity": velocity_peak,
        "velocity_peak_mps": velocity_peak,
        "peak_acceleration": acceleration_peak,
        "acceleration_peak_mps2": acceleration_peak,
        # Derived from consecutive measured-velocity finite differences; it is
        # not a commanded-jerk proxy.
        "peak_jerk": jerk_peak,
        "jerk_peak_mps3": jerk_peak,
        "saturation_ratio": row.get("acceleration_saturation_ratio_any_axis"),
        "velocity_limit_ratio": (velocity_peak / spec_limits["velocity"] if (velocity_peak is not None and spec_limits["velocity"] > 0) else None),
        "acceleration_limit_ratio": (acceleration_peak / spec_limits["acceleration"] if (acceleration_peak is not None and spec_limits["acceleration"] > 0) else None),
        "jerk_limit_ratio": (jerk_peak / spec_limits["jerk"] if (jerk_peak is not None and spec_limits["jerk"] > 0) else None),
        "runtime_metrics": runtime_metrics,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial-spec", type=Path, required=True)
    parser.add_argument("--trial-dir", type=Path, required=True)
    args = parser.parse_args()
    spec = json.loads(args.trial_spec.read_text())
    runtime_root = args.trial_dir / "runtime"
    runtime_root.mkdir(exist_ok=True)
    schedule, config, state = write_compatibility_inputs(spec, runtime_root)
    command = [str(VENV), str(OLD_C0A / "scripts" / "run_trial.py"),
               "--trial-id", spec["trial"]["trial_id"], "--state", str(state),
               "--artifact-root", str(runtime_root), "--schedule", str(schedule),
               "--config", str(config)]
    run = subprocess.run(command, cwd=REPO, text=True, capture_output=True)
    (args.trial_dir / "runtime_command.log").write_text(run.stdout + run.stderr)
    old_trial = runtime_root / "raw" / spec["trial"]["trial_id"]
    extraction_failure = ""
    if (old_trial / "manifest.json").exists():
        extract = subprocess.run(
            [str(VENV), str(OLD_C0A / "scripts" / "extract_metrics.py"), str(old_trial)],
            cwd=REPO, env=ros_environment(), text=True, capture_output=True,
        )
        (args.trial_dir / "extract_metrics.log").write_text(extract.stdout + extract.stderr)
        if extract.returncode:
            extraction_failure = "METRIC_EXTRACTION_FAILED"
    else:
        extraction_failure = "RUNTIME_TRIAL_DID_NOT_CREATE_MANIFEST"
    runtime_metrics = json.loads((old_trial / "metrics.json").read_text()) if (old_trial / "metrics.json").exists() else {}
    failure = extraction_failure
    if not failure and run.returncode:
        failure = runtime_metrics.get("hard_failures", ["RUNTIME_TRIAL_FAILED"])[0]
    metrics = normalized_metrics(runtime_metrics, failure, spec["motion_limits"])
    args.trial_dir.mkdir(parents=True, exist_ok=True)
    (args.trial_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"trial_id": spec["trial"]["trial_id"], "success": metrics["success"], "failure_reason": metrics["failure_reason"]}))
    return 0 if metrics["success"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
