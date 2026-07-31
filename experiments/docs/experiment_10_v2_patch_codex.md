# 实验 10 补丁任务：扩展重复试验与修正时间/同步指标

## 1. 任务目标

在保留现有正式批次 `exp10-formal-20260731` 不变的前提下，对实验 10 的运行和分析工具做一次补丁更新，并建立新的 `exp10-formal-v2` 批次。

本次补丁主要解决：

- 相同任务多次运行时完成时间方差较大，无法判断轨迹执行和稳定等待各自贡献；
- `readiness_timeout` 与算法执行失败混在同一成功率中；
- 当前 Arrival spread 可能读取到命令下发前的旧稳定状态；
- 稳定判定在阈值附近可能反复重置；
- 每类任务只有 5 次，难以判断时间稳定性和极端误差点；
- Task E 的复杂指令解析稳定性不足。

不要覆盖、删除或修改原批次结果。所有旧失败必须保留。

---

## 2. 新实验批次

新增一个独立批次，例如：

```text
exp10-formal-v2-<YYYYMMDD>
```

五个 Task 均重新运行，默认每个 Task 获得 **10 次成功进入任务执行阶段的 trial**。

执行规则：

1. 每次启动均记为一个 `attempt`；
2. `readiness_timeout` 仍然保留并计入 readiness 可靠性；
3. readiness 失败后允许补跑，直到该 Task 获得 10 次实际执行任务的 trial；
4. LLM 解析失败也必须保留，不能删除；
5. 所有补跑必须有独立 attempt ID，并记录 `replacement_for`；
6. 不允许用成功补跑覆盖原始失败；
7. A–E 五类 Task 在同一冻结代码、配置、模型和分析版本下运行。

同一 Task 的自然语言 prompt 保持完全相同。Task 之间使用各自固定 prompt。

---

## 3. 拆分阶段时间

当前 `stage completion_time` 混合了规划、轨迹执行和稳定等待。请增加明确的状态和时间戳。

每个 stage 至少记录：

```text
stage_start_time
assignment_complete_time
first_command_dispatch_time
last_command_dispatch_time
reference_start_time
reference_finish_time_per_uav
all_references_finished_time
stable_candidate_time_per_uav
stable_confirmed_time_per_uav
all_uavs_stable_time
stage_end_time
```

生成以下指标：

```text
planning_time
dispatch_time
reference_execution_time
trajectory_finish_spread
stabilization_delay
stable_hold_time
stable_arrival_spread
stage_wall_time
mission_wall_time
```

推荐定义：

```text
planning_time =
assignment_complete_time - stage_start_time

dispatch_time =
last_command_dispatch_time - assignment_complete_time

reference_execution_time =
all_references_finished_time - first_command_dispatch_time

stabilization_delay =
all_uavs_stable_time - all_references_finished_time

stage_wall_time =
stage_end_time - stage_start_time
```

不要再把 `stage_wall_time` 直接称为轨迹跟踪时间。

如果旧批次 CSV/rosbag 已包含足够的 `mission_id`、dispatch、`is_finished`、odom 和 stable 状态，则先对旧批次重新分析；缺失关键时间点时只重跑新批次，不伪造旧指标。

---

## 4. 优化稳定判定

稳定判定改为按 mission 独立维护状态，收到新 mission 后必须清空上一 mission 的稳定状态。

推荐采用可配置的滞回判定：

```text
进入稳定候选：
position_error < 0.35 m
speed < 0.30 m/s

退出稳定候选：
position_error > 0.45 m
或 speed > 0.40 m/s

连续保持：
1.0 s
```

要求：

- 阈值写入配置，不要硬编码；
- 同一批次所有 Task 使用相同阈值；
- 记录每次 stable candidate 进入、退出和确认事件；
- 记录导致阶段延迟最大的 UAV；
- 不要为了提高成功率随意放宽阈值；
- final position error、settling time 和 stable hold time 仍作为独立指标报告。

阶段推进仍以所有相关 UAV `stable_confirmed` 为准。

---

## 5. 修正 Arrival spread

当前 Arrival spread 需要重新定义和计算。

### 5.1 Stable arrival spread

对同一 stage：

```text
stable_arrival_spread =
max(stable_confirmed_time_per_uav)
-
min(stable_confirmed_time_per_uav)
```

只接受满足以下条件的状态：

- `mission_id` 与当前命令一致；
- timestamp 不早于该 UAV 的 command dispatch；
- 新 mission 已重置上一 mission 的 stable 状态；
- 必须经过当前 mission 的 stable candidate 和 hold；
- 不允许沿用命令切换前的 `is_hover_stable=true`。

### 5.2 Trajectory finish spread

另外新增：

```text
trajectory_finish_spread =
max(reference_finish_time_per_uav)
-
min(reference_finish_time_per_uav)
```

论文中分别报告：

- 参考轨迹完成同步性；
- 最终稳定确认同步性。

检查并拒绝：

- arrival time 早于 dispatch time；
- negative completion time；
- mission_id 缺失或不匹配；
- 同一 UAV 同一 mission 多个冲突到达事件。

---



## 6. LLM 解析控制与 Task E

同一 Task 的所有重复 trial 必须使用相同：

- prompt；
- system prompt；
- LLM model；
- temperature/top_p/seed 等推理参数；
- schema；
- retry policy。

API 支持 seed 时固定 seed 并记录；不支持时在报告中明确模型输出具有随机性。

每次 LLM 调用必须保存：

```text
attempt_index
raw_response
latency
valid_json
schema_valid
semantic_valid
repair_applied
error_type
```

针对 Task E：

- 保持任务语义和五个子任务配置不变；
- 可增强 structured output、JSON 提取和有限 repair；
- repair 只能修复包裹文本、代码块或明显格式问题，不能改写任务语义；
- 设置明确的单次请求和总解析 timeout；
- 解析失败后保留原始输出；
- 新解析流程冻结后，A–E 全部使用同一 parser 版本重新测试。

---

## 7. 时间稳定性与异常值分析

相同 prompt 不保证仿真时间完全一致，因此不要只报告 mean ± std。

每个 Task 至少报告：

```text
count
mean
std
median
IQR
min
max
P90
P95
coefficient_of_variation
```

对以下指标进行统计：

```text
planning_time
reference_execution_time
stabilization_delay
stage_wall_time
mission_wall_time
trajectory_finish_spread
stable_arrival_spread
tracking_rmse
minimum_inter_agent_distance
mean_rtf
```

异常值使用预先固定的方法标记，例如：

```text
lower = Q1 - 1.5 * IQR
upper = Q3 + 1.5 * IQR
```

要求：

- 异常 trial 仍保留在主结果中；
- 额外输出 outlier 标记和原因分析；
- 不得仅因数值较大而删除；
- 区分极端值来自 planning、tracking、stabilization、IAPF、RTF 或其他阶段。

---

## 8. 实验顺序

采用固定随机种子生成 block-randomized 运行顺序，避免按 A→B→C→D→E 连续运行造成温度、资源或启动顺序偏差。

保存：

```text
formal_batch_plan.json
```

至少记录：

```text
attempt_id
task_type
target_execution_index
run_order
replacement_for
randomization_seed
```

---

## 9. 输出文件

在新批次下生成：

```text
summaries/
├── attempt_summary.csv
├── readiness_summary.csv
├── semantic_summary.csv
├── stage_phase_timing.csv
├── mission_timing_summary.csv
├── uav_arrival_summary.csv
├── tracking_summary.csv
├── safety_summary.csv
├── resource_summary.csv
├── outlier_summary.csv
├── paper_task_table.csv
└── completion_report.md
```

`stage_phase_timing.csv` 至少包含：

```text
task_type
attempt_id
trial_id
stage_id
planning_time
dispatch_time
reference_execution_time
trajectory_finish_spread
stabilization_delay
stable_hold_time
stable_arrival_spread
stage_wall_time
slowest_uav_id
```

`attempt_summary.csv` 必须包含所有 attempt，包括 readiness 和 LLM 失败。

---

## 10. 图表

至少生成 PDF 和 PNG：

- 每个 Task 的 mission wall time 箱线图；
- reference execution time 与 stabilization delay 的堆叠或并列图；
- trajectory finish spread 箱线图；
- stable arrival spread 箱线图；
- readiness failure 分类图；
- LLM parsing success 与 latency 图；
- outlier trial 分阶段时间分解图；
- Task D 的最小距离与 IAPF 状态图；
- Task E 的成功 trial 多阶段 timeline。

---

## 11. 旧批次处理

旧批次 `exp10-formal-20260731` 必须保持原样。

新增一个只读 reanalysis 输出目录，例如：

```text
exp10-formal-20260731/reanalysis_v2/
```

仅在旧数据足够时重新计算：

- trajectory finish time；
- stabilization delay；
- corrected stable arrival spread；
- trajectory finish spread；
- outlier classification。

如果旧数据不足，明确写 `not_recoverable_from_existing_logs`，不要用推测值填充。

旧批次和 v2 批次不能直接混合计算 mean/std，因为稳定判定和 parser 版本已变化。可以在报告中并列比较，但主论文结果使用冻结后的 v2 批次。

---

## 12. 验收标准

完成后应满足：

1. 原批次未被覆盖或删除；
2. 五个 Task 均在 v2 批次获得 10 次实际执行样本；
3. 所有 readiness 和 LLM 失败 attempt 被完整保留；
4. 能区分 reference execution、stabilization 和 stable hold；
5. Arrival spread 不再出现早于 dispatch 或负 completion time；
6. 稳定判定具有 mission reset 和进入/退出滞回；
7. readiness 失败能定位到具体 UAV 和条件；
8. 同一 Task 使用完全相同 prompt 和推理配置；
9. 统计同时包含 mean/std、median/IQR、P95 和 CV；
10. 异常值只标记不删除；
11. 旧批次能重分析的指标已重新生成；
12. 新批次能自动生成完整 CSV、图表和 completion report；
13. 现有 LFS、assignment、IAPF 和控制测试继续通过；
14. 不修改核心算法，除稳定状态机、日志和解析可靠性所需的最小补丁。
