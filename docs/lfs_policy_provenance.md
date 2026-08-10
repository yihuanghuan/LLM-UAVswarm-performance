# Candidate migration policy value provenance

`migration-main-v1` 是可运行迁移基线，不是论文参数冻结。

| policy parameter | 仓库已有等价值 | migration 值与来源 | 可作为 migration baseline | 后续是否需实验确认 |
|---|---|---|---|---|
| d_hard | 是 | 1.0m，`ladrc_params.yaml:iapf_violation_distance` | 是 | 是 |
| d_plan(s=1) | 是 | 2.0m，allocator `d_safe` | 是 | 是 |
| d_plan(s) | 部分 | `1+(2-1)s`，用户确认的 margin-only 映射 | 是 | 是 |
| IAPF enter/exit(s=1) | 是 | 1.5/1.65m，`ladrc_params.yaml` | 是 | 是 |
| IAPF enter/exit(s) | 部分 | `1+0.5s` / `1+0.65s` | 是 | 是 |
| IAPF repulsion scale | 是 | 1.0，保持现有 gain | 是 | 是 |
| baseline omega_c | 是 | [3,3,3.5]，`ladrc_params.yaml` | 是 | semantic gain 待重做 |
| baseline omega_o | 是 | [10,10,15]，`ladrc_params.yaml` | 是 | semantic gain 待重做 |
| velocity limit | 是 | 5m/s，controller `max_velocity` | 是 | 是 |
| acceleration limit | 是 | 5m/s²，controller x/y 公共保守值 | 是 | 是 |
| allocator sample/weights | 是 | 20Hz、1/10/10/1、1e-3、1e-6，constructor defaults | 是 | 是 |
| nominal spacing | 部分 | 2.0m，继承 allocator 基础 planning distance | 是 | 是 |
| workspace AABB | 否 | x[-15,15], y[-10,35], z[0.5,15]，用户确认 | 是 | 是 |
| state timeout/skew/wait | 否 | 0.5/0.15/2s，用户确认 | 是 | 是 |
| qualitative multipliers | 否 | 0.8/1.0/1.25，用户确认 | 是 | 是 |
| jerk limit | 否 | 10m/s³，用户确认 | 是 | 是 |
| minimum duration | Candidate tests | 0.5s，用户确认 | 是 | 是 |
| auto timing style factors | 否 | 全部1.0，中性 migration 映射 | 是 | 是 |
| final timing recheck | 否 | tolerance=0，T_exec不同即复核一次 | 是 | 可按实验成本调整 |
| parallel d_plan aggregation | 否 | max(d_plan_k)，用户确认 | 是 | 可研究 pairwise policy |
| semantic style/task gain | 历史公式不沿用 | 全部1.0 | 是 | 必须重新设计 |
| profile smoothing alpha | 否 | 1.0，用户确认 | 是 | semantic profile 重做时确认 |

`s` 的 migration 接受范围暂为 `[1,2]`，用于保证 mapping 与 controller hard clamps 有确定覆盖范围。它不改变固定的 `d_hard` violation 定义。
