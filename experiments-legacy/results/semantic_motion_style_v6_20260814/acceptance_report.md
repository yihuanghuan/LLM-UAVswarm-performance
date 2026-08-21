# Semantic Motion Style v6 Targeted Acceptance

日期：2026-08-14
基线：`main@ea2a0a615769acef68580ddfecabeea94ce011ad`
（`freeze-paper-command-to-control-system-v1`）
Policy：`paper-current-v6`，SHA-256
`b9f048323ed3e349e45077452ef4937078da8a8978ef3de11a33d79e91294143`

结论：semantic motion-style architecture 可以冻结；当前 multiplier 与
profile smoothing 仍是 provisional calibration。没有 architecture blocker。

## 1. 接口审计与最小修改

原接口从 Candidate `m` 到 Resolver、Executable LFS、Execution Profile、
`UAVExecutionCommand`、controller、LSEF/LESO 和 PX4 acceleration 已完整存在。
原来不产生差异是四个 policy freeze point 同时把它中和：三种 style gain
全为 1、production loader 拒绝非中性 gain、compiler total-gain range 固定为
`[1,1]`、controller omega hard clamps 的上下界都等于 baseline。

本轮只做以下启用：

- style gain：smooth/normal/aggressive = `0.8/1.0/1.1`；
- auto-T factor：`1.30/1.15/1.10`，全部不小于 1；
- task adaptation 保持 `identity`，`task_gain=1.0`；
- omega clamps 改为 baseline 的 `0.75x–1.25x` 安全包络；
- compiler scalar envelope 从逐轴 controller clamps 推导；
- loader 强制 style 顺序、auto-T 顺序和三种 profile 位于 clamps 内。

Controller source、Minimum-Jerk、LADRC、PX4 acceleration、startup、allocator
和 IAPF 算法均未修改。当前 `smoothing_alpha=1.0` 表示 finite/clamp guard 后
原子应用，不是跨周期渐变。

## 2. 测试结果

- semantic/profile targeted pytest：`52 passed`；
- 全 ROS package regression：`195 tests, 0 errors, 0 failures, 1 skipped`；
- controller execution-profile guard 覆盖 non-finite rejection、hard clamp、
  broken hysteresis rejection 和 smoothing；
- 新测试证明逐轴
  `omega(smooth) < omega(normal) < omega(aggressive)`，且全部位于 clamps；
- 同 start/target/geometry/explicit T 的三种 style 得到完全相同的 duration、
  assignment 和 analytic Minimum-Jerk peaks；
- auto T 严格有序且 analytic velocity/acceleration/jerk 全部不超过
  `5/5/10`；
- 不可行的 aggressive explicit `T=0.1 s` 被 dynamic feasibility 提升到
  `T_min`，并继续通过 `d_hard` gate，验证
  `Safety > Dynamic feasibility > Explicit T > Motion style`。

## 3. Gazebo 数据集

正式结果使用两个数据集：

- `semantic_motion_style_explicit_v6_20260814_final/`：Experiment A；
  3 UAV Triangle、explicit `T=8 s`，每种 style 3 次独立 cold start，27 个
  UAV-task segments。Triangle 避免了 2 UAV 对称 Line 的等价槽位交换。
- `semantic_motion_style_v6_20260814/`：Experiments B/C；每种 style 3 次
  独立 4 UAV cold start，72 个 segments。task 2 是低规模 auto-T，task 3
  是 4 UAV Circle E2E。

两组均为 `9/9` readiness、Candidate completion 和 cold-start success。
所有真实英文命令均由在线 Candidate parser 解析；bag 中 style 与 manifest
全部一致，configuration ID 只有 `paper-current-v6`，compiled/applied omega
最大绝对误差为 0。

### Experiment A：Explicit-T isolation

每项为 9 个 UAV segments 的统计；RMSE 为均值，其余误差/状态量取最大值。

| style | T_exec | RMSE m | peak error m | settle mean s | overshoot m | saturation | z2 peak | z3 peak | final error m | speed peak m/s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| smooth | 8.000 | 0.0481 | 0.1205 | 9.021 | 0.1149 | 0 | 1.733 | 0.625 | 0.0731 | 1.667 |
| normal | 8.000 | 0.0308 | 0.0787 | 9.016 | 0.0594 | 0 | 1.738 | 0.853 | 0.0389 | 1.685 |
| aggressive | 8.000 | 0.0256 | 0.0719 | 9.025 | 0.0418 | 0 | 1.735 | 0.765 | 0.0311 | 1.670 |

逐 UAV target assignment 完全一致；实际 cold-start 起点的最大跨 trial 差异
为 `0.056 m`，因此 bag 中 path length 最大差异为 `0.032 m`。相同输入下的
nominal MJ bit-for-bit invariance 由 unit test 证明；物理 cold start 不声明
位姿 bit-for-bit 相等。三种 profile 分别为：

- smooth：`omega_c=[1.2,1.2,1.4]`，`omega_o=[4,4,6]`；
- normal：`omega_c=[1.5,1.5,1.75]`，`omega_o=[5,5,7.5]`；
- aggressive：`omega_c=[1.65,1.65,1.925]`，`omega_o=[5.5,5.5,8.25]`。

三种模式全部稳定、无 saturation。LADRC→PX4 acceleration 最大链路误差
`7.94e-8`。

### Experiment B：Auto-T semantic style

| style | T_exec mean s | predicted v/a/j peak | speed peak m/s | RMSE m | settle mean s | saturation mean/max |
|---|---:|---:|---:|---:|---:|---:|
| smooth | 4.733 | 3.189 / 2.074 / 4.552 | 3.255 | 0.1903 | 5.975 | 0 / 0 |
| normal | 4.183 | 3.597 / 2.647 / 6.575 | 3.669 | 0.1667 | 5.459 | 0 / 0 |
| aggressive | 4.000 | 3.757 / 2.892 / 7.513 | 3.837 | 0.1618 | 5.289 | 0.0489 / 0.0639 |

所有 3 个 trial 都满足严格顺序
`T_smooth > T_normal > T_aggressive >= T_min`；观测到的 T/T_min 分别约为
`1.30/1.15/1.10`。所有 analytic MJ peaks 均在 frozen motion limits 内。

Aggressive 在这条最快、约 8 m 的 auto-T 位移上仍有短时 LADRC output
saturation：平均 4.89%，最坏单 segment 6.39%；任务均稳定完成，无发散或
明显振荡。首 0.5 s saturation 为 0，说明它发生在轨迹峰值段，不是 profile
application transient。该现象是继续标定 aggressive multiplier 的依据，
不是接口断点。

Position-derived velocity 二次差分得到的 acceleration/jerk 对 EKF 噪声非常
敏感，不能替代 analytic Minimum-Jerk feasibility gate；原始 p99 值保留在
`trial_metrics.json`，但冻结的动态可行性判据仍是解析峰值。

### Experiment C：4 UAV Circle E2E

| style | T_exec mean s | predicted v/a/j peak | RMSE m | saturation | final error max m |
|---|---:|---:|---:|---:|---:|
| smooth | 3.643 | 1.890 / 1.596 / 4.552 | 0.1268 | 0 | 0.0381 |
| normal | 3.224 | 2.137 / 2.041 / 6.577 | 0.1226 | 0 | 0.0729 |
| aggressive | 3.084 | 2.240 / 2.234 / 7.517 | 0.1158 | 0 | 0.1133 |

每次均为真实 English → Candidate `m` → late resolution → allocator → profile
→ 4/4 controller → Gazebo。4/4 全部完成，auto duration 严格有序，零 hard
safety violation，整体最小邻机距离 `1.653 m`，IAPF active fraction 为 0
（符合本轮低冲突设计），三种 style 均零 saturation。LADRC→PX4 acceleration
全数据最大链路误差 `2.47e-7`，无 startup regression。

## 4. Development value 选择依据

初始 development 点 `aggressive gain=1.2, alpha_T=1.0` 把 auto trajectory
放在 jerk=10 边界，task 2 saturation 平均/最坏为 `20.17%/24.32%`。
仅把 `alpha_T` 提到 1.10 的单次 pilot 仍为 `9.48%/10.41%`。最终同时把 gain
降到 1.10 后，3 次 cold start 降到 `4.89%/6.39%`，explicit A 和 swarm C
均为 0。故当前选择保守但仍保持清晰语义差异；它不是 paper-final。

## 5. Freeze judgment

1. `m` 完整贯穿 NL → controller：是。
2. explicit T 只改变 control profile、不改变 nominal MJ policy：是。
3. auto T 正确改变 T_exec 且不低于 T_min：是。
4. smooth/normal/aggressive 均稳定：是。
5. aggressive saturation/振荡：auto-T 最快任务有短时 saturation；无明显振荡或发散。
6. profile application transient：本轮所有 command switch 前 0.5 s saturation 为 0；未发现瞬态 blocker。跨 style 的专门 mid-flight switching sweep 尚未做，属于 smoothing calibration。
7. 问题分类：parameter calibration problem；no architecture blocker。

最终状态：

```text
architecture frozen
parameter calibration provisional
```

## 6. 文档清理

删除的过程性 Markdown：

- `docs/experiment_evaluation_pipeline.md`
- `docs/legacy/xy_crossing_cost_fix.md`
- `docs/multi_sim_jsonschema_and_system_id_fix.md`
- `experiments/results/full_chain_regression_20260813/report.md`
- `experiments/results/reliability_regression_20260814/parallel_feasibility_gate_fix.md`
- `experiments/results/reliability_regression_20260814/report.md`
- `experiments/system_8uav/reports/2026-08-13_3_p0_fix_acceptance.md`
- `experiments/system_8uav/reports/2026-08-13_full_chain_evaluation.md`

保留的 authoritative/current 文档及原因：

- `README.md`：build/launch/interface 总入口；
- `docs/paper_command_to_control_architecture.md`：当前 canonical architecture；
- `docs/paper_lfs_spec.md`：Candidate/Executable frozen semantics；
- `docs/paper_candidate_runtime.md`：production runtime 与 ROS contract；
- `docs/paper_parameter_calibration.md`：数值 provenance 和 provisional 状态；
- `docs/safety_aware_topology_assignment.md`：allocator objective 与 safety gates；
- `docs/minimum_jerk_trajectory_metrics.md`：MJ 数学和 metrics contract；
- `docs/control_adaptation_logging.md`：profile application 与 observability；
- `docs/iapf_accel_feedforward.md`、`docs/iapf_velocity_hysteresis.md`、
  `docs/iapf_experiment_tooling.md`：当前 IAPF 行为/模式/实验接口；
- `experiments/README.md` 与 `experiments/docs/experiments_01..11.md`、
  `requirements.md`：正式实验协议和工具入口；
- `experiments/results/freeze_command_to_control_v1_20260814/acceptance_report.md`：
  上一 freeze 的正式证据；
- `experiments/results/ladrc_stability_regression_20260813/report.md`：
  当前 LADRC baseline 的唯一正式标定与复现实验证据；
- 本报告、两个 acceptance summary、trial metrics、manifest/scheduler log 和
  rosbag：本轮正式结果与 raw-data index。

已全局检查当前 Markdown；未发现过时的 PX4 acceleration 链路 blocker、
旧 paper-current 中性 style policy 或错误 system-ID 广播说明。
历史 JSON/raw results 保留作复现数据，不视为当前架构说明。
