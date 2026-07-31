# Experiment 10 results

每个批次保存在 `<batch_id>/`：

- `raw/`：trial CSV、rosbag、LLM/LFS 记录和运行 manifest；
- `manifests/`：供版本控制的小体积最终 manifest；
- `summaries/`：固定 CSV、论文表和完成报告；
- `figures/`：本地 PNG/PDF；
- `runtime_logs/`：本地仿真进程日志。

rosbag、运行日志和生成图片不提交到 Git；manifest、配置快照、CSV 与报告可提交。runner 拒绝覆盖任何非空 trial 目录。

