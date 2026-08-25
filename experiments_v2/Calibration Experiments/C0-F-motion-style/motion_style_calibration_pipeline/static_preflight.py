#!/usr/bin/env python3
"""Fail-closed C0-F ownership, provenance, and semantic preflight."""
from __future__ import annotations

import argparse
import copy
import hashlib
import math
from pathlib import Path
import subprocess
import sys
from typing import Any

import yaml

from common import (
    CANONICAL_POLICY, REPO, RESULTS, SCENES_FILE, START_SHA, STYLES,
    load_yaml, materialize_scene, sha256,
)

sys.path.insert(0, str(REPO / "lfs_policy"))
sys.path.insert(0, str(REPO / "location_allocate"))

from lfs_policy import load_paper_policy  # noqa: E402
from location_allocate.late_resolution import resolve_execution_task  # noqa: E402
from location_allocate.policy_adapter import load_runtime_policy  # noqa: E402
from location_allocate.state_snapshot import FreshStateSnapshotManager  # noqa: E402


FROZEN = {
    "c0_a": (
        "experiments_v2/Calibration Experiments/C0-A-ladrc-motion-limits/results/"
        "C0-A_motion_limits_freeze/frozen_execution_policy.yaml",
        "1ac009c4da6636fe4a3fcd8492fe9957e22bba94412e005a3555dd5985a5d325",
    ),
    "c0_b": (
        "experiments_v2/Calibration Experiments/C0-B-state-freshness/results/"
        "C0-B_state_freshness_freeze/frozen_state_freshness_policy.yaml",
        "fdc7b3fd038ae623699eaefd131028d53a259c22507b320c2775369c23594884",
    ),
    "c0_c": (
        "experiments_v2/Calibration Experiments/C0-C-geometry-scale/results/"
        "C0-C_geometry_scale_freeze/frozen_geometry_policy.yaml",
        "25ab21d7cc688ba3f7e5e94124fdde88795075b263fddf30c41f2d47819a61fa",
    ),
    "c0_d": (
        "experiments_v2/Calibration Experiments/C0-D-safety/results/"
        "C0-D_safety_policy_freeze/frozen_safety_policy.yaml",
        "901bc58803ace3ae8d858996e67065710920b62dda04f12c7c60e7ad1b4fd563",
    ),
    "c0_e": (
        "experiments_v2/Calibration Experiments/C0-E-iapf/results/"
        "C0-E_iapf_freeze/frozen_iapf_policy.yaml",
        "47a491a3906f00833fc25b577b5489a89ddd113a540a778b956032a03c900e48",
    ),
}

OWNED_PATHS = {
    ("timing", "auto_style_factors"),
    ("execution_profile", "style_gains", "smooth"),
    ("execution_profile", "style_gains", "aggressive"),
    ("controller_hard_clamps", "smoothing_alpha"),
}
METADATA_PATHS = {
    ("configuration_id",),
    ("parameter_status", "c0_f_motion_style"),
    ("parameter_status", "algorithm_calibration"),
    ("parameter_status", "semantic_controller"),
    ("provenance", "motion_style"),
}


def git_show_yaml(sha: str, path: str) -> dict[str, Any]:
    raw = subprocess.check_output(["git", "show", f"{sha}:{path}"], cwd=REPO)
    value = yaml.safe_load(raw)
    if not isinstance(value, dict):
        raise RuntimeError(f"base artifact is not a mapping: {path}")
    return value


def flatten(value: Any, prefix: tuple[str, ...] = ()) -> dict[tuple[str, ...], Any]:
    if isinstance(value, dict):
        result: dict[tuple[str, ...], Any] = {}
        for key, item in value.items():
            result.update(flatten(item, prefix + (str(key),)))
        return result
    return {prefix: value}


def ownership_changes(base: dict[str, Any], current: dict[str, Any]) -> tuple[list[str], list[str]]:
    before, after = flatten(base), flatten(current)
    changed = sorted(path for path in before.keys() | after.keys() if before.get(path) != after.get(path))
    permitted = OWNED_PATHS | METADATA_PATHS
    violations = [".".join(path) for path in changed if path not in permitted]
    return [".".join(path) for path in changed], violations


def snapshot():
    manager = FreshStateSnapshotManager(
        0.02208, 0.022043, require_velocity=True,
        allow_receive_time_fallback=False,
    )
    positions = ((-3.0, 5.0, 3.0), (-1.0, 7.0, 3.0),
                 (1.0, 7.0, 3.0), (3.0, 5.0, 3.0))
    for uid, position in enumerate(positions, start=1):
        manager.update(uid, position, 10.0, (0.0, 0.0, 0.0), 10.0)
    return manager.snapshot((1, 2, 3, 4), 10.0)


def snapshot_from_positions(ids, positions):
    manager = FreshStateSnapshotManager(
        0.02208, 0.022043, require_velocity=True,
        allow_receive_time_fallback=False,
    )
    for uid, position in zip(ids, positions):
        manager.update(uid, position, 10.0, (0.0, 0.0, 0.0), 10.0)
    return manager.snapshot(ids, 10.0)


def candidate(style: str, time_request: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": 1, "U": [1, 2, 3, 4], "F": {"type": "Circle"},
        "c": {"mode": "absolute", "value": [4.0, 11.0, 6.0]},
        "r": {"mode": "qualitative", "value": "normal"},
        "T": time_request, "m": style, "s": 1.0, "q": {"mode": "direct"},
    }


def semantic_checks(policy_path: Path) -> dict[str, Any]:
    loaded = load_paper_policy(policy_path)
    config, runtime = load_runtime_policy(policy_path)
    gains = loaded.execution_profile["style_gains"]
    factors = loaded.timing["auto_style_factors"]
    checks: dict[str, Any] = {
        "task_adaptation_identity": loaded.execution_profile["task_adaptation_type"] == "identity",
        "normal_style_gain_identity": gains["normal"] == 1.0,
        "style_gain_ordering": gains["smooth"] < 1.0 < gains["aggressive"],
        "auto_t_factor_ordering": factors["smooth"] > factors["normal"] > factors["aggressive"] >= 1.0,
        "smoothing_alpha_valid": 0.0 < config.controller.smoothing_alpha <= 1.0,
    }
    explicit = {
        style: resolve_execution_task(candidate(style, {"mode": "explicit", "value": 9.0}), snapshot(), runtime)
        for style in STYLES
    }
    explicit_durations = {style: result.executable_lfs.duration for style, result in explicit.items()}
    references = {
        style: [(tuple(result.assigned_targets[index]), result.trace.per_uav_dynamics[index])
                for index in range(len(result.assigned_targets))]
        for style, result in explicit.items()
    }
    checks["explicit_t_invariant"] = len(set(explicit_durations.values())) == 1
    checks["explicit_reference_invariant"] = all(
        references[style] == references["normal"] for style in STYLES
    )
    checks["compiled_task_gain_identity"] = all(
        profile.task_gain == 1.0
        for result in explicit.values() for profile in result.profiles
    )
    automatic = {
        style: resolve_execution_task(candidate(style, {"mode": "auto"}), snapshot(), runtime)
        for style in STYLES
    }
    auto_duration = {style: result.executable_lfs.duration for style, result in automatic.items()}
    checks["auto_t_runtime_ordering"] = (
        auto_duration["smooth"] > auto_duration["normal"] > auto_duration["aggressive"]
    )
    limits = runtime.timing.motion_limits
    peaks_inside = True
    for result in automatic.values():
        for peak in result.trace.per_uav_dynamics:
            peaks_inside &= peak["predicted_v_peak"] <= limits.velocity + 1e-12
            peaks_inside &= peak["predicted_a_peak"] <= limits.acceleration + 1e-12
            peaks_inside &= peak["predicted_j_peak"] <= limits.jerk + 1e-12
    checks["auto_t_analytic_peaks_inside_5_5_10"] = bool(peaks_inside)
    scene_contracts = {}
    definitions = load_yaml(SCENES_FILE)
    for scene_id, scene in definitions["scenes"].items():
        ids = tuple(int(value) for value in scene["participants"])
        spawn = tuple((0.0, 3.0 * uid, 0.83) for uid in ids)
        mission, _ = materialize_scene(scene_id, "normal")
        stage_task = mission["mission"]["nodes"][0]["task"]
        stage = resolve_execution_task(stage_task, snapshot_from_positions(ids, spawn), runtime)
        staged = snapshot_from_positions(ids, stage.assigned_targets)
        resolved = {}
        for style in STYLES:
            styled_mission, _ = materialize_scene(scene_id, style)
            score_task = styled_mission["mission"]["nodes"][1]["task"]
            resolved[style] = resolve_execution_task(score_task, staged, runtime)
        durations = {style: item.executable_lfs.duration for style, item in resolved.items()}
        mode = scene["time_request"]["mode"]
        references_equal = all(
            resolved[style].assigned_targets == resolved["normal"].assigned_targets
            and resolved[style].trace.per_uav_dynamics == resolved["normal"].trace.per_uav_dynamics
            for style in STYLES
        ) if mode == "explicit" else True
        duration_contract = (
            len(set(durations.values())) == 1 if mode == "explicit" else
            durations["smooth"] > durations["normal"] > durations["aggressive"]
        )
        safe = all(item.final_metrics.hard_violations == 0 for item in resolved.values())
        feasible = all(
            peak["predicted_v_peak"] <= 5.0 + 1e-12
            and peak["predicted_a_peak"] <= 5.0 + 1e-12
            and peak["predicted_j_peak"] <= 10.0 + 1e-12
            for item in resolved.values() for peak in item.trace.per_uav_dynamics
        )
        scene_contracts[scene_id] = {
            "time_mode": mode, "T_exec_s": durations,
            "duration_contract": duration_contract,
            "explicit_reference_invariant": references_equal,
            "nominal_hard_safety": safe, "analytic_dynamic_feasibility": feasible,
            "result": "PASS" if duration_contract and references_equal and safe and feasible else "FAIL",
        }
    checks["all_four_scene_static_contracts"] = all(
        item["result"] == "PASS" for item in scene_contracts.values()
    )
    return {
        "checks": checks,
        "explicit_t_exec_s": explicit_durations,
        "auto_t_exec_s": auto_duration,
        "scene_contracts": scene_contracts,
        "result": "PASS" if all(checks.values()) else "FAIL",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, default=CANONICAL_POLICY)
    parser.add_argument("--base-sha", default=START_SHA)
    parser.add_argument("--output", type=Path, default=RESULTS / "upstream_integrity_audit.yaml")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    args.policy = args.policy.resolve()
    base_policy = git_show_yaml(args.base_sha, "lfs_policy/config/lfs_policy.paper_current.yaml")
    current_policy = yaml.safe_load(args.policy.read_text(encoding="utf-8"))
    changed, violations = ownership_changes(base_policy, current_policy)
    artifacts = {}
    for stage, (relative, expected) in FROZEN.items():
        path = REPO / relative
        actual = sha256(path)
        artifacts[stage] = {"path": relative, "expected_sha256": expected,
                            "actual_sha256": actual, "result": "PASS" if actual == expected else "FAIL"}
    remote = subprocess.check_output(
        ["git", "ls-remote", "origin", "refs/heads/cal/C0-E-iapf"], cwd=REPO, text=True
    ).split()[0]
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    semantic = semantic_checks(args.policy)
    try:
        policy_display = str(args.policy.relative_to(REPO))
    except ValueError:
        policy_display = str(args.policy)
    result = {
        "schema_version": "c0f-upstream-integrity-audit-v1",
        "starting_c0_e_sha_expected": START_SHA,
        "starting_c0_e_sha_remote": remote,
        "working_head_at_audit": head,
        "policy_path": policy_display,
        "policy_sha256": sha256(args.policy),
        "inherited_configuration_id": base_policy["configuration_id"],
        "changed_policy_paths_from_c0_e": changed,
        "ownership_violations": violations,
        "frozen_artifacts": artifacts,
        "semantic_contracts": semantic,
    }
    passed = (
        remote == START_SHA and not violations
        and all(item["result"] == "PASS" for item in artifacts.values())
        and semantic["result"] == "PASS"
    )
    result["result"] = "PASS" if passed else "FAIL"
    if not args.check_only:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(yaml.safe_dump(result, sort_keys=False), encoding="utf-8")
    print(yaml.safe_dump(result, sort_keys=False), end="")
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
