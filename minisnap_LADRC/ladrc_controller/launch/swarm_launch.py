"""
多机集群启动文件
用法：ros2 launch ladrc_controller swarm_launch.py uav_ids:=[1,2,3]
所有 UAV 共用 config/ladrc_params.yaml 统一参数，只需修改那一个文件
"""
from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    pkg_share = get_package_share_directory('ladrc_controller')
    config_file = os.path.join(pkg_share, 'config', 'ladrc_params.yaml')

    def create_uav_nodes(context):
        ids_str = LaunchConfiguration('uav_ids').perform(context)
        ids = [int(x.strip()) for x in ids_str.strip('[]').split(',') if x.strip()]

        nodes = []
        for uid in ids:
            nodes.append(Node(
                package='ladrc_controller',
                executable='ladrc_position_controller_node',
                namespace=f'/uav{uid}',
                name='ladrc_position_controller',
                parameters=[config_file],
                output='screen',
                emulate_tty=True,
            ))
        return nodes

    return LaunchDescription([
        DeclareLaunchArgument(
            'uav_ids',
            default_value='[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]',
            description='要启动的 UAV ID 列表'),
        OpaqueFunction(function=create_uav_nodes),
    ])
