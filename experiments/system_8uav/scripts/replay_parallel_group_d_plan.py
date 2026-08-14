#!/usr/bin/env python3
"""Replay baseline_trial3 against the frozen hard/soft safety semantics."""

import json
from pathlib import Path

from location_allocate.late_resolution import (
    LateResolutionError,
    resolve_execution_parallel,
)
from location_allocate.lfs_types import StateSnapshot, UAVState
from location_allocate.policy_adapter import load_runtime_policy


ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "experiments/system_8uav/fixtures/parallel_group_d_plan_baseline_trial3.json"
POLICY = ROOT / "lfs_policy/config/lfs_policy.paper_current.yaml"


def replay(fixture_path=FIXTURE, policy_path=POLICY):
    fixture = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
    epoch = float(fixture["snapshot_epoch"])
    snapshot = StateSnapshot(
        epoch=epoch,
        states={
            int(uid): UAVState(
                position=tuple(position),
                receive_timestamp=epoch,
                velocity=(0.0, 0.0, 0.0),
                source_timestamp=epoch,
                timestamp_source="rosbag",
            )
            for uid, position in fixture["positions"].items()
        },
    )
    _, policy = load_runtime_policy(policy_path)
    try:
        result = resolve_execution_parallel(
            fixture["tasks"], snapshot, policy,
            fixture["completion_mode"],
        )
    except LateResolutionError as error:
        return {
            "outcome": "rejected",
            "error_code": error.code,
            "message": str(error),
            "diagnostics": error.diagnostics,
        }
    return {
        "outcome": "accepted",
        "d_hard": result.tasks[0].trace.d_hard,
        "group_d_plan": result.tasks[0].trace.d_plan,
        "planning_min_distance": result.planning_metrics.min_distance,
        "final_min_distance": result.final_metrics.min_distance,
        "J_margin": result.final_metrics.margin_cost,
        "final_metrics": result.tasks[0].trace.final_assignment_metrics,
        "warnings": result.tasks[0].trace.warnings,
    }


if __name__ == "__main__":
    print(json.dumps(replay(), indent=2, sort_keys=True, allow_nan=False))
