#!/usr/bin/env python3
"""Summarize all three fixed-parameter Stage A repetitions."""
from __future__ import annotations

import argparse, csv, json, math, statistics
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[3]
METRICS = (
    ("tracking_rmse_m", "Tracking RMSE", "m"),
    ("final_position_error_m", "Final error", "m"),
    ("settling_time_s", "Settling time", "s"),
    ("velocity_peak_mps", "Peak velocity", "m/s"),
    ("acceleration_peak_mps2", "Peak acceleration", "m/s²"),
    ("saturation_ratio", "Saturation ratio", ""),
)


def load_yaml(path):
    with path.open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def summary(rows, field):
    values = [num(row.get(field)) for row in rows]
    values = [value for value in values if math.isfinite(value)]
    if not values:
        return "unavailable"
    deviation = statistics.stdev(values) if len(values) > 1 else 0.0
    return f"mean {statistics.mean(values):.4f}; std {deviation:.4f}; max {max(values):.4f}; min {min(values):.4f}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=ROOT / "configs" / "baseline.yaml")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    baseline = load_yaml(args.baseline)
    output = (args.output_dir or REPO / baseline["output_dir"]).resolve()
    plan = list(csv.DictReader((output / "calibration_plan.csv").open(encoding="utf-8")))
    plan = [row for row in plan if row["stage"] == "A" and row["candidate_id"] == "baseline"]
    rows, missing = [], []
    for record in plan:
        path = output / "trials" / record["trial_id"] / "metrics.json"
        if not path.exists():
            missing.append(record["trial_id"])
            continue
        rows.append({**record, **json.loads(path.read_text())})
    failed = [row for row in rows if not row.get("success") or row.get("failure_reason")]
    by_scenario = defaultdict(list)
    for row in rows:
        by_scenario[row["scenario_id"]].append(row)
    repeat_limit = float(baseline["criteria"]["max_repeatability_spread_m"])
    repeatability_issues = []
    for scenario, values in sorted(by_scenario.items()):
        for field in ("tracking_rmse_m", "final_position_error_m"):
            samples = [num(row.get(field)) for row in values]
            if len(samples) != 3 or not all(math.isfinite(value) for value in samples):
                repeatability_issues.append(f"{scenario}:{field}:incomplete")
            elif max(samples) - min(samples) > repeat_limit:
                repeatability_issues.append(f"{scenario}:{field}:spread>{repeat_limit:.2f}m")
    nonzero_saturation = [row for row in rows if num(row.get("saturation_ratio")) != 0.0]
    worst = max(rows, key=lambda row: num(row.get("tracking_rmse_m")), default={})
    passed = len(rows) == 36 and not missing and not failed and not nonzero_saturation and not repeatability_issues
    lines = [
        "# C0-A Stage A — Repeatability Confirmation", "",
        "All trials use the fixed LADRC baseline and unchanged motion limits. This report is a feasibility/reproducibility check, not controller tuning.", "",
        "## Trial outcome", "",
        f"- Completed trials: {len(rows)}/36",
        f"- Success rate: {sum(bool(row.get('success')) for row in rows)}/{len(rows)}" if rows else "- Success rate: 0/0",
        f"- Failure cases: {len(failed) + len(missing)}",
        f"- Saturation remains zero: {'yes' if not nonzero_saturation and len(rows) == 36 else 'no'}", "",
        "## Aggregate metrics", "",
    ]
    lines.extend(f"- {label} ({unit}): {summary(rows, field)}" for field, label, unit in METRICS)
    lines += ["", "## Worst-case scenario", "", f"- {worst.get('scenario_id', 'unavailable')} ({worst.get('trial_id', 'unavailable')}): tracking RMSE {num(worst.get('tracking_rmse_m')):.4f} m; final error {num(worst.get('final_position_error_m')):.4f} m; settling time {num(worst.get('settling_time_s')):.4f} s.", "", "## Repeatability assessment", "", f"- Per-scenario tracking-RMSE and final-error spread threshold: {repeat_limit:.2f} m.", f"- Tracking metrics repeatable: {'yes' if not repeatability_issues else 'no'}.", f"- Stage A repeatability: {'PASS' if passed else 'FAIL'}.", "", "## Failure or completeness issues", ""]
    issues = [f"- {row['trial_id']}: {row.get('failure_reason') or 'unsuccessful'}" for row in failed]
    issues += [f"- {trial_id}: missing metrics" for trial_id in missing]
    issues += [f"- {issue}" for issue in repeatability_issues]
    issues += [f"- {row['trial_id']}: nonzero saturation {row.get('saturation_ratio')}" for row in nonzero_saturation]
    lines.extend(issues or ["- None."])
    (output / "stage_A_repeatability_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"completed": len(rows), "successes": sum(bool(row.get("success")) for row in rows), "passed": passed, "issues": issues}, indent=2))


if __name__ == "__main__":
    main()
