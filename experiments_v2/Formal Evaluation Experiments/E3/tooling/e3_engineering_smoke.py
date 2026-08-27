#!/usr/bin/env python3
"""Run one non-registered E3 plumbing fixture; never a scientific trial."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import yaml

from e3_formal_backend import build_runtime_spec, execute_registered_trial
from e3_runtime_diagnostics import expected_wrench_topic
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
                args.output / "raw/wrench.log",
                args.output / "raw/runtime_provenance.json",
                args.output / "raw/command_validation.json",
                args.output / "raw/stage_endpoint_snapshot.json",
                args.output / "raw/interaction_endpoint_snapshot.json"]
    evidence = {
        "backend_success": result.get("attempt_status") == "success",
        "required_files_present": all(p.exists() for p in required),
        "fixture_is_non_registered": result.get("fixture_class") ==
            "non_registered_engineering_fixture",
        "dataset_class_propagated": result.get("dataset_class") == "engineering_validation",
        "runtime_spec_labels_propagated": False,
        "runtime_provenance_pass": False,
        "controller_endpoint_present_every_phase": False,
        "recorder_endpoint_present_every_phase": False,
        "command_payload_guard_pass": False,
        "exactly_one_command_per_uav_per_phase": False,
        "controller_acceptance_event_every_uav": False,
        "controller_profile_application_log": False,
        "controller_mission_status_seen_every_uav": False,
        "staging_completed": False,
        "staging_geometry_reached": False,
        "staging_stable_continuous_2s": False,
        "interaction_completed": False,
        "clock_qos_compatible": False,
        "wrench_topic_retained": False,
        "command_seen_by_rosbag": False,
        "formal_output_absent": True,
        "suite_journal_absent": not list(args.output.rglob("*journal*")),
    }
    runtime_spec_path = args.output / "raw/runtime_spec.json"
    if runtime_spec_path.exists():
        runtime_spec = json.loads(runtime_spec_path.read_text())
        evidence["runtime_spec_labels_propagated"] = (
            runtime_spec.get("fixture_class") == "non_registered_engineering_fixture"
            and runtime_spec.get("dataset_class") == "engineering_validation"
        )
    if required[5].exists():
        evidence["runtime_provenance_pass"] = (
            json.loads(required[5].read_text()).get("status") == "PASS"
        )
    if required[6].exists():
        validation = json.loads(required[6].read_text())
        phases = validation.get("phases", {})
        evidence["command_payload_guard_pass"] = set(phases) == {"stage", "interaction"} and all(
            item.get("all_frozen_controller_metadata_guards_pass") is True
            for item in phases.values()
        )
    if required[7].exists() and required[8].exists():
        endpoint_documents = [json.loads(path.read_text()) for path in required[7:9]]
        evidence["controller_endpoint_present_every_phase"] = all(
            all(item.get("controller_endpoint_present") is True
                for item in document.get("endpoints", {}).values())
            for document in endpoint_documents
        )
        evidence["recorder_endpoint_present_every_phase"] = all(
            all(item.get("recorder_endpoint_present") is True
                for item in document.get("endpoints", {}).values())
            for document in endpoint_documents
        )
    phase_results = []
    if required[1].exists():
        stage = json.loads(required[1].read_text()); phase_results.append(stage)
        evidence["staging_completed"] = stage.get("success") is True
        final = stage.get("final_mission_status", {})
        evidence["staging_geometry_reached"] = bool(final) and all(
            item is not None and item.get("is_hover_stable") is True
            and item.get("position_error", float("inf")) <= 0.40
            for item in final.values()
        )
        evidence["staging_stable_continuous_2s"] = (
            stage.get("stable_continuous_observed_s", 0.0) >= 2.0
        )
    if required[2].exists():
        interaction = json.loads(required[2].read_text()); phase_results.append(interaction)
        evidence["interaction_completed"] = interaction.get("success") is True
    if len(phase_results) == 2:
        evidence["exactly_one_command_per_uav_per_phase"] = all(
            set(item.get("command_publish_count_by_uav", {}).values()) == {1}
            and len(item["command_publish_count_by_uav"]) == 2
            for item in phase_results
        )
        evidence["controller_acceptance_event_every_uav"] = all(
            all(item.get("controller_acceptance_event", {}).values())
            and all(item.get("mission_trajectory_started_event", {}).values())
            for item in phase_results
        )
        evidence["controller_mission_status_seen_every_uav"] = all(
            all(item.get("controller_mission_status_seen", {}).values())
            for item in phase_results
        )
        controller_log = args.output / "raw/controllers.log"
        if controller_log.exists():
            log_text = controller_log.read_text(errors="replace")
            evidence["controller_profile_application_log"] = all(
                f"Execution Profile mission={item['mission_id']}" in log_text
                for item in phase_results
            )
    if required[4].exists():
        wrench_log = required[4].read_text(errors="replace")
        evidence["clock_qos_compatible"] = "incompatible QoS" not in wrench_log
    if required[3].exists():
        bag_metadata = yaml.safe_load(required[3].read_text())
        topic_counts = {
            item["topic_metadata"]["name"]: int(item["message_count"])
            for item in bag_metadata["rosbag2_bagfile_information"]["topics_with_message_count"]
        }
        evidence["wrench_topic_retained"] = topic_counts.get(expected_wrench_topic(1), 0) > 0
        evidence["command_seen_by_rosbag"] = all(
            topic_counts.get(f"/uav{uid}/execution_command") == 2 for uid in (1, 2)
        )
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
