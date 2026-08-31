#!/usr/bin/env python3
"""Offline allocator, analytic-geometry, and motion audit for B-02 amendment v1."""

from __future__ import annotations

from dataclasses import asdict
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

from e3_formal_backend import build_runtime_spec
from e3_trial_registry import POLICY_PATH
from e3_v4_qualification import AMENDMENT_GRID_PATH, build_candidate_spec, load_yaml


TOOLING_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLING_DIR.parents[3]
for path in (REPO_ROOT / "location_allocate", REPO_ROOT / "lfs_policy"):
    sys.path.insert(0, str(path))

from location_allocate.motion_limits import minimum_jerk_peaks  # noqa: E402
from location_allocate.policy_adapter import load_runtime_policy  # noqa: E402


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build() -> dict:
    amendment = load_yaml(AMENDMENT_GRID_PATH)
    _configuration, policy = load_runtime_policy(POLICY_PATH)
    limits = policy.profile.motion_limits
    peaks = minimum_jerk_peaks(8.0, 8.0)
    rows = []
    for candidate_id in amendment["screening_order"]:
        runtimes = {
            condition: build_runtime_spec(
                build_candidate_spec(candidate_id, condition, 69707)
            )
            for condition in ("P0_F0", "P1_F0")
        }
        compact = amendment["candidates"][candidate_id]
        geometry = amendment["geometries"][compact["geometry"]]
        h = float(geometry["h_m"])
        z_sep = float(geometry["z_separation_m"])
        rows.append({
            "candidate_id": candidate_id,
            "h_m": h,
            "z_separation_m": z_sep,
            "nominal_d23_m": math.hypot(h, z_sep),
            "pure_z_geometric_lower_bound_m": h,
            "P0_assignment": runtimes["P0_F0"]["allocator_diagnostics"]["final_assignment"],
            "P1_assignment": runtimes["P1_F0"]["allocator_diagnostics"]["final_assignment"],
            "P0_predicted_d_min_m": runtimes["P0_F0"]["allocator_metrics"]["min_distance"],
            "P1_predicted_d_min_m": runtimes["P1_F0"]["allocator_metrics"]["min_distance"],
            "P0_predicted_hard_violations": runtimes["P0_F0"]["allocator_metrics"]["hard_violations"],
            "P1_predicted_hard_violations": runtimes["P1_F0"]["allocator_metrics"]["hard_violations"],
            "avoidance_modes": sorted({value["avoidance_mode"] for value in runtimes.values()}),
            "pass": (
                h < 1.5 < math.hypot(h, z_sep)
                and runtimes["P0_F0"]["allocator_diagnostics"]["final_assignment"] == [0, 1, 2, 3]
                and runtimes["P1_F0"]["allocator_diagnostics"]["final_assignment"] == [0, 1, 2, 3]
                and all(value["allocator_metrics"]["hard_violations"] == 0
                        for value in runtimes.values())
                and all(abs(value["allocator_metrics"]["min_distance"] - 2.0) <= 1e-12
                        for value in runtimes.values())
                and all(value["avoidance_mode"] == "off" for value in runtimes.values())
            ),
        })
    motion_pass = (
        peaks.velocity <= limits.velocity
        and peaks.acceleration <= limits.acceleration
        and peaks.jerk <= limits.jerk
    )
    return {
        "schema": "E3_v4_B02_amendment_v1_offline_audit_v1",
        "status": "PASS" if all(row["pass"] for row in rows) and motion_pass else "FAIL",
        "physical_pilots_consumed": 0,
        "F1_attempt_count": 0,
        "amendment_grid_sha256": sha256_file(AMENDMENT_GRID_PATH),
        "motion": {
            "displacement_m": 8.0,
            "duration_s": 8.0,
            "minimum_jerk_peaks": asdict(peaks),
            "frozen_limits": asdict(limits),
            "pass": motion_pass,
        },
        "candidates": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")
    value = build()
    args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    return 0 if value["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
