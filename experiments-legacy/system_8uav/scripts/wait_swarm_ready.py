#!/usr/bin/env python3
"""Wait for N/N controller READY feedback with a continuous stable hold."""

import argparse
import json
import time

import rclpy
from rclpy.node import Node
from uav_swarm_interfaces.msg import UAVStatus

from readiness_gate import ContinuousReadinessGate, ReadySample


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uav-ids", default="1,2,3,4,5,6,7,8")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--hold", type=float, default=1.0)
    parser.add_argument("--freshness", type=float, default=0.5)
    parser.add_argument("--minimum-altitude", type=float, default=1.0)
    parser.add_argument("--speed-tolerance", type=float, default=0.30)
    args = parser.parse_args()
    uav_ids = [int(value) for value in args.uav_ids.split(",")]

    rclpy.init()
    node = Node("full_chain_readiness_gate")
    gate = ContinuousReadinessGate(
        uav_ids, freshness_timeout=args.freshness,
        minimum_altitude=args.minimum_altitude,
        speed_tolerance=args.speed_tolerance, hold_time=args.hold,
    )
    subscriptions = []
    for uid in uav_ids:
        def callback(message, uav_id=uid):
            gate.update(uav_id, ReadySample(
                received_monotonic=time.monotonic(),
                system_ready=bool(message.system_ready),
                armed=bool(message.armed),
                offboard=bool(message.offboard),
                failsafe=bool(message.failsafe),
                altitude=float(message.altitude),
                position_derived_speed=float(message.speed),
            ))
        subscriptions.append(node.create_subscription(
            UAVStatus, f"/uav{uid}/status", callback, 20
        ))
    deadline = time.monotonic() + args.timeout
    success = False
    while time.monotonic() < deadline and rclpy.ok():
        rclpy.spin_once(node, timeout_sec=0.1)
        if gate.evaluate():
            success = True
            break
    print(json.dumps({
        "ready": success,
        "uav_count": len(uav_ids),
        "diagnostics": gate.diagnostics(),
    }, sort_keys=True))
    node.destroy_node()
    rclpy.shutdown()
    return 0 if success else 2


if __name__ == "__main__":
    raise SystemExit(main())
