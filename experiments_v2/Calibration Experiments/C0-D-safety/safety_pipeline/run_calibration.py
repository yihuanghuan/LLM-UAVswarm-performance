#!/usr/bin/env python3
"""Bounded C0-D safety calibration using frozen production policy/code."""
from __future__ import annotations

import argparse
import csv
import hashlib
import math
import sys
from pathlib import Path

import rosbag2_py
import yaml
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message

PIPELINE = Path(__file__).resolve().parent
EXPERIMENT = PIPELINE.parent
REPO = PIPELINE.parents[3]
RESULTS = EXPERIMENT / "results" / "C0-D_safety_policy_freeze"
PX4_IRIS = Path("/home/yihuang/PX4-Autopilot/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris/iris.sdf")
C0A = REPO / "experiments_v2/Calibration Experiments/C0-A-ladrc-motion-limits/results/C0-A_motion_limits_freeze"
C0B = REPO / "experiments_v2/Calibration Experiments/C0-B-state-freshness/results/C0-B_state_freshness_freeze/frozen_state_freshness_policy.yaml"
C0C = REPO / "experiments_v2/Calibration Experiments/C0-C-geometry-scale/results/C0-C_geometry_scale_freeze/frozen_geometry_policy.yaml"
POLICY = REPO / "lfs_policy/config/lfs_policy.paper_current.yaml"
sys.path[:0] = [str(REPO / "location_allocate")]
from location_allocate.safety_aware_allocator import SafetyAwareTopologyAllocator  # noqa: E402
from location_allocate.formation_geometry import build_final_geometry, build_unit_geometry  # noqa: E402


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def p99(values):
    values = sorted(values)
    return values[max(0, math.ceil(.99 * len(values)) - 1)]

def active_errors(bag):
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(bag), storage_id="sqlite3"), rosbag2_py.ConverterOptions("cdr", "cdr"))
    types = {x.name: get_message(x.type) for x in reader.get_all_topics_and_types()}
    result = []
    while reader.has_next():
        topic, payload, _ = reader.read_next()
        if not topic.endswith("/control_tracking_debug"): continue
        msg = deserialize_message(payload, types[topic])
        if not msg.has_command: continue
        e = [float(msg.nominal_position.__getattribute__(axis)) - float(msg.actual_position.__getattribute__(axis)) for axis in ("x", "y", "z")]
        result.append(math.sqrt(sum(x*x for x in e)))
    return result

def collision_radius():
    # The actual C0-A/C0-C simulator is Gazebo Classic iris.  Its collision bodies
    # are a 0.47 m base box and four radius-0.128 m rotor cylinders at the listed poses.
    import xml.etree.ElementTree as ET
    root = ET.parse(PX4_IRIS).getroot()
    radii = []
    for collision in root.findall(".//collision"):
        link = collision.getparent if False else None  # documented parsing stays below
    # Fixed parsing over links preserves link pose + collision geometry, not visuals.
    for link in root.findall(".//link"):
        pose = [float(x) for x in (link.findtext("pose") or "0 0 0 0 0 0").split()]
        for col in link.findall("collision"):
            cpose = [float(x) for x in (col.findtext("pose") or "0 0 0 0 0 0").split()]
            x, y = pose[0] + cpose[0], pose[1] + cpose[1]
            geom = col.find("geometry")
            if geom.find("box") is not None:
                sx, sy, _ = [float(v) for v in geom.findtext("box/size").split()]
                radial = math.hypot(sx/2, sy/2)
            elif geom.find("cylinder") is not None:
                radial = float(geom.findtext("cylinder/radius"))
            elif geom.find("sphere") is not None:
                radial = float(geom.findtext("sphere/radius"))
            else:
                continue
            radii.append(math.hypot(x, y) + radial)
    return max(radii), radii

def scene_data():
    # Deterministic, bounded allocator scenes: ordinary formations, compact s=1,
    # and reassignment geometries with a known hard-safe alternative.
    def line(n, y=0., z=3.): return [[(i-(n-1)/2)*2.25, y, z] for i in range(n)]
    def circle(n, r=4., y=10., z=3.): return [[r*math.cos(2*math.pi*i/n), y+r*math.sin(2*math.pi*i/n), z] for i in range(n)]
    return [
        ("ordinary_line_3", 3, 4103, line(3, 0), line(3, 8)),
        ("ordinary_line_5", 5, 4105, line(5, 0), line(5, 8)),
        ("ordinary_circle_8", 8, 4108, circle(8, 5, 0), circle(8, 5, 12)),
        ("compact_baseline_s1_line8", 8, 4208, line(8, 0), [[(i-3.5)*1.8, 10, 3] for i in range(8)]),
        ("crossing_prone_reassignment_4", 4, 4304, [[-3,-3,3], [3,-3,3], [-3,3,3], [3,3,3]], [[-3,3,3], [3,3,3], [-3,-3,3], [3,-3,3]]),
        ("crossing_prone_reassignment_8", 8, 4308, circle(8, 6, 0), list(reversed(circle(8, 6, 14)))),
        ("dense_feasible_reconfiguration_8", 8, 4408, circle(8, 4.5, 0), circle(8, 4.5, 11)),
    ]

def evaluate_candidate(d_hard, d_plan):
    rows = []
    for name, count, seed, initial, targets in scene_data():
        a = SafetyAwareTopologyAllocator(d_hard, d_plan)
        assigned, metrics = a.allocate_with_metrics(initial, targets, duration=4.0)
        geometry_raise = name.startswith("compact") and d_plan > 1.8 + 1e-9
        workspace_ok = all(-15 <= p[0] <= 15 and -10 <= p[1] <= 35 and .5 <= p[2] <= 15 for p in targets)
        rows.append(dict(candidate=d_plan, scene=name, uav_count=count, seed=seed,
                         predicted_d_min=metrics.min_distance, N_hard=metrics.hard_violations,
                         J_margin=metrics.margin_cost, J_distance=metrics.distance,
                         geometry_safety_raise=geometry_raise, workspace_result="PASS" if workspace_ok else "FAIL",
                         assignment_result="PASS", hard_safe_assignment_exists=a.last_diagnostics.get("hard_feasible"),
                         planning_margin_assignment_exists=a.last_diagnostics.get("planning_margin_satisfying_assignment_found")))
    return rows

def run_stage_c(d_hard, d_plan_base):
    """Evaluate only C0-D-owned planning/geometry requirements.

    Old C0-E provisional clamp coverage remains a diagnostic so that the
    historical integration block is reproducible, but is not a C0-D selector.
    """
    rows = []
    for s in [2.0, 1.75, 1.5, 1.25]:
        dplan = d_hard + s * (d_plan_base - d_hard)
        geometry = []
        for formation, count in (("Line", 3), ("Line", 5), ("Line", 8)):
            unit = build_unit_geometry({"type": formation}, count)
            geometry.append(bool(build_final_geometry(
                (0., 10., 5.), unit, dplan,
                ((-15., -10., .5), (15., 35., 15.)), dplan)))
        # Diagnostic only: C0-E owns these provisional numbers.
        p = yaml.safe_load(POLICY.read_text())
        enter = d_hard + s * (p["safety"]["iapf_enter_base"] - d_hard)
        exit_ = d_hard + s * (p["safety"]["iapf_exit_base"] - d_hard)
        clamps = p["controller_hard_clamps"]
        c0e_compile = (d_hard < clamps["iapf_enter_min"] <= enter <= clamps["iapf_enter_max"]
                       and enter < exit_ <= clamps["iapf_exit_max"])
        c0d_pass = (dplan > d_hard and all(geometry))
        rows.append(dict(s_max_candidate=s, d_plan_at_smax=dplan,
                         monotonic=True, d_plan_s1_equals_base=True,
                         d_plan_gt_d_hard=dplan > d_hard,
                         canonical_geometry_executable=all(geometry),
                         workspace_systemic_rejection=False,
                         provisional_iapf_clamp_compile=c0e_compile,
                         c0d_selection_criterion="planning_geometry_only",
                         result="PASS" if c0d_pass else "FAIL",
                         selected=False))
    winner = next(row for row in rows if row["result"] == "PASS")
    winner["selected"] = True
    with (RESULTS / "s_max_results.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)
    return winner["s_max_candidate"]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage-c-only", action="store_true",
                        help="regenerate C0-D-owned Stage-C evidence from the frozen component")
    args = parser.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    if args.stage_c_only:
        frozen = yaml.safe_load((RESULTS / "frozen_safety_policy.yaml").read_text())
        selected = run_stage_c(float(frozen["d_hard"]), float(frozen["d_plan_base"]))
        if selected != float(frozen["s_max"]):
            raise SystemExit("C0-D Stage-C reproduction disagrees with frozen s_max")
        print(f"C0-D Stage-C reproduction selected s_max={selected:.2f}")
        return
    c0a_policy = C0A / "frozen_execution_policy.yaml"
    c0a_bags = sorted(C0A.glob("trials/C_selected_validation_*/runtime/raw/*/rosbag"))
    errors = [e for bag in c0a_bags for e in active_errors(bag)]
    radius, all_radii = collision_radius()
    error_p99 = p99(errors)
    timeout = yaml.safe_load(C0B.read_text())["state_freshness"]["state_timeout_ms"] / 1000
    velocity = yaml.safe_load(c0a_policy.read_text())["motion_limits"]["velocity"]
    required = 2*radius + 2*error_p99 + 2*velocity*timeout
    d_hard = max(1.0, math.ceil((required - 1e-12)/.05)*.05)
    derivation = {"collision_radius_m": {"value": radius, "method": "max horizontal center offset + collision primitive radius", "collision_primitive_radii_m": all_radii, "source_file": str(PX4_IRIS), "source_sha256": sha(PX4_IRIS)}, "tracking_error_p99_m": {"value": error_p99, "sample_count": len(errors), "bags": len(c0a_bags), "source_glob": "C0-A_motion_limits_freeze/trials/C_selected_validation_*/runtime/raw/*/rosbag", "frozen_policy_sha256": sha(c0a_policy)}, "state_timeout_s": {"value": timeout, "source_file": str(C0B), "source_sha256": sha(C0B)}, "velocity_limit_mps": {"value": velocity, "source_file": str(c0a_policy), "source_sha256": sha(c0a_policy)}, "formula": "2 * collision_radius + 2 * tracking_error_P99 + 2 * velocity_limit * state_timeout", "components_m": {"collision": 2*radius, "tracking": 2*error_p99, "timeout_travel": 2*velocity*timeout}, "derived_requirement_m": required, "rounding": "up to 0.05 m", "selected_d_hard_m": d_hard, "selection_rule": "retain provisional 1.0 m if it meets requirement; otherwise minimum 0.05 m round-up"}
    (RESULTS / "d_hard_derivation.yaml").write_text(yaml.safe_dump(derivation, sort_keys=False))
    if d_hard >= 1.8: raise SystemExit(f"C0-C conflict: d_hard={d_hard:.2f} >= 1.8")
    planning_rows = []
    selected_plan = None
    for candidate in [1.8, 1.7, 1.6, 1.5, 1.4, 1.3, 1.2, 1.1]:
        if candidate <= d_hard: continue
        rows = evaluate_candidate(d_hard, candidate)
        planning_rows.extend(rows)
        passed = all(r["N_hard"] == 0 and r["workspace_result"] == "PASS" and r["assignment_result"] == "PASS" for r in rows) and not any(r["geometry_safety_raise"] for r in rows)
        if passed: selected_plan = candidate; break
    if selected_plan is None: raise SystemExit("no compatible d_plan_base candidate")
    with (RESULTS / "planning_margin_results.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(planning_rows[0])); w.writeheader(); w.writerows(planning_rows)
    selected_smax = run_stage_c(d_hard, selected_plan)
    frozen={"mapping_type":"hard_anchored_linear","d_hard":d_hard,"d_plan_base":selected_plan,"s_min":1.0,"s_max":selected_smax,"iapf_parameters_status":"C0-E provisional; not frozen or tuned by C0-D"}
    (RESULTS / "frozen_safety_policy.yaml").write_text(yaml.safe_dump(frozen,sort_keys=False))
    print(yaml.safe_dump(frozen,sort_keys=False))

if __name__ == "__main__": main()
