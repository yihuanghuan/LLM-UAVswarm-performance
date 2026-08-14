# Parallel feasibility gate 修复补充报告

日期：2026-08-14
范围：Parallel late-resolution / Safety-aware Allocator

## 确认结果

修复前的 Parallel 最终 gate 确实将 `d_plan` 硬约束化：

`final_metrics.min_distance < group_d_plan → reject`

这与冻结语义不一致。Allocator 的目标函数原本已经正确地区分：

- `N_hard` 仅统计 `d_min < d_hard`；
- `J_margin` 对 `d_min < d_plan` 的裕度侵入计分。

错误仅位于 late-resolution 最终 feasibility gate，以及 exhaustive fallback 只采用满足 `d_plan` 的排列。

## 修改后语义

- `d_min < d_hard`：拒绝，typed error 为 `parallel_nominal_trajectory_d_hard_violation`。
- `d_hard <= d_min < d_plan`：允许执行，保留正的 `J_margin`，并记录 residual planning risk。
- `d_min >= d_plan`：允许执行，`J_margin = 0`。

结构化 trace/diagnostics 新增：

- `hard_feasible`
- `planning_margin_met`
- `residual_planning_risk`
- `margin_intrusion_m`
- `d_hard` / `d_plan`
- 原有 `N_hard` / `J_margin` / `J_distance` / `min_3d_distance`

grouped pair-swap 和最多 100,000 个 group-local permutation 的 exhaustive 搜索仍保留。穷举结果现在按冻结的词典序 `(N_hard, J_margin, J_distance)` 选最优解，不跨 group 分配 UAV。

## 冻结 baseline_trial3 回放

- `d_hard = 1.0 m`
- `d_plan = 2.0 m`
- exhaustive checked = 576
- final minimum distance = 1.896689 m
- `N_hard = 0`
- `J_margin = 0.011702`
- margin intrusion = 0.103311 m
- outcome = accepted
- residual planning risk = true

该任务现在会进入执行；剩余规划裕度风险继续由既有 IAPF runtime 层处理。

## 测试

新增 Parallel 最终 gate 边界测试：

1. `d_min = 0.5 < d_hard = 1.0`：reject；
2. `d_hard = 1.0 <= d_min = 1.5 < d_plan = 2.0`：accept，`J_margin > 0`；
3. `d_min = 2.0 >= d_plan = 2.0`：accept，`J_margin = 0`。

定向测试 27 passed；完整相关 Python suite 150 passed。没有修改 startup、LADRC、Minimum Jerk 或 IAPF。
