#!/usr/bin/env python3
"""C0-C-only Candidate-owned state prewarm harness.

This is experimental startup infrastructure: it does not change the frozen
post-submission freshness wait.  It spins the actual Candidate node only until
its own snapshot manager accepts the parsed task participants.
"""
from __future__ import annotations
import argparse, json, time
from datetime import datetime, timezone

import rclpy

from location_allocate.location_allocate import UAVFormationNode, execute_runtime_payload
from location_allocate.paper_candidate_parser import parse_candidate_mission
from location_allocate.state_snapshot import SnapshotError


def participant_ids(payload):
    ids = []
    for node in payload["mission"]["nodes"]:
        tasks = [node["task"]] if node["type"] == "task" else node["tasks"]
        ids.extend(uid for task in tasks for uid in task["U"])
    return sorted(set(ids))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--command", required=True)
    parser.add_argument("--uav-ids", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--timeout", type=float, default=15.0,
                        help="C0-C orchestration-only pre-command timeout (s)")
    args = parser.parse_args()
    ros_args = ["--ros-args", "-p", "lfs_runtime_mode:=candidate_v2", "-p",
                f"uav_ids:=[{args.uav_ids}]", "-p", "candidate_completion_timeout:=180.0",
                "-p", f"lfs_policy_file:={args.policy}"]
    record = {"candidate_node_created_utc": None, "parser_completed_utc": None,
              "candidate_readiness_start_utc": None, "candidate_readiness_end_utc": None,
              "candidate_readiness_duration_s": None, "participant_ids": None,
              "snapshot_ages_s": None, "snapshot_skew_s": None,
              "execute_runtime_payload_entered": False, "candidate_completed": False,
              "failure": None, "orchestration_timeout_s": args.timeout}
    rclpy.init(args=ros_args); node = None
    try:
        node = UAVFormationNode(); record["candidate_node_created_utc"] = datetime.now(timezone.utc).isoformat()
        availability = f"Available UAV IDs: {node.available_uav_ids}\nTotal available UAVs: {len(node.available_uav_ids)}"
        payload = parse_candidate_mission(args.command, availability)
        record["parser_completed_utc"] = datetime.now(timezone.utc).isoformat()
        ids = participant_ids(payload); record["participant_ids"] = ids
        state = node.paper_runtime.policy_config.state
        record.update(state_timeout_s=state.state_timeout, snapshot_skew_threshold_s=state.snapshot_skew,
                      fresh_state_wait_timeout_s=state.fresh_state_wait_timeout)
        started = time.monotonic(); record["candidate_readiness_start_utc"] = datetime.now(timezone.utc).isoformat()
        snapshot = node.paper_runtime._await_dispatch_snapshot(ids)
        record["candidate_readiness_duration_s"] = time.monotonic() - started
        record["candidate_readiness_end_utc"] = datetime.now(timezone.utc).isoformat()
        ages = {str(uid): now - item.effective_timestamp for uid, item in snapshot.states.items()}
        record["snapshot_ages_s"] = ages; record["snapshot_skew_s"] = max(item.effective_timestamp for item in snapshot.states.values()) - min(item.effective_timestamp for item in snapshot.states.values())
        # Carry the exact just-qualified C0-B snapshot across synchronous
        # parsing/dispatch; PaperMissionRuntime validates participant equality.
        node.paper_runtime.prime_dispatch_snapshot(ids, snapshot)
        record["execute_runtime_payload_entered"] = True
        execute_runtime_payload(node, payload)
        record["candidate_completed"] = True
    except Exception as exc:
        record["failure"] = f"{type(exc).__name__}: {exc}"
    finally:
        if node is not None: node.destroy_node()
        rclpy.shutdown()
    print(json.dumps(record, sort_keys=True))
    if record["failure"]: raise SystemExit(2)


if __name__ == "__main__": main()
