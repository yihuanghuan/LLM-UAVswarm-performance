# Experiment 10 results

每个批次保存在 `<batch_id>/`：

- `raw/`：trial CSV、rosbag、LLM/LFS 记录和运行 manifest；
- `manifests/`：供版本控制的小体积最终 manifest；
- `summaries/`：固定 CSV、论文表和完成报告；
- `figures/`：本地 PNG/PDF；
- `runtime_logs/`：本地仿真进程日志。

rosbag、运行日志和生成图片不提交到 Git；manifest、配置快照、CSV 与报告可提交。runner 拒绝覆盖任何非空 trial 目录。

本次正式批次为 `exp10-formal-20260731`。实验结论、失败分类、数据完整性
检查和复现命令见
`exp10-formal-20260731/summaries/completion_report.md`。

v2 补丁批次使用独立目录 `exp10-formal-v2-20260731`。正式运行按 attempt
记录所有 readiness 与 LLM 失败，并持续补跑，直到 A–E 各获得 10 个进入
任务执行阶段的 trial。旧批次只在 `reanalysis_v2/` 下新增可恢复指标，
不修改任何既有文件。
