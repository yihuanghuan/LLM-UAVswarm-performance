"""Calibration-only wrapper for registered C0-A world-frame initial states."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
from lfs_policy import load_paper_policy


def px4_topic(px4_namespace, suffix):
    return f"/{px4_namespace}/{suffix}"


def generate_launch_description():
    def create_nodes(context):
        ids = [
            int(value.strip())
            for value in LaunchConfiguration("uav_ids").perform(context).strip("[]").split(",")
            if value.strip()
        ]
        layout = LaunchConfiguration("layout").perform(context)
        if layout not in {"single_origin", "parallel_scale"}:
            raise ValueError(f"unsupported C0-A layout: {layout}")
        policy_file = LaunchConfiguration("lfs_policy_file").perform(context)
        params_file = LaunchConfiguration("params_file").perform(context)
        controller_policy = load_paper_policy(policy_file).controller.ros_parameters()
        nodes = []
        for uid in ids:
            px4_namespace = f"px4_{uid}"
            remappings = [
                (f"/uav{uid}/fmu/out/vehicle_odometry", px4_topic(px4_namespace, "fmu/out/vehicle_odometry")),
                (f"/uav{uid}/fmu/out/vehicle_status", px4_topic(px4_namespace, "fmu/out/vehicle_status")),
                (f"/uav{uid}/fmu/in/offboard_control_mode", px4_topic(px4_namespace, "fmu/in/offboard_control_mode")),
                (f"/uav{uid}/fmu/in/trajectory_setpoint", px4_topic(px4_namespace, "fmu/in/trajectory_setpoint")),
                (f"/uav{uid}/fmu/in/vehicle_command", px4_topic(px4_namespace, "fmu/in/vehicle_command")),
            ]
            for other_id in ids:
                if other_id != uid:
                    remappings.append((
                        f"/uav{other_id}/fmu/out/vehicle_odometry",
                        px4_topic(f"px4_{other_id}", "fmu/out/vehicle_odometry"),
                    ))
            if layout == "single_origin":
                offset_x, offset_y = 0.0, 0.0
            else:
                offset_x, offset_y = -4.0, 3.0 * uid
            nodes.append(Node(
                package="ladrc_controller",
                executable="ladrc_position_controller_node",
                namespace=f"/uav{uid}",
                name="ladrc_position_controller",
                parameters=[
                    params_file,
                    {
                        "enu_offset_x": offset_x,
                        "enu_offset_y": offset_y,
                        "enu_offset_z": 1.5,
                        "px4_target_system": uid + 1,
                        "neighbor_uav_ids": ids,
                        "control_mode": "ladrc_acceleration",
                        "avoidance_mode": "iapf_dual",
                        "iapf_escape_mode": "id_order",
                    },
                    controller_policy,
                ],
                remappings=remappings,
                output="screen",
                emulate_tty=True,
            ))
        return nodes

    default_params = (
        get_package_share_directory("ladrc_controller") + "/config/ladrc_params.yaml"
    )
    default_policy = (
        get_package_share_directory("lfs_policy") + "/config/lfs_policy.paper_current.yaml"
    )
    return LaunchDescription([
        DeclareLaunchArgument("uav_ids", default_value="[1]"),
        DeclareLaunchArgument("layout", default_value="single_origin"),
        DeclareLaunchArgument("lfs_policy_file", default_value=default_policy),
        DeclareLaunchArgument("params_file", default_value=default_params),
        OpaqueFunction(function=create_nodes),
    ])
