# Minimum Jerk Trajectory Metrics

## 修改内容

执行层现在会在每架无人机收到新的 `swarm_command` 后计算 Minimum Jerk 三维轨迹指标，并持续发布最近一次任务的指标。

新增 ROS 2 topic：

```text
/uav{N}/trajectory_metrics
```

消息类型：

```text
uav_swarm_interfaces/msg/TrajectoryMetrics
```

该 topic 使用节点命名空间内的相对话题 `trajectory_metrics` 创建，因此 `swarm_launch.py` 启动 `uav1` 时实际话题为 `/uav1/trajectory_metrics`。

## 指标含义

`TrajectoryMetrics` 包含任务基本信息、理论轨迹指标和运行时误差：

```text
uav_id
start_pos
target_pos
requested_duration
trajectory_duration
motion_style
safety_factor
path_length
max_velocity
max_acceleration
max_jerk
integrated_squared_jerk
elapsed_time
arrival_time_error
final_position_error
is_finished
is_hover_stable
```

`path_length`、`max_velocity`、`max_acceleration`、`max_jerk`、`integrated_squared_jerk` 基于三维 Minimum Jerk 轨迹整体计算，而不是分别发布三个轴的独立指标。起点和终点速度、加速度仍保持原有 0 边界条件。

## 计算公式

令三维路径长度为：

```text
d = ||target - start||
```

实际轨迹时长为：

```text
T = max(requested_duration, 1e-3)
```

理论指标为：

```text
path_length = d
max_velocity = (15 / 8) * d / T
max_acceleration = (10 * sqrt(3) / 3) * d / T^2
max_jerk = 60 * d / T^3
integrated_squared_jerk = 720 * d^2 / T^5
```

运行时字段：

- `elapsed_time`：当前任务已执行时间。
- `arrival_time_error`：首次稳定悬停时间减去请求时长；稳定前为 `NaN`。
- `final_position_error`：当前全局 ENU 位置到目标点的距离。
- `is_finished`：Minimum Jerk 时间参数是否到达末端。
- `is_hover_stable`：复用原有悬停稳定判定结果。

## 验证方式

构建验证：

```bash
cd ~/learning/LLM_swarm_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
colcon build --symlink-install --packages-select uav_swarm_interfaces ladrc_controller
source install/setup.bash
ros2 interface show uav_swarm_interfaces/msg/TrajectoryMetrics
```

单机仿真中查看指标：

```bash
source ~/learning/LLM_swarm_ws/install/setup.bash
ros2 topic echo /uav1/trajectory_metrics
```

然后按 README 单机测试流程向 `/uav1/swarm_command` 发送任务即可看到指标持续更新。
