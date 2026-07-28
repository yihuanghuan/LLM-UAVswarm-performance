# Experiment 07 results

本目录包含 semantic-conditioned LADRC Gazebo 实验的完整可复现产物。

- `trials/`：30 个正式 trial；每个目录包含 rosbag、展开后的 CSV、自然语言、
  LLM 解析日志、控制日志、PX4/Gazebo 日志和 trial 配置。
- `rejected/`：失败尝试；本次为空。
- `trial_summary.csv`：逐 trial 动力学指标。
- `method_style_summary.csv`：六个方法/style 单元格的 mean ± std 源数据。
- `effect_vs_fixed.csv`：task-conditioned 相对 fixed baseline 的差值。
- `timeseries.csv`：统一 50 Hz 的位置、速度、加速度、jerk 和姿态时序。
- `mean_std_table.md`：论文表格。
- `fig_*.png/pdf`：位置、速度/加速度/jerk、pitch/roll 和箱线图。
- `llm_reliability.json`：40 次实际 API 尝试和最终 gate 结果。
- `validation_report.json`：数据完整性机器可读报告。

正式数据规模为 30 个 rosbag、210 个按 topic 导出的 CSV。所有 trial 均使用
冷启动、3 秒任务时长和 15 秒观测窗口。
