import json
import math
import time
from pathlib import Path
from typing import Dict, List

# -------------------------- ROS2 依赖导入 --------------------------
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Point
from nav_msgs.msg import Odometry
from rclpy.qos import qos_profile_sensor_data
from uav_swarm_interfaces.msg import UAVExecutionCommand, UAVStatus, UAVSwarmCommand
# -------------------------------------------------------------------
from .no_location import CandidateParseError, parse_uav_command
from .safety_aware_allocator import SafetyAwareTopologyAllocator
from .execution_command_builder import (
    build_parallel_command_batch,
    build_task_command_batch,
)
from .late_resolution import (
    LateResolutionPolicy,
    resolve_execution_parallel,
    resolve_execution_task,
)
from .state_snapshot import FreshStateSnapshotManager
from .state_snapshot import SnapshotError
from .mission_executor import MissionRuntimeCallbacks
from .candidate_mission_runtime import execute_candidate_payload
from .lfs_validator import early_validate_candidate_mission
from .policy_adapter import load_runtime_policy
from .trace_logger import append_resolution_trace
from .state_ingest import ingest_standardized_odometry
from .completion_tracker import CompletionGenerationTracker

# ====================== 硬编码：无人机初始坐标 + ID (全局地图) ======================
# 注意：这里是全局数据库，存储所有无人机的状态
all_uav_ids = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
all_initial_positions = [
    [1.4, 0.0, 1.5], [-0.7, 1.2, 1.5], [-0.7, -1.2, 1.5],
    [1.4, 0.0, 3.0], [-0.7, 1.2, 3.0], [-0.7, -1.2, 3.0],
    [-0.7, 1.2, 4.0], [-0.7, -1.2, 4.0], [1.4, 0.0, 1.0],
    [-0.7, 1.2, 1.0]
]


def _default_migration_policy_path() -> str:
    try:
        from ament_index_python.packages import get_package_share_directory

        return str(
            Path(get_package_share_directory('lfs_policy'))
            / 'config'
            / 'lfs_policy.migration.yaml'
        )
    except Exception:
        return str(
            Path(__file__).resolve().parents[2]
            / 'lfs_policy'
            / 'config'
            / 'lfs_policy.migration.yaml'
        )

# ====================== 1. 坐标生成层  ======================


class FormationGenerator:
    def __init__(self, global_center: List[float], formation_radius: float):
        self.center = global_center
        self.radius = formation_radius

    def generate_line(self, n: int) -> List[List[float]]:
        points = []
        start_x = self.center[0] - (n - 1) * self.radius / 2
        for i in range(n):
            points.append([start_x + i * self.radius, self.center[1], self.center[2]])
        return points

    def generate_circle(self, n: int) -> List[List[float]]:
        points = []
        for i in range(n):
            theta = 2 * math.pi * i / n
            x = self.center[0] + self.radius * math.cos(theta)
            y = self.center[1] + self.radius * math.sin(theta)
            points.append([x, y, self.center[2]])
        return points

    def generate_sphere(self, n: int) -> List[List[float]]:
        points = []
        phi = math.pi * (3. - math.sqrt(5.))
        for i in range(n):
            y_norm = 1 - (i / float(n - 1)) * 2
            radius_at_y = math.sqrt(1 - y_norm * y_norm)
            theta = phi * i
            x = self.center[0] + math.cos(theta) * radius_at_y * self.radius
            y = self.center[1] + y_norm * self.radius
            z = self.center[2] + math.sin(theta) * radius_at_y * self.radius
            points.append([x, y, z])
        return points

    def generate(self, formation_type: str, uav_count: int) -> List[List[float]]:
        if formation_type in ["Line", "Lineup"]:
            return self.generate_line(uav_count)
        if formation_type in ["Circle", "Polygon", "Triangle"]:
            return self.generate_circle(uav_count)
        if formation_type == "Sphere":
            return self.generate_sphere(uav_count)
        if formation_type == "Free":
            return []
        raise ValueError(f"不支持的编队类型: {formation_type}")

# ====================== 2. 安全感知拓扑分配层 ======================


class TopologyAllocator(SafetyAwareTopologyAllocator):
    def allocate(self, initial, target, cross_penalty=10.0, duration=3.0):
        del cross_penalty
        return super().allocate(initial, target, duration=duration)

# ====================== 3. ROS2 核心调度层  ======================


class UAVFormationNode(Node):
    def __init__(self):
        super().__init__('location_allocate')
        self.declare_parameter('assignment_mode', 'safety_aware')
        self.declare_parameter('lfs_runtime_mode', 'candidate_v2')
        self.declare_parameter('lfs_policy_file', '')
        self.declare_parameter('uav_ids', all_uav_ids)
        self.declare_parameter('candidate_completion_timeout', 120.0)
        self.declare_parameter('candidate_state_timeout', -1.0)
        self.declare_parameter('candidate_snapshot_skew', -1.0)
        assignment_mode = self.get_parameter(
            'assignment_mode').get_parameter_value().string_value
        if assignment_mode not in ('fixed', 'distance_hungarian', 'safety_aware'):
            raise ValueError(
                'assignment_mode must be fixed, distance_hungarian, or safety_aware')

        self.runtime_mode = self.get_parameter(
            'lfs_runtime_mode').get_parameter_value().string_value
        if self.runtime_mode not in ('candidate_v2', 'legacy_v1'):
            raise ValueError('lfs_runtime_mode must be candidate_v2 or legacy_v1')
        self.available_uav_ids = [
            int(value) for value in self.get_parameter('uav_ids').value
        ]
        if not self.available_uav_ids or len(self.available_uav_ids) != len(
                set(self.available_uav_ids)):
            raise ValueError('uav_ids must be a non-empty unique list')
        self.policy_config = None
        self.candidate_policy = None
        if self.runtime_mode == 'candidate_v2':
            configured_path = self.get_parameter(
                'lfs_policy_file').get_parameter_value().string_value
            policy_path = configured_path or _default_migration_policy_path()
            self.policy_config, self.candidate_policy = load_runtime_policy(
                policy_path)
            self.get_logger().info(
                f"Candidate v2 enabled with policy "
                f"{self.policy_config.configuration_id}")

        # Legacy Point state remains independent from Candidate snapshots.
        self.uav_state_map: Dict[int, List[float]] = {}
        for uid in self.available_uav_ids:
            self.uav_state_map[uid] = [0.0, 0.0, 0.0]

        # -------------------------- 发布者管理 --------------------------
        self.publisher = {}
        self.execution_publisher = {}
        for uid in self.available_uav_ids:
            topic_name = f'/uav{uid}/swarm_command'
            self.publisher[uid] = self.create_publisher(
                UAVSwarmCommand, topic_name, 10
            )
            self.execution_publisher[uid] = self.create_publisher(
                UAVExecutionCommand, f'/uav{uid}/execution_command', 10)
            self.get_logger().info(f"创建发布者: {topic_name}")

        # -------------------------- 订阅者管理 (odom 位置 + status 状态) --------------------------
        self.uav_hover_status: Dict[int, bool] = {}
        self.status_sub = {}
        self.odom_sub = {}
        self.swarm_state_sub = {}
        self.completion_tracker = CompletionGenerationTracker()
        for uid in self.available_uav_ids:
            self.uav_hover_status[uid] = False
            # 订阅悬停状态
            topic_name = f'/uav{uid}/status'
            self.status_sub[uid] = self.create_subscription(
                UAVStatus, topic_name,
                lambda msg, uid=uid: self._status_callback(msg, uid), 10)
            # 订阅 ENU 位置
            topic_name = f'/uav{uid}/odom'
            self.odom_sub[uid] = self.create_subscription(
                Point, topic_name,
                lambda msg, uid=uid: self._odom_callback(msg, uid), 10)
            if self.runtime_mode == 'candidate_v2':
                self.swarm_state_sub[uid] = self.create_subscription(
                    Odometry,
                    f'/uav{uid}/swarm_state',
                    lambda msg, uid=uid: self._swarm_state_callback(msg, uid),
                    qos_profile_sensor_data,
                )
            self.get_logger().info(
                f"创建订阅者: /uav{uid}/status, /uav{uid}/odom"
                + (f", /uav{uid}/swarm_state" if self.runtime_mode == 'candidate_v2' else "")
            )

        self.snapshot_manager = None
        if self.policy_config is not None:
            state_policy = self.policy_config.state
            self.snapshot_manager = FreshStateSnapshotManager(
                state_policy.state_timeout,
                state_policy.snapshot_skew,
                require_velocity=state_policy.require_velocity,
                allow_receive_time_fallback=(
                    state_policy.allow_receive_time_fallback
                ),
            )
        self._mission_counter = 0

    def _publish_single_goal(self, mission_id: int, uav_id: int, position: List[float],
                             duration: float, motion_style: str, safety_factor: float):
        """向单个无人机发送 swarm_command 自定义消息."""
        if uav_id not in self.publisher:
            self.get_logger().warn(f"未找到 UAV{uav_id} 的发布者，跳过")
            return

        msg = UAVSwarmCommand()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "world"
        msg.mission_id = mission_id
        msg.uav_id = uav_id
        msg.target_pos.x = position[0]
        msg.target_pos.y = position[1]
        msg.target_pos.z = position[2]
        msg.duration = duration
        msg.motion_style = motion_style
        msg.safety_factor = safety_factor

        self.publisher[uav_id].publish(msg)

    def _status_callback(self, msg: UAVStatus, uid: int):
        """接收 C++ 执行层反馈的悬停状态."""
        if msg.is_hover_stable and not self.uav_hover_status.get(uid, False):
            self.get_logger().info(f"   >>> UAV{uid} 到达目标并悬停稳定!")
        self.uav_hover_status[uid] = msg.is_hover_stable
        self.completion_tracker.update(uid, msg.is_hover_stable)

    def _odom_callback(self, msg: Point, uid: int):
        """接收 C++ 节点低频发布的 ENU 位置，更新全局状态地图."""
        self.uav_state_map[uid] = [msg.x, msg.y, msg.z]
        # Candidate production deliberately never feeds Point into its snapshot.

    def _swarm_state_callback(self, msg: Odometry, uid: int):
        """Ingest standardized world/ENU state with source timestamp."""
        if self.snapshot_manager is None:
            return
        receive_timestamp = self.get_clock().now().nanoseconds / 1e9
        try:
            ingest_standardized_odometry(
                self.snapshot_manager, msg, uid, receive_timestamp
            )
        except ValueError as exc:
            self.get_logger().error(
                f"拒绝 UAV{uid} swarm_state: {exc}")

    def _fresh_snapshot(self, uav_ids):
        if self.snapshot_manager is None or self.policy_config is None:
            raise RuntimeError('Candidate snapshot manager is unavailable')
        deadline = time.monotonic() + self.policy_config.state.fresh_state_wait_timeout
        last_error = None
        while time.monotonic() <= deadline:
            rclpy.spin_once(self, timeout_sec=0.05)
            now = self.get_clock().now().nanoseconds / 1e9
            try:
                return self.snapshot_manager.snapshot(uav_ids, now)
            except SnapshotError as exc:
                last_error = exc
        raise SnapshotError(
            f"fresh state wait timed out: {last_error or 'no state'}"
        )

    def _arm_candidate_completion(self, uav_ids):
        self.completion_tracker.arm(uav_ids)

    def _publish_candidate_commands(self, commands):
        self._arm_candidate_completion(command.uav_id for command in commands)
        for command in commands:
            publisher = self.execution_publisher.get(int(command.uav_id))
            if publisher is None:
                raise RuntimeError(f"missing execution publisher for UAV{command.uav_id}")
        for command in commands:
            self.execution_publisher[int(command.uav_id)].publish(command)

    def resolve_and_publish_candidate_task(
            self, task: Dict, policy: LateResolutionPolicy,
            mission_id: int, group_id: int = 0):
        """Run the new late-resolution path when explicit policy is supplied."""
        if self.snapshot_manager is None:
            raise RuntimeError(
                'Candidate state freshness parameters are not configured')
        snapshot = self._fresh_snapshot(task['U'])
        resolved = resolve_execution_task(task, snapshot, policy)
        now = self.get_clock().now()
        commands = build_task_command_batch(
            resolved, mission_id, int(task['task_id']), group_id, now.to_msg()
        )
        append_resolution_trace(resolved.trace)
        self._publish_candidate_commands(commands)
        return resolved

    def resolve_and_publish_candidate_parallel(
        self,
        tasks: List[Dict],
        policy: LateResolutionPolicy,
        mission_id: int,
        group_id: int,
        completion_mode: str,
        group_d_plan: float = None,
    ):
        """Resolve and publish one Candidate parallel group from one snapshot."""
        if self.snapshot_manager is None:
            raise RuntimeError(
                'Candidate state freshness parameters are not configured'
            )
        participant_ids = [uid for task in tasks for uid in task['U']]
        snapshot = self._fresh_snapshot(participant_ids)
        if group_d_plan is None:
            group_d_plan = max(
                policy.resolve_safety(float(task['s'])).d_plan
                for task in tasks
            )
        resolved_group = resolve_execution_parallel(
            tasks,
            snapshot,
            policy,
            completion_mode,
            group_d_plan,
        )
        now = self.get_clock().now()
        commands = build_parallel_command_batch(
            resolved_group, mission_id, group_id, now.to_msg()
        )
        for resolved in resolved_group.tasks:
            append_resolution_trace(resolved.trace)
        self._publish_candidate_commands(commands)
        return resolved_group

    def send_goal_positions(
        self,
        task_uav_ids: List[int],
        allocated_positions: List[List[float]],
        task: Dict,
    ):
        """
        广播 UAVSwarmCommand 自定义消息.

        :param task_uav_ids: 本次参与任务的无人机ID列表
        :param allocated_positions: 对应的目标坐标列表，顺序与ID一一对应
        :param task: LLM 解析的原始 task dict (获取 duration / motion_style / safety_factor)
        """
        self.get_logger().info(
            f">>> 正在向 {len(task_uav_ids)} 架无人机发送 swarm_command ..."
        )

        duration = float(task.get('duration_seconds', 3.0))
        mission_id = int(task.get('task_sequence_id', 0))
        motion_style = task.get('motion_profile', 'normal')
        val = task.get('iapf_safety_margin_factor')
        # null 时默认 1.0（配合 YAML 中 K_rep=20, R_safe=2 提供标准避障）
        # 非 null 时按 LLM 指定值单独调节
        safety_factor = float(val) if val is not None else 1.0

        # 先重置悬停状态，再发命令
        for uid in task_uav_ids:
            self.uav_hover_status[uid] = False

        for uid, pos in zip(task_uav_ids, allocated_positions):
            self._publish_single_goal(
                mission_id, uid, pos, duration, motion_style, safety_factor
            )
            self.get_logger().info(
                f"UAV{uid} -> {[round(x, 2) for x in pos]} "
                f"mission={mission_id} dur={duration}s "
                f"style={motion_style} sf={safety_factor}"
            )

    def wait_for_hover_and_time(
        self,
        task_uav_ids: List[int],
        wait_seconds: float,
        timeout: float = 120.0,
    ):
        """等待所有参与任务的无人机到达并悬停稳定."""
        self.get_logger().info(
            f">>> 等待 {len(task_uav_ids)} 架无人机到达并悬停 "
            f"(超时: {timeout}s) ..."
        )

        # 先重置悬停状态，排空 DDS 队列中旧消息
        for uid in task_uav_ids:
            self.uav_hover_status[uid] = False
        flush_start = time.time()
        while time.time() - flush_start < 2.0:
            rclpy.spin_once(self, timeout_sec=0.1)

        start_time = time.time()
        while time.time() - start_time < timeout:
            rclpy.spin_once(self, timeout_sec=0.2)

            # 检查所有参与无人机是否都已悬停
            all_stable = all(
                self.uav_hover_status.get(uid, False) for uid in task_uav_ids
            )
            if all_stable:
                elapsed = time.time() - start_time
                self.get_logger().info(
                    f"   >>> 全部 {len(task_uav_ids)} 架无人机已悬停稳定! "
                    f"(耗时 {elapsed:.1f}s)"
                )

                # 悬停保持计时
                self.get_logger().info(f">>> 开始悬停计时: {wait_seconds} 秒")
                hover_start = time.time()
                while time.time() - hover_start < wait_seconds:
                    rclpy.spin_once(self, timeout_sec=0.2)
                    time.sleep(0.1)
                self.get_logger().info("   悬停等待完成，准备执行下一任务")
                return

            # 打印等待中的进度 (每 5 秒)
            elapsed_seconds = int(time.time() - start_time)
            if elapsed_seconds % 5 == 0 and elapsed_seconds > 0:
                stable_count = sum(
                    1 for uid in task_uav_ids
                    if self.uav_hover_status.get(uid, False)
                )
                self.get_logger().info(
                    f"   等待中... {stable_count}/{len(task_uav_ids)} 已稳定"
                )

        # 超时
        stable_list = [
            uid for uid in task_uav_ids
            if self.uav_hover_status.get(uid, False)
        ]
        unstable_list = [
            uid for uid in task_uav_ids
            if not self.uav_hover_status.get(uid, False)
        ]
        self.get_logger().warn(
            f">>> 悬停等待超时! 已稳定: {stable_list}, 未稳定: {unstable_list}"
        )

    def execute_task(self, task: Dict, skip_wait: bool = False):
        """执行单步任务（核心修改：支持分群）."""
        print(f"\n{'='*60}")
        self.get_logger().info(f"执行任务 {task['task_sequence_id']}")

        # ==========================================
        # 1. 提取核心参数 (新增：提取 uav_id)
        # ==========================================
        center = task['global_center']
        radius = task['parametric_data']['formation_radius']
        f_type = task['parametric_data']['formation_type']

        # 【关键修改】从LLM输出中读取本次参与的无人机ID
        task_uav_ids: List[int] = task['uav_id']
        task_uav_count: int = task['uav_count']

        self.get_logger().info(f"任务参与无人机ID: {task_uav_ids}")

        # ==========================================
        # 2. 收一轮 odom 数据，确保读取的是当前真实位置
        # ==========================================
        for _ in range(10):
            rclpy.spin_once(self, timeout_sec=0.05)

        # ==========================================
        # 3. 从全局状态中提取参与机的当前位置
        # ==========================================
        current_subset = []
        for uid in task_uav_ids:
            if uid in self.uav_state_map:
                current_subset.append(self.uav_state_map[uid].copy())
            else:
                self.get_logger().error(f"严重错误：数据库中找不到 UAV{uid} 的位置！")
                return
        # ==========================================
        # 打印本次任务参与无人机的起始坐标
        # ==========================================
        self.get_logger().info("   ---------- 本次任务起始坐标 ----------")
        self.get_logger().info(f"   {'UAV ID':<8} | {'起始坐标 (x, y, z)':<30}")
        self.get_logger().info("   " + "-" * 45)
        for uid, pos in zip(task_uav_ids, current_subset):
            pos_str = f"[{pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f}]"
            self.get_logger().info(f"   {uid:<8} | {pos_str:<30}")
        self.get_logger().info("   ---------------------------------------")

        # ==========================================
        # 3. 生成目标坐标
        # ==========================================
        generator = FormationGenerator(center, radius)
        targets = generator.generate(f_type, task_uav_count)

        if not targets:
            self.get_logger().info("编队类型: Free (返回初始点)")
            # Free模式：找到这些无人机的初始点
            targets = []
            for uid in task_uav_ids:
                idx = all_uav_ids.index(uid)
                targets.append(all_initial_positions[idx].copy())
        else:
            self.get_logger().info(
                f"编队类型: {f_type} | 中心: {center} | 半径: {radius}"
            )

        # ==========================================
        # 4. 匈牙利算法分配 (仅针对参与机)
        # ==========================================
        allocator = TopologyAllocator()
        # 输入：参与机的当前位置，参与机的目标点
        allocation_duration = float(task.get('duration_seconds', 3.0))
        assignment_mode = self.get_parameter(
            'assignment_mode').get_parameter_value().string_value
        allocated_subset, _ = allocator.allocate_mode_with_metrics(
            current_subset, targets, duration=allocation_duration,
            mode=assignment_mode)
        metrics = allocator.metrics_dict()
        self.get_logger().info(
            "   safety-aware topology cost: "
            f"total={metrics['total']:.3f}, dist={metrics['distance']:.3f}m, "
            f"xy_cross={metrics['xy_crossings']}, "
            f"prox_cross={metrics['proximity_crossings']}, "
            f"safety={metrics['safety']:.3f}, "
            f"d_min={metrics['min_distance']:.3f}m, "
            f"swap_iter={metrics['iterations']}"
        )

        # 打印分配结果映射表
        # ==========================================
        self.get_logger().info("   ---------- 分配结果映射表 ----------")
        self.get_logger().info(f"   {'UAV ID':<8} | {'分配后的目标坐标 (x, y, z)':<30}")
        self.get_logger().info("   " + "-" * 45)
        for uid, pos in zip(task_uav_ids, allocated_subset):
            # 格式化坐标，保留2位小数
            pos_str = f"[{pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f}]"
            self.get_logger().info(f"   {uid:<8} | {pos_str:<30}")
        self.get_logger().info("   ---------------------------------------")

        # ==========================================
        # 5. ROS2 发送坐标 (仅发给参与机)
        # ==========================================
        self.send_goal_positions(task_uav_ids, allocated_subset, task)

        # ==========================================
        # 6. 更新全局状态地图
        # ==========================================
        for uid, new_pos in zip(task_uav_ids, allocated_subset):
            self.uav_state_map[uid] = new_pos.copy()
            self.get_logger().debug(f"更新 UAV{uid} 状态 -> {new_pos}")

        # ==========================================
        # 7. 处理阻塞逻辑
        # ==========================================
        if not skip_wait:
            blocking_triggers = (
                'hover_and_wait', 'continuous_transit', 'direct_execution'
            )
            if (
                task.get('trigger_condition') in blocking_triggers
                or task.get('task_sequence_id', 1) > 1
            ):
                wt = task.get('wait_time') or 0.0
                self.wait_for_hover_and_time(task_uav_ids, wt)

    def execute_grouped_tasks(self, tasks: List[Dict]):
        """Jointly allocate simultaneous disjoint groups and publish together."""
        for _ in range(10):
            rclpy.spin_once(self, timeout_sec=0.05)

        grouped_inputs = []
        durations = []
        for task in tasks:
            uav_ids = [int(uid) for uid in task['uav_id']]
            initial = [self.uav_state_map[uid].copy() for uid in uav_ids]
            generator = FormationGenerator(
                task['global_center'],
                task['parametric_data']['formation_radius'])
            targets = generator.generate(
                task['parametric_data']['formation_type'], len(uav_ids))
            if not targets:
                targets = [
                    all_initial_positions[all_uav_ids.index(uid)].copy()
                    for uid in uav_ids
                ]
            grouped_inputs.append({
                'uav_ids': uav_ids,
                'initial': initial,
                'targets': targets,
            })
            durations.append(float(task.get('duration_seconds', 3.0)))

        if max(durations) - min(durations) > 1e-6:
            raise ValueError(
                'parallel grouped assignment requires an identical duration')
        assignment_mode = self.get_parameter(
            'assignment_mode').get_parameter_value().string_value
        allocator = TopologyAllocator()
        allocated_groups, metrics = allocator.allocate_grouped(
            grouped_inputs, duration=durations[0], mode=assignment_mode)
        self.get_logger().info(
            f"joint grouped assignment mode={assignment_mode} "
            f"d_min={metrics.min_distance:.3f} total={metrics.total:.3f}")

        for task, group_input, allocated in zip(
                tasks, grouped_inputs, allocated_groups):
            self.send_goal_positions(group_input['uav_ids'], allocated, task)
            for uid, position in zip(group_input['uav_ids'], allocated):
                self.uav_state_map[uid] = position.copy()

    def _candidate_failure(self, task, stage, error, mission_id, group_id=0):
        try:
            append_resolution_trace({
                'mission_id': mission_id,
                'group_id': group_id,
                'task_id': int(task.get('task_id', 0)),
                'candidate_lfs': task,
                'configuration_id': (
                    self.policy_config.configuration_id
                    if self.policy_config is not None else None
                ),
                'rejection_stage': stage,
                'rejection_reason': str(error),
            })
        except Exception as trace_error:
            self.get_logger().error(
                f'failed to write Candidate rejection trace: {trace_error}')

    def _wait_elapsed(self, duration: float):
        if not math.isfinite(duration) or duration < 0.0:
            raise ValueError('elapsed wait duration must be finite and non-negative')
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            rclpy.spin_once(
                self, timeout_sec=min(0.1, max(0.0, deadline - time.monotonic()))
            )

    def _wait_candidate_stable(self, uav_ids):
        configured_timeout = float(
            self.get_parameter('candidate_completion_timeout').value)
        deadline = time.monotonic() + configured_timeout
        ids = tuple(int(uid) for uid in uav_ids)
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.1)
            if self.completion_tracker.all_stable(ids):
                return
        pending = [uid for uid in ids if not self.completion_tracker.is_stable(uid)]
        raise TimeoutError(f'Candidate hover completion timed out: {pending}')

    def _wait_candidate_machine(self, machine, resolved):
        if machine.completion_event == 'stable':
            self._wait_candidate_stable(resolved.executable_lfs.uav_ids)
        elif machine.completion_event == 'trajectory_complete':
            self._wait_elapsed(resolved.executable_lfs.duration)
        else:
            raise ValueError(
                f'unsupported completion event: {machine.completion_event}')

    def _wait_candidate_parallel(self, machines, resolved_group):
        started = time.monotonic()
        configured_timeout = float(
            self.get_parameter('candidate_completion_timeout').value)
        records = []
        for machine, resolved in zip(machines, resolved_group.tasks):
            records.append({
                'machine': machine,
                'resolved': resolved,
                'completion_deadline': (
                    started + resolved.executable_lfs.duration
                    if machine.completion_event == 'trajectory_complete'
                    else None
                ),
                'completed': False,
                'wait_deadline': None,
                'done': False,
            })
        longest_timed_path = max(
            record['resolved'].executable_lfs.duration
            + (
                record['machine'].post_completion_wait.duration
                if record['machine'].post_completion_wait is not None
                and record['machine'].post_completion_wait.duration is not None
                else 0.0
            )
            for record in records
        )
        timeout = max(configured_timeout, longest_timed_path)
        while time.monotonic() - started < timeout:
            rclpy.spin_once(self, timeout_sec=0.05)
            now = time.monotonic()
            for record in records:
                if not record['completed']:
                    machine = record['machine']
                    resolved = record['resolved']
                    if machine.completion_event == 'stable':
                        completed = self.completion_tracker.all_stable(
                            resolved.executable_lfs.uav_ids)
                    elif machine.completion_event == 'trajectory_complete':
                        completed = now >= record['completion_deadline']
                    else:
                        raise ValueError(
                            f'unsupported completion event: '
                            f'{machine.completion_event}')
                    if completed:
                        record['completed'] = True
                        wait = machine.post_completion_wait
                        if wait is None:
                            record['done'] = True
                        elif wait.condition == 'elapsed' and wait.duration is not None:
                            record['wait_deadline'] = now + wait.duration
                        else:
                            raise ValueError('unsupported parallel post-completion wait')
                elif not record['done'] and now >= record['wait_deadline']:
                    record['done'] = True
            if all(record['done'] for record in records):
                return
        raise TimeoutError('Candidate parallel completion timed out')

    def run_candidate_mission(self, candidate_mission: Dict):
        """Production Candidate Mission Graph and late-resolution runtime."""
        if self.runtime_mode != 'candidate_v2' or self.candidate_policy is None:
            raise RuntimeError('Candidate runtime is not enabled')
        # Early validation is repeated at the execution boundary even though
        # the parser already validates its output.
        validated = early_validate_candidate_mission(candidate_mission)
        for node in validated['mission']['nodes']:
            tasks = node.get('tasks', [])
            if node['type'] == 'task':
                tasks = [node['task']]
            for task in tasks:
                self.candidate_policy.resolve_safety(float(task['s']))
        self._mission_counter += 1
        mission_id = self._mission_counter
        group_counter = {'value': 0}

        def execute_task(machine):
            try:
                resolved = self.resolve_and_publish_candidate_task(
                    machine.task, self.candidate_policy, mission_id)
                self._wait_candidate_machine(machine, resolved)
            except Exception as exc:
                self._candidate_failure(
                    machine.task, 'task_runtime', exc, mission_id)
                raise

        def execute_parallel(machines, completion_mode):
            group_counter['value'] += 1
            group_id = group_counter['value']
            tasks = [machine.task for machine in machines]
            try:
                resolved = self.resolve_and_publish_candidate_parallel(
                    tasks,
                    self.candidate_policy,
                    mission_id,
                    group_id,
                    completion_mode,
                )
                self._wait_candidate_parallel(machines, resolved)
            except Exception as exc:
                for task in tasks:
                    self._candidate_failure(
                        task, 'parallel_runtime', exc, mission_id, group_id)
                raise

        def execute_wait(wait_spec):
            if wait_spec.condition != 'elapsed' or wait_spec.duration is None:
                raise ValueError('unsupported WaitNode')
            self._wait_elapsed(wait_spec.duration)

        compiled = execute_candidate_payload(
            validated,
            MissionRuntimeCallbacks(
                execute_task=execute_task,
                execute_parallel=execute_parallel,
                execute_wait=execute_wait,
            ),
        )
        self.get_logger().info(
            f'Candidate mission {mission_id} completed')
        return compiled

    def run_mission(self, llm_output: Dict):
        tasks = llm_output.get('task_sequences', [])
        if not tasks:
            self.get_logger().error("LLM 输出为空，没有任务可执行")
            return

        i = 0
        while i < len(tasks):
            # 收集连续、UAV 集合不重叠的任务编组（并行执行）
            group = [tasks[i]]
            group_ids = set(tasks[i].get('uav_id', []))
            j = i + 1
            while j < len(tasks):
                next_ids = set(tasks[j].get('uav_id', []))
                if group_ids & next_ids:  # 有重叠 → 不能并行
                    break
                group.append(tasks[j])
                group_ids |= next_ids
                j += 1

            if len(group) > 1:
                self.get_logger().info(f">>> 并行执行任务 {i+1}-{j}（UAV 集合不重叠）")
                self.execute_grouped_tasks(group)
                all_ids = list(group_ids)
                self.get_logger().info(f">>> 等待 {len(all_ids)} 架无人机全部悬停...")
                self.wait_for_hover_and_time(all_ids, 1.0)
            else:
                if i > 0:
                    prev_ids = set(tasks[i-1].get('uav_id', []))
                    self.get_logger().info(">>> 等待前一任务悬停...")
                    self.wait_for_hover_and_time(list(prev_ids), 1.0)
                self.execute_task(tasks[i])
            i = j

        self.get_logger().info(">>> 所有任务序列执行完毕！")
# ====================== 主入口 (终端输入循环) ======================


def execute_runtime_payload(node, payload):
    """One explicit dispatch point; Candidate errors never enter legacy."""
    if node.runtime_mode == 'candidate_v2':
        return node.run_candidate_mission(payload)
    if node.runtime_mode == 'legacy_v1':
        return node.run_mission(payload)
    raise ValueError(f'unsupported runtime mode: {node.runtime_mode}')


def main():
    rclpy.init()

    node = UAVFormationNode()
    test_ros = (
        f"当前可用无人机编号: {node.available_uav_ids}，"
        f"总数: {len(node.available_uav_ids)}"
    )

    try:
        # 主循环：持续等待输入
        while True:
            # 获取用户输入
            user_command = input("\n请输入无人机编队指令: ")

            # 退出指令
            if user_command.strip().lower() in ["exit", "quit", "q"]:
                break

            # 空输入跳过
            if not user_command.strip():
                continue

            # 调用LLM解析
            print("正在调用 LLM 解析指令...")
            # test_ros 仅用于让 LLM 判断可用 UAV 数量。
            try:
                llm_result = parse_uav_command(
                    user_command, test_ros, node.runtime_mode)
            except CandidateParseError as exc:
                node.get_logger().error(str(exc))
                continue

            # 打印解析结果（保持原有格式）
            print("\n" + "=" * 50)
            print("最终解析结果：")
            print("=" * 50)
            print(json.dumps(llm_result, indent=2, ensure_ascii=False))

            # 执行任务
            try:
                execute_runtime_payload(node, llm_result)
            except Exception as exc:
                node.get_logger().error(
                    f"任务执行失败，未进入 legacy fallback: {exc}")
                continue

            # 执行完毕提示
            print("\n任务执行完毕，等待下一条指令...")

    except KeyboardInterrupt:
        node.get_logger().info("收到 Ctrl+C，停止任务")
    finally:
        node.destroy_node()
        rclpy.shutdown()
        print("\n系统已退出")


if __name__ == "__main__":
    main()
