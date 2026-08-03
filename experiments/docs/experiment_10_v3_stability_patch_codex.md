# 实验 10 补丁任务：修正稳定判定、Stage Timeout 与结果统计

## 1. 目标

基于 `exp/10-system-8uav` 当前 v2 实验结果，修正以下问题：

- Task B、Task E 大量出现 `stage_timeout`；
- 当前稳定判定存在路径依赖：曾进入 `<0.35 m` 的 UAV 可以在 0.35–0.45 m 区间确认稳定，而始终停在该区间的 UAV 永远无法进入 candidate；
- `stage_timeout` 不能区分命令、参考轨迹和稳定收敛阶段；
- 多次 `stable_confirmed` 被错误视为冲突；
- 失败 trial 的缺失时间被写成 0，污染均值；
- 需要用新标准重分析已有数据，并补充一批可用于论文的实验。

保留现有批次和原始数据，不覆盖：

```text
exp10-formal-v2-gated-20260803
```

---

## 2. 修正稳定判定

将稳定状态机改为 mission 独立状态机。收到新 mission 后，必须清空上一 mission 的 candidate、confirmed 和 arrival 状态。

建议默认阈值：

```text
进入稳定候选：
position_error <= 0.40 m
speed <= 0.30 m/s

退出候选或确认状态：
position_error > 0.50 m
或 speed > 0.40 m/s

连续保持时间：
1.0 s
```

要求：

- candidate 进入标准直接使用统一 acceptance threshold，避免 0.35–0.45 m 区间的路径依赖；
- hysteresis 只用于防止进入 candidate/confirmed 后在边界附近频繁切换；
- 阈值必须写入配置；
- 记录每个 UAV 的 candidate enter、candidate exit、confirmed 和 confirmed exit；
- 保留 final position error、speed 和 settling time，不用放宽阈值掩盖控制异常；
- 对类似 Task A `attempt_0040` 中约 9 m 的误差，必须仍判定为真实执行异常。

---

## 3. 拆分 Stage Timeout

不要继续将所有失败统一记为 `stage_timeout`。

每个 stage 至少区分：

```text
dispatch_timeout
reference_finish_timeout
stabilization_timeout
stage_data_stale
```

推荐流程：

1. 等待全部 UAV command acknowledgment；
2. 等待全部 UAV `is_finished=true`；
3. 从 `all_references_finished_time` 开始等待稳定确认；
4. 所有 UAV confirmed 后结束 stage。

建议超时配置：

```text
dispatch_timeout = 5 s
reference_finish_timeout = requested_duration + 5 s
stabilization_timeout = 30 s
stage_hard_timeout = 上述阶段总和
```

发生失败时保存逐 UAV 诊断：

```text
uav_id
mission_id
command_ack
reference_finished
stability_state
position_error
speed
odom_age
status_age
iapf_active
nearest_neighbor_distance
last_candidate_time
last_confirmed_time
failure_condition
```

---

## 4. 修正 Arrival Spread 与多次 confirmed

### Trajectory finish spread

```text
max(reference_finish_time_per_uav)
-
min(reference_finish_time_per_uav)
```

### Stable arrival spread

使用每个 UAV 在当前 stage 内的“最终有效稳定区间”：

- 构建 `UNSTABLE → CANDIDATE → CONFIRMED` 状态区间；
- 如果出现多次 confirmed，选择 stage 结束时仍有效的最后一个连续 confirmed 区间；
- Arrival time 取该最终 confirmed 区间的起点；
- 不再把多次 confirmed 直接标记为 `conflicting_stable_confirmed`；
- 如果任一必需 UAV 没有最终有效 confirmed，则该 stage 的 stable arrival spread 写为 `NaN`，并记录原因；
- 禁止 arrival time 早于 command dispatch 或 reference start。

---

## 5. 修正统计汇总

当前失败 trial 中缺失的阶段数据不能写成 0。

修改规则：

- 缺失值统一写 `NaN`；
- 主论文连续指标仅统计：
  - `execution_success=true`
  - 所有 stage timing valid
  - 所有 required UAV timestamp 完整
- 所有 attempt 仍用于 readiness、semantic 和 execution success rate；
- timeout trial 单独进入诊断表；
- partial-stage 数据可以保留，但不能混入主表均值；
- 输出 `mean/std`、`median/IQR`、P95 和成功次数；
- 异常点只标记，不删除。

重点修正：

```text
mission_timing_summary.csv
paper_task_table.csv
stage_phase_timing.csv
uav_arrival_summary.csv
outlier_summary.csv
```

---

## 6. 重新分析已有 v2 数据

在原批次下新增只读目录：

```text
exp10-formal-v2-gated-20260803/reanalysis_v3/
```

使用新分析逻辑重新计算：

- corrected trajectory finish spread；
- corrected stable arrival spread；
- reference execution time；
- stabilization delay；
- stage failure classification；
- 每个 timeout 的最慢 UAV 和具体原因；
- 不使用 0 填充缺失时间；
- Task A `attempt_0040`、Task B 和 Task E 的 timeout 逐项诊断。

如果现有日志无法恢复某项指标，写明：

```text
not_recoverable_from_existing_logs
```

不得推测或插值。

---

## 7. 补充实验

由于稳定判定语义发生变化，新的正式结果不能与旧批次直接合并。

创建新批次，例如：

```text
exp10-formal-v3-<YYYYMMDD>
```

### 正式端到端实验

- Task A–E 全部重新运行；
- 每个 Task 至少获得 10 次进入任务执行阶段的 trial；
- 使用同一冻结代码、配置、prompt、LLM 和 parser；
- 保留所有 readiness、LLM 和执行失败；
- 主论文使用 v3 结果。

### 执行层诊断实验

额外增加一个 execution-only replay：

- 使用已验证并冻结的 LFS，不实时调用 LLM；
- 重点重跑 Task B 和 Task E；
- 每个 Task 至少 10 次；
- 用于判断 stage timeout 是否来自控制/稳定判定，而不是 LLM 输出变化；
- 该结果作为诊断或补充实验，不能替代端到端结果。

---

## 8. 验收标准

1. 稳定判定不再存在 0.35–0.45 m 区间路径依赖；
2. 新 mission 会完全重置上一 mission 的稳定状态；
3. timeout 能区分 dispatch、reference finish 和 stabilization；
4. timeout 日志能定位到具体 UAV 和失败条件；
5. 多次 confirmed 可被正确解析为状态区间；
6. Arrival spread 不出现负值、旧状态或伪冲突；
7. 缺失时间使用 `NaN`，不再用 0 污染统计；
8. 原 v2 批次完成 reanalysis_v3；
9. A–E 完成新的 v3 正式批次；
10. Task B、Task E 完成 execution-only replay；
11. 生成更新后的 CSV、图表和 completion report；
12. 不修改 LFS、assignment、Minimum Jerk、LADRC 或 IAPF 核心算法，除稳定状态机和必要日志外。
