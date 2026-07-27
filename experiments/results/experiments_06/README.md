# Experiment 06 results

本目录保存 Gazebo 闭环轨迹跟踪实验的完整结果。正式数据位于
`trials/`，每个场景与方法各有 5 次独立冷启动，共 45 个 trial 和
210 个逐机结果。`rejected/` 仅用于审计启动失败、被中断的尝试以及
加入 PX4 readiness gate 前的旧数据，不参与任何统计。

主要入口：

- `experiment_record.md`：实验配置、命令、结论和复现说明；
- `validation_report.md`：数据完整性与有效性检查；
- `method_summary.csv`：场景/方法级汇总；
- `trial_summary.csv`、`uav_trial_summary.csv`：trial/逐机汇总；
- `tracking_timeseries.csv`：对齐后的时序数据；
- `table_tracking_comparison.md`：论文式对比表；
- `fig_*.pdf`、`fig_*.png`：3D 轨迹、误差、速度/加速度和 RMSE 箱线图；
- `run_config.json`：固定协议与随机调度；
- `analysis_manifest.json`：来源、计数和关键文件校验和。

所有统计只读取 `trials/`。不要把 `rejected/` 合并回正式样本。
