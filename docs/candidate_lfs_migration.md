# Candidate LFS 运行、接口与迁移

## 当前 main 兼容行为

默认 `location_allocate` main、旧 LLM v1 prompt、`FormationGenerator`、`/uavN/swarm_command` 和既有实验脚本保持可用。新 Candidate 路径没有生产参数默认值，不会被默认 main 偷偷启用。

旧消息到达控制器时：

- target 和合法 duration 继续生效；
- safety factor 被约束为至少 1；
- motion style 只记录，不再计算 semantic LADRC gain；
- LADRC 使用 `ladrc_params.yaml` baseline/normal 值，并输出 legacy fallback warning；
- 活跃的新 Execution Profile 任务优先，旧消息会被忽略。

## 新接口

`/uavN/execution_command` 使用 `uav_swarm_interfaces/msg/UAVExecutionCommand`：

```text
Header header
uint32 mission_id
uint32 task_id
uint32 group_id
uint8 uav_id
Point target_pos
ExecutionProfile profile
```

`ExecutionProfile.duration` 是唯一 duration。外层消息没有第二份 duration。Profile 还包含 style、三轴 `omega_c/omega_o`、velocity/acceleration/jerk limits、IAPF enter/exit/repulsion soft 参数、style/task provenance gain 和 `configuration_id`。`d_hard` 不在消息中，继续由控制器固定配置定义 violation。

## 构建与测试

```bash
cd ~/learning/LLM_swarm_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install \
  --packages-select uav_swarm_interfaces location_allocate ladrc_controller
source install/setup.bash
colcon test --packages-select uav_swarm_interfaces location_allocate ladrc_controller
colcon test-result --all --verbose
```

虚拟环境运行 Python 单测时，需要保留 ROS 的 local dist-packages：

```bash
source llm_env/bin/activate
source /opt/ros/humble/setup.bash
source install/setup.bash
export PYTHONPATH="$PWD/src/LLM-UAVswarm-performance/location_allocate:$PWD/install/uav_swarm_interfaces/local/lib/python3.10/dist-packages:/opt/ros/humble/local/lib/python3.10/dist-packages"
```

## 启用 Candidate 路径前的必要步骤

1. 复制并填写 `location_allocate/config/lfs_policy.template.yaml` 中全部相关 null；评审并分配唯一 `configuration_id`。
2. 由 composition root 显式构造 `ScalePolicy`、`TimingPolicy`、allocator factory、safety resolver 和 `ExecutionProfilePolicy`。任何缺项都应 fail closed。
3. 为调度节点显式设置正数 `candidate_state_timeout` 和非负 `candidate_snapshot_skew`；未设置时 snapshot manager 不启用。
4. 为控制器配置所有 execution-profile hard clamps 和 smoothing alpha，然后显式设置 `enable_execution_profiles:=true`。缺少 clamps 时新 profile 被拒绝。
5. Candidate Mission 先通过 early validation 与 `compile_candidate_mission()`；每个即将执行的 task/group 再调用 late-resolution API。parallel group 必须传入经评审的 `group_d_plan` 聚合结果。

在 provisional 参数获确认前，不应把这些步骤固化进默认 launch。

## 迁移保护

- 不删除或重命名旧 topic/message/API；旧 LFS eager path 仍有回归测试。
- `Lineup`/`Free` 的 legacy geometry 保持历史行为；Candidate v2 明确拒绝并等待确认。
- 新增代码和测试不写 `experiments/results`。历史结果目录不作为测试输出目录，不执行清理或覆盖。
- ResolutionTrace 与 Executable LFS 分离；实验运行方应以新的 run ID 追加保存 trace，不回写历史 run。
- 新旧命令优先级由控制器执行，而不是依赖 DDS 到达顺序。

## 验收覆盖

- Candidate → Executable → Execution Profile → composite message；
- early/runtime validation 分层、stale/missing/future/skew state；
- participant-only centroid 与 relative offset；
- Unit Geometry → Scale Resolution → Final Geometry；Triangle/Polygon 真实几何；
- qualitative r 安全下限 `d_plan(s)/delta_F` 和 AABB 冲突失败；
- explicit/auto T × smooth/normal/aggressive；不可行 explicit T 上调并留 trace；
- `T_plan`/`T_exec` 差异只触发一次复评；
- parallel independent/synchronized duration 和完成后 hover 轨迹；
- invalid/NaN/Inf/boundary inputs；
- legacy input、消息优先级、profile finite/clamp/smooth controller guard；
- 原 allocator、IAPF 和 legacy LFS 回归测试。
