"""Production, non-interactive Paper Candidate dispatch entry point."""
from __future__ import annotations
import argparse
import json
import rclpy
from .location_allocate import UAVFormationNode, execute_runtime_payload
from .paper_candidate_parser import parse_candidate_mission


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--command", required=True)
    parser.add_argument("--uav-ids", required=True)
    parser.add_argument("--policy", required=True)
    args = parser.parse_args()
    rclpy.init(args=["--ros-args", "-p", "lfs_runtime_mode:=candidate_v2", "-p",
                     f"uav_ids:=[{args.uav_ids}]", "-p", f"lfs_policy_file:={args.policy}"])
    node = None
    result = {"candidate_completed": False, "failure": None}
    try:
        node = UAVFormationNode()
        availability = f"Available UAV IDs: {node.available_uav_ids}\nTotal available UAVs: {len(node.available_uav_ids)}"
        payload = parse_candidate_mission(args.command, availability)
        execute_runtime_payload(node, payload)
        result["candidate_completed"] = True
    except Exception as exc:
        result["failure"] = f"{type(exc).__name__}: {exc}"
    finally:
        if node is not None: node.destroy_node()
        rclpy.shutdown()
    print(json.dumps(result, sort_keys=True))
    if result["failure"]: raise SystemExit(2)


if __name__ == "__main__": main()
