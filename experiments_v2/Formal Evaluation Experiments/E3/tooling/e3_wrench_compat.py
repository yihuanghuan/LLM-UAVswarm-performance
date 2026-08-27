#!/usr/bin/env python3
"""ROS-Humble compatibility launcher for the byte-unchanged sealed E3 driver.

`rclpy.node.Node.publishers` is a read-only introspection property.  The sealed
driver predates that collision and stores its own uid->publisher mapping under
the same name.  This subclass supplies storage only for that name; every
disturbance behavior method remains inherited, unmodified, from the sealed
driver.
"""

from __future__ import annotations

from pathlib import Path
import sys

import rclpy
from rclpy.qos import qos_profile_sensor_data

FORMAL_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(FORMAL_DIR / "harness"))
from e3_wrench_driver import E3WrenchDriver  # noqa: E402


class HumbleCompatibleE3WrenchDriver(E3WrenchDriver):
    @property
    def publishers(self):
        return self._e3_registered_publishers

    @publishers.setter
    def publishers(self, value):
        self._e3_registered_publishers = value

    def create_subscription(self, msg_type, topic, callback, qos_profile, **kwargs):
        # Gazebo Classic publishes /clock best-effort in this sealed
        # environment.  Select a compatible transport QoS without changing
        # the inherited /clock-based timing state machine.
        if topic == "/clock":
            qos_profile = qos_profile_sensor_data
        return super().create_subscription(
            msg_type, topic, callback, qos_profile, **kwargs)


def main():
    rclpy.init()
    node = HumbleCompatibleE3WrenchDriver()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
