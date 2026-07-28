# Experiment 07 validation

- [x] 分支从 `gazebo-experiment-v1` 创建。
- [x] 六个方法/style 单元格各有 5 个正式 trial。
- [x] 30 个 trial 均为独立 PX4/Gazebo 冷启动。
- [x] 每个 trial 均重新调用 LLM。
- [x] 30 个最终 LFS 结果全部通过预注册 gate。
- [x] 每个 rosbag 均包含 7 个预注册 topic。
- [x] PX4 position、velocity、quaternion 数组均展开为独立 CSV 字段。
- [x] fixed baseline 的 15 个 gain multiplier 全部为 1.0。
- [x] task-conditioned 的 15 个 gain multiplier 全部与公式一致。
- [x] 所有非-settling 指标均为有限值。
- [x] settling 未满足时保留 N/A，未调整阈值。
- [x] PNG/PDF 图可从原始数据重新生成。
- [x] 12 项实验单元测试通过。
- [x] `uav_swarm_interfaces`、`ladrc_controller`、`location_allocate` 构建成功。

机器可读结果见 `validation_report.json`。
