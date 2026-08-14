# 8 UAV Gazebo 全链路回归报告（2026-08-13）

## 结论

本轮不能判定“实验没有问题”，因此没有提交或推送 `main`。

- 默认 `px4_position` 顺序编队链路通过 2 次有效 8 UAV 冷启动：`square → line`、`circle → square` 均从英文自然语言输入执行到 `Candidate mission completed`，最终 8/8 稳定确认。
- 并行分组链路失败：LLM 生成了结构正确的 synchronized parallel Candidate，但 runtime 在分配阶段拒绝执行，错误为 `parallel assignment violates explicit group_d_plan`。
- 显式 `ladrc_acceleration` 8 UAV 链路失败：8/8 未完成目标，末段平均位置误差 8.940 m；UAV7/8 被 PX4 `auto preflight disarming`，其余飞机在地面附近且控制输出持续饱和。
- 另有两次启动工装失败被保留：一次控制器启动早于 EKF 高度健康，另一次人为等待过久导致模型落地并锁定错误的无任务悬停高度。这两次不计入有效基线通过率，但说明端到端启动仍依赖严格时序。

## 测试环境和范围

- 分支：本地 `main`（相对 `origin/main` 含待验收修改）
- 仿真：Gazebo Classic、PX4 SITL 8 instances、Micro XRCE-DDS、8 个控制节点
- 自然语言入口：`location_allocate` Paper Candidate runtime，在线模型 `MiniMax-M2.7-highspeed`
- policy：`paper-current-v3`
- 稳定判定：position-derived filtered speed，进入阈值 0.30 m/s，连续保持 1 s
- 每个有效样本均录制 ROS bag；历史实验数据未覆盖

本轮发现 `ladrc_params.yaml` 的已验证低带宽参数会被 Paper Execution Profile 的旧值覆盖，因此将当前 policy 与控制器配置同步：`omega_c=[1.5,1.5,1.75]`、`omega_o=[5,5,7.5]`，configuration id 更新为 `paper-current-v3`。该修正通过单元测试，但由于全链路仍有 blocker，未提交。

## 实验矩阵

| 样本 | 模式 | 英文任务/阶段 | 结果 | 关键证据 |
|---|---|---|---|---|
| startup_attempt0 | LADRC | 无任务 | 启动拒绝（不计） | PX4 `height estimate not stable`；状态机 8/8 正确进入 `STARTUP_FAILED` |
| LADRC trial1 | `ladrc_acceleration` | line → circle | 失败 | Candidate 合法；90 s hover completion timeout；8/8 未稳定，末段平均误差 8.940 m |
| baseline_trial1 | `px4_position` | line → circle | 工装失败（不计） | 启动前等待过久，模型落地；5 架 auto preflight disarming，末段平均误差 7.945 m |
| baseline_trial2 | `px4_position` | square → line | 通过 | 8/8 ARM/OFFBOARD；`Candidate mission 1 completed`；8/8 稳定 |
| baseline_trial3-A | `px4_position` | 两个 4 机 line 并行 → circle | 失败 | Candidate 解析成功，执行前报 `parallel assignment violates explicit group_d_plan`，未发布任务 |
| baseline_trial3-B | `px4_position` | circle → square | 通过 | 相同冷启动中重新输入顺序任务；`Candidate mission 2 completed`；8/8 稳定 |

有效默认基线为 2/2 顺序任务通过；包含预期支持的并行任务后为 2/3 指令通过。由于并行任务存在框架级阻断，不能给出整体框架无问题的结论。

## 有效基线末段指标

指标取每架飞机最终 mission 的最后 8 s，位置峰峰值为 8 架中的最大值。

| 指标 | square → line | circle → square |
|---|---:|---:|
| stable confirmed | 8/8 | 8/8 |
| 8 机平均位置误差 | 0.215 m | 0.178 m |
| 8 机平均 raw EKF speed | 0.318 m/s | 0.258 m/s |
| 8 机平均 position-derived speed | 0.021 m/s | 0.018 m/s |
| 8 机平均 LESO z2 norm | 0.062 m/s | 0.055 m/s |
| 最大最终位置误差 | 0.233 m | 0.189 m |
| 最大最终 position-derived speed | 0.033 m/s | 0.022 m/s |
| 最大位置峰峰值 x/y/z | 0.059/0.087/0.056 m | 0.049/0.058/0.036 m |

两次有效任务末段位置派生速度均远低于 0.30 m/s，峰峰值不超过 8.7 cm。raw EKF speed 在第一轮平均仍为 0.318 m/s，而位置实际变化很小，再次验证 completion 不应使用 raw EKF velocity。

日志中的 `ladrc_output` 在 `px4_position` 模式仅用于诊断，不能把其饱和率当作 PX4 实际发布的 position setpoint 饱和率；基线通过与否以位置跟踪、position-derived speed、VehicleStatus 和 completion feedback 为准。

## 失败分类

### 并行 Candidate 契约不一致

自然语言明确要求 UAV1–4 与 UAV5–8 同时形成两条线，再合并成圆。LLM 返回：

- `type: parallel`
- `completion_mode: synchronized`
- 两个互不重叠的 4 UAV task
- 后接全 8 UAV circle task

Candidate schema/parser 均通过，但 late resolution 的安全分配无法满足显式 `group_d_plan`，runtime 直接拒绝。现有单元测试全部通过，说明测试覆盖未包含这一真实英文分组几何。建议下一步复现并核对：组间中心、组内 spacing/radius 的语义，parallel frozen max aggregation，以及 allocator 对跨组最小距离的约束是否与生成器一致。本轮按要求只报告，不擅自改变 policy 或安全距离。

### 8 UAV LADRC 规模化失败

该轮不是 completion detector false negative。末段位置派生速度很低是因为飞机基本停在地面附近，而目标误差仍巨大；8 机平均误差为 8.940 m、最大最终误差 14.087 m、稳定确认 0/8。PX4 日志还记录 UAV7/8 `Disarmed by auto preflight disarming`。因此应归类为 startup/takeoff 与 8 机 LADRC 执行的真实问题，而非 EKF velocity inconsistency。

单机 3/3、双机试验和默认 position 基线的通过证据仍有效；当前证据不足以继续盲调 LADRC 参数。下一步应先增加“ARM/OFFBOARD 已确认后必须在自动预飞解锁窗口前收到有效起飞任务”的执行门禁，再区分 8 机启动时序与 LADRC/IAPF 规模化控制问题。

### 启动工装敏感性

两类错误启动均被状态和日志正确暴露，但启动流程仍不够自洽：

1. 太早启动控制器时，PX4 EKF 报 `height estimate not stable`，ARM 被拒绝。
2. 等待健康过久时，Gazebo 初始悬空模型先落地，控制器随后把落地后的局部高度锁为 idle hover；若任务在 PX4 自动预飞解锁窗口后才到达，就无法执行。

有效样本采用 odometry/VehicleStatus topic 就绪后立即启动控制器，并在 8/8 ARM/OFFBOARD 后输入英文任务。建议将这个时序固化为启动脚本，而不是依赖人工操作。

## 自动化验证

- `location_allocate`：134 passed，1 skipped
- `lfs_policy`：10 passed
- 之前完成的控制器/接口构建与全套测试仍为通过状态
- `colcon` 在扫描 workspace 内 `llm_env` 的 NumPy Cython 示例时会打印已知的 package discovery 告警，不影响选定包测试结果

## 数据位置

- `rosbags/startup_attempt0`：过早启动/EKF 高度未稳定
- `rosbags/trial1`：8 UAV LADRC line → circle 失败
- `rosbags/baseline_trial1`：过晚启动工装失败
- `rosbags/baseline_trial2`：px4_position square → line 通过
- `rosbags/baseline_trial3`：并行 Candidate 拒绝，随后 circle → square 通过

## 发布决定

未提交、未推送。阻断项至少包括：

1. 合法并行分组 Candidate 无法通过 late-resolution/group_d_plan 分配；
2. 显式 8 UAV LADRC 全链路未起飞/未跟踪；
3. 启动时序尚未自动化，人工早/晚启动均可导致失败。

待上述问题处理并完成新的多次冷启动回归后，再评估推送 `main`。
