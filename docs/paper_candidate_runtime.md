# Paper Candidate LFS Runtime

## 默认与兼容模式

`location_allocate` 当前默认使用：

```text
Natural Language → Candidate Mission → Mission Graph/FSM
→ per-task/group fresh snapshot → late resolution
→ Executable LFS → Execution Profile → UAVExecutionCommand
```

显式兼容模式：

```bash
ros2 run location_allocate location_allocate --ros-args \
  -p lfs_runtime_mode:=legacy_v1
```

legacy 模式保留 v1 parser、`task_sequences`、旧 FormationGenerator、
`/uavN/odom`、`UAVSwarmCommand` 和历史 allocator API。Candidate 解析、验证或执行失败时只记录错误和 ResolutionTrace，不会进入 legacy fallback。

## Candidate 运行

构建：

```bash
cd ~/learning/LLM_swarm_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select \
  uav_swarm_interfaces lfs_policy location_allocate ladrc_controller
source install/setup.bash
```

PX4/Gazebo 和 XRCE Agent 启动后：

```bash
# 控制器：默认加载 paper-current policy，并接收新复合消息
ros2 launch ladrc_controller swarm_launch.py uav_ids:=[1,2,3,4,5]

# 调度器：Candidate v2 是默认 mode
ros2 run location_allocate location_allocate
```

示例自然语言：

```text
Have UAVs 1 through 5 form a circle.
```

未给出 center、scale、duration 时，Candidate 分别输出 `c:auto`、`r:auto`、`T:auto`，不会补 `[0,0,1.5]`、`1.5m` 或 `3s`。

Paper Candidate `F` 是结构化 descriptor，例如 `{"type":"Circle"}` 或 `{"type":"Polygon","sides":4}`。`q` 也是唯一的结构化 transition descriptor；悬停等待写为 `{"mode":"hover-and-wait","duration":2}`，paper JSON 不输出独立 WaitNode。

## Policy 层级

- `location_allocate/config/lfs_policy.template.yaml`：完整字段模板，允许 null/TBD，production loader 必须拒绝。
- `lfs_policy/config/lfs_policy.paper_current.yaml`：当前论文主路径，`configuration_id=paper-current-v11-c0-f-frozen`；C0-A～C0-F 参数组已冻结。
- `lfs_policy/config/lfs_policy.legacy.yaml`：只供显式历史兼容。

正式仿真基线由 immutable `paper-final-sim-v2` tag 固定；完整参数状态见
[paper_parameter_calibration.md](paper_parameter_calibration.md)。

启动时 typed loader 会一次性检查 missing/null、NaN/Inf、workspace 顺序、`s` 范围、安全 ordering、IAPF hysteresis、repulsion 非负、controller clamp 覆盖、configuration ID 和 provenance。任何不完整 policy 都在发布 UAV command 前 fail fast。

Safety Compiler 在 late resolution 中将 Candidate `s` 一次性编译为
allocator `d_plan` 与 Execution Profile 的 IAPF enter/exit/repulsion scale；
controller 和 IAPF core 不再解释 `s`。完整约定见
[paper_safety_factor.md](paper_safety_factor.md)。

## 状态接口

Candidate production state：

```text
/uavN/swarm_state : nav_msgs/msg/Odometry
header.frame_id    : world
child_frame_id     : uavN/base_link_enu
position           : global ENU（含 spawn offset）
linear velocity    : global ENU
header.stamp       : controller 收到对应 PX4 sample 时的 ROS clock
```

PX4 timestamp 是 boot-clock microseconds，不能冒充 ROS epoch/sim time，因此 frame-normalization publisher 在接收 sample 时生成 ROS source stamp。Scheduler 另存 receive stamp，freshness 使用 header source stamp。

当前 paper runtime 使用 `paper-current-v11-c0-f-frozen` 中已经冻结的
C0-A/C0-B freshness policy：

- `state_timeout=0.022080s`（C0-B P99 + 固定 10 ms）
- `snapshot_skew=0.022043s`（C0-B P99 + 固定 10 ms）
- 等待 fresh state 最多 `0.010000s`（在冻结 freshness predicates 下重放校正后，P99 + 固定 10 ms）
- velocity 必须 finite
- zero/future/stale timestamp 拒绝
- `allow_receive_time_fallback=false`

debug 显式打开 fallback 时会在 ResolutionTrace 留 warning。ParallelGroup 对 U 的并集只建立一个 immutable snapshot。

旧 `/uavN/odom : geometry_msgs/Point` 保持原类型和频率，只供 legacy 路径使用。

## 新执行接口

`/uavN/execution_command` 使用 `UAVExecutionCommand`：

```text
Header header
uint32 mission_id
uint32 task_id
uint32 group_id
uint8 uav_id
Point target_pos
ExecutionProfile profile
```

`profile.duration` 来自最终 `T_exec`，是新路径唯一 duration。当前
paper-current policy 只启用 motion style：`style_gain` 为
`0.8/1.0/1.1`，`task_adaptation_type=identity` 且 `task_gain=1.0`。
Compiler 将总 gain 同时作用于 `omega_c/omega_o`。velocity、acceleration、
jerk limits 用于 timing、完整性检查和审计；controller 没有新增
velocity/jerk runtime enforcement。

控制器收到新命令后会进行 finite、hard clamp 和 smooth apply，并发布本任务代际的 `is_hover_stable=false`。Scheduler 只有看到该 false 后才接受后续 true，避免上一任务状态误判。

## ResolutionTrace

默认追加到：

```text
~/.ros/candidate_resolution_trace.jsonl
```

记录 Candidate、configuration ID、snapshot source/receive timestamp、center/scale/timing 来源、correction、fallback warning和 rejection reason。它与 Executable LFS 八元组分离，不写入或覆盖历史 `experiments/results`。

## 当前控制边界

- 显式 `T` 在动态可行时保持不变；style 只改变 controller profile。
- `T=auto` 使用 C0-F frozen factor：smooth/normal/aggressive 为
  `1.30/1.15/1.10`，且始终不小于 `T_min`。
- Controller 先做 finite check 和 hard clamp，再原子应用 profile；当前
  `smoothing_alpha=1.0`，不做跨周期渐变。
- `ladrc_acceleration` 模式中，LADRC `update()` 输出已接入 PX4
  acceleration setpoint；默认 `px4_position` 仍是对照基线。
- task-dependent adaptation 尚未启用；profile velocity/jerk limit 尚未成为
  controller runtime enforcement。
- Minimum-Jerk、LADRC 与 IAPF 的数学未改变。Lineup/Free 只属于 legacy。
