#!/usr/bin/env python3
"""Launch one controller batch while retaining the full swarm neighbor set."""

from __future__ import annotations

import json
import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from lfs_policy import load_paper_policy


def parse_ids(value: str) -> list[int]:
    return [int(item) for item in value.strip("[]").split(",") if item.strip()]


def topic(namespace: str, suffix: str) -> str:
    return f"/{namespace}/{suffix}"


def generate_launch_description() -> LaunchDescription:
    package_share = get_package_share_directory("ladrc_controller")
    config_file = os.path.join(package_share, "config", "ladrc_params.yaml")

    def create_nodes(context):
        launch_ids = parse_ids(LaunchConfiguration("launch_uav_ids").perform(context))
        swarm_ids = parse_ids(LaunchConfiguration("swarm_uav_ids").perform(context))
        if not launch_ids or not set(launch_ids) <= set(swarm_ids):
            raise RuntimeError("controller batch IDs must be a non-empty subset of full swarm IDs")
        with open(LaunchConfiguration("layout_json").perform(context), encoding="utf-8") as stream:
            layout = {int(row["uav_id"]): row for row in json.load(stream)["positions"]}
        if set(layout) != set(swarm_ids):
            raise RuntimeError("layout/full-swarm UAV-ID mismatch")
        policy = load_paper_policy(LaunchConfiguration("lfs_policy_file").perform(context)).controller.ros_parameters()
        control_mode = LaunchConfiguration("control_mode").perform(context)
        avoidance_mode = LaunchConfiguration("avoidance_mode").perform(context)
        escape_mode = LaunchConfiguration("iapf_escape_mode").perform(context)
        nodes = []
        for uid in launch_ids:
            namespace = f"px4_{uid}"
            remappings = [
                (f"/uav{uid}/fmu/out/vehicle_odometry", topic(namespace, "fmu/out/vehicle_odometry")),
                (f"/uav{uid}/fmu/out/vehicle_status", topic(namespace, "fmu/out/vehicle_status")),
                (f"/uav{uid}/fmu/in/offboard_control_mode", topic(namespace, "fmu/in/offboard_control_mode")),
                (f"/uav{uid}/fmu/in/trajectory_setpoint", topic(namespace, "fmu/in/trajectory_setpoint")),
                (f"/uav{uid}/fmu/in/vehicle_command", topic(namespace, "fmu/in/vehicle_command")),
            ]
            for other in swarm_ids:
                if other != uid:
                    remappings.append((f"/uav{other}/fmu/out/vehicle_odometry", topic(f"px4_{other}", "fmu/out/vehicle_odometry")))
            position = layout[uid]
            nodes.append(Node(
                package="ladrc_controller",
                executable="ladrc_position_controller_node",
                namespace=f"/uav{uid}",
                name="ladrc_position_controller",
                parameters=[config_file, {
                    "enu_offset_x": float(position["x"]),
                    "enu_offset_y": float(position["y"]),
                    "enu_offset_z": 0.0,
                    "px4_target_system": uid + 1,
                    "neighbor_uav_ids": swarm_ids,
                    "iapf_escape_mode": escape_mode,
                    "iapf_filter_alpha": 0.20,
                    "control_mode": control_mode,
                    "avoidance_mode": avoidance_mode,
                }, policy],
                remappings=remappings,
                output="screen",
                emulate_tty=True,
            ))
        return nodes

    default_policy = os.path.join(get_package_share_directory("lfs_policy"), "config", "lfs_policy.paper_current.yaml")
    return LaunchDescription([
        DeclareLaunchArgument("layout_json"),
        DeclareLaunchArgument("launch_uav_ids"),
        DeclareLaunchArgument("swarm_uav_ids"),
        DeclareLaunchArgument("lfs_policy_file", default_value=default_policy),
        DeclareLaunchArgument("control_mode", default_value="ladrc_acceleration"),
        DeclareLaunchArgument("avoidance_mode", default_value="iapf_dual"),
        DeclareLaunchArgument("iapf_escape_mode", default_value="id_order"),
        OpaqueFunction(function=create_nodes),
    ])
