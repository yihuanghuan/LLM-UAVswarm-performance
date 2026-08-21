#!/usr/bin/env python3
"""Write the Stage A baseline-validation report from completed trial metrics."""
from __future__ import annotations

import argparse, csv, json, math, statistics
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[2]


def load_yaml(path):
    with path.open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def stats(rows, field):
    values = [number(row.get(field)) for row in rows]
    values = [value for value in values if math.isfinite(value)]
    if not values:
        return "unavailable"
    return f"mean {statistics.mean(values):.4f}; max {max(values):.4f}; min {min(values):.4f}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=ROOT / "configs" / "baseline.yaml")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    baseline = load_yaml(args.baseline)
    output = (args.output_dir or REPO / baseline["output_dir"]).resolve()
    plan = list(csv.DictReader((output / "calibration_plan.csv").open(encoding="utf-8")))
    stage_a = [row for row in plan if row["stage"] == "A" and row["candidate_id"] == "baseline" and row["repetition"] == "1"]
    rows = []
    for trial in stage_a:
        metric_path = output / "trials" / trial["trial_id"] / "metrics.json"
        metric = json.loads(metric_path.read_text()) if metric_path.exists() else {"success": False, "failure_reason": "MISSING_METRICS"}
        for peak, limit, ratio in (("velocity_peak_mps", "velocity", "velocity_limit_ratio"), ("acceleration_peak_mps2", "acceleration", "acceleration_limit_ratio"), ("jerk_peak_mps3", "jerk", "jerk_limit_ratio")):
            if metric.get(ratio) is None and math.isfinite(number(metric.get(peak))):
                metric[ratio] = number(metric[peak]) / float(trial[limit])
        rows.append({**trial, **metric})
    criteria = baseline["criteria"]
    failures = []
    for row in rows:
        bad = (not row.get("success") or bool(row.get("failure_reason")) or
               not math.isfinite(number(row.get("tracking_rmse_m"))) or number(row.get("tracking_rmse_m")) > criteria["max_tracking_rmse_m"] or
               not math.isfinite(number(row.get("final_position_error_m"))) or number(row.get("final_position_error_m")) > criteria["max_final_position_error_m"] or
               not math.isfinite(number(row.get("max_position_error_m"))) or number(row.get("max_position_error_m")) > criteria["max_position_error_m"] or
               not math.isfinite(number(row.get("saturation_ratio"))) or number(row.get("saturation_ratio")) > criteria["max_saturation_ratio"] or
               (criteria["require_settling"] and (not math.isfinite(number(row.get("settling_time_s"))) or number(row.get("settling_time_s")) < 0)))
        if bad: failures.append(row)
    worst = max(rows, key=lambda row: number(row.get("tracking_rmse_m")), default={})
    lines = [
        "# C0-A Stage A — Controller Baseline Validation", "",
        "This is a single-repeat screening pass with fixed LADRC parameters and fixed motion limits; it is not gain tuning or a policy freeze.", "",
        "## Coverage", "",
        f"- Planned/executed cases: {len(stage_a)}/{len(rows)}",
        "- Distances: short, medium, long.",
        "- Directions: x, y, z, diagonal.",
        "- Repetitions completed: 1 per case (repeatability remains pending).", "",
        "## Outcome", "",
        f"- Successes: {sum(bool(row.get('success')) for row in rows)}/{len(rows)}",
        f"- Failures: {len(failures)}",
        f"- Stage A screening: {'PASS' if not failures and len(rows) == len(stage_a) else 'FAIL'}",
        f"- Stage B readiness: {'acceptable for a bounded initial sweep' if not failures and len(rows) == len(stage_a) else 'not acceptable'}; three-repeat confirmation is still required before any freeze.", "",
        "## Metric statistics", "",
        f"- Tracking RMSE (m): {stats(rows, 'tracking_rmse_m')}",
        f"- Final position error (m): {stats(rows, 'final_position_error_m')}",
        f"- Settling time (s): {stats(rows, 'settling_time_s')}",
        f"- Peak velocity (m/s): {stats(rows, 'velocity_peak_mps')}",
        f"- Peak acceleration (m/s²): {stats(rows, 'acceleration_peak_mps2')}",
        f"- Peak jerk (m/s³): {stats(rows, 'jerk_peak_mps3')}",
        f"- Saturation ratio: {stats(rows, 'saturation_ratio')}",
        f"- Velocity-limit utilization: {stats(rows, 'velocity_limit_ratio')}",
        f"- Acceleration-limit utilization: {stats(rows, 'acceleration_limit_ratio')}",
        f"- Jerk-limit utilization: {stats(rows, 'jerk_limit_ratio')}", "",
        "Jerk utilization is diagnostic only: it is an unfiltered second finite difference of PX4 measured velocity and therefore includes estimator/sample noise. It is not used as a Stage A pass/fail condition; analytic reference jerk remains separately bounded by the compiled profile.", "",
        "## Worst-case scenario", "",
        f"- {worst.get('scenario_id', 'unavailable')} ({worst.get('trial_id', 'unavailable')}): tracking RMSE {number(worst.get('tracking_rmse_m')):.4f} m; final error {number(worst.get('final_position_error_m')):.4f} m; saturation {number(worst.get('saturation_ratio')):.4f}.", "",
        "## Failure cases", "",
    ]
    lines += ([f"- {row['trial_id']}: {row.get('failure_reason') or 'threshold violation'}" for row in failures] or ["- None."])
    (output / "stage_A_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"executed": len(rows), "successes": sum(bool(row.get("success")) for row in rows), "failures": len(failures), "worst_case": worst.get("trial_id")}, indent=2))


if __name__ == "__main__":
    main()
