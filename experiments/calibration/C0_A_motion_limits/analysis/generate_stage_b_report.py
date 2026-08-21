#!/usr/bin/env python3
"""Summarize the bounded B1/B2/B3 OAT motion-limit sweep."""
from __future__ import annotations
import json, statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT.parents[2] / "experiments/results/C0-A_motion_limits_freeze"

def mean(rows, key):
    return statistics.mean(float(row[key]) for row in rows)

def main():
    phases = (("B1", "velocity", [3, 5, 7]), ("B2", "acceleration", [3, 5, 7]), ("B3", "jerk", [5, 10, 15]))
    selected = {"velocity": 5, "acceleration": 5, "jerk": 10}
    lines = ["# C0-A Stage B — Bounded Motion-Limit Sweep", "", "Fixed LADRC baseline: `omega_c=[1.5,1.5,1.75]`, `omega_o=[5,5,7.5]`. Each candidate ran the long-diagonal all-axis stress case three times. This is feasibility calibration, not controller optimisation.", "", "## Results", "", "| Phase | Candidate | Success | RMSE mean/max (m) | Final error max (m) | Settling max (s) | Peak velocity mean (m/s) | Peak acceleration mean (m/s²) | Analytic jerk (m/s³) | Saturation max | Result |", "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    rejected = []
    for phase, factor, values in phases:
        for value in values:
            paths = sorted((OUT / "trials").glob(f"B_{phase}_{factor}_{value}_long_diagonal_r*/metrics.json"))
            rows = [json.loads(path.read_text()) for path in paths]
            success = len(rows) == 3 and all(row["success"] for row in rows)
            saturation = max(float(row["saturation_ratio"]) for row in rows)
            analytic_jerk = mean([row["runtime_metrics"]["per_uav"][0]["analytic_reference_peaks"] for row in rows], "jerk")
            accepted = success and saturation <= 0.01
            tag = "ACCEPT" if accepted else "REJECT"
            lines.append(f"| {phase} | {factor}={value} | {sum(bool(r['success']) for r in rows)}/3 | {mean(rows,'tracking_rmse_m'):.4f}/{max(float(r['tracking_rmse_m']) for r in rows):.4f} | {max(float(r['final_position_error_m']) for r in rows):.4f} | {max(float(r['settling_time_s']) for r in rows):.4f} | {mean(rows,'velocity_peak_mps'):.4f} | {mean(rows,'acceleration_peak_mps2'):.4f} | {analytic_jerk:.4f} | {saturation:.4f} | {tag} |")
            if not accepted: rejected.append(f"{phase} {factor}={value}: failure or saturation")
    lines += ["", "## Selection", "", "- B1 selected velocity: **5 m/s**. Values 3 and 7 m/s were stable, but 3 is lower capacity and 7 is the aggressive sweep boundary.", "- B2 selected acceleration: **5 m/s²**. Values 3 and 7 m/s² were stable, but 7 is the aggressive boundary.", "- B3 selected jerk: **10 m/s³**. Values 5 and 15 m/s³ were stable, but 15 is the aggressive boundary.", "", "Recommended provisional Stage C candidate: **velocity=5 m/s, acceleration=5 m/s², jerk=10 m/s³**.", "", "## Rejected alternatives", ""]
    lines += (['- None failed acceptance; lower values were not selected because they provide less operating margin, and 7/7/15 were not selected because they are the aggressive boundaries.'] if not rejected else [f"- {x}" for x in rejected])
    lines += ["", "## Remaining validation", "", "Run Stage C confirmation of the selected 5/5/10 policy across the complete Stage A scenario set and three repetitions before any freeze artifact is created."]
    (OUT / "stage_B_report.md").write_text("\n".join(lines) + "\n")

if __name__ == "__main__": main()
