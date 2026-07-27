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

离线比较 `random`、`nearest_neighbor`、`hungarian_distance`、`safety_aware_hungarian` 分配策略。
自动生成 `small`、`medium`、`large`、`dense`、`crossing-prone` 五类场景。

```bash
python3 experiments/scripts/eval_assignment_offline.py \
  --trials 50 \
  --output experiments/results/assignment_results.csv
```

输出：`experiments/results/assignment_results.csv`。
固定字段：`trial_id/scenario/num_uav/method/total_path_length/avg_path_length/xy_crossings/proximity_crossings/min_distance/safety_cost/total_cost/compute_time_ms`。

### eval_trajectory_profiles.py

离线生成 `step`、`linear`、`trapezoidal`、`minimum_jerk` 轨迹时序和解析指标。
不连续边界不会通过有限差分伪装成有限 jerk：无严格有限值的字段输出 `NaN`
并带有对应的 `*_valid=false` 标志。

```bash
python3 experiments/scripts/eval_trajectory_profiles.py \
  --output-summary experiments/results/trajectory_profile_results.csv \
  --output-timeseries experiments/results/trajectory_profile_timeseries.csv
```

输出：`trajectory_profile_results.csv`、`trajectory_profile_timeseries.csv`。
summary 固定字段包括 `max_velocity/max_acceleration/max_jerk/integrated_squared_jerk/final_error`。

### 实验 5 闭环轨迹对比

`run_experiment_05.py` 对四种轨迹方法各执行三次独立的五机 PX4/Gazebo
冷启动试验。脚本在确认五架机均已发布实际 odom 后发令，并通过统一的未来
ROS 时间戳同步启动轨迹。

```bash
source /opt/ros/humble/setup.bash
source ~/learning/LLM_swarm_ws/install/setup.bash
python3 experiments/scripts/run_experiment_05.py \
  --output-dir experiments/results/experiments_05

python3 experiments/scripts/analyze_experiment_05.py \
  --input-dir experiments/results/experiments_05
```

分析输出包括逐机、逐 trial、逐方法 CSV，参考轨迹四联图、闭环指标图、
平滑性图、三维多机轨迹图和 Markdown 汇总表。缺少任一 UAV metrics 的
启动尝试会自动隔离到 `rejected/` 并重跑，不参与正式统计。

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
