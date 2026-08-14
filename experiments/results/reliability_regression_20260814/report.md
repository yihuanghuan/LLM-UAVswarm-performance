# 8 UAV 端到端可靠性恢复与回归报告

日期：2026-08-14
分支：本地 `main`（未提交、未推送）

## 结论

本轮恢复了基于反馈的完整启动、自动起飞和 READY 门控，修复了试验 runner 的任务输入时序，并统一了 LADRC baseline 的运行时参数来源。标准试验流程已经不再依赖人工选择 ARM、OFFBOARD 或自然语言输入时机。

- `px4_position` 8 UAV 英文自然语言顺序任务：3 次独立 cold start，3/3 完成。
- LADRC 分级门禁：单机、2 UAV、4 UAV、8 UAV 均为 3/3；随后 8 UAV 英文自然语言 E2E 完成。
- 历史 parallel 英文任务：Candidate 合法；确定性回放和真实 READY 后的 full-chain runtime 均给出明确安全拒绝。根因为 Case B，而不是 runtime 计算错误。
- 没有降低 `d_hard` 或 `d_plan`，没有修改 Minimum Jerk、LESO/LSEF、IAPF 架构，也没有关闭 PX4 auto preflight disarming。

## 1. main 与 Experiment 10 对照

修改前的 `main` 确实丢失了 Experiment 10 已验证的关键工程逻辑。原 `main` 仅按固定计数依次打印 ARM/OFFBOARD 成功，随后直接进入 `RUNNING_TRAJECTORY`；没有 VehicleStatus 确认、估计器稳定门控、自动起飞、READY 或 position-derived hover completion。

Experiment 10 已有而修改前 `main` 缺失的内容：

- fresh odometry/VehicleStatus、failsafe 和地面静止连续门控；
- ARM/OFFBOARD 的 VehicleStatus 确认与 retry；
- `TAKING_OFF`，起飞高度约 1.5 m；
- 起飞位置误差和 position-derived speed 连续保持后才 ready；
- `PositionVelocityFilter` 和 hysteretic `HoverStability`；
- `system_ready` 语义。

后续 `main` 新增而 Experiment 10 没有的内容包括 Candidate `UAVExecutionCommand`、Execution Profile guard、`ControlSetpoint` 双控制模式、全局 `SwarmState`、更完整的 IAPF/LADRC debug 和 paper policy 注入。因此没有机械 cherry-pick，而是把 Exp10 的启动/稳定语义适配到当前控制链。

## 2. 实际移植与适配

- 新建独立 `StartupStateMachine`：连续 estimator settle、prestream、有限 ARM/OFFBOARD retry、总超时、自动起飞稳定保持和 FAILED 锁止。
- ARM 前要求 fresh odometry、fresh VehicleStatus、`!failsafe`、position-derived filter valid/静止，并使用当前 PX4 提供的 `pre_flight_checks_pass`。
- prestream 期间持续发布 OffboardControlMode 和冻结的合法 holding setpoint。
- `px4_position` 使用 position setpoint 自动起飞；`ladrc_acceleration` 复用当前 reference → LADRC → PX4 acceleration 接口。
- 任务早到只覆盖保存 newest pending command；READY 后才 accept、初始化 Minimum Jerk 并记录 trajectory start。任务晚到时飞机已经处于空中稳定悬停。
- ARM 已确认后，如果 ARM/OFFBOARD/feedback/runtime 状态丢失超过 0.5 s，立即锁止 FAILED、撤销 ready 和任务；不主动空中 DISARM，不自动 re-arm/re-enter Offboard。
- completion 使用 position-derived filtered speed；raw EKF velocity 和 LESO z2 只用于诊断。

默认启动配置为：settle 10.0 s、prestream 1.5 s、takeoff altitude 1.5 m、位置容差 0.25 m、速度容差 0.15 m/s、保持 0.5 s、请求间隔 1.0 s、总超时 60 s、最多 20 次请求。

## 3. 修改文件

启动、控制和接口：

- `minisnap_LADRC/ladrc_controller/src/ladrc_position_controller_node.cpp`
- `minisnap_LADRC/ladrc_controller/include/ladrc_controller/startup_state_machine.hpp`
- `minisnap_LADRC/ladrc_controller/include/ladrc_controller/position_velocity_filter.hpp`
- `minisnap_LADRC/ladrc_controller/include/ladrc_controller/hover_stability.hpp`
- `minisnap_LADRC/ladrc_controller/config/ladrc_params.yaml`
- `minisnap_LADRC/ladrc_controller/launch/ladrc_controller.launch.py`
- `minisnap_LADRC/ladrc_controller/launch/swarm_launch.py`
- `minisnap_LADRC/ladrc_controller/CMakeLists.txt`
- `uav_swarm_interfaces/msg/StartupEvent.msg`
- `uav_swarm_interfaces/msg/UAVStatus.msg`
- `uav_swarm_interfaces/msg/ControlTrackingDebug.msg`
- `uav_swarm_interfaces/CMakeLists.txt`

Parallel 诊断与最小搜索补强：

- `location_allocate/location_allocate/safety_aware_allocator.py`
- `location_allocate/location_allocate/late_resolution.py`
- `location_allocate/location_allocate/paper_runtime.py`
- `experiments/system_8uav/fixtures/parallel_group_d_plan_baseline_trial3.json`
- `experiments/system_8uav/scripts/replay_parallel_group_d_plan.py`
- `location_allocate/test/test_parallel_regression_replay.py`

参数真源与 consistency tests：

- `lfs_policy/config/lfs_policy.paper_current.yaml`
- `lfs_policy/lfs_policy/loader.py`
- `lfs_policy/test/test_policy_loader.py`
- `location_allocate/test/test_policy_adapter.py`

自动化 runner 与分析：

- `experiments/system_8uav/scripts/readiness_gate.py`
- `experiments/system_8uav/scripts/wait_swarm_ready.py`
- `experiments/system_8uav/scripts/run_natural_language_trial.py`
- `experiments/system_8uav/scripts/analyze_ladrc_stability.py`
- `experiments/system_8uav/tests/test_readiness_gate.py`

仓库在本轮开始前已有其他未提交修改和历史实验目录；本轮没有清理、覆盖或归属这些用户数据。

## 4. 当前 startup state flow

`WAIT_ESTIMATOR_READY → PRESTREAM → ARMING → SETTING_OFFBOARD → TAKING_OFF → READY`

任一有限重试耗尽、总超时或 post-ARM 状态丢失进入锁止 `FAILED`。READY 是唯一允许正式 accept formation command 的状态。`StartupEvent` 记录 estimator ready、prestream、ARM request/confirm、OFFBOARD request/confirm、takeoff start/stable、system ready、pending、command accepted 和 mission trajectory start。

正式 runner 的顺序固定为：

`Gazebo/PX4 → controller → estimator gate → ARM/OFFBOARD → automatic takeoff → N/N stable READY → rosbag → English command → execution`

runner 要求全部 UAV 同时满足 fresh status、`system_ready`、armed、offboard、无 failsafe、高度至少 1.0 m、position-derived speed 不超过 0.30 m/s，并连续保持 1.0 s。

在本轮覆盖的标准 cold-start 时序中，人工“启动早/晚”依赖已经消除。外部反馈在 ARM 后真实丢失时会按确认策略锁止，仍需操作者重启，而不会自行恢复飞行状态。

## 5. Execution Profile / YAML 参数真源

运行时 baseline 的唯一权威来源现在是 `lfs_policy.paper_current.yaml` 的 `execution_profile`：

- `baseline_omega_c = [1.5, 1.5, 1.75]`
- `baseline_omega_o = [5.0, 5.0, 7.5]`

`ladrc_params.yaml` 不再重复定义 omega baseline；C++ 参数必须由选中的 policy/launch 注入。`controller_hard_clamps` 仍是安全边界而不是另一套 baseline，loader 验证 baseline 位于 clamps 内，并由同一个 `ros_parameters()` 同时向控制节点注入 baseline 和 limits。

consistency test 已建立：normal style、`task_gain=1` 的编译 profile 必须逐轴等于 policy 中冻结 baseline；ROS 注入值也必须逐轴一致，否则测试失败。

## 6. LADRC 1 → 2 → 4 → 8 分级结果

每一级均完成 3 次独立 cold start，3/3 后才升级。所有样本均 confirmed armed/offboard、完成自动起飞和 stable confirmation。

### 单机

| Trial | final error (m) | position speed (m/s) | raw EKF speed (m/s) | LESO z2 norm (m/s) | saturation | 结果 |
|---|---:|---:|---:|---:|---:|---|
| 1 | 0.0027 | 0.0094 | 0.3113 | 0.0774 | 0 | 通过 |
| 2 | 0.0126 | 0.0117 | 0.1265 | 0.0232 | 0 | 通过 |
| 3 | 0.0084 | 0.0128 | 0.1032 | 0.0508 | 0 | 通过 |

settling time 约 9.0 s。Trial 1 的 raw EKF speed 大于 0.3 m/s，但位置误差和 position-derived speed 都很小，属于 EKF velocity inconsistency，而不是控制发散。

### 2/4/8 UAV 汇总（每轮取最不利 UAV）

| 层级 | Trial | max final error (m) | max position speed (m/s) | max raw EKF speed (m/s) | max LESO z2 (m/s) | saturation | IAPF active | 结果 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| 2 UAV Line | 1 | 0.0134 | 0.0093 | 0.1659 | 0.0302 | 0 | 0 | 通过 |
| 2 UAV Line | 2 | 0.0158 | 0.0171 | 0.1835 | 0.0274 | 0 | 0 | 通过 |
| 2 UAV Line | 3 | 0.0157 | 0.0170 | 0.1459 | 0.0502 | 0 | 0 | 通过 |
| 4 UAV Circle | 1 | 0.0192 | 0.0183 | 0.1941 | 0.0250 | 0 | 0 | 通过 |
| 4 UAV Circle | 2 | 0.0197 | 0.0142 | 0.1927 | 0.0265 | 0 | 0 | 通过 |
| 4 UAV Circle | 3 | 0.0200 | 0.0185 | 0.2115 | 0.0626 | 0 | 0 | 通过 |
| 8 UAV Circle | 1 | 0.0185 | 0.0281 | 0.3349 | 0.0806 | 0 | 0 | 通过 |
| 8 UAV Circle | 2 | 0.0214 | 0.0149 | 0.3929 | 0.0461 | 0 | 0 | 通过 |
| 8 UAV Circle | 3 | 0.0217 | 0.0232 | 0.3353 | 0.0978 | 0 | 0 | 通过 |

因此上一次 8 UAV LADRC 的“地面附近、大误差、auto preflight disarming”应归类为 startup/takeoff invalid；在干净空中 READY 初始条件下没有复现。

## 7. px4_position 8 UAV sequential E2E

三次任务均为英文输入的 Circle → Square，同一任务、三次独立 Gazebo/PX4 cold start。

| Trial | 8/8 READY before bag | parser/assignment | Candidate completed | rosbag messages | rosbag size |
|---|---|---|---|---:|---:|
| `px4_e2e_trial_1_retry2` | 是 | 成功 | 是 | 70,702 | 34.8 MB |
| `px4_e2e_trial_2_retry` | 是 | 成功 | 是 | 80,727 | 39.9 MB |
| `px4_e2e_trial_3_retry` | 是 | 成功 | 是 | 74,024 | 36.5 MB |

结果：3/3。两个更早目录保留了 runner 工装缺陷证据：一次 readiness 脚本权限调用错误、一次 scheduler 使用错误 Python 导致缺少 `openai`；修复后没有删除这些失败目录，也没有将它们混入有效 cold-start 统计。

## 8. 8 UAV LADRC 英文 E2E

在分级 3/3 全部通过后，以同一英文 Circle → Square 任务完成一次新的 8 UAV cold-start E2E。manifest 为 `readiness_before_rosbag=true`、`candidate_completed=true`、scheduler return code 0；rosbag 约 48 MB、100,421 条消息。

最终任务末态：

| UAV | final error (m) | raw EKF speed (m/s) | position speed (m/s) | LESO z2 (m/s) | last 1 s saturation |
|---:|---:|---:|---:|---:|---:|
| 1 | 0.0186 | 0.5376 | 0.1060 | 0.1990 | 0 |
| 2 | 0.0220 | 0.6783 | 0.1875 | 0.3295 | 0 |
| 3 | 0.0175 | 0.6765 | 0.1908 | 0.3172 | 0 |
| 4 | 0.0092 | 0.4988 | 0.1435 | 0.2104 | 0 |
| 5 | 0.0227 | 0.4978 | 0.1723 | 0.2311 | 0 |
| 6 | 0.0219 | 0.6402 | 0.1720 | 0.2733 | 0 |
| 7 | 0.0555 | 0.6484 | 0.1487 | 0.3170 | 0 |
| 8 | 0.0191 | 0.5394 | 0.1050 | 0.2120 | 0 |

8/8 stable confirmed。raw EKF speed 全部高于 0.3 m/s，但 position-derived speed 和位置误差均满足要求；若仍使用 raw EKF 判据，本次将被错误判失败。

## 9. Parallel 根因与最小修改

根因分类：**Case B — 最终目标安全，但 nominal synchronized trajectory 在冻结 group assignment 约束下不可行。**

冻结 baseline_trial3 状态的确定性回放结果：

- group 0：UAV1–4，Line，center `[-5, 13.5, 3]`，spacing 2 m；targets x = `[-8, -6, -4, -2]`。
- group 1：UAV5–8，Line，center `[5, 13.5, 3]`，spacing 2 m；targets x = `[2, 4, 6, 8]`。
- `group_d_plan = 2.0 m`，`d_hard = 1.0 m`。
- local-search assignment 的 predicted minimum = 1.891789 m。
- offending pair = UAV2/UAV4，均属 group 0；progress = 0.896493，time = 7.50008 s。
- 允许的 4! × 4! = 576 个组内排列全部检查；无可行 assignment。
- 最佳组内排列 minimum = 1.896689 m，仍小于 2.0 m。
- final target minimum = 2.0 m；没有 `d_hard` violation。

最小修改是：保留原安全检查和 group 隔离，在普通 pair-swap 失败后，对规模可控的 group-local permutations 做确定性穷举；若仍失败，返回 typed error `parallel_nominal_trajectory_d_plan_violation`，携带 Case A/B/C/D 分类、两组几何、planning/final assignment、距离、冲突对和最近时刻。没有跨 group 交换 UAV，没有降低阈值。

## 10. Parallel full-chain 回归

使用历史原始英文指令，在新的 8 UAV `px4_position` cold start 中完成 8/8 READY、rosbag 启动和 LLM Candidate 解析。runtime 返回：

`parallel nominal trajectory violates explicit group_d_plan`

rosbag 中 8 个 `/uavN/execution_command` 的 message count 均为 0，证明 atomic batch 在安全失败时没有部分发布。这是预期、明确、可解释的安全拒绝，不计为 runtime bug，也不应强行执行后续 Circle。

## 11. 自动化验证

- `colcon build --packages-select uav_swarm_interfaces ladrc_controller lfs_policy location_allocate`：4 packages built。
- `colcon test`：185 tests，0 errors，0 failures，1 skipped。
- 独立源码 Python suite：147 passed。
- runner/analysis scripts：`py_compile` 通过。
- deterministic parallel replay test：通过。
- `git diff --check`：通过。

colcon 在扫描 workspace 内 `llm_env` 的 NumPy Cython 示例时仍打印已知 package-discovery 告警；选定的 4 个 package 均实际构建完成，测试结果不受影响。

## 12. 仍存在的 blocker / 后续判断

- 没有阻止标准 sequential baseline 或 LADRC E2E 的 P0 blocker。
- 历史 parallel 几何在当前冻结 `group_d_plan` 下确实不可执行；若业务上必须执行同一语义，需要上层改变几何、时长/航路或任务表达，而不是在本轮降低安全门限。当前 Safety-aware Allocator 仍不是完整轨迹规划器。
- post-ARM 反馈故障采用锁止策略，按确认意见不自动 re-arm/offboard；这属于明确的安全边界，不是未实现的静默恢复。
- 当前 LADRC 数据没有显示需要立即继续调参：分级门禁和 full-chain 均通过，末 1 s 无 saturation。raw EKF velocity 偏置仍存在，但已从 completion 判据中隔离并保留诊断。

## 13. 提交状态

按要求，本轮没有 commit 或 push。全部历史结果和此前报告均保留；新证据位于 `experiments/results/reliability_regression_20260814/`。
