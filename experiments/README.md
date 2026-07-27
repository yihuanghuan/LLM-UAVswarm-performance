# 实验评估工具链

本目录用于论文实验的离线评估、日志整理和绘图。除 `collect_rosbag_topics.sh` 外，脚本尽量不依赖 ROS，可直接读取 JSON 或 CSV 运行。

## 目录

- `commands/`：LLM 指令模板，字段为 `id/type/command/ros_aux_info`。
- `scripts/`：实验评估、日志分析和绘图脚本。
- `logs/`：仿真或 rosbag 原始记录目录。
- `results/`：固定字段 CSV 结果目录。
- `figures/`：论文图输出目录。

## 常用命令

```bash
cd ~/learning/LLM_swarm_ws/src/LLM-UAVswarm-performance
source ~/learning/LLM_swarm_ws/llm_env/bin/activate
source ~/learning/LLM_swarm_ws/install/setup.bash
```

## 脚本说明

### eval_llm_parser.py

批量读取 `experiments/commands/*.json`，调用 `location_allocate.no_location.parse_uav_command`，输出 LLM 解析成功率、延迟和 schema 结果。

```bash
python3 experiments/scripts/eval_llm_parser.py \
  --input experiments/commands \
  --output experiments/results/llm_parser_results.csv \
  --limit 5
```

输出：`experiments/results/llm_parser_results.csv`。

### eval_lfs_compiler.py

不调用 LLM，构造 formal LFS、invalid LFS 和 legacy `task_sequences` 样例，调用 `validate_and_compile_lfs`。

```bash
python3 experiments/scripts/eval_lfs_compiler.py \
  --output experiments/results/lfs_compiler_results.csv
```

输出：`experiments/results/lfs_compiler_results.csv`。

### eval_assignment_offline.py

实验 04 离线比较 `random`、`nearest_neighbor`、`hungarian_distance`、
`hungarian_crossing_penalty`、`safety_aware_local_swap` 五种分配策略。
自动生成 `small`、`medium`、`large`、`dense`、`crossing-prone` 五类场景，
并保存每次试验的场景坐标和分配索引以便复算。

```bash
python3 experiments/scripts/eval_assignment_offline.py \
  --trials 100 \
  --output-dir experiments/results/experiments_04/feasible_scenarios_v3 \
  --safety-distance 2.0 \
  --critical-distance 1.5 \
  --scenario-min-distance 2.1

python3 experiments/scripts/analyze_assignment_offline.py \
  --input-dir experiments/results/experiments_04/feasible_scenarios_v3
```

输出目录包含原始 CSV、场景 JSONL、汇总 CSV、Markdown 表格、配置、分析清单，
以及 min distance 箱线图、crossing 柱状图、定性路径图和 Pareto 图。
默认每个场景运行 100 次；安全违规按同步名义轨迹中低于 2 m 的机对采样点计数。
所有场景的初始点集和目标点集都保证至少 2.1 m 的机间距，使失败事件只能由过渡轨迹引入。
`dense` 使用半径 3.2 m 的 8 机紧凑圆形目标；另以低于 1.5 m 记录严重违规和严重失败率，
但不替代 2 m 的主要安全裕度判据。
如果指定目录已有内容，评估脚本会自动创建带 UTC 时间戳的子目录，绝不覆盖旧数据。

### eval_trajectory_profiles.py

离线生成 `step`、`linear`、`trapezoidal`、`minimum_jerk` 轨迹时序和指标。

```bash
python3 experiments/scripts/eval_trajectory_profiles.py \
  --output-summary experiments/results/trajectory_profile_results.csv \
  --output-timeseries experiments/results/trajectory_profile_timeseries.csv
```

输出：`trajectory_profile_results.csv`、`trajectory_profile_timeseries.csv`。
summary 固定字段包括 `max_velocity/max_acceleration/max_jerk/integrated_squared_jerk/final_error`。

### analyze_pairwise_distance.py

读取包含 `timestamp,uav_id,x,y,z` 的 odom CSV，计算所有 UAV 两两距离。

```bash
python3 experiments/scripts/analyze_pairwise_distance.py \
  --input experiments/logs/odom.csv \
  --output-dir experiments/results \
  --safety-threshold 1.5 \
  --experiment-id exp001 \
  --time-bin 0.05
```

输出：`pairwise_distance_timeseries.csv`、`pairwise_distance_summary.csv`。
summary 固定字段：`experiment_id/num_uav/min_inter_agent_distance/mean_min_distance/safety_threshold/safety_violation_count/near_miss_duration/closest_pair`。
默认按 `0.05` 秒时间分箱同步不同 UAV 的 odom；如需恢复精确 timestamp 分组，可设置 `--time-bin 0`。

### eval_iapf.py

汇总不同 IAPF 方法下的机间距离、轨迹指标和任务结果。
脚本固定输出 `no_iapf`、`iapf_position_only`、`iapf_position_accel`、`safety_assignment_plus_iapf` 四类方法；输入 CSV 可用 `method`、`iapf_method`、`experiment_id` 或 `condition` 字段标识方法。

```bash
python3 experiments/scripts/eval_iapf.py \
  --pairwise experiments/results/pairwise_distance_summary.csv \
  --trajectory experiments/results/trajectory_profile_results.csv \
  --mission experiments/results/mission_summary.csv \
  --output experiments/results/iapf_summary.csv
```

输出：`experiments/results/iapf_summary.csv`。

### eval_semantic_control.py

读取控制适应日志，按 `motion_style` 汇总增益、速度、加速度、稳定时间和跟踪误差。

```bash
python3 experiments/scripts/eval_semantic_control.py \
  --input logs/control_adaptation_log.csv \
  --output experiments/results/semantic_control_summary.csv
```

输出：`experiments/results/semantic_control_summary.csv`。

### collect_rosbag_topics.sh

统一记录论文实验话题。该脚本依赖 ROS 2。
记录内容包括 `/uav*/odom`、`/uav*/status`、`/uav*/trajectory_metrics`、`/uav*/control_adaptation`、`/uav*/swarm_command` 和 `/uav*/fmu/out/vehicle_odometry`。

```bash
bash experiments/scripts/collect_rosbag_topics.sh exp001
```

默认输出目录：`experiments/logs/rosbags/exp001`。

### plot_all.py

读取 `experiments/results/*.csv`，生成 PNG 和 PDF 图。

```bash
python3 experiments/scripts/plot_all.py --all
python3 experiments/scripts/plot_all.py --which assignment
python3 experiments/scripts/plot_all.py --which trajectory_profiles
```

输出目录：`experiments/figures/`。
支持类别：`llm`、`assignment`、`trajectory`、`semantic`、`iapf`；支持单图：`llm_latency`、`llm_success_rate`、`assignment_min_distance`、`assignment_crossings`、`trajectory_profiles`、`semantic_control_summary`、`iapf_min_distance`。
