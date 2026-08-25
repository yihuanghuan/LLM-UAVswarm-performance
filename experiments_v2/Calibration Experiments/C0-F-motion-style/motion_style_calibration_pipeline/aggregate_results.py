#!/usr/bin/env python3
"""Aggregate immutable C0-F raw trials and evaluate calibration gates."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

from common import RAW, RESULTS, SCENES_FILE, STYLES, load_yaml


FIELDS = (
    "trial_id", "stage", "scene", "scene_family", "style", "cold_start", "seed",
    "policy_sha256", "configuration_id", "control_mode", "mission_success",
    "candidate_completed", "T_min_s", "T_exec_s", "motion_style", "style_gain",
    "task_gain", "compiled_omega_c", "compiled_omega_o", "applied_omega_c",
    "applied_omega_o", "analytic_mj_velocity_peak_mps",
    "analytic_mj_acceleration_peak_mps2", "analytic_mj_jerk_peak_mps3",
    "tracking_rmse_m", "final_error_m", "settling_time_s", "overshoot_m",
    "controller_acceleration_saturation_ratio",
    "controller_acceleration_saturation_samples", "profile_clamp_activity",
    "iapf_clamp_activity", "peak_tilt_deg", "hard_safety_violation_count",
    "minimum_pairwise_distance_m", "iapf_activation_fraction",
    "dynamic_feasibility_violation", "compiled_applied_profile_consistent",
    "instability_or_divergence", "persistent_oscillation",
    "explicit_t_invariance", "auto_t_ordering", "condition_result",
    "failure_reason", "raw_dir",
)


def bool_value(value) -> bool:
    return bool(value) and str(value).lower() not in ("false", "0", "none")


def condition_pass(metrics: dict) -> bool:
    return all((
        metrics.get("metric_extraction_success") is True,
        metrics.get("mission_success") is True,
        metrics.get("candidate_completed") is True,
        int(metrics.get("hard_safety_violation_count", 1)) == 0,
        metrics.get("dynamic_feasibility_violation") is False,
        int(metrics.get("profile_clamp_activity", 1)) == 0,
        int(metrics.get("iapf_clamp_activity", 1)) == 0,
        float(metrics.get("controller_acceleration_saturation_ratio", 1.0)) == 0.0,
        metrics.get("compiled_applied_profile_consistent") is True,
        metrics.get("instability_or_divergence") is False,
        metrics.get("persistent_oscillation") is False,
        float(metrics.get("tracking_rmse_m", math.inf)) <= 0.35,
        float(metrics.get("final_error_m", math.inf)) <= 0.30,
        float(metrics.get("iapf_activation_fraction", 1.0)) == 0.0,
    ))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--root", type=Path, default=RAW)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or RESULTS / (
        "screening_results.csv" if args.stage == "screening" else
        "confirmation_results.csv" if args.stage == "confirmation" else
        "style_switch_smoke.csv"
    )
    rows = []
    for manifest_path in sorted(args.root.glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (args.stage == "style_switch" and not manifest["stage"].startswith("style_switch")) or (
            args.stage != "style_switch" and manifest["stage"] != args.stage
        ):
            continue
        metrics_path = manifest_path.with_name("metrics.json")
        metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.is_file() else {}
        row = {**manifest, **metrics}
        try:
            row["raw_dir"] = str(manifest_path.parent.relative_to(RESULTS))
        except ValueError:
            row["raw_dir"] = str(manifest_path.parent)
        row["condition_result"] = "PASS" if condition_pass(metrics) else "FAIL"
        rows.append(row)

    definitions = load_yaml(SCENES_FILE)
    if args.stage in ("screening", "confirmation"):
        groups = {}
        for row in rows:
            groups.setdefault((row["scene"], int(row["cold_start"])), {})[row["style"]] = row
        for (scene_id, _cold), styled in groups.items():
            if set(styled) != set(STYLES):
                for row in styled.values():
                    row["condition_result"] = "FAIL"
                continue
            mode = definitions["scenes"][scene_id]["time_request"]["mode"]
            durations = {style: float(styled[style]["T_exec_s"]) for style in STYLES}
            explicit_pass = mode != "explicit" or max(durations.values()) - min(durations.values()) <= 1e-6
            auto_pass = mode != "auto" or (
                durations["smooth"] > durations["normal"] > durations["aggressive"]
                and all(durations[style] + 1e-9 >= float(styled[style]["T_min_s"]) for style in STYLES)
            )
            for row in styled.values():
                row["explicit_t_invariance"] = explicit_pass if mode == "explicit" else "N/A"
                row["auto_t_ordering"] = auto_pass if mode == "auto" else "N/A"
                if not explicit_pass or not auto_pass:
                    row["condition_result"] = "FAIL"
    else:
        for row in rows:
            row["explicit_t_invariance"] = "N/A"
            row["auto_t_ordering"] = "N/A"

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            cooked = {}
            for field in FIELDS:
                value = row.get(field, "")
                cooked[field] = json.dumps(value, separators=(",", ":")) if isinstance(value, (list, dict)) else value
            writer.writerow(cooked)
    if args.stage == "screening":
        expected = 12
    elif args.stage == "confirmation":
        expected = 24
    else:
        expected = 2 if any(row["stage"] == "style_switch_confirmation" for row in rows) else 1
    passed = len(rows) == expected and all(row["condition_result"] == "PASS" for row in rows)
    print(json.dumps({"stage": args.stage, "rows": len(rows), "expected": expected,
                      "passed": sum(row["condition_result"] == "PASS" for row in rows),
                      "result": "PASS" if passed else "FAIL", "output": str(output)}, sort_keys=True))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
