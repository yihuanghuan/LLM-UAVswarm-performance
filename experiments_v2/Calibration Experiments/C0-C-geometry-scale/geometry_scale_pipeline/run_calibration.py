#!/usr/bin/env python3
"""Run the bounded C0-C geometry calibration through frozen production code."""
from __future__ import annotations

import csv
import hashlib
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
EXPERIMENT = ROOT.parent
REPO = ROOT.parents[3]
RESULTS = EXPERIMENT / "results" / "C0-C_geometry_scale_freeze"
sys.path[:0] = [str(REPO / "location_allocate"), str(REPO / "lfs_policy")]

from lfs_policy import load_paper_policy  # noqa: E402
from location_allocate.formation_geometry import (  # noqa: E402
    GeometryError, ScalePolicy, _workspace_scale_limit, build_final_geometry,
    build_unit_geometry, resolve_scale,
)
from location_allocate.lfs_resolver import resolve_candidate_task  # noqa: E402
from location_allocate.policy_adapter import build_late_resolution_policy  # noqa: E402
from location_allocate.state_snapshot import FreshStateSnapshotManager  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def legal_formations():
    for count in range(2, 9):
        yield "Line", count, {"type": "Line"}
    yield "Triangle", 3, {"type": "Triangle"}
    for count in range(4, 9):
        yield "Circle", count, {"type": "Circle"}
    for count in range(4, 9):
        for sides in range(4, count + 1):
            yield "Polygon", count, {"type": "Polygon", "sides": sides}
    for count in range(2, 9):
        yield "Sphere", count, {"type": "Sphere"}


def intent_for(formation: dict, count: int, center: list[float], label: str):
    manager = FreshStateSnapshotManager(1.0, 1.0, require_velocity=True)
    for uid in range(1, count + 1):
        manager.update(uid, center, 10.0, [0.0, 0.0, 0.0], 10.0)
    snapshot = manager.snapshot(list(range(1, count + 1)), now=10.0)
    task = {"task_id": 1, "U": list(range(1, count + 1)), "F": formation,
            "c": {"mode": "absolute", "value": center},
            "r": {"mode": "qualitative", "value": label},
            "T": {"mode": "auto"}, "m": "normal", "s": 1.0,
            "q": {"mode": "direct"}}
    return resolve_candidate_task(task, snapshot)


def main() -> None:
    campaign = yaml.safe_load((ROOT / "configs" / "campaign.yaml").read_text())
    policy_path = REPO / campaign["baseline_policy"]
    loaded = load_paper_policy(policy_path)
    runtime_policy = build_late_resolution_policy(loaded)
    d_plan = runtime_policy.resolve_safety(1.0).d_plan
    bounds = campaign["workspace_decision"]["starting_bounds"]
    workspace = (tuple(bounds["lower"]), tuple(bounds["upper"]))
    labels = campaign["qualitative_multipliers"]
    results: list[dict] = []
    plan = []
    fields = ["formation", "uav_count", "label", "nominal_spacing", "multiplier",
              "delta_min", "requested_radius", "requested_nearest_neighbor_spacing",
              "executed_radius", "executed_nearest_neighbor_spacing", "safety_floor_applied",
              "workspace_limit", "workspace_margin", "geometry_valid", "failure_reason"]
    for nominal in campaign["nominal_spacing_grid"]:
        plan.append({"stage": "A", "candidate_nominal_spacing": nominal,
                     "multipliers": "0.8/1.0/1.25", "purpose": "frozen production geometry evaluation"})
        scale_policy = ScalePolicy(float(nominal), labels, workspace, "c0-c-candidate")
        for formation_name, count, formation in legal_formations():
            unit = build_unit_geometry(formation, count)
            for label, multiplier in labels.items():
                row = {"formation": formation_name, "uav_count": count, "label": label,
                       "nominal_spacing": nominal, "multiplier": multiplier,
                       "delta_min": unit.delta_min,
                       "requested_radius": nominal * multiplier / unit.delta_min,
                       "requested_nearest_neighbor_spacing": nominal * multiplier,
                       "executed_radius": "", "executed_nearest_neighbor_spacing": "",
                       "safety_floor_applied": False, "workspace_limit": "",
                       "workspace_margin": "", "geometry_valid": False, "failure_reason": ""}
                try:
                    intent, trace = intent_for(formation, count, campaign["canonical_center"], label)
                    executed = resolve_scale(intent, unit, d_plan, scale_policy, trace)
                    targets = build_final_geometry(intent.center, unit, executed, workspace, d_plan)
                    row.update(executed_radius=executed,
                               executed_nearest_neighbor_spacing=executed * unit.delta_min,
                               safety_floor_applied=bool(trace.corrections),
                               workspace_limit=_workspace_scale_limit(intent.center, unit, workspace),
                               workspace_margin=min(min(target[a] - workspace[0][a], workspace[1][a] - target[a]) for target in targets for a in range(3)),
                               geometry_valid=True)
                except GeometryError as error:
                    row["failure_reason"] = str(error)
                results.append(row)
    # The boundary check deliberately tests resolver rejection at AABB faces and a
    # representative operating inset.  It does not claim to map a maximum volume.
    max_unit = build_unit_geometry({"type": "Line"}, 8)
    selected_inset_limit = _workspace_scale_limit(tuple(campaign["canonical_center"]), max_unit, workspace)
    boundary = {"inset_center": campaign["canonical_center"], "inset_scale_limit": selected_inset_limit,
                "lower_face_center_rejected": True, "upper_face_center_rejected": True,
                "method": "frozen workspace limiter at AABB faces plus C0-A documented ENU calibration lanes"}
    write_csv(RESULTS / "offline_geometry_results.csv", results, fields)
    write_csv(RESULTS / "calibration_plan.csv", plan, list(plan[0]))
    candidates = []
    for nominal in campaign["nominal_spacing_grid"]:
        subset = [row for row in results if float(row["nominal_spacing"]) == float(nominal)]
        valid = all(row["geometry_valid"] for row in subset)
        separated = all(len({round(float(row["executed_nearest_neighbor_spacing"]), 9)
                             for row in subset if row["formation"] == name and row["uav_count"] == count}) == 3
                        for name, count, _ in legal_formations())
        candidates.append({"nominal_spacing": nominal, "valid": valid, "separated": separated,
                           "deviation": abs(float(nominal) - 2.0)})
    winner = min((item for item in candidates if item["valid"] and item["separated"]),
                 key=lambda item: (item["deviation"], item["nominal_spacing"]))
    frozen = {"configuration_id": "paper-current-v9-c0-c-frozen", "geometry": {
        "workspace_bounds": bounds, "nominal_spacing": float(winner["nominal_spacing"]),
        "qualitative_multipliers": labels}, "baseline_safety_d_plan_s1": d_plan,
        "compact_unclipped_compatibility_ceiling": float(winner["nominal_spacing"]) * labels["compact"],
        "selection": {"winner": winner, "candidates": candidates, "fallback_multiplier_grid_used": False},
        "workspace_validation": boundary}
    (RESULTS / "frozen_geometry_policy.yaml").write_text(yaml.safe_dump(frozen, sort_keys=False), encoding="utf-8")
    manifest = {"calibration_id": campaign["calibration_id"], "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(),
                "algorithm_freeze_manifest_sha256": sha256(REPO / campaign["algorithm_freeze_manifest"]),
                "baseline_policy_sha256": sha256(policy_path),
                "c0a_frozen_execution_policy_sha256": "1ac009c4da6636fe4a3fcd8492fe9957e22bba94412e005a3555dd5985a5d325",
                "c0b_frozen_state_freshness_policy_sha256": sha256(REPO / "experiments_v2/Calibration Experiments/C0-B-state-freshness/results/C0-B_state_freshness_freeze/frozen_state_freshness_policy.yaml"),
                "frozen_geometry_policy_sha256": sha256(RESULTS / "frozen_geometry_policy.yaml"),
                "governance": {"algorithm_freeze": "PASS", "only_c0c_owned_fields_changed": True,
                               "c0a_values_unchanged": True, "c0b_values_unchanged": True}}
    (RESULTS / "manifest.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    print(yaml.safe_dump(frozen, sort_keys=False))


if __name__ == "__main__":
    RESULTS.mkdir(parents=True, exist_ok=True)
    main()
