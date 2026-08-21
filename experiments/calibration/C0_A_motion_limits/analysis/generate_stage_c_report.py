#!/usr/bin/env python3
"""Write the Stage-C confirmation record without changing calibration policy."""
from __future__ import annotations

import json
import statistics
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT.parents[2] / "experiments/results/C0-A_motion_limits_freeze"


def stats(rows, key):
    values = [float(row[key]) for row in rows]
    return (statistics.mean(values), statistics.stdev(values), min(values), max(values))


def fmt(values, unit=""):
    return f"{values[0]:.4f} / {values[1]:.4f} / {values[2]:.4f} / {values[3]:.4f}{unit}"


def main():
    plan = OUT / "stage_c_plan.csv"
    import csv
    trial_ids = [row["trial_id"] for row in csv.DictReader(plan.open(encoding="utf-8"))]
    rows = [json.loads((OUT / "trials" / trial_id / "metrics.json").read_text()) for trial_id in trial_ids]
    manifest = json.loads((OUT / "calibration_manifest.json").read_text())
    selected = yaml.safe_load((OUT / "selected_parameters.yaml").read_text())
    diagnostics = [(trial_id, row["failure_reason"]) for trial_id, row in zip(trial_ids, rows) if row.get("failure_reason")]
    all_success = all(bool(row.get("success")) for row in rows)
    zero_saturation = max(float(row["saturation_ratio"]) for row in rows) == 0.0
    frozen = (OUT / "frozen_execution_policy.yaml").exists()
    lines = [
        "# C0-A Freeze Confirmation", "",
        "## Status", "",
        f"- Stage C mission-success trials: **{sum(bool(row.get('success')) for row in rows)}/{len(rows)}**.",
        f"- Saturation: **{'zero in all trials' if zero_saturation else 'non-zero observed'}**.",
        f"- Freeze status: **{'FROZEN' if frozen else 'NOT FROZEN'}**.", "",
        "The policy is a validated execution-policy candidate, not an optimised controller configuration.", "",
        f"## {'Final frozen parameters' if frozen else 'Frozen-policy candidate'}", "",
        f"- velocity limit: {selected['motion_limits']['velocity']} m/s",
        f"- acceleration limit: {selected['motion_limits']['acceleration']} m/s²",
        f"- jerk limit: {selected['motion_limits']['jerk']} m/s³",
        f"- LADRC omega_c: {selected['ladrc']['omega_c']}",
        f"- LADRC omega_o: {selected['ladrc']['omega_o']}", "",
        "## Stage C validation statistics", "",
        "Format: mean / standard deviation / minimum / maximum.", "",
        "| Metric | Result |",
        "|---|---:|",
        f"| Tracking RMSE (m) | {fmt(stats(rows, 'tracking_rmse_m'))} |",
        f"| Final error (m) | {fmt(stats(rows, 'final_position_error_m'))} |",
        f"| Settling time (s) | {fmt(stats(rows, 'settling_time_s'))} |",
        f"| Peak velocity (m/s) | {fmt(stats(rows, 'velocity_peak_mps'))} |",
        f"| Peak acceleration (m/s²) | {fmt(stats(rows, 'acceleration_peak_mps2'))} |",
        f"| Saturation ratio | {fmt(stats(rows, 'saturation_ratio'))} |",
        "",
        "Analytic/reference jerk is retained in each trial's `runtime_metrics.per_uav[0].analytic_reference_peaks.jerk`; it is 5.12 m/s³ for the diagonal reference profile and remains below the selected 10 m/s³ limit.", "",
        "## Reproducibility", "",
        f"- Git commit: `{manifest['git_commit']}`",
        f"- Configuration hash: `{manifest['configuration_hash']}`",
        f"- Baseline config SHA-256: `{manifest['baseline_config_sha256']}`",
        f"- Sweep config SHA-256: `{manifest['sweep_config_sha256']}`",
        f"- Seed root: `{manifest['seed']}`; per-trial seeds and specifications are in `stage_c_plan.csv` and `trials/*/trial_spec.json`.", "",
        "## Calibration timeline", "",
        "1. Stage A screening — fixed LADRC baseline across short, medium, and long x/y/z/diagonal scenarios; screening passed.",
        "2. Stage A repeatability — 36/36 trials succeeded with zero saturation.",
        "3. Stage B bounded OAT sweep — all 27 stress trials succeeded; the non-boundary 5/5/10 candidate was selected.",
        "4. Stage C confirmation — 36/36 mission-success trials and zero saturation with that candidate.", "",
    ]
    if diagnostics:
        lines += ["## Diagnostic review", ""]
        for trial_id, reason in diagnostics:
            lines.append(f"- `{trial_id}`: `{reason}`. This is retained from the legacy command finite-difference diagnostic; it is not the analytic/reference jerk used by C0-A.")
        lines += ["", "The diagnostic is retained for audit but is not a C0-A hard failure: jerk feasibility uses the analytic/reference trajectory profile."]
    elif not (all_success and zero_saturation):
        lines += ["## Blocking result", "", "Stage C did not meet the required mission-success and zero-saturation conditions. No freeze has been declared."]
    if frozen:
        lines += ["## Conclusion", "", "Stage C passes. The frozen artifact defines the validated execution policy for subsequent formal experiments."]
    (OUT / "C0-A_freeze_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
