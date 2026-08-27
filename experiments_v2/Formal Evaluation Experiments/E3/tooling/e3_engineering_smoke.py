#!/usr/bin/env python3
"""Run one non-registered E3 plumbing fixture; never a scientific trial."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import yaml

from e3_formal_backend import build_runtime_spec, execute_registered_trial
from e3_trial_registry import POLICY_SHA256


FIXTURE_ID = "ENG-E3-PLUMBING-2UAV-ZERO-SCIENCE-v1"


def fixture():
    return {
        "trial_id": FIXTURE_ID, "seed": 990003, "uav_ids": [1, 2],
        "fixture_class": "non_registered_engineering_fixture",
        "dataset_class": "engineering_validation",
        "initial_positions_m": {1: [0.0, 3.0, 3.0], 2: [0.0, 6.0, 3.0]},
        "ordered_targets_m": {1: [0.5, 3.0, 3.0], 2: [0.5, 6.0, 3.0]},
        "duration_s": 3.0, "assignment_mode": "safety_aware",
        "avoidance_mode": "iapf_dual", "timeout_after_t0_s": 9.0,
        "staging": {"stable_continuous_s": 2.0, "scored": False},
        "scoring": {"t0": "interaction_execution_command_timestamp",
                    "end_offset_s": 5.0},
        "invariants": {"safety_s": 1.0, "q": {"mode": "direct"}},
        "disturbance": {"affected_uavs": [1], "vectors_N": {1: [0.10, 0.0, 0.0]},
                        "onset_s": 0.5, "duration_s": 0.5},
        "metric_log_schema": {"raw_required": ["clock", "execution_command_t0",
            "per_uav_position_3d", "per_uav_nominal_reference", "per_uav_safe_reference",
            "iapf_active", "iapf_delta_p", "iapf_delta_a", "allocator_prediction",
            "completion_events", "hard_failures", "wrench_commands"]},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("engineering smoke output already exists")
    args.output.mkdir(parents=True)
    build_runtime_spec(fixture())
    result = execute_registered_trial(fixture(), args.output / "raw")
    required = [args.output / "raw/physical_result.json",
                args.output / "raw/stage_result.json",
                args.output / "raw/interaction_result.json",
                args.output / "raw/rosbag/metadata.yaml",
                args.output / "raw/wrench.log"]
    evidence = {
        "backend_success": result.get("attempt_status") == "success",
        "required_files_present": all(p.exists() for p in required),
        "fixture_is_non_registered": result.get("fixture_class") ==
            "non_registered_engineering_fixture",
        "staging_completed": False,
        "interaction_completed": False,
        "clock_qos_compatible": False,
        "wrench_topic_retained": False,
    }
    if required[1].exists():
        evidence["staging_completed"] = json.loads(required[1].read_text()).get("success") is True
    if required[2].exists():
        evidence["interaction_completed"] = json.loads(required[2].read_text()).get("success") is True
    if required[4].exists():
        wrench_log = required[4].read_text(errors="replace")
        evidence["clock_qos_compatible"] = "incompatible QoS" not in wrench_log
    if required[3].exists():
        bag_metadata = yaml.safe_load(required[3].read_text())
        topics = {
            item["topic_metadata"]["name"]
            for item in bag_metadata["rosbag2_bagfile_information"]["topics_with_message_count"]
        }
        evidence["wrench_topic_retained"] = "/gazebo/force/uav1/wrench" in topics
    status = "PASS" if all(evidence.values()) else "FAIL"
    manifest = {
        "manifest_type": "E3_live_engineering_smoke_v1",
        "fixture_id": FIXTURE_ID, "fixture_registered_formal_trial": False,
        "dataset_class": "engineering_validation", "accepted_formal_result": False,
        "result_notice": "NOT_FORMAL_RESULT", "scientific_interpretation": None,
        "policy_sha256": POLICY_SHA256, "status": status,
        "evidence_checks": evidence,
        "coverage": {"ros_gazebo_px4": True, "assignment_mode_switch_plumbing": True,
                     "disturbance_plugin_driver": True, "staging_detection": True,
                     "raw_logging": True},
        "backend_result": result,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
    }
    (args.output / "smoke_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, sort_keys=True))
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
