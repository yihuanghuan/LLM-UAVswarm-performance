"""Real E3 backend construction; invoked only after the global formal gate.

This module deliberately contains no campaign ordering logic.  It resolves the
sealed allocator condition, compiles frozen execution profiles, and delegates
one cold execution to the experiment-only ROS process harness.
"""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from typing import Any, Dict

from e3_trial_registry import POLICY_PATH, REPO_ROOT, canonical_sha256


def _imports() -> None:
    for path in (REPO_ROOT / "location_allocate", REPO_ROOT / "lfs_policy"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))


def build_runtime_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    _imports()
    from location_allocate.execution_profile_compiler import compile_execution_profiles
    from location_allocate.lfs_types import ExecutableLFS
    from location_allocate.policy_adapter import load_runtime_policy

    _config, policy = load_runtime_policy(POLICY_PATH)
    safety = policy.resolve_safety(float(spec["invariants"]["safety_s"]))
    allocator = policy.allocator_factory(safety.d_hard, safety.d_plan)
    # ROS 2 geometry message setters require Python floats even when a sealed
    # YAML coordinate is numerically integral. This is representation-only
    # normalization; values and all scientific geometry remain unchanged.
    initial = [
        [float(value) for value in spec["initial_positions_m"][uid]]
        for uid in spec["uav_ids"]
    ]
    ordered_targets = [
        [float(value) for value in spec["ordered_targets_m"][uid]]
        for uid in spec["uav_ids"]
    ]
    assigned, metrics = allocator.allocate_mode_with_metrics(
        initial, ordered_targets, spec["duration_s"],
        mode=spec["assignment_mode"],
    )
    executable = ExecutableLFS(
        uav_ids=tuple(int(uid) for uid in spec["uav_ids"]),
        formation={"type": "E3_registered_ordered_target_set"},
        center=(0.0, 0.0, 0.0), radius=0.0,
        duration=float(spec["duration_s"]), motion_style="normal",
        safety_factor=float(spec["invariants"]["safety_s"]),
        trigger_semantics=dict(spec["invariants"]["q"]),
    )
    profiles = compile_execution_profiles(
        executable, initial, assigned, policy.profile, safety.soft_iapf,
    )
    runtime = {
        "runtime_spec_type": "E3_registered_physical_runtime_spec_v2",
        "fixture_class": spec.get("fixture_class", "registered_formal_spec"),
        "dataset_class": spec.get("dataset_class", "formal_evaluation"),
        "trial_id": spec["trial_id"], "seed": spec["seed"],
        "uav_ids": spec["uav_ids"], "initial_positions_m": initial,
        "ordered_targets_m": ordered_targets,
        "assigned_targets_m": assigned,
        "allocator_metrics": asdict(metrics),
        "allocator_diagnostics": allocator.metrics_dict(),
        "assignment_mode": spec["assignment_mode"],
        "avoidance_mode": spec["avoidance_mode"],
        "duration_s": spec["duration_s"], "staging": spec["staging"],
        "scoring": spec["scoring"], "timeout_after_t0_s": spec["timeout_after_t0_s"],
        "disturbance": spec["disturbance"],
        "profiles": [asdict(profile) for profile in profiles],
        "required_raw_schema": spec["metric_log_schema"]["raw_required"],
        "policy_path": str(POLICY_PATH),
    }
    runtime["runtime_spec_sha256"] = canonical_sha256(runtime)
    return runtime


def execute_registered_trial(spec: Dict[str, Any], raw_dir: Path) -> Dict[str, Any]:
    raw_dir = Path(raw_dir).resolve()
    runtime = build_runtime_spec(spec)
    raw_dir.mkdir(parents=True, exist_ok=True)
    spec_path = raw_dir / "runtime_spec.json"
    spec_path.write_text(json.dumps(runtime, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    harness = Path(__file__).with_name("e3_physical_trial.py")
    result_path = raw_dir / "physical_result.json"
    command = [sys.executable, str(harness), "--runtime-spec", str(spec_path),
               "--output", str(raw_dir), "--result", str(result_path)]
    completed = subprocess.run(
        command, cwd=REPO_ROOT, text=True, capture_output=True,
        timeout=float(runtime["timeout_after_t0_s"]) + 300.0,
    )
    (raw_dir / "harness.stdout.log").write_text(completed.stdout, encoding="utf-8")
    (raw_dir / "harness.stderr.log").write_text(completed.stderr, encoding="utf-8")
    if not result_path.exists():
        raise RuntimeError("E3 physical harness did not retain physical_result.json")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["harness_returncode"] = completed.returncode
    return result
