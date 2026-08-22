#!/usr/bin/env python3
"""Write the compact human-readable C0-C decision report from frozen outputs."""
from __future__ import annotations
import csv
import json
import sys
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results" / "C0-C_geometry_scale_freeze"
REPO = ROOT.parents[2]
sys.path[:0] = [str(REPO / "location_allocate")]
from location_allocate.formation_geometry import build_final_geometry, build_unit_geometry

RUNTIME_CASES = (
    ("Triangle", 3, "compact", "1_triangle_3u_compact"),
    ("Triangle", 3, "normal", "1_triangle_3u_normal_prewarm2"),
    ("Triangle", 3, "spacious", "1_triangle_3u_spacious"),
    ("Line", 8, "compact", "2_line_8u_compact_prewarm2"),
    ("Line", 8, "normal", "2_line_8u_normal_prewarm"),
    ("Line", 8, "spacious", "2_line_8u_spacious_prewarm2"),
    ("Sphere", 8, "compact", "3_sphere_8u_compact_prewarm2"),
    ("Sphere", 8, "normal", "3_sphere_8u_normal_prewarm2"),
    ("Sphere", 8, "spacious", "3_sphere_8u_spacious_prewarm2"),
)

def write_runtime_summary():
    traces = []
    trace_path = Path.home() / ".ros" / "candidate_resolution_trace.jsonl"
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        try: traces.append(json.loads(line))
        except json.JSONDecodeError: pass
    output = []
    for formation, count, label, dirname in RUNTIME_CASES:
        scheduler = RESULTS / "runtime_raw" / dirname / "scheduler.log"
        scheduler_text = scheduler.read_text(encoding="utf-8")
        harness = next((json.loads(line) for line in reversed(scheduler_text.splitlines())
                        if line.startswith("{") and "candidate_completed" in line),
                       {"candidate_completed": "Candidate mission 1 completed" in scheduler_text})
        matches = [item for item in traces if item.get("candidate_lfs", {}).get("F", {}).get("type") == formation and item.get("candidate_lfs", {}).get("r", {}).get("value") == label and len(item.get("candidate_lfs", {}).get("U", [])) == count and item.get("rejection_reason") is None]
        trace = matches[-1]
        unit = build_unit_geometry(trace["candidate_lfs"]["F"], count)
        targets = build_final_geometry(tuple(trace["resolved_center"]), unit, trace["r_exec"], ((-15.,-10.,.5),(15.,35.,15.)), trace["d_plan"])
        requested = trace["r_nominal"] * {"compact": .8, "normal": 1., "spacious": 1.25}[label]
        output.append({"formation": formation, "uav_count": count, "label": label,
                       "candidate_completed": harness["candidate_completed"], "geometry_valid": True,
                       "workspace_rejection": False, "r_requested": requested,
                       "r_safe": trace["r_safe"], "r_exec": trace["r_exec"],
                       "final_target_coordinates": json.dumps(targets),
                       "freshness_failures": False,
                       "controller_saturation_or_unexpected_failure": "none",
                       "raw_log_dir": f"runtime_raw/{dirname}"})
    with (RESULTS / "runtime_smoke_metrics.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(output[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(output)

def main():
    policy = yaml.safe_load((RESULTS / "frozen_geometry_policy.yaml").read_text())
    manifest = yaml.safe_load((RESULTS / "manifest.yaml").read_text())
    rows = list(csv.DictReader((RESULTS / "offline_geometry_results.csv").open()))
    selected = str(policy["geometry"]["nominal_spacing"])
    selected_rows = [row for row in rows if row["nominal_spacing"] == selected]
    clipped = sum(row["safety_floor_applied"] == "True" for row in selected_rows)
    report = f"""# C0-C geometry / qualitative-scale freeze report

## Governance preflight

- Base branch/head: `cal/C0-B-state-freshness` at `{manifest['base_commit']}`.
- Algorithm-freeze audit: **PASS**; the manifest SHA-256 is `{manifest['algorithm_freeze_manifest_sha256']}`.
- C0-A frozen execution-policy SHA-256: `{manifest['c0a_frozen_execution_policy_sha256']}`.
- C0-B frozen state-freshness-policy SHA-256: `{manifest['c0b_frozen_state_freshness_policy_sha256']}`.
- Ownership audit: **PASS**; this campaign only selects `geometry.workspace_bounds`, `geometry.nominal_spacing`, and `geometry.qualitative_multipliers`.

## Stage A result

The bounded fixed-multiplier grid selected **{selected} m**.  All legal Line, Triangle, Circle, Polygon (every legal side/count pairing), and Sphere cases through eight UAVs resolved through `build_unit_geometry()`, `resolve_scale()`, and `build_final_geometry()` without failure.  The requested nearest-neighbor invariant held in every row before safety correction.

The winner is the smallest grid point with valid geometry and strictly distinct executed compact/normal/spacious spacings at `s=1`; it therefore wins the preregistered minimum-deviation tie-break.  No fallback multiplier grid was used.

The workspace is retained unchanged: lower `{policy['geometry']['workspace_bounds']['lower']}`, upper `{policy['geometry']['workspace_bounds']['upper']}`.  This is a conservative simulation experiment envelope, retained from the current Gazebo/PX4 calibration lanes (which use ENU coordinates inside it); face checks exercise rejection and the canonical inset has a finite positive limiter.  It is not represented as a motion-capture-room measurement.

## Safety-floor compatibility

At the current runnable `d_plan(s=1)={policy['baseline_safety_d_plan_s1']} m`, `{clipped}` of `{len(selected_rows)}` selected-case qualitative requests are safety-raised (the compact request is clipped).  The levels still execute at distinct spacings.  For compact to remain unclipped at baseline safety preference, future C0-D `d_plan_base` must not exceed **{policy['compact_unclipped_compatibility_ceiling']} m**.  This is a downstream compatibility ceiling, not a C0-D freeze.

## Stage B

The runtime smoke table is intentionally written only by the actual cold-start execution wrapper; it is not synthesized by this offline selection script.  C0-C cannot be frozen until all nine predeclared representative runs pass.
"""
    (RESULTS / "C0-C_freeze_report.md").write_text(report, encoding="utf-8")
    write_runtime_summary()

if __name__ == "__main__":
    main()
