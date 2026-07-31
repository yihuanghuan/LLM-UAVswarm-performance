# 实验 10 完成报告

## 实验记录

- 实验：8 机 Gazebo 端到端受控评估
- 分支：`exp/10-system-8uav`
- 固定基线：`gazebo-experiment-v1`（`df5c5bc9`）
- 实现提交：`7b126da3`、`884926cf`
- 正式批次：`exp10-formal-20260731`
- 配置 checksum：`b9d8375a4ab2450da890f834f26c0b2218da8ecacab6e528b9bb3193bddaccdf`
- 模型：每个 trial 实时调用 `MiniMax-M2.7-highspeed`
- 重复次数：Task A–E 各 5 次，共 25 次
- 隔离方式：每次 trial 重启 MicroXRCEAgent、8 机 PX4 SITL、Gazebo 和 8 个控制节点
- 数据位置：`experiments/results/experiments_10/exp10-formal-20260731`

最终提交 SHA 以远程分支 `origin/exp/10-system-8uav` 的 tip 为准，并在最终
交付记录中给出；Git commit 无法在自身内容中保存自身 SHA。

## 固定配置

- `assignment_mode=safety_aware`
- `avoidance_mode=iapf_dual`
- `iapf_escape_mode=id_order`
- Minimum Jerk 与 semantic-conditioned LADRC 开启
- `safety_factor=1.0`
- collision / violation / IAPF enter / exit：
  `0.70 / 1.00 / 1.50 / 1.65 m`
- 悬停完成：位置误差和速度均 `<0.40`，连续保持 `1 s`
- 实时性：trial mean RTF `>=0.95`，控制频率 `>=45 Hz`

完整快照位于批次的 `configuration/`，正式调度顺序位于
`formal_batch_plan.json`。

## 正式结果

连续性能指标只对 `overall_success` trial 统计；成功次数分母包含全部 5 次。

| Task | 成功 | 完成时间 (s) | Tracking RMSE (m) | 最小距离 (m) | Arrival spread (s) | IAPF 活跃 (s) | Mean RTF |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 4/5 | 11.072 ± 0.035 | 0.693 ± 0.013 | 2.522 ± 0.020 | 0.014 ± 0.006 | 0.000 ± 0.000 | 0.989 ± 0.002 |
| B | 4/5 | 43.888 ± 4.078 | 0.826 ± 0.095 | 1.779 ± 0.173 | 10.475 ± 10.170 | 0.000 ± 0.000 | 0.997 ± 0.001 |
| C | 5/5 | 20.301 ± 12.727 | 0.623 ± 0.079 | 2.097 ± 0.014 | 0.013 ± 0.006 | 0.000 ± 0.000 | 0.985 ± 0.012 |
| D | 5/5 | 15.271 ± 8.069 | 0.700 ± 0.067 | 1.362 ± 0.179 | 3.692 ± 7.866 | 7.452 ± 7.622 | 0.987 ± 0.004 |
| E | 1/5 | 59.156 ± 0.000 | 1.154 ± 0.000 | 1.612 ± 0.000 | 12.483 ± 0.000 | 0.000 ± 0.000 | 0.994 ± 0.000 |

总体为 `19/25` overall success。6 个失败均被保留：

- `readiness_timeout`：3 次（A trial 3、B trial 2、E trial 3）；
- `llm_parse_failure`：3 次（E trial 1、2、4），MiniMax 在每次的 3 个
  API 尝试中都未输出可严格解析的单一 JSON。

所有 19 个成功 trial 均无碰撞或 violation，最小观测距离为 `1.091 m`；
成功 trial 的最低 trial mean RTF 为 `0.965`，有效控制频率均不低于
`45 Hz`。Task D 的 5 次均通过安全门槛，共记录 11 次 IAPF 激活。

## 数据完整性

- 25/25 trial manifest；
- 25/25 trial 结构化 CSV；
- 22/22 在 readiness 后开始记录的 rosbag 具有 metadata；3 个
  readiness 失败按流程未启动 rosbag；
- 19/19 成功 rosbag 均包含 8 架 UAV 的 odom、status、
  trajectory_metrics、control_adaptation、iapf_debug、swarm_command、
  PX4 vehicle_odometry 以及 `/clock`；
- 6 个固定 summary CSV、论文表和 22 个 PNG/PDF 图均成功生成；
- 原始数据和 rosbag 总量约 351 MB，按仓库规则保留在本地但不提交 Git。

Gazebo Classic 在本环境声明了 `/gazebo/performance_metrics`，但不发布样本，
因此 RTF 使用 manifest 标记的 `clock_wall_ratio`：以 `/clock` 累计仿真时间
除以单调 wall time 计算。

## 运行命令

```bash
python3 experiments/system_8uav/scripts/run_batch.py \
  --batch-id exp10-formal-20260731 --phase formal --manage-sim

python3 experiments/system_8uav/scripts/summarize_system_trials.py \
  --batch-id exp10-formal-20260731

python3 experiments/system_8uav/scripts/plot_system_results.py \
  --batch-id exp10-formal-20260731
```

## 验证

- Experiment 10、LFS 与 safety-aware allocator 测试：`25 passed`；
- C++ 测试：IAPF `9/9 passed`，trajectory profiles `5/5 passed`；
- `uav_swarm_interfaces`、`location_allocate`、`ladrc_controller` 构建成功；
- `location_allocate` 功能测试通过；
- 该包原有 flake8/pep257 检查仍报告 77 个基线风格问题，本实验未对无关
  历史代码做批量格式化；
- 工作区 `llm_env` 中 NumPy 示例包会导致 colcon 包发现阶段输出缺少
  Cython 的警告，但指定的三个 ROS 包构建和测试不受影响。
