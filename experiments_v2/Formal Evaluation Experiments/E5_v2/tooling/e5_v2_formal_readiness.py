#!/usr/bin/env python3
"""Frozen all-UAV fresh-state/readiness gate for E5-v2 formal execution."""

from __future__ import annotations

import argparse
import json
import math
import time

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from uav_swarm_interfaces.msg import UAVStatus


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uav-ids", required=True)
    parser.add_argument("--timeout", type=float, required=True)
    parser.add_argument("--hold", type=float, required=True)
    parser.add_argument("--freshness", type=float, required=True)
    parser.add_argument("--minimum-altitude", type=float, required=True)
    parser.add_argument("--speed-tolerance", type=float, required=True)
    args = parser.parse_args()
    ids = tuple(int(value) for value in args.uav_ids.split(","))
    if not ids or len(ids) != len(set(ids)):
        raise SystemExit("uav-ids must be non-empty and unique")

    rclpy.init()
    node = Node("e5_v2_formal_all_uav_readiness")
    status, state, subscriptions = {}, {}, []
    started, ready_since = time.monotonic(), None

    for uid in ids:
        def status_callback(message, uav_id=uid):
            status[uav_id] = {
                "received_monotonic": time.monotonic(),
                "system_ready": bool(message.system_ready),
                "armed": bool(message.armed),
                "offboard": bool(message.offboard),
                "failsafe": bool(message.failsafe),
                "altitude": float(message.altitude),
                "speed": float(message.speed),
            }

        def state_callback(message, uav_id=uid):
            state[uav_id] = {
                "received_monotonic": time.monotonic(),
                "position": [float(message.pose.pose.position.x),
                             float(message.pose.pose.position.y),
                             float(message.pose.pose.position.z)],
                "velocity": [float(message.twist.twist.linear.x),
                             float(message.twist.twist.linear.y),
                             float(message.twist.twist.linear.z)],
            }

        subscriptions.append(node.create_subscription(
            UAVStatus, f"/uav{uid}/status", status_callback, 20))
        subscriptions.append(node.create_subscription(
            Odometry, f"/uav{uid}/swarm_state", state_callback,
            qos_profile_sensor_data))

    success = False
    deadline = started + args.timeout
    while time.monotonic() < deadline and rclpy.ok():
        rclpy.spin_once(node, timeout_sec=0.1)
        now = time.monotonic()
        ready = True
        for uid in ids:
            sample, motion = status.get(uid), state.get(uid)
            if sample is None or motion is None:
                ready = False
                continue
            ready = ready and (
                now - sample["received_monotonic"] <= args.freshness
                and now - motion["received_monotonic"] <= args.freshness
                and sample["system_ready"] and sample["armed"]
                and sample["offboard"] and not sample["failsafe"]
                and math.isfinite(sample["altitude"])
                and math.isfinite(sample["speed"])
                and all(math.isfinite(value) for key in ("position", "velocity")
                        for value in motion[key])
                and sample["altitude"] >= args.minimum_altitude
                and sample["speed"] <= args.speed_tolerance
            )
        if not ready:
            ready_since = None
        elif ready_since is None:
            ready_since = now
        elif now - ready_since >= args.hold:
            success = True
            break

    finished = time.monotonic()
    report = {
        "schema": "E5_v2_formal_readiness_v1",
        "ready": success,
        "uav_count": len(ids),
        "uav_ids": list(ids),
        "elapsed_s": finished - started,
        "status": {},
        "state": {},
    }
    for uid in ids:
        sample, motion = status.get(uid), state.get(uid)
        report["status"][str(uid)] = {"present": sample is not None, **(
            {} if sample is None else {
                **{key: value for key, value in sample.items()
                   if key != "received_monotonic"},
                "age_s": finished - sample["received_monotonic"],
            })}
        report["state"][str(uid)] = {"present": motion is not None, **(
            {} if motion is None else {
                "position": motion["position"], "velocity": motion["velocity"],
                "age_s": finished - motion["received_monotonic"],
            })}
    print(json.dumps(report, sort_keys=True))
    node.destroy_node()
    rclpy.shutdown()
    return 0 if success else 2


if __name__ == "__main__":
    raise SystemExit(main())
