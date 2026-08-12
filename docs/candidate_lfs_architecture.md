# Candidate LFS → Executable LFS 架构

本文描述已经冻结的 paper Candidate v2 架构。架构冻结不等于数值参数冻结：默认 runtime 使用 `paper-current-v1`，其中尚未校准的数值明确标记为 provisional。

## 新旧流程

旧路径（仅显式 `legacy_v1`，继续保留）：

```text
Natural Language → LLM v1 LFS → eager validation/normalization
→ FormationGenerator → allocator → UAVSwarmCommand
→ YAML baseline LADRC + IAPF
```

Candidate v2 路径（默认）：

```text
Natural Language → LLM Semantic Parser → Candidate Mission / Candidate LFS
→ Early Schema Validation → Early Semantic Validation
→ Mission / Task Graph Compiler → sequential / parallel / internal WaitSpec → FSM
→ 即将执行的 task 或 parallel group
    → one fresh StateSnapshot
    → Runtime Validation
    → Deterministic Center Resolver
    → Unit Geometry → Scale Resolution → Final Geometry
    → Planning Timing Estimate (T_plan)
    → Safety-aware Allocator
    → Final Timing Resolver (T_exec)
    → exactly one assignment safety re-evaluation when T_exec != T_plan
    → Executable LFS + ResolutionTrace
    → Execution Profile Compiler
    → UAVExecutionCommand
    → Per-UAV Minimum-Jerk + LADRC + IAPF
```

Mission Graph 编译只处理 Candidate 级任务关系。任何依赖当前位置的数值都在对应 task 真正开始前解析，因此第二阶段的 `current_swarm_centroid` 不会在第一阶段开始前被提前固化。

## 模块边界

| 模块 | 输入 | 输出/职责 |
|---|---|---|
| Candidate schema | Candidate Mission JSON | `task`、`parallel`、`wait` 节点；单任务保留八元组语义 |
| Schema Validator | JSON | 类型、必填字段、枚举、基本范围 |
| Early Semantic Validator | 无状态 Candidate Mission | task ID、并行 UAV 重叠、`s >= 1` 等 |
| Mission Graph Compiler | Candidate Mission、显式 `QRelationPolicy` | `CompiledMission`；唯一消费 `q` 的模块 |
| Per-task FSM Compiler | `CompiledTaskNode` | `TaskStateMachine`；不再读取 Candidate `q` |
| Fresh State Snapshot Manager | `/uavN/swarm_state` 的 ENU position、velocity、source/receive timestamp | 对 U 完整、fresh、skew 有界的不可变 snapshot |
| Runtime Validator | task、fresh snapshot | 参与 UAV 和时刻相关检查 |
| Deterministic Resolver | task、snapshot | `ResolvedTaskIntent`；本任务 U 的中心解析 |
| Unit Geometry | F、N | 无中心、无尺度的 offsets 和 `delta_F(N)` |
| Scale Resolution | unit geometry、r request、`d_plan(s)` | `r_exec`；使用 `r_safe=d_plan(s)/delta_F(N)` |
| Final Geometry | center、unit offsets、`r_exec`、AABB | 所有世界坐标目标点及逐点边界检查 |
| Planning Timing Estimate | 未分配 starts/targets、`T_request`、显式 timing policy | allocator 专用 `T_plan` |
| Safety-aware Allocator | starts、targets、`T_plan`、`d_plan` | assignment、实际 `D_i`、安全指标；不解析 T |
| Final Timing Resolver | assignment 后 `D_max`、`T_request` | 最终 `T_exec` |
| Executable LFS | 已解析 U/F/c/r/T/m/s/q | 正式 `tau_exec=(U,F,c,r,T,m,s,q)` |
| ResolutionTrace | Candidate、snapshot 与各阶段结果 | correction、provenance、warning、rejection；不进入八元组 |
| Execution Profile Compiler | Executable LFS、assignment、每机 `D_i`、显式 policy | 每机 LADRC、limits、IAPF soft 参数和来源 |
| UAVExecutionCommand | target、Execution Profile、IDs | 新复合执行消息；duration 只存在于 profile |
| Legacy compatibility | UAVSwarmCommand | target/duration 有效；style 仅记录；baseline LADRC |
| Per-UAV Controller | 新/旧消息、实时状态 | finite/check、hard clamp、smooth apply、LADRC/IAPF、日志 |

Allocator、Resolver 和 Compiler 是独立模块；没有共享一个含糊的“任务处理器”。

## 冻结语义

- `current_swarm_centroid` 与 `maintain_current_centroid` 只计算当前 task 的 U：`c_U(t)=sum(p_i)/|U|`。
- `relative + current_swarm_centroid` 使用同一 resolver 后叠加 world-frame offset；若未来需要全局质心，必须新增 `active_swarm_centroid`。
- snapshot 对所有参与 UAV 是 all-or-nothing；缺失、过期、未来时间戳或过大 epoch skew 均失败，不会忽略 UAV。
- Candidate state 使用 `/uavN/swarm_state : nav_msgs/Odometry`；旧 Point odom 不会进入 Candidate snapshot。ParallelGroup 的 center、start、timing 和 allocator 共用一个 snapshot epoch。
- `d_hard` 是固定 violation 定义，不随 `s` 改变；`d_plan(s)` 与 IAPF soft activation margin 可增大。
- `r_safe` 使用 `d_plan(s)`，不使用 `d_hard`。若 workspace 与安全下限冲突，任务失败，不缩小到不安全尺度。
- `T_request` 来自 Candidate；`T_plan` 只供 allocator；`T_exec` 在 assignment 后定稿，并是 Executable LFS、Execution Profile、消息和控制器的唯一 duration 来源。
- explicit T 可行时保持原值；不可行时确定性上调并写入 trace。auto T 可使用 m；explicit 且可行时 m 不修改 T。
- T 优先级为 Safety > Dynamic feasibility > Explicit time preference > Motion style。
- 只要最终 T 与 planning T 存在实际可表示差异就只复评一次，不循环重优化；内部浮点 epsilon 只用于数值比较。
- parallel 默认 `independent`；评估区间为 `[0,max(T_k)]`，提前完成者保持在 goal。只有显式 `synchronized` 才统一到最大可行 T。
- `completion_mode` 只属于 `ParallelGroup`，不进入 LFS 八元组。
- `q` 是唯一 canonical task transition descriptor：`direct`、`continuous` 或带 duration 的 `hover-and-wait`。Paper JSON 不接受独立 WaitNode；Mission Graph Compiler 将 q 转成内部 completion event/WaitSpec，运行 FSM 不重复解释。
- LLM 不输出 `omega_c`、`omega_o`、LADRC gain、控制限幅或 IAPF 增益。它们只由确定性 Execution Profile Compiler 生成。
- 新消息优先于旧消息。新 profile 活跃时，旧 `UAVSwarmCommand` 不可覆盖它。

## Paper-current baseline / Provisional

仓库默认使用 `lfs_policy/config/lfs_policy.paper_current.yaml`。其 workspace、freshness、qualitative scale、jerk 和 hard clamps 中的具体数字仍为 provisional。旧 migration 文件只为路径兼容保留。完整状态见 `docs/paper_parameter_calibration.md`。

当前 Execution Profile 对 style/task 使用中性恒等映射，全部 gain 为 1，smoothing alpha 为 1；这是 baseline-frozen，不是最终 semantic LADRC 创新点。

当前 controller 仍未把 LADRC `update()` 输出接入 PX4 acceleration/setpoint 主通道，也没有新增 velocity/jerk runtime enforcement；本架构图中的 controller stage 只表示消息接收、检查、现有 LADRC/IAPF runtime和日志边界。

## Paper formation vocabulary

Paper schema `paper-candidate-schema-v2` 将 F 定义为 descriptor，只支持 Circle、Line、Sphere、Triangle、Polygon。Polygon 必须携带 `sides>=4`，且 UAV 数量不少于 sides；目标沿正 sides 边形周长等距分布。Triangle 只允许 3 UAV。Circle 使用半采样相位的均匀圆周点，避免 3-UAV executable targets 与 +X 起始的 Triangle 完全相同。Lineup 与 Free 仅存在于 legacy schema 和历史 FormationGenerator。

## 关键实现文件

- `schemas/lfs_schema.json`
- `location_allocate/location_allocate/{lfs_validator,mission_compiler,mission_executor,state_snapshot,lfs_resolver}.py`
- `location_allocate/location_allocate/{formation_geometry,timing_resolution,safety_aware_allocator,late_resolution}.py`
- `location_allocate/location_allocate/{execution_profile_compiler,execution_command_builder}.py`
- `uav_swarm_interfaces/msg/{ExecutionProfile,UAVExecutionCommand}.msg`
- `minisnap_LADRC/ladrc_controller/include/ladrc_controller/execution_profile_guard.hpp`
- `minisnap_LADRC/ladrc_controller/src/ladrc_position_controller_node.cpp`
