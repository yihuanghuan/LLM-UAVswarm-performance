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
        Node(
            package='location_allocate',
            executable='location_allocate',
            name='location_allocate',
            parameters=[{
                'assignment_mode': LaunchConfiguration('assignment_mode'),
            }],
            output='screen'),
    ])
