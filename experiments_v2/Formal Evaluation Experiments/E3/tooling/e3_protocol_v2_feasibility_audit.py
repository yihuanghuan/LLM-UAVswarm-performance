#!/usr/bin/env python3
"""Deterministic analytic and compile-only audit of corrected E3 protocol v2."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import math
import platform
from pathlib import Path
import sys
from typing import Any, Dict, Iterable, List

from e3_formal_backend import build_runtime_spec
from e3_trial_registry import (
    CONDITIONS,
    POLICY_PATH,
    build_exact_spec,
    canonical_sha256,
    load_yaml,
    scenario_index,
)


E3_DIR = Path(__file__).resolve().parent.parent
V2_PROTOCOL_PATH = E3_DIR.parent / "protocols/E3_protocol_v2.yaml"
V2_REGISTRY_PATH = E3_DIR / "e3_factorial_registry_v2.yaml"
V2_PROTOCOL_SHA256 = "3b1177983058351a443395966fce92ddb91e990e10a1b9b10d44921d8b854ecf"
V2_REGISTRY_SHA256 = "f722d8a917ed6af57a3f75a79ef62720fdafb5835115a66d8e0582eb453d36a3"


def _v2_registry() -> Dict[str, Any]:
    return load_yaml(V2_REGISTRY_PATH)


def _v2_trial_ids(registry: Dict[str, Any]) -> List[str]:
    return [
        f"{scenario['scenario_id']}__{condition}__S{seed}"
        for scenario in registry["scenarios"]
        for condition in CONDITIONS
        for seed in registry["paired_seeds"]
    ]


def _imports() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    for path in (repo_root / "location_allocate", repo_root / "lfs_policy"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))


def _minimum_durations(distance: float, limits: Any) -> Dict[str, float]:
    velocity = 1.875 * distance / limits.velocity
    acceleration = math.sqrt(
        (10.0 / math.sqrt(3.0)) * distance / limits.acceleration
    )
    jerk = (60.0 * distance / limits.jerk) ** (1.0 / 3.0)
    return {
        "velocity_s": velocity,
        "acceleration_s": acceleration,
        "jerk_s": jerk,
        "required_s": max(velocity, acceleration, jerk),
    }


def analytic_rows() -> List[Dict[str, Any]]:
    """Audit all 24 scenario-condition cells using production assignment logic."""
    _imports()
    from location_allocate.motion_limits import minimum_jerk_peaks
    from location_allocate.policy_adapter import load_runtime_policy

    registry = _v2_registry()
    scenarios = scenario_index(registry)
    _configuration, policy = load_runtime_policy(POLICY_PATH)
    safety = policy.resolve_safety(1.0)
    limits = policy.profile.motion_limits
    rows: List[Dict[str, Any]] = []
    for scenario_id in scenarios:
        for condition in CONDITIONS:
            spec = build_exact_spec(
                f"{scenario_id}__{condition}__S{registry['paired_seeds'][0]}",
                registry=registry,
            )
            initial = [
                [float(value) for value in spec["initial_positions_m"][uid]]
                for uid in spec["uav_ids"]
            ]
            targets = [
                [float(value) for value in spec["ordered_targets_m"][uid]]
                for uid in spec["uav_ids"]
            ]
            allocator = policy.allocator_factory(safety.d_hard, safety.d_plan)
            assigned, _metrics = allocator.allocate_mode_with_metrics(
                initial,
                targets,
                spec["duration_s"],
                mode=spec["assignment_mode"],
            )
            distances = [
                math.dist(start, target)
                for start, target in zip(initial, assigned)
            ]
            maximum = max(distances)
            peaks = minimum_jerk_peaks(maximum, spec["duration_s"])
            required = _minimum_durations(maximum, limits)
            tolerance = 1e-12
            feasible = (
                peaks.velocity <= limits.velocity + tolerance
                and peaks.acceleration <= limits.acceleration + tolerance
                and peaks.jerk <= limits.jerk + tolerance
            )
            row = {
                "scenario_id": scenario_id,
                "condition": condition,
                "assignment_mode": spec["assignment_mode"],
                "maximum_assigned_displacement_m": maximum,
                "duration_s": spec["duration_s"],
                "minimum_duration": required,
                "peaks": asdict(peaks),
                "margins": {
                    "velocity": limits.velocity - peaks.velocity,
                    "acceleration": limits.acceleration - peaks.acceleration,
                    "jerk": limits.jerk - peaks.jerk,
                },
                "feasibility": "PASS" if feasible else "FAIL",
                "seed_replications": len(registry["paired_seeds"]),
            }
            row["row_sha256"] = canonical_sha256(row)
            rows.append(row)
    return rows


def compile_all_registered_specs(
    trial_ids: Iterable[str] | None = None,
) -> Dict[str, Any]:
    """Compile every registered exact spec without launching PX4 or Gazebo."""
    registry = _v2_registry()
    ids = list(trial_ids if trial_ids is not None else _v2_trial_ids(registry))
    failures = []
    runtime_hashes = {}
    for trial_id in ids:
        try:
            runtime = build_runtime_spec(build_exact_spec(trial_id, registry=registry))
            runtime_hashes[trial_id] = runtime["runtime_spec_sha256"]
        except Exception as exc:  # retained in deterministic audit evidence
            failures.append({
                "trial_id": trial_id,
                "error_type": type(exc).__name__,
                "error": str(exc),
            })
    return {
        "checked": len(ids),
        "passed": len(ids) - len(failures),
        "failed": len(failures),
        "failures": failures,
        "runtime_spec_hashes": runtime_hashes,
        "status": "PASS" if not failures else "FAIL",
    }


def build_audit() -> Dict[str, Any]:
    _imports()
    import numpy
    import scipy

    rows = analytic_rows()
    compiler = compile_all_registered_specs()
    registry = _v2_registry()
    analytic_passes = sum(row["feasibility"] == "PASS" for row in rows)
    trial_count = len(_v2_trial_ids(registry))
    report = {
        "audit_type": "E3_protocol_v2_analytic_and_compile_audit_v1",
        "dataset_class": "engineering_validation",
        "accepted_formal_result": False,
        "result_notice": "NOT_FORMAL_RESULT",
        "formal_cursor_consumed": False,
        "analytic_environment": {
            "python_executable": sys.executable,
            "python_version": platform.python_version(),
            "numpy_version": numpy.__version__,
            "scipy_version": scipy.__version__,
            "role": "production ROS/PX4 formal execution interpreter",
        },
        "protocol_sha256": V2_PROTOCOL_SHA256,
        "registry_sha256": V2_REGISTRY_SHA256,
        "population": {
            "scenarios": len(registry["scenarios"]),
            "conditions": len(CONDITIONS),
            "seeds": len(registry["paired_seeds"]),
            "registered_trials": trial_count,
        },
        "analytic": {
            "cells_checked": len(rows),
            "cells_passed": analytic_passes,
            "cells_failed": len(rows) - analytic_passes,
            "registered_trials_inheriting_pass": (
                trial_count if analytic_passes == len(rows) else None
            ),
            "rows": rows,
            "status": "PASS" if analytic_passes == len(rows) else "FAIL",
        },
        "production_compiler": compiler,
    }
    report["status"] = (
        "PASS"
        if report["analytic"]["status"] == "PASS"
        and compiler["status"] == "PASS"
        else "FAIL"
    )
    report["audit_sha256"] = canonical_sha256(report)
    return report


def markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# E3 protocol v2 analytic feasibility audit",
        "",
        "| Scenario | Condition | Assignment | D_max (m) | T (s) | v_peak | a_peak | j_peak | Status |",
        "|---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in report["analytic"]["rows"]:
        peaks = row["peaks"]
        lines.append(
            f"| {row['scenario_id']} | {row['condition']} | {row['assignment_mode']} "
            f"| {row['maximum_assigned_displacement_m']:.12f} "
            f"| {row['duration_s']:.1f} | {peaks['velocity']:.12f} "
            f"| {peaks['acceleration']:.12f} | {peaks['jerk']:.12f} "
            f"| {row['feasibility']} |"
        )
    lines.extend([
        "",
        f"Analytic cells: {report['analytic']['cells_passed']}/{report['analytic']['cells_checked']} PASS.",
        f"Registered trials: {report['analytic']['registered_trials_inheriting_pass']}/{report['population']['registered_trials']} analytically feasible.",
        f"Production compiler: {report['production_compiler']['passed']}/{report['production_compiler']['checked']} PASS.",
        f"Overall: {report['status']}.",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args()
    report = build_audit()
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    if args.markdown_output:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(markdown(report), encoding="utf-8")
    print(json.dumps({
        "status": report["status"],
        "analytic": {
            "checked": report["analytic"]["cells_checked"],
            "passed": report["analytic"]["cells_passed"],
        },
        "production_compiler": {
            "checked": report["production_compiler"]["checked"],
            "passed": report["production_compiler"]["passed"],
        },
        "audit_sha256": report["audit_sha256"],
    }, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
