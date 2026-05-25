"""
多机集群启动文件
用法：ros2 launch ladrc_controller swarm_launch.py uav_ids:=[1,2,3]
PX4 命名空间映射 (sitl_multiple_run.sh 从 instance 1 开始):
  UAV1 → PX4 instance 1 (命名空间 /px4_1)
  UAV2 → PX4 instance 2 (命名空间 /px4_2)
  UAV3 → PX4 instance 3 (命名空间 /px4_3)
  通用: UAV{N} → PX4 instance {N} → 命名空间 /px4_{N}
  注意: instance 0 仅在单机 make px4_sitl 时出现 (无命名空间)
"""
from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from ament_index_python.packages import get_package_share_directory
import os


def px4_topic(px4_ns: str, suffix: str) -> str:
    """构造 PX4 话题绝对路径"""
    if px4_ns:
        return f'/{px4_ns}/{suffix}'
    return f'/{suffix}'


def generate_launch_description():
    pkg_share = get_package_share_directory('ladrc_controller')
    config_file = os.path.join(pkg_share, 'config', 'ladrc_params.yaml')

    def create_uav_nodes(context):
        ids_str = LaunchConfiguration('uav_ids').perform(context)
        ids = [int(x.strip()) for x in ids_str.strip('[]').split(',') if x.strip()]

        nodes = []
        for uid in ids:
            # PX4 instance 编号：sitl_multiple_run.sh 从 1 开始（-i 1），
            # 单机模式 make px4_sitl 从 0 开始。这里默认多机模式从 1 开始
            px4_instance = uid  # uid 直接对应 PX4 instance
            px4_ns = '' if px4_instance == 0 else f'px4_{px4_instance}'

            # 本节点的 PX4 话题重映射
            # 使用绝对路径 (命名空间展开后的路径) 作为 from，确保 remap 正确匹配
            remappings = [
                (f'/uav{uid}/fmu/out/vehicle_odometry', px4_topic(px4_ns, 'fmu/out/vehicle_odometry')),
                (f'/uav{uid}/fmu/in/offboard_control_mode', px4_topic(px4_ns, 'fmu/in/offboard_control_mode')),
                (f'/uav{uid}/fmu/in/trajectory_setpoint', px4_topic(px4_ns, 'fmu/in/trajectory_setpoint')),
                (f'/uav{uid}/fmu/in/vehicle_command', px4_topic(px4_ns, 'fmu/in/vehicle_command')),
            ]

            # 邻居 Odom 订阅重映射：/uav{M}/fmu/out/vehicle_odometry → PX4 实例 {M-1}
            for other_id in ids:
                if other_id == uid:
                    continue
                other_px4 = other_id  # PX4 instance = UAV id (1-indexed)
                other_px4_ns = '' if other_px4 == 0 else f'px4_{other_px4}'
                remappings.append(
                    (f'/uav{other_id}/fmu/out/vehicle_odometry',
                     px4_topic(other_px4_ns, 'fmu/out/vehicle_odometry'))
                )

            # sitl_multiple_run.sh 默认 spawn 位置: X=0, Y=3*instance, Z=0.83
            # 将偏移量传入节点，odom 发布时加上偏移，调度层可见全局坐标
            spawn_offset = {
                'enu_offset_x': 0.0,
                'enu_offset_y': 3.0 * uid,  # instance N → Y = 3*N
                'enu_offset_z': 0.0,
            }

            nodes.append(Node(
                package='ladrc_controller',
                executable='ladrc_position_controller_node',
                namespace=f'/uav{uid}',
                name='ladrc_position_controller',
                parameters=[config_file, spawn_offset, {'neighbor_uav_ids': ids}],
                remappings=remappings,
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
