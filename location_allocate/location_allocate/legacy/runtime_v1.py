"""Historical task_sequences scheduler used only in explicit legacy mode."""

import time

import rclpy
from uav_swarm_interfaces.msg import UAVSwarmCommand

from .scheduler_v1 import FormationGenerator
from ..safety_aware_allocator import SafetyAwareTopologyAllocator


ALL_UAV_IDS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
ALL_INITIAL_POSITIONS = [
    [1.4, 0.0, 1.5], [-0.7, 1.2, 1.5], [-0.7, -1.2, 1.5],
    [1.4, 0.0, 3.0], [-0.7, 1.2, 3.0], [-0.7, -1.2, 3.0],
    [-0.7, 1.2, 4.0], [-0.7, -1.2, 4.0], [1.4, 0.0, 1.0],
    [-0.7, 1.2, 1.0],
]


class LegacyTopologyAllocator(SafetyAwareTopologyAllocator):
    def allocate(self, initial, target, cross_penalty=10.0, duration=3.0):
        del cross_penalty
        return super().allocate(initial, target, duration=duration)


class LegacyMissionRuntime:
    """Preserve historical geometry, grouping heuristic, and wire protocol."""

    def __init__(self, node, publishers, state_map, hover_status):
        self.node = node
        self.publishers = publishers
        self.state_map = state_map
        self.hover_status = hover_status

    def _publish_single_goal(self, mission_id, uav_id, position, duration,
                             motion_style, safety_factor):
        if uav_id not in self.publishers:
            self.node.get_logger().warn(f"未找到 UAV{uav_id} 的发布者，跳过")
            return
        msg = UAVSwarmCommand()
        msg.header.stamp = self.node.get_clock().now().to_msg()
        msg.header.frame_id = "world"
        msg.mission_id = mission_id
        msg.uav_id = uav_id
        msg.target_pos.x, msg.target_pos.y, msg.target_pos.z = position
        msg.duration = duration
        msg.motion_style = motion_style
        msg.safety_factor = safety_factor
        self.publishers[uav_id].publish(msg)

    def send_goal_positions(self, uav_ids, positions, task):
        duration = float(task.get("duration_seconds", 3.0))
        mission_id = int(task.get("task_sequence_id", 0))
        style = task.get("motion_profile", "normal")
        value = task.get("iapf_safety_margin_factor")
        safety = float(value) if value is not None else 1.0
        for uid in uav_ids:
            self.hover_status[uid] = False
        for uid, position in zip(uav_ids, positions):
            self._publish_single_goal(
                mission_id, uid, position, duration, style, safety
            )
            self.node.get_logger().info(
                f"UAV{uid} -> {[round(x, 2) for x in position]} "
                f"mission={mission_id} dur={duration}s "
                f"style={style} sf={safety}"
            )

    def wait_for_hover_and_time(self, uav_ids, wait_seconds, timeout=120.0):
        for uid in uav_ids:
            self.hover_status[uid] = False
        flush_start = time.time()
        while time.time() - flush_start < 2.0:
            rclpy.spin_once(self.node, timeout_sec=0.1)
        started = time.time()
        while time.time() - started < timeout:
            rclpy.spin_once(self.node, timeout_sec=0.2)
            if all(self.hover_status.get(uid, False) for uid in uav_ids):
                hover_start = time.time()
                while time.time() - hover_start < wait_seconds:
                    rclpy.spin_once(self.node, timeout_sec=0.2)
                    time.sleep(0.1)
                return
        stable = [uid for uid in uav_ids if self.hover_status.get(uid, False)]
        unstable = [uid for uid in uav_ids if uid not in stable]
        self.node.get_logger().warn(
            f">>> 悬停等待超时! 已稳定: {stable}, 未稳定: {unstable}"
        )

    @staticmethod
    def _targets(task):
        uav_ids = [int(uid) for uid in task["uav_id"]]
        generator = FormationGenerator(
            task["global_center"],
            task["parametric_data"]["formation_radius"],
        )
        targets = generator.generate(
            task["parametric_data"]["formation_type"], len(uav_ids)
        )
        if not targets:
            targets = [
                ALL_INITIAL_POSITIONS[ALL_UAV_IDS.index(uid)].copy()
                for uid in uav_ids
            ]
        return uav_ids, targets

    def execute_task(self, task, skip_wait=False):
        uav_ids = [int(uid) for uid in task["uav_id"]]
        for _ in range(10):
            rclpy.spin_once(self.node, timeout_sec=0.05)
        initial = [self.state_map[uid].copy() for uid in uav_ids]
        _, targets = self._targets(task)
        allocator = LegacyTopologyAllocator()
        duration = float(task.get("duration_seconds", 3.0))
        mode = self.node.get_parameter(
            "assignment_mode"
        ).get_parameter_value().string_value
        allocated, _ = allocator.allocate_mode_with_metrics(
            initial, targets, duration=duration, mode=mode
        )
        self.send_goal_positions(uav_ids, allocated, task)
        for uid, position in zip(uav_ids, allocated):
            self.state_map[uid] = position.copy()
        if not skip_wait:
            blocking = (
                "hover_and_wait", "continuous_transit", "direct_execution"
            )
            if (
                task.get("trigger_condition") in blocking
                or task.get("task_sequence_id", 1) > 1
            ):
                self.wait_for_hover_and_time(
                    uav_ids, task.get("wait_time") or 0.0
                )

    def execute_grouped_tasks(self, tasks):
        for _ in range(10):
            rclpy.spin_once(self.node, timeout_sec=0.05)
        grouped_inputs = []
        durations = []
        for task in tasks:
            uav_ids, targets = self._targets(task)
            grouped_inputs.append({
                "uav_ids": uav_ids,
                "initial": [self.state_map[uid].copy() for uid in uav_ids],
                "targets": targets,
            })
            durations.append(float(task.get("duration_seconds", 3.0)))
        if max(durations) - min(durations) > 1e-6:
            raise ValueError(
                "parallel grouped assignment requires an identical duration"
            )
        mode = self.node.get_parameter(
            "assignment_mode"
        ).get_parameter_value().string_value
        allocator = LegacyTopologyAllocator()
        groups, metrics = allocator.allocate_grouped(
            grouped_inputs, duration=durations[0], mode=mode
        )
        self.node.get_logger().info(
            f"joint grouped assignment mode={mode} "
            f"d_min={metrics.min_distance:.3f} total={metrics.total:.3f}"
        )
        for task, group_input, allocated in zip(tasks, grouped_inputs, groups):
            self.send_goal_positions(group_input["uav_ids"], allocated, task)
            for uid, position in zip(group_input["uav_ids"], allocated):
                self.state_map[uid] = position.copy()

    def run(self, payload):
        tasks = payload.get("task_sequences", [])
        if not tasks:
            self.node.get_logger().error("LLM 输出为空，没有任务可执行")
            return
        index = 0
        while index < len(tasks):
            group = [tasks[index]]
            group_ids = set(tasks[index].get("uav_id", []))
            end = index + 1
            while end < len(tasks):
                next_ids = set(tasks[end].get("uav_id", []))
                if group_ids & next_ids:
                    break
                group.append(tasks[end])
                group_ids |= next_ids
                end += 1
            if len(group) > 1:
                self.execute_grouped_tasks(group)
                self.wait_for_hover_and_time(list(group_ids), 1.0)
            else:
                if index > 0:
                    previous = set(tasks[index - 1].get("uav_id", []))
                    self.wait_for_hover_and_time(list(previous), 1.0)
                self.execute_task(tasks[index])
            index = end
        self.node.get_logger().info(">>> 所有任务序列执行完毕！")
