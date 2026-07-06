import math
import time
from typing import List, Dict
import json

# -------------------------- ROS2 依赖导入 --------------------------
import rclpy
from rclpy.node import Node
from uav_swarm_interfaces.msg import UAVSwarmCommand, UAVStatus
from geometry_msgs.msg import Point
# -------------------------------------------------------------------
from .no_location import parse_uav_command
from .safety_aware_allocator import SafetyAwareTopologyAllocator

# ====================== 硬编码：无人机初始坐标 + ID (全局地图) ======================
# 注意：这里是全局数据库，存储所有无人机的状态
all_uav_ids = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
all_initial_positions = [
    [1.4, 0.0, 1.5], [-0.7, 1.2, 1.5], [-0.7, -1.2, 1.5],
    [1.4, 0.0, 3.0], [-0.7, 1.2, 3.0], [-0.7, -1.2, 3.0],
    [-0.7, 1.2, 4.0], [-0.7, -1.2, 4.0], [1.4, 0.0, 1.0],
    [-0.7, 1.2, 1.0]
]

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
        if formation_type in ["Line", "Lineup"]: return self.generate_line(uav_count)
        elif formation_type in ["Circle", "Polygon", "Triangle"]: return self.generate_circle(uav_count)
        elif formation_type == "Sphere": return self.generate_sphere(uav_count)
        elif formation_type == "Free": return []
        else: raise ValueError(f"不支持的编队类型: {formation_type}")

# ====================== 2. 安全感知拓扑分配层 ======================
class TopologyAllocator(SafetyAwareTopologyAllocator):
    def allocate(self, initial, target, cross_penalty=10.0, duration=3.0):
        del cross_penalty
        return super().allocate(initial, target, duration=duration)

# ====================== 3. ROS2 核心调度层  ======================
class UAVFormationNode(Node):
    def __init__(self):
        super().__init__('location_allocate')
        
        # 状态变量：由 C++ 节点低频发布的 /uav{id}/odom 实时更新（不再使用硬编码初始坐标）
        self.uav_state_map: Dict[int, List[float]] = {}
        for uid in all_uav_ids:
            self.uav_state_map[uid] = [0.0, 0.0, 0.0]

        # -------------------------- 发布者管理 --------------------------
        self.publisher = {}
        for uid in all_uav_ids:
            topic_name = f'/uav{uid}/swarm_command'
            self.publisher[uid] = self.create_publisher(UAVSwarmCommand, topic_name, 10)
            self.get_logger().info(f"创建发布者: {topic_name}")

        # -------------------------- 订阅者管理 (odom 位置 + status 状态) --------------------------
        self.uav_hover_status: Dict[int, bool] = {}
        self.status_sub = {}
        self.odom_sub = {}
        for uid in all_uav_ids:
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
            self.get_logger().info(f"创建订阅者: /uav{uid}/status, /uav{uid}/odom")

    def _publish_single_goal(self, uav_id: int, position: List[float],
                             duration: float, motion_style: str, safety_factor: float):
        """向单个无人机发送 swarm_command 自定义消息"""
        if uav_id not in self.publisher:
            self.get_logger().warn(f"未找到 UAV{uav_id} 的发布者，跳过")
            return

        msg = UAVSwarmCommand()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "world"
        msg.uav_id = uav_id
        msg.target_pos.x = position[0]
        msg.target_pos.y = position[1]
        msg.target_pos.z = position[2]
        msg.duration = duration
        msg.motion_style = motion_style
        msg.safety_factor = safety_factor

        self.publisher[uav_id].publish(msg)

    def _status_callback(self, msg: UAVStatus, uid: int):
        """接收 C++ 执行层反馈的悬停状态"""
        if msg.is_hover_stable and not self.uav_hover_status.get(uid, False):
            self.get_logger().info(f"   >>> UAV{uid} 到达目标并悬停稳定!")
        self.uav_hover_status[uid] = msg.is_hover_stable

    def _odom_callback(self, msg: Point, uid: int):
        """接收 C++ 节点低频发布的 ENU 位置，更新全局状态地图"""
        self.uav_state_map[uid] = [msg.x, msg.y, msg.z]

    def send_goal_positions(self, task_uav_ids: List[int], allocated_positions: List[List[float]],
                            task: Dict):
        """
        广播 UAVSwarmCommand 自定义消息
        :param task_uav_ids: 本次参与任务的无人机ID列表
        :param allocated_positions: 对应的目标坐标列表，顺序与ID一一对应
        :param task: LLM 解析的原始 task dict (获取 duration / motion_style / safety_factor)
        """
        self.get_logger().info(f">>> 正在向 {len(task_uav_ids)} 架无人机发送 swarm_command ...")

        duration = float(task.get('duration_seconds', 3.0))
        motion_style = task.get('motion_profile', 'normal')
        val = task.get('iapf_safety_margin_factor')
        # null 时默认 1.0（配合 YAML 中 K_rep=20, R_safe=2 提供标准避障）
        # 非 null 时按 LLM 指定值单独调节
        safety_factor = float(val) if val is not None else 1.0

        # 先重置悬停状态，再发命令
        for uid in task_uav_ids:
            self.uav_hover_status[uid] = False

        for uid, pos in zip(task_uav_ids, allocated_positions):
            self._publish_single_goal(uid, pos, duration, motion_style, safety_factor)
            self.get_logger().info(f"UAV{uid} -> {[round(x,2) for x in pos]} "
                                    f"dur={duration}s style={motion_style} sf={safety_factor}")

    def wait_for_hover_and_time(self, task_uav_ids: List[int], wait_seconds: float, timeout: float = 120.0):
        """等待所有参与任务的无人机到达目标并悬停稳定 (基于 /uav{id}/status 真实反馈)"""
        self.get_logger().info(f">>> 等待 {len(task_uav_ids)} 架无人机到达并悬停 (超时: {timeout}s) ...")

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
            all_stable = all(self.uav_hover_status.get(uid, False) for uid in task_uav_ids)
            if all_stable:
                elapsed = time.time() - start_time
                self.get_logger().info(f"   >>> 全部 {len(task_uav_ids)} 架无人机已悬停稳定! (耗时 {elapsed:.1f}s)")

                # 悬停保持计时
                self.get_logger().info(f">>> 开始悬停计时: {wait_seconds} 秒")
                hover_start = time.time()
                while time.time() - hover_start < wait_seconds:
                    rclpy.spin_once(self, timeout_sec=0.2)
                    time.sleep(0.1)
                self.get_logger().info("   悬停等待完成，准备执行下一任务")
                return

            # 打印等待中的进度 (每 5 秒)
            if int(time.time() - start_time) % 5 == 0 and int(time.time() - start_time) > 0:
                stable_count = sum(1 for uid in task_uav_ids if self.uav_hover_status.get(uid, False))
                self.get_logger().info(f"   等待中... {stable_count}/{len(task_uav_ids)} 已稳定")

        # 超时
        stable_list = [uid for uid in task_uav_ids if self.uav_hover_status.get(uid, False)]
        unstable_list = [uid for uid in task_uav_ids if not self.uav_hover_status.get(uid, False)]
        self.get_logger().warn(f">>> 悬停等待超时! 已稳定: {stable_list}, 未稳定: {unstable_list}")

    def execute_task(self, task: Dict, skip_wait: bool = False):
        """执行单步任务（核心修改：支持分群）"""
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
            self.get_logger().info(f"编队类型: {f_type} | 中心: {center} | 半径: {radius}")

        # ==========================================
        # 4. 匈牙利算法分配 (仅针对参与机)
        # ==========================================
        allocator = TopologyAllocator()
        # 输入：参与机的当前位置，参与机的目标点
        allocation_duration = float(task.get('duration_seconds', 3.0))
        allocated_subset = allocator.allocate(current_subset, targets, duration=allocation_duration)
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

         #打印分配结果映射表
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
            if task.get('trigger_condition') in ('hover_and_wait', 'continuous_transit', 'direct_execution') \
               or task.get('task_sequence_id', 1) > 1:
                wt = task.get('wait_time') or 0.0
                self.wait_for_hover_and_time(task_uav_ids, wt)

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
                for task in group:
                    self.execute_task(task, skip_wait=True)  # 先全部发送，不等
                all_ids = list(group_ids)
                self.get_logger().info(f">>> 等待 {len(all_ids)} 架无人机全部悬停...")
                self.wait_for_hover_and_time(all_ids, 1.0)
            else:
                if i > 0:
                    prev_ids = set(tasks[i-1].get('uav_id', []))
                    self.get_logger().info(f">>> 等待前一任务悬停...")
                    self.wait_for_hover_and_time(list(prev_ids), 1.0)
                self.execute_task(tasks[i])
            i = j

        self.get_logger().info(">>> 所有任务序列执行完毕！")



# ====================== 主入口 (终端输入循环) ======================
def main():
    rclpy.init()
    
    # 硬编码可用无人机数量和id
    test_ros = "当前可用无人机编号: [1,2,3,4,5,6,7,8,9,10]，总数: 10"
    node = UAVFormationNode()
    
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
            llm_result = parse_uav_command(user_command, test_ros)#test_ros只是用来让LLM判断一共有多少架UAV可以用
            
            # 打印解析结果（保持原有格式）
            print("\n" + "=" * 50)
            print("最终解析结果：")
            print("=" * 50)
            print(json.dumps(llm_result, indent=2, ensure_ascii=False))
            
            # 执行任务
            node.run_mission(llm_result)
            
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
