# 实验 10：8 机系统级受控评估

本目录实现五类固定自然语言任务的端到端运行、结构化记录、汇总和绘图。正式实验固定使用 safety-aware assignment、Minimum Jerk、semantic-conditioned LADRC、`iapf_dual`、`id_order` 和 `safety_factor=1.0`。

## 目录

- `commands/`：Task A–E 的自然语言和冻结语义配置；
- `configs/full_system.yaml`：实验、IAPF、安全、实时性和路径参数；
- `scripts/run_trial.py`：单 trial runner；
- `scripts/run_batch.py`：pilot/正式批处理和逐 trial 仿真重启；
- `scripts/summarize_system_trials.py`：六类固定 CSV、manifest 和论文表；
- `scripts/plot_system_results.py`：所有规定 PNG/PDF 图；
- `tests/`：配置、LFS、调度和指标单元测试。

正式输出位于 `experiments/results/experiments_10/<batch_id>/`。失败 trial 与成功 trial 使用相同目录和 manifest，不会被覆盖或删除。

## 环境准备

```bash
cd ~/learning/LLM_swarm_ws
source /opt/ros/humble/setup.bash
source llm_env/bin/activate
source install/setup.bash
export PX4_AUTOPILOT_DIR=~/PX4-Autopilot
export LLM_API_KEY='...'
cd src/LLM-UAVswarm-performance
```

构建并测试：

```bash
cd ~/learning/LLM_swarm_ws
colcon build --symlink-install \
  --packages-select uav_swarm_interfaces location_allocate ladrc_controller
colcon test --packages-select location_allocate ladrc_controller
colcon test-result --verbose

cd src/LLM-UAVswarm-performance
PYTHONPATH=experiments/system_8uav/scripts:location_allocate \
  pytest -q experiments/system_8uav/tests location_allocate/test
```

## Dry run

Dry run 不启动 ROS/Gazebo，不写 trial 原始数据：

```bash
PYTHONPATH=experiments/system_8uav/scripts:location_allocate \
python3 experiments/system_8uav/scripts/run_batch.py \
  --batch-id exp10-dryrun --phase formal --dry-run
```

## Pilot 与正式运行

自动模式为每个 trial 独立启动并关闭 MicroXRCEAgent、8 机 PX4/Gazebo 和控制器：

```bash
python3 experiments/system_8uav/scripts/run_batch.py \
  --batch-id exp10-YYYYMMDD --phase pilot --manage-sim

python3 experiments/system_8uav/scripts/run_batch.py \
  --batch-id exp10-YYYYMMDD --phase formal --manage-sim
```

外部环境已人工启动时，省略 `--manage-sim`。单 trial 示例：

```bash
python3 experiments/system_8uav/scripts/run_trial.py \
  --batch-id exp10-YYYYMMDD --phase pilot \
  --task task_d_dense --trial 1
```

`--resume` 只跳过已有 trial，绝不覆盖。正式批次为 5 个固定随机 block，每个 block 包含 A–E 各一次。

## 汇总与绘图

```bash
python3 experiments/system_8uav/scripts/summarize_system_trials.py \
  --batch-id exp10-YYYYMMDD

python3 experiments/system_8uav/scripts/plot_system_results.py \
  --batch-id exp10-YYYYMMDD
```

`summaries/` 固定生成：

- `system_trial_summary.csv`
- `stage_timeline.csv`
- `uav_arrival_summary.csv`
- `tracking_summary.csv`
- `safety_summary.csv`
- `resource_summary.csv`
- `paper_task_table.csv`

控制误差采用 actual position 对 modulated reference；避障偏移采用 modulated reference 对 nominal Minimum Jerk reference。安全判定使用 `0.70 m` collision、`1.00 m` violation、`1.50/1.65 m` IAPF enter/exit；实际最小距离低于 `1.00 m` 即判失败。经 8 机 pilot 固定悬停完成阈值为位置/速度均 `<0.40` 并连续保持 `1 s`；控制器默认值仍为 `0.30`，仅实验 launch 覆盖。mean RTF 低于 `0.95` 或有效控制频率低于 `45 Hz` 时记录 `gazebo_realtime_failure`。
