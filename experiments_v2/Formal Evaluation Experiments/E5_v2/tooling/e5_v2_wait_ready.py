#!/usr/bin/env python3
"""Dynamic-ID readiness gate used only by E5-v2 engineering smoke."""

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
    node = Node("e5_v2_engineering_readiness")
    samples = {}
    states = {}
    subscriptions = []
    ready_since = None
    started = time.monotonic()

    for uid in ids:
        def callback(message, uav_id=uid):
            samples[uav_id] = {
                "received_monotonic": time.monotonic(),
                "system_ready": bool(message.system_ready),
                "armed": bool(message.armed),
                "offboard": bool(message.offboard),
                "failsafe": bool(message.failsafe),
                "altitude": float(message.altitude),
                "speed": float(message.speed),
                "position_error": float(message.position_error),
            }
        subscriptions.append(node.create_subscription(
            UAVStatus, f"/uav{uid}/status", callback, 20
        ))
        def state_callback(message, uav_id=uid):
            states[uav_id] = {
                "received_monotonic": time.monotonic(),
                "position": [
                    float(message.pose.pose.position.x),
                    float(message.pose.pose.position.y),
                    float(message.pose.pose.position.z),
                ],
                "velocity": [
                    float(message.twist.twist.linear.x),
                    float(message.twist.twist.linear.y),
                    float(message.twist.twist.linear.z),
                ],
            }
        subscriptions.append(node.create_subscription(
            Odometry,
            f"/uav{uid}/swarm_state",
            state_callback,
            qos_profile_sensor_data,
        ))

    success = False
    deadline = started + args.timeout
    while time.monotonic() < deadline and rclpy.ok():
        rclpy.spin_once(node, timeout_sec=0.1)
        now = time.monotonic()
        ready = True
        for uid in ids:
            sample = samples.get(uid)
            state = states.get(uid)
            ready = ready and sample is not None and state is not None
            if sample is None or state is None:
                continue
            # position_error is a mission diagnostic and is intentionally +Inf
            # before any scientific command. Engineering finite-state readiness
            # therefore uses the standardized position/velocity state plus the
            # status altitude/speed signals, matching the production gate.
            values_finite = (
                all(math.isfinite(sample[key]) for key in ("altitude", "speed"))
                and all(math.isfinite(value) for value in state["position"])
                and all(math.isfinite(value) for value in state["velocity"])
            )
            ready = ready and (
                now - sample["received_monotonic"] <= args.freshness
                and now - state["received_monotonic"] <= args.freshness
                and sample["system_ready"]
                and sample["armed"]
                and sample["offboard"]
                and not sample["failsafe"]
                and values_finite
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
    diagnostics = {}
    state_diagnostics = {}
    for uid in ids:
        sample = samples.get(uid)
        diagnostics[str(uid)] = {
            "present": sample is not None,
            **({} if sample is None else {
                "age_s": finished - sample["received_monotonic"],
                **{key: value for key, value in sample.items()
                   if key != "received_monotonic"},
            }),
        }
        state = states.get(uid)
        state_diagnostics[str(uid)] = {
            "present": state is not None,
            **({} if state is None else {
                "age_s": finished - state["received_monotonic"],
                "position": state["position"],
                "velocity": state["velocity"],
            }),
        }
    print(json.dumps({
        "ready": success,
        "uav_count": len(ids),
        "uav_ids": list(ids),
        "elapsed_s": finished - started,
        "all_states_finite": all(
            diagnostics[str(uid)].get("present")
            and state_diagnostics[str(uid)].get("present")
            and all(math.isfinite(diagnostics[str(uid)][key]) for key in (
                "altitude", "speed"
            ))
            and all(
                math.isfinite(value)
                for key in ("position", "velocity")
                for value in state_diagnostics[str(uid)][key]
            )
            for uid in ids
        ),
        "diagnostics": diagnostics,
        "state_diagnostics": state_diagnostics,
    }, sort_keys=True))
    node.destroy_node()
    rclpy.shutdown()
    return 0 if success else 2


if __name__ == "__main__":
    raise SystemExit(main())
