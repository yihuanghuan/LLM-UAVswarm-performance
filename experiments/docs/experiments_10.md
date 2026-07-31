# 实验 10：8 机 Gazebo 端到端受控评估开发任务

## 1. 任务目标

基于当前仓库已有的 LFS、编队几何生成、安全感知目标分配、Minimum Jerk、semantic-conditioned LADRC、velocity-aware hysteretic IAPF 和 PX4/Gazebo 多机链路，补齐“实验 10：系统级 8 机 Gazebo controlled evaluation”所需的运行、记录、汇总和绘图工具。

该实验用于验证完整系统在 8 机规模下是否具备：

- 自然语言到多机执行的端到端可行性；
- 单任务、串行任务、并行分组任务和混合任务的组合执行能力；
- 多机同步到达与闭环阶段推进能力；
- 高密度变阵中的安全性和 IAPF 恢复能力；
- 8 机 PX4 SITL + Gazebo 条件下的实时性和可重复性。

本任务重点是把现有 8 机演示升级为可重复、可量化、可用于论文的 controlled evaluation。不要重新实现已有核心算法。

---

## 2. 实验固定配置

完整系统默认使用：

- `assignment_mode = safety_aware`
- `avoidance_mode = iapf_dual`
- `iapf_escape_mode = id_order`
- Minimum Jerk 轨迹
- semantic-conditioned LADRC 开启
- `safety_factor = 1.0`
- 控制频率采用当前项目默认值

每类任务默认重复 5 次，最低支持 3 次。每次 trial 必须保留成功和失败结果，不允许自动删除失败 trial。

---

## 3. 五类 8 机任务

请为以下五类任务提供固定自然语言指令模板、对应配置和可重复运行入口。

### Task A：单一全体编队

8 架无人机变换为统一圆形编队，用于验证基础端到端执行、同步到达和低冲突场景性能。

建议配置：

- 8 架无人机全部参与
- Circle
- normal
- duration 约 8–10 s
- radius 约 4 m

### Task B：串行变阵

同一组 8 架无人机先组成直线，再组成圆形。第二阶段必须在第一阶段全部无人机稳定悬停后开始。

建议配置：

- Stage 1：Line，smooth，约 10 s
- Stage 2：Circle，aggressive，约 8 s

### Task C：并行分组编队

将 8 架无人机分为两个不重叠集合并行执行：

- UAV1–5：Circle
- UAV6–8：Line

两个并行任务使用相同 duration。验证 grouped assignment、跨组安全评估和同步执行。

### Task D：高密度聚拢

8 架无人机聚拢为较密集圆形，主动触发 IAPF。

目标圆半径不要小于约 2.2 m，避免最终目标本身长期违反当前 IAPF 退出距离。该任务重点观察 IAPF 激活、滞回退出、轨迹恢复和最小机间距。

### Task E：组合式长序列

设计一个包含并行和串行逻辑的三阶段任务：

1. UAV1–4 与 UAV5–8 分成两个编队并行移动；
2. 两组并行交换区域，duration 保持一致；
3. 全部 8 架无人机合并为一个统一编队。

用于验证长序列 LFS、多阶段闭环调度、parallel-to-sequential 切换和完整系统稳定性。

---

## 4. 每次 trial 的标准流程

请实现统一 trial runner，基本流程如下：

1. 记录 experiment ID、task type、trial ID 和配置；
2. 启动或确认 8 机 PX4 SITL、Gazebo、控制节点和调度器已经就绪；
3. 等待所有 UAV 进入 Offboard 并稳定悬停；
4. 启动 rosbag 和系统资源记录；
5. 输入固定自然语言指令；
6. 执行完整 LLM → LFS → assignment → trajectory → control 链路；
7. 等待全部阶段完成或达到 timeout；
8. 结束后继续记录 3–5 s；
9. 停止记录并生成 trial manifest；
10. 标记 success/failure 和 failure reason。

脚本应支持手动启动外部仿真环境，也可提供半自动模式。不要强制把 PX4/Gazebo 启停逻辑写死在一个脚本里。

---

## 5. 需要采集的话题

更新 rosbag 采集脚本，至少记录：

```text
/uav[0-9]+/odom
/uav[0-9]+/status
/uav[0-9]+/trajectory_metrics
/uav[0-9]+/control_adaptation
/uav[0-9]+/iapf_debug
/uav[0-9]+/swarm_command
/px4_[0-9]+/fmu/out/vehicle_odometry
/clock
```

同时兼容单机 PX4 instance 0 的 `/fmu/out/vehicle_odometry`，但实验 10 主要使用 8 机多实例话题。

---

## 6. Trial manifest

每个 trial 生成一份 JSON 或 YAML manifest，至少包含：

```text
experiment_id
task_type
trial_id
command_text
llm_model
assignment_mode
avoidance_mode
iapf_escape_mode
iapf_parameters
motion_styles
start_time
end_time
timeout
semantic_success
execution_success
safety_success
overall_success
failure_reason
rosbag_path
```

---

## 7. 需要计算的指标

### 7.1 认知与调度层

- LLM parsing success
- retry count
- parsing latency
- LFS validation/compilation latency
- assignment compute time
- command dispatch skew
- planned XY crossings
- planned proximity crossings
- planned minimum distance
- local swap iterations

如果当前调度器只把部分指标打印到终端，请增加结构化日志，不要依赖人工解析终端文本。

### 7.2 轨迹与控制层

- per-stage completion time
- total execution time
- total end-to-end time
- mission completion overhead
- final position error
- arrival time error
- arrival spread：最晚与最早 UAV 到达时间差
- tracking RMSE
- peak velocity
- peak acceleration
- semantic gain multiplier

需要区分两种误差：

1. `controller_tracking_rmse`：actual position vs modulated reference；
2. `avoidance_deviation`：modulated reference vs nominal Minimum Jerk reference。

不要把 IAPF 主动偏移直接算成控制器跟踪误差。

### 7.3 安全层

- minimum inter-agent distance
- violation count 和 violation duration，阈值采用当前 violation distance
- near-miss duration，阈值采用当前 IAPF enter distance
- IAPF activation count
- IAPF active duration
- hysteresis switching count
- closing speed at activation
- maximum active neighbor count
- position/acceleration saturation ratio
- stale-neighbor ratio
- safety completion rate

### 7.4 系统实时性

- Gazebo RTF：mean、minimum、P5
- CPU：mean、P95、max
- memory：mean、max
- control-loop effective frequency
- timeout rate

---

## 8. 成功判定

分别计算：

### Semantic success

- LLM 输出可解析；
- schema 和 semantic validation 通过；
- 全部任务成功编译。

### Execution success

- 所有预期 UAV 收到命令；
- 所有阶段在 timeout 内完成；
- 所有 UAV 最终进入稳定状态；
- 串行和并行阶段顺序正确。

### Safety success

- 无 Gazebo 碰撞；
- 无持续性 violation；
- 最小机间距满足实验定义。

### Overall success

```text
overall_success =
semantic_success AND execution_success AND safety_success
```

失败时记录明确的 `failure_reason`，例如：

- `llm_parse_failure`
- `schema_failure`
- `assignment_failure`
- `dispatch_failure`
- `stage_timeout`
- `tracking_failure`
- `safety_violation`
- `gazebo_realtime_failure`
- `unknown`

---

## 9. 建议新增或扩展的脚本

请根据当前 `experiments/` 工具链，优先复用已有脚本，只补缺口。

建议包含：

```text
experiments/system_8uav/
├── commands/
│   ├── task_a_simple.json
│   ├── task_b_sequential.json
│   ├── task_c_grouped.json
│   ├── task_d_dense.json
│   └── task_e_mixed.json
├── configs/
│   └── full_system.yaml
├── scripts/
│   ├── run_trial.py
│   ├── build_trial_manifest.py
│   ├── summarize_system_trials.py
│   ├── analyze_system_timeline.py
│   ├── analyze_iapf_debug.py
│   ├── analyze_tracking_references.py
│   └── monitor_system_resources.py
├── logs/
├── results/
└── figures/
```

允许调整目录，但功能必须覆盖。

---

## 10. 输出结果

至少生成：

### CSV

```text
system_trial_summary.csv
stage_timeline.csv
uav_arrival_summary.csv
tracking_summary.csv
safety_summary.csv
resource_summary.csv
```

`system_trial_summary.csv` 每行对应一个 trial，至少包含：

```text
experiment_id
task_type
trial_id
overall_success
semantic_success
execution_success
safety_success
total_latency
completion_time
tracking_rmse
arrival_spread
min_distance
iapf_active_duration
violation_count
mean_rtf
p95_cpu
failure_reason
```

### 图

至少生成 PNG 和 PDF：

- 各任务代表性 3D 轨迹；
- mixed task 多阶段 timeline；
- dense task 最小机间距 + IAPF 状态图；
- 五类任务 completion time 箱线图；
- 五类任务 tracking RMSE 箱线图；
- 五类任务 minimum distance 箱线图；
- 五类任务 arrival spread 箱线图。

### 表

输出五类任务的 `mean ± std` 汇总，并保留成功次数，例如 `5/5`。

---

## 11. 预期趋势

代码和文档中不要写死最终实验结果，只说明预期趋势：

- Task A 成功率最高、IAPF 激活最少；
- Task B 正确完成闭环阶段切换；
- Task C 两组近似同时开始并保持组归属；
- Task D 明显触发 IAPF，最小距离保持在 violation threshold 以上，并在末端退出避障；
- Task E 负载最高，但仍应保持较高任务完成率和可接受的 RTF；
- 随任务复杂度增加，completion time、IAPF 活跃时间和调度负担可能增加。

---

## 12. 工程约束

- 不重写现有 LFS、assignment、Minimum Jerk、LADRC 或 IAPF 核心算法；
- 优先复用现有消息和实验脚本；
- 新增脚本使用 Python 3，并提供 argparse；
- 结果路径和 CSV 字段固定；
- 所有 trial 可重复运行；
- 不允许只依赖终端输出；
- 不允许只生成视频而没有结构化数据；
- 对缺失话题或不完整 trial 给出清晰错误，不要静默跳过；
- 更新 `experiments/README.md`，说明环境准备、运行顺序、参数和结果文件；
- 新增必要的单元测试或最小样例数据；
- 不自动提交大体积 rosbag、Gazebo 日志或生成图片到 Git。

---

## 13. 验收标准

完成后应满足：

1. 五类任务均有固定指令和配置；
2. 能对任一任务执行 1 次 dry run；
3. 能批量组织每类 3–5 次 trial；
4. rosbag 包含完整的 swarm、PX4、trajectory、control 和 IAPF 数据；
5. 每个 trial 都生成 manifest；
6. 能自动判定 semantic/execution/safety/overall success；
7. 能生成系统级 summary CSV；
8. 能生成 timeline、3D trajectory、安全距离和箱线图；
9. `mean ± std` 和成功次数可直接用于论文表格；
10. 更新 README 并提供完整示例命令；
11. 不破坏当前单机和多机控制链路；
12. 运行现有测试和新增测试，记录验证结果。
