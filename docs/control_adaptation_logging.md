# LADRC Control Adaptation Logging

## 修改内容

本次修改将执行层的 `motion_style → gain_multiplier` 固定映射改为任务条件化带宽计算，并增加控制适应日志。

调度器现在会把 `task_sequence_id` 写入 `UAVSwarmCommand.mission_id`，执行层据此把多架无人机的同一子任务日志对齐。

新增 ROS 2 topic：

```text
/uav{N}/control_adaptation
```

消息类型：

```text
uav_swarm_interfaces/msg/ControlAdaptationLog
```

新增 CSV：

```text
logs/control_adaptation_log.csv
```

## 带宽计算

执行层新增函数：

```cpp
double computeSemanticTaskGain(
    const std::string& motion_style,
    double target_distance,
    double duration);
```

计算方式：

```text
average_speed = target_distance / max(duration, 1e-3)
kappa = clamp(style_base * (0.75 + 0.25 * average_speed / style_v_ref), 0.5, 2.0)
omega_o_new = kappa * omega_o_base
omega_c_new = kappa * omega_c_base
```

默认参数：

```text
smooth     style_base=0.75  style_v_ref=1.0 m/s
normal     style_base=1.00  style_v_ref=1.8 m/s
aggressive style_base=1.30  style_v_ref=2.6 m/s
```

未知 `motion_style` 按 `normal` 处理并输出 warning。

## 日志字段

`ControlAdaptationLog` 和 CSV 均记录：

```text
mission_id
uav_id
motion_style
target_distance
duration
average_speed
gain_multiplier
omega_o_x
omega_o_y
omega_o_z
omega_c_x
omega_c_y
omega_c_z
peak_velocity
peak_acceleration
settling_time
tracking_rmse
```

topic 按控制节点低频指标节奏持续发布。CSV 在任务首次稳定悬停时写入一行汇总；如果任务被新命令覆盖，则先写入旧任务当前汇总。

## 验证方式

构建验证：

```bash
cd ~/learning/LLM_swarm_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
colcon build --symlink-install \
  --paths src/LLM-UAVswarm-performance/uav_swarm_interfaces \
          src/LLM-UAVswarm-performance/minisnap_LADRC/ladrc_controller \
          src/LLM-UAVswarm-performance/location_allocate \
  --packages-select uav_swarm_interfaces ladrc_controller location_allocate \
  --allow-overriding uav_swarm_interfaces ladrc_controller location_allocate
```

仿真中查看：

```bash
ros2 topic echo /uav1/control_adaptation
tail -f src/LLM-UAVswarm-performance/logs/control_adaptation_log.csv
```
