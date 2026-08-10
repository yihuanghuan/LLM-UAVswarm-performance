from launch import LaunchDescription
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from ament_index_python.packages import get_package_share_directory
import os
from lfs_policy import load_policy


def generate_launch_description():
    pkg_share = get_package_share_directory('ladrc_controller')
    config_file = os.path.join(pkg_share, 'config', 'ladrc_params.yaml')
    default_policy_file = os.path.join(
        get_package_share_directory('lfs_policy'),
        'config', 'lfs_policy.migration.yaml')

    def create_node(context):
        policy_file = LaunchConfiguration('lfs_policy_file').perform(context)
        controller_policy = load_policy(
            policy_file, production=True).controller.ros_parameters()
        return [Node(
            package='ladrc_controller',
            executable='ladrc_position_controller_node',
            name='ladrc_position_controller',
            namespace=LaunchConfiguration('namespace'),
            parameters=[
                LaunchConfiguration('params_file'),
                {
                    'avoidance_mode': LaunchConfiguration('avoidance_mode'),
                    'iapf_escape_mode': LaunchConfiguration('iapf_escape_mode'),
                    'iapf_enter_distance': ParameterValue(
                        LaunchConfiguration('iapf_enter_distance'),
                        value_type=float),
                    'iapf_exit_distance': ParameterValue(
                        LaunchConfiguration('iapf_exit_distance'),
                        value_type=float),
                    'iapf_filter_alpha': ParameterValue(
                        LaunchConfiguration('iapf_filter_alpha'),
                        value_type=float),
                },
                controller_policy,
            ],
            output='screen'
        )]

    return LaunchDescription([
        DeclareLaunchArgument(
            'lfs_policy_file',
            default_value=default_policy_file,
            description='Complete Candidate production/migration policy'
        ),

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
        DeclareLaunchArgument(
            'iapf_enter_distance', default_value='1.50'),
        DeclareLaunchArgument(
            'iapf_exit_distance', default_value='1.65'),
        DeclareLaunchArgument(
            'iapf_filter_alpha', default_value='0.20'),

        OpaqueFunction(function=create_node),
    ])
