#!/usr/bin/env python3
"""Independent audit of one retained E3 live engineering smoke."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import yaml

from e3_runtime_diagnostics import expected_wrench_topic, runtime_provenance_gate


def audit(smoke_root: Path):
    root = Path(smoke_root).resolve(); raw = root / "raw"; checks = []

    def check(name, passed, details):
        checks.append({"check": name, "status": "PASS" if passed else "FAIL",
                       "details": details})

    try:
        manifest = json.loads((root / "smoke_manifest.json").read_text())
        physical = json.loads((raw / "physical_result.json").read_text())
        runtime = json.loads((raw / "runtime_provenance.json").read_text())
        stage = json.loads((raw / "stage_result.json").read_text())
        interaction = json.loads((raw / "interaction_result.json").read_text())
        command_validation = json.loads((raw / "command_validation.json").read_text())
        endpoint_documents = [
            json.loads((raw / f"{phase}_endpoint_snapshot.json").read_text())
            for phase in ("stage", "interaction")
        ]
        metadata = yaml.safe_load((raw / "rosbag/metadata.yaml").read_text())
        counts = {
            item["topic_metadata"]["name"]: int(item["message_count"])
            for item in metadata["rosbag2_bagfile_information"]["topics_with_message_count"]
        }
        check("nonformal_labels", manifest["dataset_class"] == "engineering_validation"
              and manifest["accepted_formal_result"] is False
              and manifest["result_notice"] == "NOT_FORMAL_RESULT"
              and physical["dataset_class"] == "engineering_validation"
              and physical["fixture_class"] == "non_registered_engineering_fixture",
              {"fixture_id": manifest["fixture_id"]})
        check("runtime_provenance", runtime_provenance_gate(runtime), runtime["checks"])
        check("endpoint_identity", all(
            all(item["controller_endpoint_present"] and item["recorder_endpoint_present"]
                for item in document["endpoints"].values())
            for document in endpoint_documents), {"phases": 2})
        check("single_publish_and_acceptance", all(
            set(result["command_publish_count_by_uav"].values()) == {1}
            and all(result["controller_acceptance_event"].values())
            and all(result["mission_trajectory_started_event"].values())
            and all(result["controller_mission_status_seen"].values())
            for result in (stage, interaction)), {"uavs": [1, 2]})
        check("command_payload_guards", set(command_validation["phases"]) ==
              {"stage", "interaction"} and all(
                  phase["all_frozen_controller_metadata_guards_pass"]
                  for phase in command_validation["phases"].values()), {})
        check("sealed_staging_gate", stage["success"] is True
              and stage["stable_continuous_observed_s"] >= 2.0
              and all(item["is_hover_stable"] and item["position_error"] <= 0.40
                      for item in stage["final_mission_status"].values()),
              {"stable_continuous_observed_s": stage["stable_continuous_observed_s"]})
        check("interaction_execution", interaction["success"] is True,
              {"mission_id": interaction["mission_id"]})
        check("rosbag_command_retention", all(
            counts.get(f"/uav{uid}/execution_command") == 2 for uid in (1, 2)),
            {f"uav{uid}": counts.get(f"/uav{uid}/execution_command") for uid in (1, 2)})
        wrench = expected_wrench_topic(1)
        check("registered_wrench_transport", counts.get(wrench, 0) > 0,
              {"topic": wrench, "message_count": counts.get(wrench, 0)})
        check("smoke_self_audit", manifest["status"] == "PASS"
              and all(manifest["evidence_checks"].values()), manifest["evidence_checks"])
        check("formal_outputs_absent", not list(root.rglob("*journal*"))
              and not list(root.rglob("formal-attempt*.json")), {})
    except Exception as exc:
        check("internal_error", False, {"type": type(exc).__name__, "message": str(exc)})
    return {
        "audit_type": "E3_formal_adapter_live_smoke_audit_v1",
        "status": "PASS" if all(item["status"] == "PASS" for item in checks) else "FAIL",
        "dataset_class": "engineering_validation",
        "accepted_formal_result": False,
        "checks": checks,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("smoke_root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(); result = audit(args.smoke_root)
    if args.output:
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
