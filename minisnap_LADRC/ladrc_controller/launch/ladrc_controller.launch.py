from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from ament_index_python.packages import get_package_share_directory
from launch_ros.parameter_descriptions import ParameterValue
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
            'enable_iapf_accel_feedforward',
            default_value='true',
            description='Whether to publish IAPF acceleration feedforward'
        ),
        DeclareLaunchArgument(
            'enable_ladrc_accel_feedforward',
            default_value='false',
            description='Whether to publish LADRC acceleration feedforward'
        ),
        DeclareLaunchArgument(
            'semantic_gain_mode',
            default_value='task_conditioned',
            description='LADRC gain mode: fixed or task_conditioned'
        ),
        DeclareLaunchArgument(
            'fixed_gain_multiplier',
            default_value='1.0',
            description='Fixed LADRC gain multiplier'
        ),

        Node(
            package='ladrc_controller',
            executable='ladrc_position_controller_node',
            name='ladrc_position_controller',
            namespace=LaunchConfiguration('namespace'),
            parameters=[
                LaunchConfiguration('params_file'),
                {
                    'enable_iapf_accel_feedforward': ParameterValue(
                        LaunchConfiguration('enable_iapf_accel_feedforward'),
                        value_type=bool),
                    'enable_ladrc_accel_feedforward': ParameterValue(
                        LaunchConfiguration('enable_ladrc_accel_feedforward'),
                        value_type=bool),
                    'semantic_gain_mode': ParameterValue(
                        LaunchConfiguration('semantic_gain_mode'),
                        value_type=str),
                    'fixed_gain_multiplier': ParameterValue(
                        LaunchConfiguration('fixed_gain_multiplier'),
                        value_type=float),
                },
            ],
            output='screen'
        ),
    ])
