from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument(
            'assignment_mode',
            default_value='safety_aware',
            description='fixed/distance_hungarian/safety_aware'),
        DeclareLaunchArgument(
            'lfs_runtime_mode',
            default_value='candidate_v2',
            description='candidate_v2/legacy_v1'),
        DeclareLaunchArgument(
            'lfs_policy_file',
            default_value='',
            description='Empty selects installed paper-current policy'),
        Node(
            package='location_allocate',
            executable='location_allocate',
            name='location_allocate',
            parameters=[{
                'assignment_mode': LaunchConfiguration('assignment_mode'),
                'lfs_runtime_mode': LaunchConfiguration('lfs_runtime_mode'),
                'lfs_policy_file': LaunchConfiguration('lfs_policy_file'),
            }],
            output='screen'),
    ])
