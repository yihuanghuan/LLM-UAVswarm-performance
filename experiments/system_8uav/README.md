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

8 个 PX4 实例保持原有并发启动时序，随后由实验专用 launcher 执行统一
XRCE 启动门检查。全部实例必须在 `xrce_per_uav_start_timeout` 内报告 time
sync converged，控制器才会启动；这样不会引入逐架启动的运行态偏差。超时仍按
`simulator_startup_failure` 保留，不会静默重试或隐藏 attempt。

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

论文表和箱线图中的连续性能指标仅统计 `overall_success` trial；成功次数的
分母始终是全部正式 trial，因此失败不会被隐藏，也不会用 0 秒完成时间污染
性能均值。

控制误差采用 actual position 对 modulated reference；避障偏移采用 modulated reference 对 nominal Minimum Jerk reference。安全判定使用 `0.70 m` collision、`1.00 m` violation、`1.50/1.65 m` IAPF enter/exit；实际最小距离低于 `1.00 m` 即判失败。经 8 机 pilot 固定悬停完成阈值为位置/速度均 `<0.40` 并连续保持 `1 s`；控制器默认值仍为 `0.30`，仅实验 launch 覆盖。mean RTF 低于 `0.95` 或有效控制频率低于 `45 Hz` 时记录 `gazebo_realtime_failure`。

## v2 attempt-controlled 批次

```bash
python3 experiments/system_8uav/scripts/run_batch.py \
  --batch-id exp10-formal-v2-20260731 --phase formal --manage-sim

python3 experiments/system_8uav/scripts/summarize_v2.py \
  --batch-id exp10-formal-v2-20260731

python3 experiments/system_8uav/scripts/plot_v2.py \
  experiments/results/experiments_10/exp10-formal-v2-20260731
```

中断恢复时对相同命令增加 `--resume`。每次启动使用不可复用的 attempt ID；
readiness/LLM 失败保留并生成 replacement，进入执行阶段后的失败 trial
仍计入每类 10 个执行样本。v2 mission 稳定状态使用 0.35/0.30 进入、
0.45/0.40 退出和连续 1 秒 hold；启动 readiness 的独立速度阈值为
0.40 m/s。

## v3 稳定性与阶段诊断

v3 将稳定候选位置阈值改为 `<=0.40 m`，退出阈值为 `>0.50 m`；速度
阈值保持 `<=0.30 m/s` 进入、`>0.40 m/s` 退出。每个新 mission 都会
重置 candidate/confirmed，阶段等待依次区分 command ack、reference finish
和 stabilization。

execution-only replay 使用 `frozen_lfs/` 中经过语义校验的 Task B/E LFS，
不会调用 LLM：

```bash
python3 experiments/system_8uav/scripts/run_batch.py \
  --batch-id exp10-pilot-v3-replay-20260803 \
  --phase pilot --task task_b_sequential --task task_e_mixed \
  --trials-per-task 5 --input-mode replay --manage-sim
```

端到端正式批次仍使用 LLM：

```bash
python3 experiments/system_8uav/scripts/run_batch.py \
  --batch-id exp10-formal-v3-20260803 \
  --phase formal --trials-per-task 10 --input-mode llm --manage-sim
```

v3 汇总仅将 `execution_success=true` 且所有 stage/UAV 时间完整的 trial 纳入
论文连续指标；其他 attempt 仍保留在成功率和 timeout 诊断中，缺失值写为
`NaN`：

```bash
python3 experiments/system_8uav/scripts/summarize_v3.py \
  --batch-id exp10-formal-v3-20260803
python3 experiments/system_8uav/scripts/plot_v3.py \
  experiments/results/experiments_10/exp10-formal-v3-20260803

python3 experiments/system_8uav/scripts/reanalyze_v2_v3.py \
  --batch-id exp10-formal-v2-gated-20260803
```
