# 实验 09：规划层—执行层安全机制协同消融

## 交付状态

- 状态：成功完成
- 分支：`exp/09-safety-ablation`
- 固定基础：`gazebo-experiment-v1`
- 正式协议提交：`9a1b9ee8caa143e99d3b60125619ed860019e63b`
- 正式运行代码提交：`dea81bfda0b9f1d84997bca284d2497e993548b2`
- pilot：`pilot/exp09-pilot-20260730`
- 正式数据：`formal/exp09-formal-20260730`
- 最终分支提交：以远程 `exp/09-safety-ablation` 分支 tip 为准

本实验从固定 tag 独立建分支，没有修改、移动或覆盖
`gazebo-experiment-v1`。实验专用控制器开关默认保持 inert，只由实验 09
运行脚本显式启用。

## 设计与配置

实验采用 `assignment_mode × avoidance_mode` 的 2×2 配对因子设计：

| Variant | Assignment | Avoidance |
| --- | --- | --- |
| B0 | `distance_hungarian` | `off` |
| P | `safety_aware` | `off` |
| E | `distance_hungarian` | `iapf_dual` |
| Full | `safety_aware` | `iapf_dual` |

固定配置为 LFS + Minimum Jerk + LADRC、`motion_style=normal`。正式批次包含：

- 4 个配置：`s1_crossing_4`、`s1_crossing_8`、
  `s2_dense_local_bias`、`s3_staggered_dynamic_crossing`；
- 每个配置 4 个 variant；
- 每个配置/variant 使用配对 seed 4201–4215，共 15 次；
- 总计 `4 × 4 × 15 = 240` 次正式试验。

pilot 共 16 次，覆盖 4 个配置与 4 个 variant，并在正式运行前生成
`PILOT_ACCEPTED`。冻结协议与 10 个配置文件的 SHA-256 见
`pilot/exp09-pilot-20260730/frozen_protocol.json`。

## 数据完整性

- 有效正式试次目录：240
- `trial_summary.csv`：240
- 配对 seed：每个配置/variant 均为完整的 4201–4215
- 代表 seed 4201 rosbag：16
- 代表视频：4 个 MP4，均可解码
- 启动阶段自动重试：10
- 正式任务失败：1（`s1_crossing_8/Full/seed 4214`，`timeout`）
- 碰撞事件：0

10 次重试均发生在正式记录前的预定位或参数设置阶段。失败启动被保存为
`*_failed_attempt_0`，不计入 240 个正式样本，也没有覆盖成功结果。

## 主结果

下表为各 15 次配对试验的均值；完整 mean、standard deviation 和 95% CI
见 `formal/exp09-formal-20260730/summaries/variant_summary.csv`。

| Scenario | Variant | Mission | Safety | Min distance (m) | Violations | RMSE (m) | Duration (s) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| s1_crossing_4 | B0 | 1.000 | 0.000 | 0.728 | 1.000 | 0.729 | 12.892 |
| s1_crossing_4 | P | 1.000 | 1.000 | 2.908 | 0.000 | 0.695 | 9.172 |
| s1_crossing_4 | E | 1.000 | 0.067 | 0.986 | 0.933 | 0.769 | 11.314 |
| s1_crossing_4 | Full | 1.000 | 1.000 | 2.907 | 0.000 | 0.671 | 10.117 |
| s1_crossing_8 | B0 | 1.000 | 1.000 | 1.376 | 0.000 | 0.559 | 8.415 |
| s1_crossing_8 | P | 1.000 | 1.000 | 1.904 | 0.000 | 0.539 | 8.393 |
| s1_crossing_8 | E | 1.000 | 1.000 | 1.413 | 0.000 | 0.547 | 8.770 |
| s1_crossing_8 | Full | 0.933 | 0.933 | 1.897 | 0.000 | 0.530 | 8.747 |
| s2_dense_local_bias | B0 | 1.000 | 0.000 | 0.690 | 1.000 | 0.465 | 13.189 |
| s2_dense_local_bias | P | 1.000 | 0.000 | 0.692 | 1.000 | 0.474 | 12.192 |
| s2_dense_local_bias | E | 1.000 | 1.000 | 1.082 | 0.000 | 0.447 | 11.228 |
| s2_dense_local_bias | Full | 1.000 | 1.000 | 1.079 | 0.000 | 0.442 | 10.530 |
| s3_staggered_dynamic_crossing | B0 | 1.000 | 0.000 | 0.755 | 1.000 | 0.725 | 11.782 |
| s3_staggered_dynamic_crossing | P | 1.000 | 1.000 | 2.900 | 0.000 | 0.652 | 10.745 |
| s3_staggered_dynamic_crossing | E | 1.000 | 0.800 | 1.006 | 0.200 | 0.761 | 11.956 |
| s3_staggered_dynamic_crossing | Full | 1.000 | 1.000 | 2.902 | 0.000 | 0.673 | 9.194 |

统计使用配对 Wilcoxon 或 McNemar 检验、配对 bootstrap 95% CI、精确
sign-flip 因子效应，并在预注册比较族内进行 Holm correction。完整结果见
`planned_comparisons.csv` 与 `factorial_effects.csv`。

## 假设结论

### H1：部分支持

在 4 机 crossing 配置中，P 相对 B0 将名义 XY crossing 的配对中位数降低
1 次，并将 predicted minimum distance 提高 2.166 m，二者
`p_holm=0.000366`。在 8 机配置中，名义 crossing 计数不变，但预测最小距离
提高 0.535 m，`p_holm=0.000366`。因此 safety-aware assignment 明显提高
预测间距，但 crossing count 的改善依赖具体拓扑。

### H2：部分支持

E 相对 B0 在全部四个配置中均显著提高真实最小机间距，配对中位提升分别为
0.257、0.032、0.403 和 0.253 m，均 `p_holm=0.000732`。Mission success
没有显著变化，因为 B0 在四个配置中已经全部完成任务。Safety success 在
S2 和 S3 显著提高，在 S1/4 的提升不足以通过校正，S1/8 则存在 ceiling
effect。

### H3：场景依赖的部分支持

在 S1/4、S1/8 和 S3 中，Full 相对 E 显著降低 IAPF active duration、
position offset 和 acceleration offset，相关比较 `p_holm=0.001465`。
在 S1/4 和 S3 中 Full 的 safety-aware assignment 已消除名义冲突，因此
代表性汇总中的 IAPF active duration 降至 0。S2 中 P 不能消除局部密集
风险，E 与 Full 的 IAPF 负担近似相同，差异不显著。四个配置的
trajectory deviation 差异均未显著。

### H4：整体支持，但有一个可靠性例外

Full 在 S1/4、S2、S3 达到 100% mission success 和 safety success；
在 crossing 场景的最小距离与 P 并列最优，在 S2 与 E 并列最优。任务时长
和 tracking RMSE 没有出现一致的不可接受增加，若干配置反而下降。然而
S1/8 的 Full/seed 4214 出现一次 timeout，使该配置的 mission/safety
success 为 14/15；因此不能声称 Full 在所有配置中无条件最优。

按照预定义 rescue event 判据，本批次没有 rescue event：所有对应的
无 IAPF variant 均已 mission success，因而不存在“off 失败、on 成功”的
配对样本。

## 产物

- 原始 CSV、metadata、运行日志与代表 rosbag：
  `formal/exp09-formal-20260730/raw/`
- 汇总统计：`formal/exp09-formal-20260730/summaries/`
- PNG/PDF 图：`formal/exp09-formal-20260730/figures/`
- 代表 MP4：`formal/exp09-formal-20260730/videos/`
- 批次清单：`formal/exp09-formal-20260730/batch_manifest.json`
- SHA-256 清单：
  `formal/exp09-formal-20260730/artifact_checksums.json`

所有 `raw/**`、rosbag 和 MP4 通过 Git LFS 跟踪。

## 运行与复现命令

```bash
source /opt/ros/humble/setup.bash
source install/setup.bash
export PYTHONPATH="$PWD/location_allocate:$PWD/experiments/09-safety-ablation/scripts${PYTHONPATH:+:$PYTHONPATH}"

# 16-run pilot
python3 experiments/09-safety-ablation/scripts/run_batch.py \
  --batch-id exp09-pilot-20260730 --phase pilot --manage-sim
python3 experiments/09-safety-ablation/scripts/validate_pilot.py \
  experiments/results/experiments_09/pilot/exp09-pilot-20260730

# 240-run formal batch
python3 experiments/09-safety-ablation/scripts/run_batch.py \
  --batch-id exp09-formal-20260730 --phase formal --manage-sim --resume

formal=experiments/results/experiments_09/formal/exp09-formal-20260730
python3 experiments/09-safety-ablation/scripts/reanalyze_batch.py "$formal"
python3 experiments/09-safety-ablation/scripts/aggregate_trials.py "$formal"
python3 experiments/09-safety-ablation/scripts/plot_results.py "$formal"
python3 experiments/09-safety-ablation/scripts/render_videos.py "$formal"
python3 experiments/09-safety-ablation/scripts/checksum_results.py "$formal"
```

## 验证

- 实验 09 Python tests：25 passed
- assignment/LFS functional tests：15 passed（其中 allocator tests 9 passed）
- IAPF C++ tests：9 passed
- ROS 2 三个 package build：成功
- 代表 MP4：4/4 可由 OpenCV 解码
- 功能测试均通过

仓库已有的 package-wide lint 基线仍报告 76 个 flake8 和 18 个 pep257
问题；这些是实验分支建立前已有的风格债务，不是实验 09 功能回归。
