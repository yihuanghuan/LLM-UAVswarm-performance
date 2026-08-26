#!/usr/bin/env python3
"""Experiment-only, simulation-clocked rectangular wrench driver for E3.

The production planner and controller are not imported or modified.  Every
factorial condition runs this same driver; scenario configuration alone selects
zero or registered nonzero wrenches.
"""

import json

import rclpy
from geometry_msgs.msg import Wrench
from rclpy.node import Node
from rosgraph_msgs.msg import Clock
from std_msgs.msg import Empty


class E3WrenchDriver(Node):
    def __init__(self):
        super().__init__("e3_wrench_driver")
        self.declare_parameter("wrenches_json", "{}")
        self.declare_parameter("onset_s", 2.0)
        self.declare_parameter("duration_s", 1.5)
        raw = json.loads(str(self.get_parameter("wrenches_json").value))
        self.vectors = {
            int(uid): tuple(float(value) for value in vector)
            for uid, vector in raw.items()
        }
        if any(len(vector) != 3 for vector in self.vectors.values()):
            raise ValueError("every registered E3 wrench needs [Fx,Fy,Fz]")
        self.onset = float(self.get_parameter("onset_s").value)
        self.duration = float(self.get_parameter("duration_s").value)
        if self.onset < 0.0 or self.duration <= 0.0:
            raise ValueError("invalid registered onset/duration")
        self.publishers = {
            uid: self.create_publisher(
                Wrench, f"/e3_force/mavlink_{uid + 1}/wrench", 10
            )
            for uid in self.vectors
        }
        self.latest_sim_time = None
        self.arm_time = None
        self.zero_sent = False
        self.create_subscription(Clock, "/clock", self._on_clock, 50)
        self.create_subscription(Empty, "/e3/disturbance_arm", self._on_arm, 10)

    @staticmethod
    def _seconds(clock):
        return float(clock.sec) + float(clock.nanosec) / 1e9

    def _publish(self, active):
        for uid, vector in self.vectors.items():
            message = Wrench()
            if active:
                message.force.x, message.force.y, message.force.z = vector
            self.publishers[uid].publish(message)

    def _on_arm(self, _message):
        if self.latest_sim_time is None:
            raise RuntimeError("cannot arm E3 disturbance before first /clock")
        if self.arm_time is not None:
            raise RuntimeError("E3 disturbance may be armed only once per trial")
        self.arm_time = self.latest_sim_time
        self.zero_sent = False

    def _on_clock(self, message):
        self.latest_sim_time = self._seconds(message.clock)
        if self.arm_time is None:
            return
        elapsed = self.latest_sim_time - self.arm_time
        active = self.onset <= elapsed < self.onset + self.duration
        if active:
            self._publish(True)
        elif elapsed >= self.onset + self.duration and not self.zero_sent:
            self._publish(False)
            self.zero_sent = True


def main():
    rclpy.init()
    node = E3WrenchDriver()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
