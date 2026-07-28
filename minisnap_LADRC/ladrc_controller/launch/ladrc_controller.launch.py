from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from ament_index_python.packages import get_package_share_directory
import os


def generate_launch_description():
    pkg_share = get_package_share_directory('ladrc_controller')
    config_file = os.path.join(pkg_share, 'config', 'ladrc_params.yaml')

    return LaunchDescription([
        DeclareLaunchArgument(
            'params_file',
            default_value=config_file,
            description='Path to LADRC parameters file'
        ),

        DeclareLaunchArgument(
            'namespace',
            default_value='',
            description='Namespace for this UAV node (e.g. /uav1)'
        ),

        DeclareLaunchArgument(
            'avoidance_mode',
            default_value='iapf_dual',
            description='off/classic_position/iapf_position/iapf_dual'
        ),

        DeclareLaunchArgument(
            'iapf_escape_mode',
            default_value='id_order',
            description='none/fixed_positive_z/id_order'
        ),

        Node(
            package='ladrc_controller',
            executable='ladrc_position_controller_node',
            name='ladrc_position_controller',
            namespace=LaunchConfiguration('namespace'),
            parameters=[
                LaunchConfiguration('params_file'),
                {
                    'avoidance_mode': LaunchConfiguration('avoidance_mode'),
                    'iapf_escape_mode': LaunchConfiguration('iapf_escape_mode'),
                },
            ],
            output='screen'
        ),
    ])
