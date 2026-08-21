# Command-to-control system v1 冻结验收报告

日期：2026-08-14
结论：**PASS，可以冻结；没有发现新的 P0 blocker。**

## 1. Single-task feasibility gate

修复前，`resolve_execution_task()` 的最终 gate 为：

```python
if final_metrics.min_distance + 1e-9 < safety.d_plan:
    reject
```

它错误地把期望规划裕度 `d_plan` 当作第二个硬约束。现在 single-task 与 Parallel 完全统一：

- `d_min < d_hard`：reject，并返回 typed hard-safety diagnostics；
- `d_hard <= d_min < d_plan`：accept，保留正的 `J_margin`，trace 标记 `residual_planning_risk=true` 并记录 `margin_intrusion_m` warning；
- `d_min >= d_plan`：accept，`J_margin=0`，`residual_planning_risk=false`。

Allocator 的词典序目标 `(N_hard, J_margin, J_distance)`、`d_hard`、`d_plan`、group-local 搜索均未修改。运行期 residual risk 仍交由既有 IAPF。

修改文件：

- `location_allocate/location_allocate/late_resolution.py`
- `location_allocate/test/test_late_resolution.py`
- `docs/safety_aware_topology_assignment.md`

新增 single-task 边界测试：

1. `d_min=0.5 < d_hard=1.0`：reject；
2. `d_hard=1.0 <= d_min=1.5 < d_plan=2.0`：accept，`J_margin>0`；
3. `d_min>=d_plan`：accept，`J_margin=0`。

## 2. 自动回归

- 相关完整 Python suite：153 passed；
- `lfs_policy` functional tests：11 passed；
- single/parallel allocator 定向 suite：30 passed；
- colcon build：`uav_swarm_interfaces`、`ladrc_controller`、`lfs_policy`、`location_allocate` 全部成功；
- colcon test：191 tests，0 errors，0 failures，1 skipped；
- `git diff --check`：通过。

Colcon 在工作区发现 `llm_env` 内 NumPy Cython 示例时会输出缺少 Cython 的 package-identification 告警；所选 4 个 ROS 包仍全部构建和测试成功，该告警不属于产品包失败。

本轮未修改 startup/auto takeoff、PX4 position、LADRC acceleration、Execution Profile、Minimum Jerk 或 IAPF 实现。启动、控制接口、IAPF、Minimum Jerk 的已有 C++ 回归均通过；本次 E2E 也实际覆盖了 feedback-driven startup、自动起飞和 `px4_position` baseline。

## 3. 真实 8 UAV Parallel E2E

使用此前失败过的英文指令，完成了一次新的独立 Gazebo/PX4 cold start：两组 4 机 Line 并行执行，全部稳定后，8 机顺序进入 Circle。

### Pipeline 与规划结果

- READY：8/8；全部 armed、OFFBOARD、system_ready，0 failsafe；
- Candidate：合法；节点为 synchronized Parallel(task 1 + task 2)，随后 sequential task 3；
- allocator：`lexicographic-safety-aware-v2`；
- assignment：`[1, 3, 0, 2, 5, 7, 4, 6]`；没有跨 group 分配；
- `d_hard = 1.0 m`；
- `d_plan = 2.0 m`；
- predicted minimum distance：`1.896928 m`；
- `N_hard = 0`；
- `J_margin = 0.011595`；
- residual planning risk：`true`；
- margin intrusion：`0.103072 m`；
- late resolution：accepted，没有因 `d_min < d_plan` 拒绝。

### Dispatch、执行与安全

- UAV 1–4 各收到 task 1 command；UAV 5–8 各收到 task 2 command；
- 随后 UAV 1–8 各收到 task 3 command；每机共 2 条 execution command；
- parallel 首批 command 到 sequential task 3 dispatch：`12.231 s`，证明两个并行组完成稳定汇合后 scheduler 正常前进；
- 实测全程最小机间距：`1.842524 m`（UAV 6/8），高于 `d_hard=1.0 m`；
- parallel 阶段实测最小距离：`1.842524 m`；sequential 阶段：`1.916579 m`；
- IAPF：本次 10,216 个 mission debug samples 中 `iapf_active=0`，即未介入；观测最近邻最小值约 `1.848028 m`，未进入现有 IAPF 触发区；
- scheduler 报告 Candidate mission 1 completed；
- 最终 8/8 `STABILITY_CONFIRMED`，全部仍 armed + OFFBOARD、0 failsafe；
- 最终 position error 范围：`0.1881–0.2196 m`；position-derived speed：`0.0392–0.0664 m/s`。

## 4. 证据与可复现性

测试时 HEAD 为 `8a81b9062cf4b83e352da885a73f41bea693e166`，被测三文件 source patch SHA-256 为 `71a9f194cadc75018a9cf832684e1ccd0bc7928fdd3d2f24479888733e10bce1`。colcon 使用 symlink-install，因此 E2E 运行的是本报告所述待提交源代码。

保留证据：

- `parallel_e2e_trial_1/rosbag/`：完整 rosbag；
- `parallel_e2e_trial_1/manifest.json`：指令与 runner 结果；
- `parallel_e2e_trial_1/readiness.log`：8/8 READY 快照；
- `parallel_e2e_trial_1/scheduler.log`：Candidate 与 mission completion；
- `parallel_e2e_trial_1/resolution_trace.jsonl`：assignment、阈值、J_margin 和 residual-risk trace；
- `acceptance_summary.json`：bag 独立分析摘要。

原始 rosbag 和 runtime logs 保留在实验目录中，不覆盖任何历史实验数据；冻结提交仅纳入代码、测试、文档和精简文本证据，不纳入大体积数据库。
