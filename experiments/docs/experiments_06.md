# 8. 实验 6：Gazebo 中的轨迹跟踪对比

## 目的

证明 Minimum Jerk + LADRC 在仿真中可以实际跟踪，而不是只有参考轨迹好看。

---

## 实验设计

在 Gazebo 中执行单机和多机轨迹：

| 场景 | 说明 |
| --- | --- |
| single-UAV point-to-point | 单机点到点 |
| 5-UAV circle formation | 5机圆形 |
| 8-UAV line-to-circle | 8机变阵 |

---

## Baseline

| 方法 | 说明 |
| --- | --- |
| PX4 default position setpoint only | 只发目标点 |
| Linear reference + controller | 线性参考 |
| Minimum Jerk + LADRC | 你的方法 |

---

## 收集数据

| 数据 | 说明 |
| --- | --- |
| `p_ref(t)` | 参考位置 |
| `p_actual(t)` | 实际位置 |
| tracking RMSE | 跟踪均方根误差 |
| max tracking error | 最大误差 |
| settling time | 稳定时间 |
| overshoot | 超调 |
| velocity / acceleration | 速度加速度 |
| arrival time | 到达时间 |

---

## 展示形式

| 图/表 | 内容 |
| --- | --- |
| 3D plot | 参考轨迹 vs 实际轨迹 |
| Line plot | tracking error over time |
| Table | RMSE / max error / settling time |
| Box plot | 多次 trial 的 RMSE 分布 |

---

## 改进意见
文档需要比较：

PX4 default setpoint
Linear reference + controller
Minimum Jerk + LADRC

但目前：

控制节点主要运行 Minimum Jerk；
没有明显的 trajectory_profile 运行参数；
没有 Gazebo tracking evaluator；
没有自动对齐 p_ref(t) 和 p_actual(t)；
没有生成 RMSE、overshoot、settling time、arrival variance 的统一脚本。

当前离线 eval_trajectory_profiles.py 只能比较数学参考轨迹，不能代替 Gazebo 闭环跟踪实验。

需要新增：

analyze_tracking_performance.py

输入：

/uav*/trajectory_metrics；
/uav*/odom；
/px4_*/fmu/out/vehicle_odometry；
/uav*/swarm_command。

输出：

tracking_rmse
max_tracking_error
settling_time
overshoot
arrival_time
arrival_time_variance
final_position_error

同时需要为控制节点或实验 launch 增加：

trajectory_profile:=step|linear|minimum_jerk

---

## 固定实验协议

- 分支：`exp/06-gazebo-tracking`，基础版本：
  `gazebo-experiment-v1` (`df5c5bc9b7a1af695c41dea5744bcb546b7f0a47`)。
- 方法：
  - `px4_step`：step 目标点，关闭 LADRC 加速度前馈；
  - `linear_ladrc`：linear 参考，开启 LADRC 加速度前馈；
  - `minimum_jerk_ladrc`：Minimum Jerk 参考，开启 LADRC 加速度前馈。
- 场景：单机 8 秒点到点、5 机 8 秒线到圆、8 机 12 秒线到圆。
- 每个场景和方法进行 5 次独立冷启动，共 45 次正式 trial。
- 全部实验使用 `normal`，关闭 IAPF，采用固定非交叉目标分配。
- tracking RMSE 仅统计命令轨迹时段。
- arrival 条件为目标误差小于 0.3 m 且速度小于 0.3 m/s。
- settling time 要求 arrival 条件连续保持 1 秒；不满足时保留为缺失值，
  不事后修改阈值。
