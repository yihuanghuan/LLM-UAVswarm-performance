#!/usr/bin/env python3
"""Read-only ROS observer for a C0-B baseline freshness measurement run."""
from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data


class FreshnessProbe(Node):
    def __init__(self, scenario, uav_count, output, state_timeout_ms, skew_ms):
        super().__init__("c0_b_freshness_probe")
        self.scenario, self.uav_count = scenario, uav_count
        self.state_timeout_s, self.skew_s = state_timeout_ms / 1000.0, skew_ms / 1000.0
        self.latest = {}
        self.wait_started = None
        self.rows = []
        for uid in range(1, uav_count + 1):
            self.create_subscription(Odometry, f"/uav{uid}/swarm_state",
                                     lambda msg, uid=uid: self.receive(msg, uid),
                                     qos_profile_sensor_data)
        self.create_timer(0.02, self.sample)
        self.output = output

    def now(self):
        return self.get_clock().now().nanoseconds / 1e9

    def receive(self, message, uid):
        self.latest[uid] = float(message.header.stamp.sec) + float(message.header.stamp.nanosec) / 1e9

    def sample(self):
        now = self.now()
        if len(self.latest) != self.uav_count:
            return
        stamps = list(self.latest.values())
        ages = {uid: max(0.0, now - stamp) for uid, stamp in self.latest.items()}
        skew = max(stamps) - min(stamps)
        fresh = all(age <= self.state_timeout_s for age in ages.values()) and skew <= self.skew_s
        # Same all-or-nothing predicates as FreshStateSnapshotManager.  The
        # wait metric is observational and cannot publish or influence a plan.
        # A planning request with an already fresh snapshot has zero waiting.
        # Once the observer sees an unavailable snapshot, its wait begins and
        # ends only when all states satisfy the production freshness predicate.
        if fresh:
            waited_ms = 0.0 if self.wait_started is None else (time.monotonic() - self.wait_started) * 1000.0
            self.wait_started = None
        elif self.wait_started is None:
            self.wait_started = time.monotonic()
            waited_ms = 0.0
        else:
            waited_ms = (time.monotonic() - self.wait_started) * 1000.0
        for uid, age in ages.items():
            self.rows.append({"timestamp": f"{now:.9f}", "scenario": self.scenario,
                              "uav_count": self.uav_count, "uav_id": uid,
                              "state_age_ms": f"{age * 1000.0:.6f}",
                              "snapshot_skew_ms": f"{skew * 1000.0:.6f}",
                              "planner_wait_ms": f"{waited_ms:.6f}"})

    def close(self):
        self.output.parent.mkdir(parents=True, exist_ok=True)
        with self.output.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=("timestamp", "scenario", "uav_count", "uav_id", "state_age_ms", "snapshot_skew_ms", "planner_wait_ms"))
            writer.writeheader()
            writer.writerows(self.rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True, choices=("hover", "straight_motion", "waypoint_transition", "multi_uav_4", "multi_uav_8"))
    parser.add_argument("--uav-count", type=int, required=True)
    parser.add_argument("--duration-s", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    # Existing provisional policy values are observation-only predicates; this
    # does not change any runtime setting.
    parser.add_argument("--observer-state-timeout-ms", type=float, default=500.0)
    parser.add_argument("--observer-skew-ms", type=float, default=150.0)
    args = parser.parse_args()
    expected = {"hover": 1, "straight_motion": 1, "waypoint_transition": 4, "multi_uav_4": 4, "multi_uav_8": 8}
    if args.uav_count != expected[args.scenario] or args.duration_s <= 0:
        raise SystemExit("scenario/uav-count mismatch or non-positive duration")
    rclpy.init()
    probe = FreshnessProbe(args.scenario, args.uav_count, args.output,
                           args.observer_state_timeout_ms, args.observer_skew_ms)
    try:
        deadline = time.monotonic() + args.duration_s
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(probe, timeout_sec=min(0.1, deadline - time.monotonic()))
    finally:
        probe.close()
        probe.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
