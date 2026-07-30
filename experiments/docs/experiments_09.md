# 实验 9：规划层—执行层安全机制协同消融

## 1. 目的

本实验用于定量分析多无人机安全机制中两个关键组成部分的独立贡献与协同关系：

1. 规划层的 safety-aware topology assignment；
2. 执行层的 distributed IAPF safety modulation。

实验回答以下问题：

- Safety-aware assignment 是否能够提前减少可预测的轨迹交叉和近距离风险？
- IAPF 是否能够处理规划阶段无法完全避免的动态冲突和执行误差？
- 两层机制组合后，是否能够在提高任务成功率和最小机间距的同时，降低 IAPF 介入负担和轨迹偏离？

LFS、Minimum Jerk 和 LADRC 在所有 variant 中保持不变，避免将认知层、轨迹层和控制层因素混入安全机制消融。

---

## 2. 实验变量

采用 2×2 因子设计：

| Variant | assignment_mode | avoidance_mode | 含义 |
| --- | --- | --- | --- |
| B0 | distance_hungarian | off | 基础组，无专用安全机制 |
| P | safety_aware | off | 仅规划层安全 |
| E | distance_hungarian | iapf_dual | 仅执行层安全 |
| Full | safety_aware | iapf_dual | 规划层与执行层协同 |

固定条件：

- 使用相同的预生成 LFS；
- Minimum Jerk 始终开启；
- motion_style 固定为 normal；
- LADRC、IAPF、PX4 参数保持一致；
- 相同 seed 使用相同起点、目标点、任务时长和扰动。

---

## 3. 实验场景

### S1：Crossing-prone assignment

构造起点与目标顺序容易导致轨迹交叉的 4/8 机编队变换，用于验证规划层 safety-aware assignment。

### S2：Dense convergence with local bias

多架无人机向小半径编队聚拢，并设置局部偏差或非对称目标，用于验证 IAPF 的局部救援能力。

### S3：Staggered dynamic crossing

两组无人机分时进入交叉区域，用于验证静态规划与动态避障的互补作用。

每个场景、每个 variant 重复至少 10 次，建议 15 次。所有 variant 使用配对 seed。

---

## 4. 收集数据

### 规划层

- nominal_xy_crossings
- nominal_proximity_crossings
- predicted_min_distance
- total_path_length
- assignment_compute_time_ms
- local_swap_iterations

### 实际安全

- actual_min_distance
- violation_count
- violation_duration
- near_miss_duration
- collision_count
- closest_pair

### IAPF 介入

- iapf_activation_count
- iapf_active_duration
- iapf_active_ratio
- intervention_latency
- mean/max_position_offset
- mean/max_acceleration_offset
- saturation_count
- stale_neighbor_ratio

### 任务性能

- mission_success
- safety_success
- tracking_rmse
- trajectory_deviation
- arrival_time_variance
- mission_duration
- recovery_time
- failure_reason

---

## 5. 成功判据

Mission success：

- 所有 UAV 在 timeout 前进入 hover stable；
- position error < 0.3 m；
- velocity < 0.3 m/s。

Safety success：

- mission_success = true；
- actual_min_distance ≥ violation_distance；
- collision_count = 0。

Rescue event：

- 相同 seed 下，无 IAPF variant 失败，而对应 IAPF variant 成功。

---

## 6. 核心假设

H1：P 相比 B0 能降低名义交叉数并提高预测最小距离。

H2：E 相比 B0 能提高真实最小机间距和任务成功率。

H3：Full 相比 E 具有更低的 IAPF 激活时间、修正幅度和轨迹偏离。

H4：Full 在任务成功率、安全成功率和最小机间距上达到最优或并列最优，同时不会造成不可接受的任务时长与跟踪误差增加。

---

## 7. 展示形式

- 主消融表：success、safety success、min distance、violations、RMSE、duration；
- 交互效应图：assignment_mode × avoidance_mode；
- IAPF 负担图：E vs Full；
- 典型场景 3D 轨迹图；
- pairwise distance 与 IAPF activation 时序图；
- failure reason 统计图。

所有统计结果报告 mean ± std、95% confidence interval、p-value 和 effect size，并对多重比较采用 Holm correction。