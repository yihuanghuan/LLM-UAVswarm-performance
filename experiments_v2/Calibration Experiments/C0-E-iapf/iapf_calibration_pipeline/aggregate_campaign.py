#!/usr/bin/env python3
"""Aggregate immutable C0-E trial manifests/metrics into committed CSVs."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


FIELDS = (
    "trial_id", "stage", "candidate", "scene", "scene_family", "s",
    "cold_start", "result", "failure_reason", "candidate_completed",
    "metric_extraction_success", "scene_semantics_valid",
    "scene_initially_safe", "critical_pair",
    "initial_pair_distance_m", "initial_critical_distance_m",
    "relative_closing_metric", "lateral_offset_m",
    "relative_vertical_speed_mps", "neighbor_count",
    "min_pair_distance_m", "hard_violation_count",
    "hard_violation_duration_s", "mission_failure", "stall", "timeout",
    "iapf_active_duration_s", "activation_count", "deactivation_count",
    "chatter_toggle_count", "integrated_position_modulation",
    "peak_position_modulation", "integrated_acceleration_modulation",
    "peak_acceleration_modulation", "clamp_activity", "tracking_rmse_m",
    "final_error_m", "acceleration_saturation_ratio", "control_mode",
    "dispatch", "runtime", "policy_sha256", "scene_definitions_sha256",
    "mission_sha256", "raw_dir",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--one-valid-per-scene", action="store_true")
    validity = parser.add_mutually_exclusive_group()
    validity.add_argument("--valid-runtime-only", action="store_true")
    validity.add_argument("--invalid-runtime-only", action="store_true")
    args = parser.parse_args()
    rows = []
    for manifest_path in sorted(args.root.glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("stage") != args.stage:
            continue
        metrics_path = manifest_path.with_name("metrics.json")
        metrics = json.loads(metrics_path.read_text()) if metrics_path.is_file() else {}
        row = {**manifest, **metrics}
        row["critical_pair"] = json.dumps(row.get("critical_pair"))
        row["raw_dir"] = str(manifest_path.parent.relative_to(args.root.parent))
        rows.append({field: row.get(field) for field in FIELDS})
    def valid_runtime(row):
        return (
            row["result"] == "PASS"
            and row["candidate_completed"] is True
            and row["metric_extraction_success"] is True
            and row["scene_semantics_valid"] is True
            and row["scene_initially_safe"] is True
        )
    if args.valid_runtime_only:
        rows = [row for row in rows if valid_runtime(row)]
    elif args.invalid_runtime_only:
        rows = [row for row in rows if not valid_runtime(row)]
    if args.one_valid_per_scene:
        selected = {}
        for row in rows:
            if (row["result"] == "PASS" and row["scene_semantics_valid"] is True
                    and row["scene_initially_safe"] is True
                    and row["hard_violation_count"] == 0):
                selected.setdefault(row["scene"], row)
        rows = [selected[scene] for scene in ("S1", "S2", "S3", "S4", "S5")
                if scene in selected]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=FIELDS, lineterminator="\n"
        )
        writer.writeheader(); writer.writerows(rows)
    print(f"wrote {len(rows)} rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
