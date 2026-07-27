# 实验 06：Gazebo 轨迹跟踪对比

## 状态

- 状态：成功完成
- 分支：`exp/06-gazebo-tracking`
- 基础标签：`gazebo-experiment-v1`
- 基础提交：`df5c5bc9b7a1af695c41dea5744bcb546b7f0a47`
- 实现实验协议的提交：
  - `810ff821c35ad3cc43db3e7e5e0b869305da0275`
  - `b9da562`
  - `81906dbc995ba08cd904fb4f302d4ac305e0a3b6`
- 结果数据提交：`b51dcf3e313df46f702c15c9054af4898bd04924`
- 执行日期：2026-07-27（Asia/Shanghai）
- 随机种子：`20260727`

## 固定配置

| 场景 | 无人机数 | 命令时长 | 目标 |
| --- | ---: | ---: | --- |
| `single_uav` | 1 | 8 s | `[6, 0, 5]` |
| `five_uav_circle` | 5 | 8 s | 圆心 `[10, 9, 5]`、半径 4 m |
| `eight_uav_line_to_circle` | 8 | 12 s | 圆心 `[10, 13.5, 5]`、半径 6 m |

每个场景均比较 3 种方法，并各做 5 次独立冷启动：

- `px4_step`：阶跃目标点，关闭 LADRC 加速度前馈；
- `linear_ladrc`：线性参考，开启 LADRC 加速度前馈；
- `minimum_jerk_ladrc`：Minimum Jerk 参考，开启 LADRC 加速度前馈。

全部试验采用 `normal` 模式、关闭 IAPF，并使用固定非交叉目标分配。
任务发布前要求每架 PX4 均为 armed、OFFBOARD 且非 failsafe。到达条件为
目标误差小于 0.3 m 且速度小于 0.3 m/s；settling 要求该条件连续保持
1 秒。RMSE 只统计命令轨迹时段。

## 汇总结果

| 场景 | 方法 | RMSE (m) | 最大误差 (m) | 平均到达时间 (s) | 平均最终误差 (m) | 到达成功率 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 8机线到圆 | Linear + LADRC | 0.294 | 1.225 | 12.651 | 0.031 | 100% |
| 8机线到圆 | Minimum Jerk + LADRC | 0.314 | 1.553 | 10.790 | 0.028 | 100% |
| 8机线到圆 | PX4 step | 4.353 | 16.988 | 7.942 | 0.466 | 92.5% |
| 5机圆形 | Linear + LADRC | 0.501 | 1.471 | 8.997 | 0.050 | 100% |
| 5机圆形 | Minimum Jerk + LADRC | 0.638 | 2.109 | 7.504 | 0.048 | 100% |
| 5机圆形 | PX4 step | 5.148 | 15.048 | 7.985 | 0.330 | 96% |
| 单机点到点 | Linear + LADRC | 0.337 | 0.561 | 8.427 | 0.036 | 100% |
| 单机点到点 | Minimum Jerk + LADRC | 0.354 | 0.677 | 7.408 | 0.034 | 100% |
| 单机点到点 | PX4 step | 3.418 | 8.092 | 5.627 | 0.174 | 100% |

完整精度保存在 `method_summary.csv`。LADRC 两种连续参考相对阶跃基线将
RMSE 降低约 88%–93%，且所有场景的到达成功率均为 100%，证明
Minimum Jerk 参考在 Gazebo 闭环中可以被实际跟踪。Minimum Jerk 比线性
参考平均提前约 1–2 秒到达，但本实验中其 RMSE 在三个场景都略高于线性
参考，因此数据不支持“Minimum Jerk 的 RMSE 优于 Linear”的结论。

LADRC 两种方法在命令时段内没有连续 1 秒满足 settling 条件，因此
`settling_time_s` 按协议保留为空值；未修改阈值或事后筛选。部分阶跃
trial 未达到稳定判据同样作为方法表现保留。

## 执行与复现

从仓库工作区执行：

```bash
source /opt/ros/humble/setup.bash
source ../../install/setup.bash
source ../../llm_env/bin/activate
python experiments/scripts/run_experiment_06.py \
  --output-dir experiments/results/experiments_06
python experiments/scripts/analyze_tracking_performance.py \
  experiments/results/experiments_06 \
  --output-dir experiments/results/experiments_06
```

运行器使用固定种子打乱 45 个 trial，并对每个 trial 冷启动 Gazebo/PX4。
若 readiness gate 不通过，尝试会移动到 `rejected/` 后重试。完整目标点、
方法开关和实际调度顺序见 `run_config.json`。

## 环境

- Ubuntu 22.04，Linux `6.8.0-124-generic`，x86_64
- ROS 2 Humble
- Python 3.10.12
- GCC/G++ 11.4.0

正式数据包含 45 个 rosbag、210 份 `trajectory_metrics` CSV 和 210 份
`vehicle_status` CSV。验证细节见 `validation_report.md`。
