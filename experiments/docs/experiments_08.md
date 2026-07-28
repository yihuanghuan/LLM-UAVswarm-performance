# 实验 8：IAPF 多无人机安全避障仿真对比（优化版指导文档）

---



# 1. 实验目标与研究问题

本实验应回答以下三个彼此独立的问题。

## 1.1 局部避障是否有效

在相同初始状态、目标映射和任务时限下，IAPF 是否能够：

- 提高全程最小机间距；
- 减少安全阈值违规事件；
- 缩短危险接近持续时间；
- 在不过度偏离名义轨迹的情况下完成任务。

## 1.2 加速度前馈是否有额外作用

当前执行层支持将 IAPF 同时作用于位置参考和加速度参考。需要验证：

- 位置调制与位置+加速度双通道相比，避障响应是否更快；
- 双通道是否造成更大的轨迹偏移、控制输入或振荡；
- 加速度前馈的收益是否在不同场景中一致。

## 1.3 规划层和局部安全层是否互补

需要分别评估：

- safety-aware assignment 单独使用时的贡献；
- IAPF 单独使用时的贡献；
- safety-aware assignment 与 IAPF 联合使用时，是否进一步降低局部避障负担。

---

# 2. 允许支撑的论文结论

实验最终应支撑以下克制表述：

```text
Under identical initial states, target mappings, and mission deadlines,
IAPF-based setpoint modulation increases the minimum inter-agent distance
and reduces close-proximity risk. Acceleration feedforward can shorten the
avoidance response, while safety-aware assignment reduces the frequency and
magnitude of local avoidance interventions.
```

禁止直接声称：

```text
IAPF guarantees collision avoidance.
```

当前 APF/IAPF 属于启发式局部安全方法，没有形式化安全保证。实验结果只能证明其在设定场景和参数范围内的经验效果。

---

# 3. 当前代码基础与需要澄清的实现边界

当前代码已经具备以下基础：

1. `SafetyAwareTopologyAllocator`：
   - 以距离 Hungarian 分配为初始解；
   - 对 Minimum Jerk 名义轨迹采样；
   - 评估 XY 线段交叉、时空接近、最小机间距和安全代价；
   - 通过两两目标交换进行局部优化。
2. 执行层 IAPF：
   - 计算邻机斥力；
   - 将斥力作用到位置 setpoint；
   - 可选将斥力作用到 acceleration setpoint；
   - 加速度前馈有限幅。
3. 已有离线分析脚本可计算：
   - pairwise distance；
   - minimum distance；
   - threshold violation samples；
   - near-miss duration。

但当前实现还不能直接支撑完整实验，原因包括：

- 没有统一的 avoidance mode；
- “Classic APF”和当前 IAPF 没有清晰、可参数化的实现边界；
- 关闭加速度前馈并不等于关闭位置 IAPF；
- 当前固定正 Z 破局分量不能保证两机产生相反的相对运动；
- 极近距离处存在数值奇点和跳过邻机的问题；
- 邻机位置没有 freshness 检查；
- 分组并行任务只评估组内 assignment，没有联合评估跨组轨迹；
- 当前日志不足以计算激活时长、轨迹偏移、恢复时间和限幅比例；
- 当前 violation count 实际是违规采样点数，不是独立违规事件数。

---

# 4. 必须完成的代码优化

## 4.1 增加统一的实验模式参数

在控制节点中新增字符串参数：

```yaml
avoidance_mode: "iapf_dual"
```

允许值：

```text
off
classic_position
iapf_position
iapf_dual
```

含义：

| 模式 | 径向 APF | 破局分量 | 位置调制 | 加速度前馈 |
|---|---:|---:|---:|---:|
| `off` | × | × | × | × |
| `classic_position` | ✓ | × | ✓ | × |
| `iapf_position` | ✓ | ✓ | ✓ | × |
| `iapf_dual` | ✓ | ✓ | ✓ | ✓ |

保留现有 `enable_iapf_accel_feedforward` 参数用于向后兼容，但正式实验应优先使用 `avoidance_mode`。如果两者同时存在，应明确参数优先级并输出警告日志。

在调度层增加：

```yaml
assignment_mode: "safety_aware"
```

允许值：

```text
fixed
distance_hungarian
safety_aware
```

其中：

- `fixed`：严格使用场景文件中指定的 UAV→目标映射；
- `distance_hungarian`：仅最小化总路径长度；
- `safety_aware`：使用现有安全感知 assignment 和局部交换优化。

必须支持在 launch 或实验配置中设置这些参数。

---

## 4.2 正式实现 Classic APF baseline

Classic APF 定义为只有径向斥力：

\[
\mathbf F_{rep}=
K_{rep}
\left(\frac{1}{d}-\frac{1}{R_{safe}}\right)
\frac{1}{d^2}
\hat{\mathbf d}
\]

其要求：

```text
escape component = 0
position modulation = enabled
acceleration feedforward = disabled
```

不要把“关闭全部 IAPF”作为 Classic APF，也不要让 Classic APF 使用当前破局 Z 分量。

---

## 4.3 修正局部极小值破局方向

当前所有无人机都增加同方向正 Z 分量，可能导致两机共同上升，而不是相互分离。

将破局策略参数化：

```yaml
iapf_escape_mode: "id_order"
iapf_escape_gain: 0.05
```

至少支持：

```text
none
fixed_positive_z
id_order
```

推荐正式方法使用 `id_order`：

```cpp
escape_sign = self_uav_id < neighbor_id ? 1.0 : -1.0;
force.z() += escape_sign * magnitude * iapf_escape_gain;
```

要求同一对 UAV 得到相反方向的破局分量，并保持确定性和可重复性。

在 vertical interaction 场景中，额外做一次小型消融：

```text
fixed_positive_z vs id_order
```

该消融可以放在附录或实现报告中，不必纳入全部场景的主实验矩阵。

---

## 4.4 增加数值保护和双通道限幅

当前 APF 在接近零距离时会迅速增大，不能只对 acceleration feedforward 限幅。

新增参数：

```yaml
iapf_distance_epsilon: 0.10

iapf_position_gain: 0.05
iapf_position_limit: 0.50

iapf_accel_gain: 0.30
iapf_accel_limit: 2.00
```

实现要求：

```cpp
d_effective = std::max(distance, iapf_distance_epsilon);
raw_force = compute_apf(d_effective);
position_offset = clamp_norm(iapf_position_gain * raw_force,
                             iapf_position_limit);
acceleration_offset = clamp_norm(iapf_accel_gain * raw_force,
                                 iapf_accel_limit);
```

不要在 `distance <= 0.01` 时直接忽略邻机。除非消息本身无效，否则极近距离应继续产生有限、受控的避障输出。

需要记录位置和加速度通道是否发生限幅。

---

## 4.5 增加邻机状态 freshness 检查

当前邻机 map 不能只保存位置，应改为：

```cpp
struct NeighborState {
    Eigen::Vector3d position;
    rclcpp::Time receive_time;
};
```

新增参数：

```yaml
neighbor_timeout: 0.20
```

只有满足以下条件的邻机才参与 IAPF：

```text
now - receive_time <= neighbor_timeout
```

过期邻机不能继续产生斥力。需要记录：

```text
valid_neighbor_count
stale_neighbor_count
```

---

## 4.6 增加结构化 IAPF 调试消息和 CSV 日志

新增消息，建议命名：

```text
uav_swarm_interfaces/msg/IAPFDebug.msg
```

至少包含：

```text
std_msgs/Header header
uint32 mission_id
uint8 uav_id
string avoidance_mode
uint8 nearest_neighbor_id
float32 nearest_neighbor_distance
bool iapf_active
geometry_msgs/Vector3 raw_repulsion
geometry_msgs/Vector3 position_offset
geometry_msgs/Vector3 acceleration_offset
bool position_saturated
bool acceleration_saturated
uint16 valid_neighbor_count
uint16 stale_neighbor_count
geometry_msgs/Point nominal_reference
geometry_msgs/Point modulated_reference
```

每架无人机发布：

```text
/uav{id}/iapf_debug
```

并支持写入：

```text
experiments/08-iapf/results/<run_id>/iapf_debug.csv
```

日志至少应包含：

```text
timestamp
experiment_id
scenario
method
trial
seed
mission_id
uav_id
nearest_neighbor_id
nearest_neighbor_distance
iapf_active
raw_repulsion_x/y/z
position_offset_x/y/z
acceleration_offset_x/y/z
position_saturated
acceleration_saturated
valid_neighbor_count
stale_neighbor_count
nominal_ref_x/y/z
modulated_ref_x/y/z
```

---

## 4.7 修正 grouped reconfiguration 的联合安全评估

当前并行任务分别进行组内 assignment，无法提前发现不同任务组之间的轨迹冲突。

增加联合评估流程：

```text
收集同一并行任务组中的全部 UAV
→ 生成各任务组目标点
→ 保持“目标只能在所属组内交换”的约束
→ 对所有 UAV 的名义轨迹统一计算跨组最小距离
→ 对每组内目标做受约束 local swap
→ 选择联合安全代价更低的组合
```

不能允许 Group A 的 UAV 被分配到 Group B 的目标点。

建议新增接口：

```python
allocate_grouped(
    groups=[
        {"uav_ids": [...], "initial": [...], "targets": [...]},
        ...
    ],
    duration=...
)
```

联合代价必须计算所有 UAV 对，包括跨组 UAV 对。

---

## 4.8 统一并记录安全阈值体系

不要在 allocator、IAPF、分析脚本和文档中使用含义不明的多个独立阈值。

统一配置：

```yaml
d_collision: <根据 Iris 模型碰撞尺寸计算>
d_violation: 1.00
r_iapf: 1.50
d_assignment: 2.00
```

满足：

```text
d_collision < d_violation < r_iapf < d_assignment
```

含义：

| 参数 | 含义 |
|---|---|
| `d_collision` | 根据模型碰撞半径和安全余量确定的物理碰撞判据 |
| `d_violation` | 严重安全违规阈值 |
| `r_iapf` | IAPF 开始激活的距离 |
| `d_assignment` | 规划层提前规避危险拓扑的距离 |

`d_collision` 不要凭空设定。应读取或检查 Gazebo Iris 模型的 collision geometry，再给出计算依据和最终值。

每次 trial 的实际阈值和控制参数必须写入 `run_metadata.json`，不能只依赖 YAML 文件。

---

## 4.9 增加可复现的场景运行器

新增：

```text
experiments/08-iapf/scripts/run_experiment.py
```

运行器至少支持：

```bash
python3 experiments/08-iapf/scripts/run_experiment.py \
  --scenario head_on \
  --method M3 \
  --trial 1 \
  --seed 42
```

每次 trial 应自动完成：

```text
1. 读取场景配置
2. 记录所有参数和 Git commit
3. 将 UAV 移动到标准初始位置
4. 等待全部 UAV 悬停稳定
5. 清空旧状态和旧日志
6. 启动 rosbag/CSV 记录
7. 下发正式实验任务
8. 等待成功、失败或超时
9. 继续记录固定 post-hold 时间
10. 停止记录并运行离线分析
11. 写入 trial summary
```

不要依赖人工逐条输入自然语言命令完成正式实验。该实验评估的是安全层，不应混入 LLM 输出随机性。

---

# 5. 正式实验方法矩阵

主实验使用以下六种方法。

| ID | Assignment | Local avoidance | 目的 |
|---|---|---|---|
| **M0** | distance Hungarian 或场景固定映射 | off | 完全无局部安全层 |
| **M1** | 与 M0 相同 | Classic APF，position only | 标准 APF baseline |
| **M2** | 与 M0 相同 | IAPF，position only | 验证破局改进本身 |
| **M3** | 与 M0 相同 | IAPF，position + acceleration | 验证双通道前馈 |
| **M4** | safety-aware assignment | off | 单独验证规划层 |
| **M5** | safety-aware assignment | IAPF dual | 完整方法 |

注意：

1. 对 head-on 和 vertical interaction，主实验必须锁定交换映射，因此 M0–M3 使用 `assignment_mode=fixed`。
2. M4、M5 的 assignment 优势主要在 dense formation 和 grouped reconfiguration 中验证。
3. 同一场景内，各方法必须使用完全相同的初始位置、目标点、任务时限和随机种子。
4. 除所比较变量外，LADRC、Minimum Jerk、PX4 和仿真参数保持一致。

---

# 6. 实验场景

场景配置统一放在：

```text
experiments/08-iapf/configs/scenarios/
```

建议文件：

```text
head_on.yaml
dense_feasible.yaml
dense_infeasible.yaml
vertical.yaml
grouped_reconfiguration.yaml
```

每个场景文件应明确：

```text
scenario_name
uav_ids
initial_positions
target_positions 或 formation definition
fixed_assignment
duration
pre_hold_time
post_hold_time
timeout
motion_style
randomization_range
```

---

## 6.1 场景 A：Head-on crossing

### 基本设置

两机同高度交换位置，例如：

```text
UAV1: [-3.0, 0.0, 2.5] → [ 3.0, 0.0, 2.5]
UAV2: [ 3.0, 0.0, 2.5] → [-3.0, 0.0, 2.5]
duration: 5.0 s
assignment_mode: fixed
```

可以增加 4 机十字交叉作为扩展场景，但正式主结果优先保证两机场景可重复。

### 主要测试内容

- IAPF 首次激活时间；
- minimum distance；
- position-only 与 dual-channel 的避障响应差异；
- trajectory deviation；
- recovery time；
- 是否出现对称死锁。

### 关键限制

不能使用 Hungarian 自动重新分配交换目标，否则算法可能通过“不交换目标”绕开碰撞，实验将失去意义。

---

## 6.2 场景 B：Multi-UAV dense formation

使用 8 架无人机从分散状态收缩为圆形编队。

### 可行密集编队

若 `r_iapf=1.5 m`，8 机圆形可先使用：

```text
formation_radius: 2.4 m
```

相邻目标点距离约为：

\[
2R\sin(\pi/8)\approx1.84\text{ m}
\]

目标阵型本身不违反 IAPF 激活距离，但收缩过程中仍可能产生近距离风险。

该场景用于正式比较 M0–M5。

### 不可行压力测试

额外设置：

```text
formation_radius: 1.5 m
```

相邻目标点距离约为 1.15 m，低于 `r_iapf=1.5 m`。

该场景只作为 infeasible stress test，必须单独报告。不能把“所有 UAV 完全到达目标”作为唯一成功判据，因为目标几何与安全约束本身冲突。

需要记录：

- 系统是否主动停留在安全边界；
- 是否持续振荡；
- 是否超时；
- 安全性和任务完成度之间的冲突。

---

## 6.3 场景 C：Vertical interaction

建议设置：

```text
UAV1: [0.0, 0.0, 1.5] → [0.0, 0.0, 4.5]
UAV2: [0.0, 0.0, 4.5] → [0.0, 0.0, 1.5]
duration: 5.0 s
assignment_mode: fixed
```

该场景用于验证：

- 三维避障能力；
- 固定正 Z 破局分量是否导致共同上移；
- `id_order` 破局策略是否产生相反方向的相对分离；
- 双通道前馈是否引发过大垂向加速度或振荡。

除主实验外，额外执行：

```text
fixed_positive_z vs id_order
```

---

## 6.4 场景 D：Grouped reconfiguration

建议使用两组各 4 架无人机：

```text
Group A：沿 X 方向穿越中心并完成变阵
Group B：沿 Y 方向穿越中心并完成变阵
```

要求两组同时开始，名义轨迹在中心区域存在跨组冲突风险。

比较：

```text
组内独立 assignment
联合跨组安全评估
联合安全 assignment + IAPF
```

该场景重点验证：

- 联合规划是否增加跨组 minimum distance；
- safety-aware assignment 是否减少 IAPF activation ratio；
- 是否减少轨迹偏移和 recovery time；
- 是否保持任务完成时间和到达同步性。

---

# 7. 数据记录格式

建议目录：

```text
experiments/08-iapf/
├── configs/
│   ├── experiment_defaults.yaml
│   ├── methods.yaml
│   └── scenarios/
│       ├── head_on.yaml
│       ├── dense_feasible.yaml
│       ├── dense_infeasible.yaml
│       ├── vertical.yaml
│       └── grouped_reconfiguration.yaml
├── scripts/
│   ├── run_experiment.py
│   ├── analyze_iapf.py
│   ├── aggregate_trials.py
│   ├── plot_iapf_results.py
│   └── validate_synthetic_data.py
├── tests/
│   ├── test_event_counting.py
│   ├── test_distance_resampling.py
│   ├── test_risk_integral.py
│   └── test_assignment_modes.py
└── results/
    └── <experiment_batch_id>/
        ├── batch_metadata.json
        ├── raw/
        │   └── <scenario>/<method>/trial_<N>/
        │       ├── run_metadata.json
        │       ├── odom.csv
        │       ├── iapf_debug.csv
        │       ├── assignment.csv
        │       ├── mission_events.csv
        │       └── rosbag2/
        ├── summaries/
        │   ├── trial_summary.csv
        │   ├── method_summary.csv
        │   └── statistical_tests.csv
        └── figures/
```

`run_metadata.json` 至少包含：

```text
experiment_id
batch_id
scenario
method
trial
seed
git_commit
date_time
uav_ids
duration
motion_style
assignment_mode
avoidance_mode
all IAPF parameters
all safety thresholds
control frequency
simulator version
PX4 version
ROS distribution
RTF summary
```

---

# 8. 指标定义

## 8.1 距离时序

将所有 UAV odometry 重采样到统一时间轴。建议：

```text
sampling frequency: 20 Hz
interpolation: linear
```

不要仅按 timestamp 四舍五入后取某个样本，因为不同 UAV 的消息时间不同，会给 minimum distance 引入同步误差。

计算：

\[
d_{ij}(t)=\|p_i(t)-p_j(t)\|
\]

\[
d_{min}(t)=\min_{i<j}d_{ij}(t)
\]

\[
d_{min}^{global}=\min_t d_{min}(t)
\]

---

## 8.2 主安全指标

| 指标 | 定义 |
|---|---|
| `minimum_inter_agent_distance` | 全程所有 UAV 对的最小距离 |
| `collision_event_count` | 每对 UAV 连续低于 `d_collision` 的区间数 |
| `violation_event_count` | 每对 UAV 连续低于 `d_violation` 的区间数 |
| `risk_exposure_time` | 所有 UAV 对低于 `d_violation` 的累计时长 |
| `mission_success` | 无碰撞、未超时且全部 UAV 达到稳定判据 |

事件计数必须基于连续区间，而不是违规采样点数量。

例如某一 UAV 对连续 0.8 秒低于阈值，应计为：

```text
1 violation event
0.8 s risk exposure
```

而不是按 20 Hz 计为 16 次违规。

---

## 8.3 风险积分

新增综合风险指标：

\[
J_{risk}=\sum_{i<j}\int_0^T
\max(0,d_{violation}-d_{ij}(t))^2dt
\]

该指标同时反映危险距离的深度和持续时间。

输出字段：

```text
risk_integral
```

---

## 8.4 避障介入指标

| 指标 | 定义 |
|---|---|
| `iapf_activation_time` | 至少一个邻机触发 IAPF 的累计时间 |
| `iapf_activation_ratio` | 激活时间 / 正式任务总时间 |
| `mean_repulsion_norm` | 激活期间原始斥力模长均值 |
| `max_repulsion_norm` | 原始斥力最大模长 |
| `position_saturation_ratio` | 位置偏置达到限幅的样本比例 |
| `acceleration_saturation_ratio` | 加速度偏置达到限幅的样本比例 |

---

## 8.5 轨迹效率指标

名义轨迹为不含避障调制的 Minimum Jerk reference。

计算：

```text
mean_trajectory_deviation
max_trajectory_deviation
actual_path_length
nominal_path_length
path_length_ratio = actual_path_length / nominal_path_length
```

trajectory deviation 定义为：

\[
e_{dev}(t)=\|p_{actual}(t)-p_{nominal}(t)\|
\]

---

## 8.6 恢复和卡死指标

### Recovery time

定义为：

```text
最后一次所有相关 UAV 退出 IAPF 激活区间
→ 所有 UAV 再次满足悬停稳定判据
```

若任务超时仍未稳定，则记为 `NaN`，同时标记 failure reason。

### Stall event

建议定义：

```text
distance_to_target > 0.5 m
AND speed < 0.15 m/s
AND condition continuously lasts >= 2.0 s
```

每个连续区间计为一个 stall event。

阈值必须写入配置文件，不能在分析脚本中硬编码。

---

## 8.7 控制负担指标

如可从 setpoint 或调试日志获得，计算：

\[
J_{control}=\int_0^T\|a_{setpoint}(t)\|^2dt
\]

至少输出：

```text
peak_acceleration_setpoint
integrated_squared_acceleration
```

该指标用于判断双通道避障是否以过大的控制输入换取安全距离。

---

# 9. Mission success 与 failure reason

统一成功判据：

```text
1. collision_event_count == 0
2. 所有参与 UAV 在 timeout 前进入 hover stable
3. 最终位置误差满足现有稳定阈值
4. 仿真过程中没有 PX4 failsafe、失联或异常退出
```

输出标准化失败原因：

```text
collision
timeout
stall
px4_failsafe
node_crash
stale_odometry
invalid_initialization
infeasible_target
unknown
```

对于 `dense_infeasible`，额外报告：

```text
safe_completion_ratio
final_formation_error
```

并允许 `infeasible_target` 作为独立结果，不和普通可行场景的 mission success 直接混合统计。

---

# 10. 重复次数和实验协议

## 10.1 Pilot

每个场景和方法先运行：

```text
3 次 pilot trial
```

用于检查：

- 初始位置是否一致；
- 日志是否完整；
- 场景是否确实触发安全风险；
- timeout 是否合理；
- 参数是否存在明显数值发散。

Pilot 结果不能用于正式论文统计，也不能针对单一正式测试场景反复调参。

## 10.2 正式实验

建议：

```text
4 个可行主场景
× 6 个方法
× 10 次重复
= 240 个正式 trial
```

`dense_infeasible` 作为独立压力测试，不并入主实验平均值。

每个 trial 使用配对随机种子，例如：

```text
scenario=head_on, seed=42
```

M0–M5 全部使用同一个 seed 和相同初始扰动。

## 10.3 可控随机化

允许对初始位置加入小扰动：

```text
x/y/z perturbation: configurable
```

例如 ±0.05 m，但必须：

- 由 seed 决定；
- 对所有方法复用；
- 记录在 metadata 中；
- 不改变场景基本几何关系。

---

# 11. 参数调节原则

将场景分为：

```text
calibration scenarios
test scenarios
```

只允许在 calibration scenarios 上调节：

```text
K_rep
position_gain
position_limit
accel_gain
accel_limit
escape_gain
neighbor_timeout
```

正式测试时固定参数，禁止为每个场景分别选择一组最优参数。

如确实需要场景相关参数，必须把它作为独立方法或敏感性分析，而不是默默更改。

建议补充一组参数敏感性实验：

```text
K_rep: low / nominal / high
accel_gain: 0 / nominal / high
```

敏感性实验不要求覆盖全部方法和场景，可选 head-on 与 dense_feasible 两个代表场景。

---

# 12. 统计分析

`aggregate_trials.py` 应输出每个方法在每个场景下的：

```text
mean
standard deviation
median
IQR
95% bootstrap confidence interval
```

建议正式比较：

1. 多方法总体差异：Friedman test；
2. 配对两两比较：Wilcoxon signed-rank test；
3. 多重比较校正：Holm correction；
4. mission success rate：同时报告 Wilson 95% confidence interval。

需要比较的主指标：

```text
minimum_inter_agent_distance
violation_event_count
risk_exposure_time
risk_integral
mission_success
mean_trajectory_deviation
recovery_time
iapf_activation_ratio
```

统计脚本必须能处理失败 trial 和 `NaN recovery_time`，不能静默删除失败样本。应明确输出有效样本数。

---

# 13. 图表要求

## 13.1 主文建议图

### 图 1：代表性距离时序

Head-on 场景展示：

```text
M0 / M1 / M2 / M3
```

绘制：

```text
distance over time
r_iapf horizontal line
d_violation horizontal line
d_collision horizontal line
IAPF active intervals
```

### 图 2：Minimum distance 分布

按场景绘制 M0–M5 的 box plot 或 violin plot。

### 图 3：安全—效率权衡

```text
x-axis: mean trajectory deviation 或 path length ratio
y-axis: risk integral
```

用于说明安全提升是否带来过大轨迹代价。

### 图 4：IAPF 局部介入负担

比较：

```text
iapf_activation_ratio
mean_repulsion_norm
recovery_time
```

重点展示 M3 与 M5，验证安全 assignment 是否减少局部避障负担。

### 图 5：3D 轨迹

每个场景选一组代表 trial，绘制：

```text
nominal trajectory
actual trajectory
start/target points
closest-approach location
```

## 13.2 不建议的画法

8 架无人机共有 28 对距离曲线，不要在主文一张图中全部绘制。

主文优先展示：

```text
global minimum distance over time
closest pair distance
```

完整 pairwise curves 可输出到 supplementary figures。

## 13.3 汇总表

至少生成：

| Method | Success rate | Min distance | Violation events | Risk integral | Deviation | Recovery time | Activation ratio |
|---|---:|---:|---:|---:|---:|---:|---:|

表中使用：

```text
median [IQR]
```

或：

```text
mean ± std
```

但整张表必须统一。

---

# 14. 分析脚本优化要求

基于现有 `analyze_pairwise_distance.py` 扩展或重写时，必须完成：

1. 对多 UAV odometry 插值到统一时间轴；
2. 区分：
   - violation sample count；
   - violation event count；
   - violation duration；
3. 同时使用 `d_collision`、`d_violation` 和 `r_iapf`；
4. 计算风险积分；
5. 读取 IAPF debug 日志计算 activation 和 saturation；
6. 读取名义 reference 计算 trajectory deviation；
7. 输出 per-pair summary 和 global summary；
8. 对缺失数据、时间不重叠、非有限数值明确报错；
9. 使用合成数据编写单元测试。

至少测试以下合成情况：

```text
两机始终安全
一次连续违规事件
两次分离的违规事件
恰好等于阈值
发生碰撞
时间戳不同步
中间缺少一段 odom
IAPF 激活但未限幅
IAPF 激活且发生限幅
```

---

# 15. 实现顺序

Codex 按以下顺序执行，避免一次性修改过多后无法定位问题。

## Phase 1：模式和参数标准化

```text
1. 增加 avoidance_mode
2. 增加 assignment_mode
3. 保留旧参数兼容逻辑
4. 更新 launch 和 YAML
5. 编译并检查参数可见
```

## Phase 2：IAPF 算法安全修正

```text
1. Classic APF 分支
2. escape_mode 参数化
3. id_order 对称破局
4. distance epsilon
5. position/acceleration 双限幅
6. neighbor freshness
7. 单元测试或独立函数测试
```

## Phase 3：日志和消息

```text
1. 新增 IAPFDebug.msg
2. 发布 /uav{id}/iapf_debug
3. 增加 CSV/rosbag 记录
4. 验证所有字段
```

## Phase 4：规划层联合评估

```text
1. distance-only assignment 模式
2. fixed assignment 模式
3. grouped constrained assignment
4. 跨组轨迹安全代价
5. assignment 日志
```

## Phase 5：实验运行器和场景

```text
1. 场景 YAML
2. 自动预定位
3. 自动稳定等待
4. trial metadata
5. 自动任务下发
6. 自动结束和故障判定
```

## Phase 6：分析与绘图

```text
1. 时间同步和 pairwise distance
2. 事件计数
3. 风险积分
4. trajectory deviation
5. IAPF activation/saturation
6. trial aggregation
7. 统计检验
8. 图表生成
```

## Phase 7：验证

```text
1. Python unit tests
2. C++ package build
3. launch --show-args
4. synthetic CSV test
5. 2-UAV head-on smoke test
6. 3-UAV or 5-UAV smoke test
7. 记录结果和限制
```

---

# 16. 验收标准

完成任务至少满足以下条件。

## 16.1 编译与测试

- `uav_swarm_interfaces` 编译成功；
- `ladrc_controller` 编译成功；
- Python 分析脚本通过单元测试；
- launch 参数可见且可覆盖；
- 新消息可以正常 echo；
- 合成数据能够正确区分一次连续违规和多次独立违规。

## 16.2 方法切换

能够仅通过配置执行：

```text
M0–M5
```

无需修改源码。

## 16.3 日志完整性

任一 smoke trial 至少生成：

```text
run_metadata.json
odom.csv
iapf_debug.csv
assignment.csv
mission_events.csv
trial_summary.csv
```

## 16.4 场景可执行

至少验证：

```text
head_on: M0 与 M3
dense_feasible: M3 与 M5
```

若无法完成全部方法，明确记录未运行原因，不能生成虚构数据。

## 16.5 结果可解释

trial summary 必须能回答：

```text
是否成功
失败原因
全程最小距离
违规事件次数
风险暴露时间
风险积分
IAPF 激活比例
轨迹偏移
恢复时间
是否发生限幅
```

---

# 17. 最终交付内容

Codex 最终应交付：

```text
1. IAPF 和 assignment 的参数化代码修改
2. IAPFDebug 消息与日志
3. grouped constrained safety-aware assignment
4. 场景配置文件
5. 自动实验运行器
6. 离线分析和统计脚本
7. 绘图脚本
8. 单元测试
9. smoke test 输出
10. docs/experiment_08_implementation_report.md
```

实现报告中必须包含：

```text
修改摘要
修改文件列表
各实验模式定义
运行命令
结果文件结构
已完成测试
当前未完成项
已知限制
正式批量实验建议
```

---

# 18. 最终实验叙事

完成后，实验 8 应形成以下清晰逻辑：

```text
M0：没有局部避障，建立风险基线
M1：Classic APF 提供基本径向避障
M2：IAPF 破局机制改善对称或三维交互
M3：加速度前馈提高局部避障响应速度
M4：安全感知目标分配在执行前降低名义轨迹风险
M5：规划层与局部安全层联合，减少危险接近和局部避障负担
```

最终关注的不只是“有没有碰撞”，而是同时评估：

```text
安全性
任务成功率
轨迹效率
恢复能力
控制负担
方法可重复性
```
