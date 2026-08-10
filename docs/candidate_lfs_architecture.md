# Candidate LFS → Executable LFS 架构

本文描述迁移期实现。架构不等于参数冻结：所有尚未确认的数值只通过显式 policy 注入，仓库不提供可被误认为正式值的生产默认值。

## 新旧流程

旧路径（继续保留）：

```text
Natural Language → LLM v1 LFS → eager validation/normalization
→ FormationGenerator → allocator → UAVSwarmCommand
→ YAML baseline LADRC + IAPF
```

Candidate v2 路径：

```text
Natural Language → LLM Semantic Parser → Candidate Mission / Candidate LFS
→ Early Schema Validation → Early Semantic Validation
→ Mission / Task Graph Compiler → sequential / parallel / WaitNode → FSM
→ 即将执行的 task 或 parallel group
    → one fresh StateSnapshot
    → Runtime Validation
    → Deterministic Center Resolver
    → Unit Geometry → Scale Resolution → Final Geometry
    → Planning Timing Estimate (T_plan)
    → Safety-aware Allocator
    → Final Timing Resolver (T_exec)
    → at most one assignment safety re-evaluation
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
| Fresh State Snapshot Manager | position、可选 velocity、source/receive timestamp | 对 U 完整、fresh、skew 有界的不可变 snapshot |
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
- `d_hard` 是固定 violation 定义，不随 `s` 改变；`d_plan(s)` 与 IAPF soft activation margin 可增大。
- `r_safe` 使用 `d_plan(s)`，不使用 `d_hard`。若 workspace 与安全下限冲突，任务失败，不缩小到不安全尺度。
- `T_request` 来自 Candidate；`T_plan` 只供 allocator；`T_exec` 在 assignment 后定稿，并是 Executable LFS、Execution Profile、消息和控制器的唯一 duration 来源。
- explicit T 可行时保持原值；不可行时确定性上调并写入 trace。auto T 可使用 m；explicit 且可行时 m 不修改 T。
- T 优先级为 Safety > Dynamic feasibility > Explicit time preference > Motion style。
- 最终 T 与 planning T 超过显式 tolerance 时只复评一次，不循环重优化。
- parallel 默认 `independent`；评估区间为 `[0,max(T_k)]`，提前完成者保持在 goal。只有显式 `synchronized` 才统一到最大可行 T。
- `completion_mode` 只属于 `ParallelGroup`，不进入 LFS 八元组。
- `q` 只由 Mission Graph Compiler 转成 completion event/WaitSpec；运行 FSM 使用编译结果，不重复解释 q。
- LLM 不输出 `omega_c`、`omega_o`、LADRC gain、控制限幅或 IAPF 增益。它们只由确定性 Execution Profile Compiler 生成。
- 新消息优先于旧消息。新 profile 活跃时，旧 `UAVSwarmCommand` 不可覆盖它。

## Provisional / TBD

以下只定义配置槽位，不冻结数值：workspace AABB、snapshot timeout/skew、nominal spacing、qualitative r 倍率、`d_hard` 的最终实验值、`d_plan(s)` 映射、IAPF soft 映射、动力学 limits、auto-T 算法选择及参数、timing recheck tolerance、allocator weights/sample rate、parallel planning-margin 聚合、style/task gain 函数、LADRC bandwidth 和所有 controller hard clamp。

候选公式实现（例如解析 Minimum-Jerk feasibility timing 和线性 task-intensity gain）只有在调用方显式构造 policy 时才会启用；它们不是生产默认或冻结算法。统一待填结构见 `location_allocate/config/lfs_policy.template.yaml`。

## 仍需确认

- `Lineup`：v2 删除、定义为带朝向的 Line、或作为独立队列 primitive。当前 Candidate schema 为迁移保留枚举，但新 geometry fail closed；v1 历史行为不变。
- `Free`：v2 删除、显式 per-UAV target primitive、或 return-home primitive。当前同样 fail closed，v1 不变。
- “前方”的 reference：world +x、swarm heading 或 leader heading。
- Candidate Mission wire schema 的正式版本号和长期兼容承诺。
- 上述全部 provisional 参数和候选函数的实验定稿。

## 关键实现文件

- `schemas/lfs_schema.json`
- `location_allocate/location_allocate/{lfs_validator,mission_compiler,mission_executor,state_snapshot,lfs_resolver}.py`
- `location_allocate/location_allocate/{formation_geometry,timing_resolution,safety_aware_allocator,late_resolution}.py`
- `location_allocate/location_allocate/{execution_profile_compiler,execution_command_builder}.py`
- `uav_swarm_interfaces/msg/{ExecutionProfile,UAVExecutionCommand}.msg`
- `minisnap_LADRC/ladrc_controller/include/ladrc_controller/execution_profile_guard.hpp`
- `minisnap_LADRC/ladrc_controller/src/ladrc_position_controller_node.cpp`
