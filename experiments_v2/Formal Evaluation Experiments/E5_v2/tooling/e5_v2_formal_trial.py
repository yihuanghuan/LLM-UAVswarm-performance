#!/usr/bin/env python3
"""Submit one exact command through the real frozen Candidate runtime."""

from __future__ import annotations

import argparse
import json
import time
import traceback
from pathlib import Path

import rclpy

from e5_v2_formal_common import exclusive_json, load_json


FORBIDDEN_RUNTIME_KEYS = {
    "candidate_semantic_ground_truth", "candidate_ground_truth_sha256",
    "candidate", "mission_json", "fallback_candidate",
}


def run(submission: dict) -> dict:
    forbidden = sorted(FORBIDDEN_RUNTIME_KEYS.intersection(submission))
    if forbidden:
        raise ValueError(f"runtime payload contains forbidden GT/injection keys: {forbidden}")
    required = {"attempt_id", "seed", "N", "uav_ids", "exact_command",
                "mission_timeout_s", "policy_path"}
    missing = sorted(required - set(submission))
    if missing:
        raise ValueError(f"runtime submission missing: {missing}")
    ids = [int(value) for value in submission["uav_ids"]]
    if ids != list(range(1, int(submission["N"]) + 1)):
        raise ValueError("runtime UAV IDs are not the registered dynamic enumeration")

    ros_arguments = [
        "--ros-args",
        "-p", "lfs_runtime_mode:=candidate_v2",
        "-p", "assignment_mode:=safety_aware",
        "-p", f"uav_ids:=[{','.join(map(str, ids))}]",
        "-p", f"lfs_policy_file:={submission['policy_path']}",
        "-p", f"candidate_completion_timeout:={float(submission['mission_timeout_s'])}",
        "-p", "candidate_dispatch_readiness_timeout:=15.0",
    ]
    rclpy.init(args=ros_arguments)
    from location_allocate.location_allocate import UAVFormationNode, execute_runtime_payload
    from location_allocate.paper_candidate_parser import parse_candidate_mission

    node = None
    candidate = None
    result = {
        "schema": "E5_v2_formal_semantic_runtime_result_v1",
        "attempt_id": submission["attempt_id"],
        "seed": int(submission["seed"]),
        "N": int(submission["N"]),
        "exact_command": submission["exact_command"],
        "candidate_source": "real_semantic_frontend",
        "candidate_ground_truth_injected": False,
        "fallback_used": False,
        "success": False,
        "candidate": None,
        "stages": {},
        "timestamps_ns": {"worker_started": time.time_ns()},
    }
    try:
        node = UAVFormationNode()
        availability = (
            f"Available UAV IDs: {ids}\nTotal available UAVs: {len(ids)}")
        started = time.perf_counter_ns()
        try:
            candidate = parse_candidate_mission(submission["exact_command"], availability)
            result["candidate"] = candidate
            result["stages"]["semantic_frontend"] = {"success": True}
            result["stages"]["candidate_parsing"] = {"success": True}
            result["stages"]["candidate_validation"] = {"success": True}
        except Exception as exc:
            result["stages"]["semantic_frontend"] = {
                "success": False, "error_type": type(exc).__name__, "reason": str(exc)}
            result["stages"]["candidate_parsing"] = {"success": False}
            result["stages"]["candidate_validation"] = {"success": False}
            raise
        finally:
            result.setdefault("latencies_s", {})["T_LLM"] = (
                time.perf_counter_ns() - started) / 1e9

        started = time.perf_counter_ns()
        result["timestamps_ns"]["mission_dispatch_started"] = time.time_ns()
        try:
            compiled = execute_runtime_payload(node, candidate)
            result["compiled_mission_type"] = type(compiled).__name__
            result["stages"]["runtime"] = {"success": True}
            result["stages"]["mission_completion"] = {"success": True}
            result["success"] = True
        except Exception as exc:
            result["stages"]["runtime"] = {
                "success": False, "error_type": type(exc).__name__, "reason": str(exc)}
            result["stages"]["mission_completion"] = {"success": False}
            raise
        finally:
            result.setdefault("latencies_s", {})["T_mission_execution"] = (
                time.perf_counter_ns() - started) / 1e9
            result["timestamps_ns"]["mission_terminal"] = time.time_ns()
    except Exception as exc:
        result["terminal_error"] = {
            "type": type(exc).__name__, "reason": str(exc),
            "traceback": traceback.format_exc(),
        }
    finally:
        result["timestamps_ns"]["worker_finished"] = time.time_ns()
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-submission", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(load_json(args.runtime_submission))
    except Exception as exc:
        result = {
            "schema": "E5_v2_formal_semantic_runtime_result_v1",
            "success": False, "candidate": None,
            "candidate_ground_truth_injected": False, "fallback_used": False,
            "terminal_error": {"type": type(exc).__name__, "reason": str(exc)},
        }
    exclusive_json(args.output, result)
    return 0 if result.get("success") else 2


if __name__ == "__main__":
    raise SystemExit(main())
