# LADRC 单机稳定判定回归、参数修复与复测报告

## 1. 结论

当前 `main@e550e15f` 确实丢失了 `exp/10-system-8uav` 已有的 position-derived stability 修复：HEAD 中稳定判定直接计算 `current_odom_.velocity` 模长，并以单个 sample 置 `stable=true`；Exp10 中则已有 `position_velocity_filter.hpp`、`hover_stability.hpp` 及其测试。

最小移植恢复后，稳定判定已改为 position-derived filtered speed + hysteresis + 1 s 连续保持。随后数据也确认了用户指出的另一层问题：原参数虽然会短暂触发 stable，但无人机持续真实振荡。通过仅降低 LADRC 三轴控制器/观测器带宽，振荡获得稳定、可重复的改善：单机 3 次 cold start 全部通过，双机回归中 2/2 UAV 通过。

本轮未改 LADRC/LESO/LSEF 数学、`b0`、加速度限幅、Minimum Jerk、IAPF、Execution Profile 或 PX4 acceleration-level Offboard 接口，也未放宽任何稳定阈值。

## 2. 稳定判定回归修复

恢复并使用：

- 位置差分速度：`v_raw=(p_k-p_{k-1})/dt`
- 一阶低通：`tau=0.5 s`
- 稳定进入：position error `<=0.40 m` 且 position-derived speed `<=0.30 m/s`
- 稳定退出：position error `>0.50 m` 或 speed `>0.40 m/s`
- 状态机：`UNSTABLE -> CANDIDATE -> 1.0 s -> CONFIRMED`
- 新 mission 只重置 stability state，不重置 LESO

稳定判定现在只使用 `position_velocity_filter.speed()`。raw PX4 EKF velocity 和 LESO `z2` 只用于诊断。

`control_tracking_debug` 同时记录：raw EKF velocity/speed、position-derived filtered velocity/speed 和 LESO `z2`/norm。

## 3. 原参数复测：短暂 stable 不等于真实收敛

原参数为 X/Y `omega_c=3.0, omega_o=10.0`，Z `omega_c=3.5, omega_o=15.0`。三次单机均成功确认 armed + offboard，并在约 11.02 s 首次确认 stable；但之后反复退出和重新进入。下表为每个 bag 最后 10 s，而不是首次 stable 时刻。

| 试次 | mean pos err (m) | mean raw EKF speed (m/s) | mean pos-derived speed (m/s) | mean LESO z2 (m/s) | saturation | stable 状态转换 | 三轴位置峰峰值（末 30 s, m） |
|---|---:|---:|---:|---:|---:|---:|---|
| O1 | 0.204 | 1.124 | 0.372 | 0.693 | 70.1% | 20 | 0.667 / 0.597 / 0.194 |
| O2 | 0.208 | 1.130 | 0.379 | 0.728 | 76.8% | 16 | 0.630 / 0.702 / 0.164 |
| O3 | 0.220 | 1.181 | 0.398 | 0.746 | 71.3% | 20 | 0.683 / 0.796 / 0.238 |

这三次属于 Case B：position-derived speed 也长期高于 0.3 m/s，真实位置峰峰值达到约 0.6–0.8 m，并伴随约 70% 水平限幅。因此它们不能按“3/3 稳定”验收；首次确认只是振荡轨迹短暂满足 1 s 窗口。

原参数双机试验同样复现问题：UAV1/UAV2 最后 10 s 的 position-derived speed 分别为 0.344/0.371 m/s，位置误差均值为 0.195/0.214 m，饱和率为 58.9%/57.7%，稳定状态转换 40/24 次。UAV2 首次确认甚至延迟到 52.38 s。

## 4. 参数诊断与修改

第一阶段只降低水平带宽：X/Y `omega_c 3.0 -> 1.5`，`omega_o 10.0 -> 5.0`。末 30 s 水平峰峰值从 0.6–0.8 m 降至 0.023–0.025 m，水平饱和率从约 70% 降为 0；但 Z 轴仍有 0.205 m 峰峰值和 5.6% 垂直饱和。

第二阶段保持水平候选值，并降低高度带宽：Z `omega_c 3.5 -> 1.75`，`omega_o 15.0 -> 7.5`。末 30 s 三轴峰峰值为 0.030/0.039/0.039 m，position-derived speed 均值 0.018 m/s，三轴饱和率为 0。

因此最终写入默认 LADRC 参数的候选值为：

| 轴 | omega_c（原 → 新） | omega_o（原 → 新） | b0 |
|---|---:|---:|---:|
| X | 3.0 → 1.5 | 10.0 → 5.0 | 1.0（不变） |
| Y | 3.0 → 1.5 | 10.0 → 5.0 | 1.0（不变） |
| Z | 3.5 → 1.75 | 15.0 → 7.5 | 1.0（不变） |

## 5. 调参后单机 3 次 cold-start 验收

任务均为 `[0,3,2]`、Minimum Jerk 10 s。三次启动均在第一次请求后得到 armed + offboard 双确认。

| 试次 | startup | settling (s) | final pos err (m) | final raw / pos-derived / z2 (m/s) | last 10 s mean pos err (m) | last 10 s mean raw / pos-derived / z2 (m/s) | saturation | stable |
|---|---|---:|---:|---|---:|---|---:|---|
| T1 | confirmed | 11.020 | 0.0100 | 0.314 / 0.0158 / 0.0370 | 0.0120 | 0.306 / 0.0196 / 0.0554 | 0% | confirmed，未退出 |
| T2 | confirmed | 11.020 | 0.0105 | 0.353 / 0.0058 / 0.0356 | 0.0108 | 0.337 / 0.0178 / 0.0590 | 0% | confirmed，未退出 |
| T3 | confirmed | 11.020 | 0.0103 | 0.342 / 0.0074 / 0.0312 | 0.0116 | 0.335 / 0.0187 / 0.0601 | 0% | confirmed，未退出 |

三次末 30 s 各轴峰峰值最大值为 0.043 m，position-derived speed 的 P95 最大值为 0.0347 m/s，稳定状态均只有一次 `false -> true` 转换。单机达到 3/3。

这里又出现清晰的 Case A：T2/T3 的 final raw EKF speed 仍为 0.353/0.342 m/s，last-10-s raw 均值也高于 0.3 m/s；但 position-derived speed 仅约 0.018 m/s、位置误差约 1 cm、饱和率为 0。若用 raw EKF speed，这两次会被误判失败。

## 6. 双机回归

双机任务与原试验一致：UAV1 到 `[-1.5,4.5,2]`，UAV2 到 `[1.5,4.5,2]`，10 s。

| UAV | startup | settling (s) | final pos err (m) | last 10 s mean raw / pos-derived / z2 (m/s) | 末 30 s三轴峰峰值 (m) | saturation | stable |
|---|---|---:|---:|---|---|---:|---|
| 1 | confirmed | 11.000 | 0.0045 | 0.232 / 0.0129 / 0.0405 | 0.033 / 0.021 / 0.032 | 0% | confirmed，未退出 |
| 2 | confirmed | 11.000 | 0.0108 | 0.235 / 0.0156 / 0.0434 | 0.028 / 0.023 / 0.034 | 0% | confirmed，未退出 |

双机并行节点、命名空间 remap、ARM/OFFBOARD feedback state machine 均正常。

## 7. L1/L2 根因分类

- 历史 L1：70.95% saturation、末段 raw speed 1.114 m/s，至少包含真实控制振荡，不能归为纯 completion false negative。
- 历史 L2：旧日志没有 position-derived velocity，无法仅凭 0.440 m/s raw EKF speed 干净定案。新试验证明静止时 raw EKF 可稳定在约 0.31–0.34 m/s，因此 L2 很可能同时含 EKF velocity inconsistency；但不能对缺失数据作确定性追溯结论。
- 本轮原参数 O1–O3：有 position-derived 数据，明确属于真实控制振荡/不收敛。
- 本轮调参后 T1–T3：真实收敛；T2/T3 若使用 raw EKF 会属于 completion false negative。

## 8. 修改文件与回归边界

稳定判定和诊断修改：

- `minisnap_LADRC/ladrc_controller/include/ladrc_controller/position_velocity_filter.hpp`
- `minisnap_LADRC/ladrc_controller/include/ladrc_controller/hover_stability.hpp`
- `minisnap_LADRC/ladrc_controller/src/ladrc_position_controller_node.cpp`
- `minisnap_LADRC/ladrc_controller/config/ladrc_params.yaml`
- `minisnap_LADRC/ladrc_controller/CMakeLists.txt`
- `minisnap_LADRC/ladrc_controller/test/test_position_velocity_filter.cpp`
- `minisnap_LADRC/ladrc_controller/test/test_hover_stability.cpp`
- `uav_swarm_interfaces/msg/ControlTrackingDebug.msg`

分析与报告：

- `experiments/system_8uav/scripts/analyze_ladrc_stability.py`
- `experiments/results/ladrc_stability_regression_20260813/report.md`
- `experiments/results/ladrc_stability_regression_20260813/rosbags/`

`px4_position` 默认模式和控制路径未修改；此前当前 main 上的 8 UAV full-chain baseline 证据保留在 `experiments/system_8uav/reports/2026-08-13_3_p0_fix_acceptance.md`。本轮没有覆盖任何历史报告或 `experiments_10` 数据。

## 9. 最终判断

稳定判定回归已恢复，持续晃动也通过参数降带宽解决，并在单机 3 次 cold start 和一次双机试验中复现。当前证据不支持继续修改 LADRC 数学或做更激进调参；下一步应先用相同参数按 4/8 UAV 分级扩大样本，并继续以末段振幅、position-derived speed、稳定退出次数和饱和率作为门禁，而不能只看首次 `stable=true`。
