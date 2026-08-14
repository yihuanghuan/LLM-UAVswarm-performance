# LLM-Driven Multi-UAV Swarm Control System

[![ROS2](https://img.shields.io/badge/ROS2-Humble-brightgreen)](https://docs.ros.org/en/humble/)
[![PX4](https://img.shields.io/badge/PX4-v1.14+-blue)](https://px4.io/)
[![Gazebo](https://img.shields.io/badge/Gazebo-Classic%2011-orange)](https://classic.gazebosim.org/)
[![C++](https://img.shields.io/badge/C++-17-blue.svg)](https://en.cppreference.com/w/cpp/17)
[![Python](https://img.shields.io/badge/Python-3.10-yellow.svg)](https://www.python.org/)

基于大型语言模型 (LLM) 和 ROS 2 的多无人机集群编队系统。操作员输入自然语言指令，系统通过 Candidate Mission、确定性 late resolution 和安全感知分配生成复合执行消息。执行层默认由 LADRC 生成平动加速度并通过 PX4 acceleration-level Offboard 接口闭环跟踪。

## 系统架构

```text
Natural Language → LLM → Candidate Mission → Mission Graph / FSM
→ fresh snapshot → validation/resolution/geometry → T_plan → allocator
→ T_exec → Executable LFS + ResolutionTrace → Execution Profile
→ UAVExecutionCommand → controller checks/LADRC runtime
→ existing Minimum-Jerk + IAPF setpoint path → PX4
```

这是论文实验的正式 paper Candidate path。旧 LFS → `UAVSwarmCommand` 仅作为显式 legacy compatibility path 保留。权威语义见 [Paper LFS Specification](docs/paper_lfs_spec.md)，运行方法见 [Paper Candidate Runtime](docs/paper_candidate_runtime.md)。

### 三层解耦

| 层级 | 技术栈 | 职责 |
|------|--------|------|
| **认知层** | Python + LLM API | 自然语言 → 规范 JSON 蓝图（编队类型、参数、时间、运动风格） |
| **调度层** | Python ROS 2 (`location_allocate`) | 坐标生成、匈牙利算法防交叉分配、状态闭环、多任务编排 |
| **执行层** | C++ ROS 2 (`ladrc_controller`) | profile 检查、Minimum Jerk 轨迹、IAPF 分布式避障和 LADRC acceleration-level 外环 |

## 核心特性

- **自然语言控制**：支持单一/复合/并行编队指令，如"1到5号机组成圆形，6到8号机组成直线"
- **匈牙利防交叉分配**：全局最优目标分配，避免飞行轨迹交叉
- **LADRC profile 边界**：新路径由中央 Execution Profile Compiler 确定性生成参数；控制器校验、硬限幅和平滑应用，LADRC 输出直接进入 PX4 acceleration setpoint
- **IAPF 分布式避障**：基于相对速度、滞回和平滑的双通道斥力，使用确定性成对垂直逃逸方向缓解局部极小值
- **多机命名空间隔离**：自动话题重映射，兼容 PX4 多实例 Gazebo 仿真
- **闭环状态反馈**：基于真实悬停检测推进任务序列
- **5-10 机规模验证**：Gazebo Classic 实时仿真，RTF ≥ 0.95

## 环境要求

| 组件 | 版本 |
|------|------|
| Ubuntu | 22.04 |
| ROS 2 | Humble |
| PX4-Autopilot | v1.14+ |
| Gazebo | Classic 11 |
| Eigen | 3.4+ |
| Python | 3.10 |
| LLM API | MiniMax / OpenAI 兼容 |

## 安装

### 1. 克隆仓库

```bash
mkdir -p ~/learning/LLM_swarm_ws/src
cd ~/learning/LLM_swarm_ws/src
git clone https://github.com/yihuanghuan/LLM-UAVswarm-performance.git
```

### 2. 安装依赖

```bash
# ROS 2 依赖
sudo apt install ros-humble-ros-gz ros-humble-gazebo-ros-pkgs

# Python 依赖
python3 -m venv ~/learning/LLM_swarm_ws/llm_env
source ~/learning/LLM_swarm_ws/llm_env/bin/activate
pip install openai numpy scipy httpx jsonschema

# PX4 消息包
cd ~/learning/LLM_swarm_ws/src/LLM-UAVswarm-performance/px4_msgs
colcon build --packages-select px4_msgs
```

### 3. 编译

```bash
cd ~/learning/LLM_swarm_ws
source install/setup.bash
colcon build --symlink-install
```

## 快速启动

### 单机测试

```bash
# 终端 1: XRCE-DDS 桥接
MicroXRCEAgent udp4 -p 8888

# 终端 2: PX4 SITL 单机
cd ~/PX4-Autopilot
make px4_sitl gazebo-classic

# 终端 3: C++ 控制节点
source ~/learning/LLM_swarm_ws/install/setup.bash
ros2 launch ladrc_controller swarm_launch.py uav_ids:=[0]

# 终端 4: 发送飞行指令
source ~/learning/LLM_swarm_ws/install/setup.bash
ros2 topic pub --once /uav0/swarm_command uav_swarm_interfaces/msg/UAVSwarmCommand \
  "{header: {stamp: {sec: 0, nanosec: 0}, frame_id: 'world'}, mission_id: 1, uav_id: 0, \
    target_pos: {x: 3.0, y: 0.0, z: 3.0}, duration: 5.0, \
    motion_style: 'normal', safety_factor: 1.0}"
```

单机 `make px4_sitl gazebo-classic` 使用 PX4 instance 0，话题为 `/fmu/...`；`swarm_launch.py` 中用 `uav_ids:=[0]` 对应该单机实例。多机 `sitl_multiple_run.sh` 仍使用 `uav_ids:=[1,2,...]`。

### 多机编队（调度器完整链路）

```bash
# 终端 1
MicroXRCEAgent udp4 -p 8888

# 终端 2: N 机 PX4 (替换 N 为 3/5/8)
cd ~/PX4-Autopilot
./Tools/simulation/gazebo-classic/sitl_multiple_run.sh -m iris -n 5

# 终端 3: C++ 控制节点
source ~/learning/LLM_swarm_ws/install/setup.bash
ros2 launch ladrc_controller swarm_launch.py uav_ids:=[1,2,3,4,5]

# IAPF 加速度前馈对比实验可直接覆盖开关
ros2 launch ladrc_controller swarm_launch.py uav_ids:=[1,2,3,4,5] enable_iapf_accel_feedforward:=false
ros2 launch ladrc_controller swarm_launch.py uav_ids:=[1,2,3,4,5] enable_iapf_accel_feedforward:=true

# 终端 4: LLM 调度器
source ~/learning/LLM_swarm_ws/install/setup.bash
export LLM_API_KEY='<your-key>'
ros2 run location_allocate location_allocate
```

调度器默认使用英文 `candidate_v2` parser 和 `paper-current-v1` policy。只有历史实验/回归需要显式加入 `--ros-args -p lfs_runtime_mode:=legacy_v1`。Paper Candidate 失败不会 fallback 到旧 `task_sequences`。

当前冻结接口版本为 `paper-candidate-en-v2` / `paper-candidate-schema-v2`。Formation 使用结构化 descriptor；Polygon 必须显式给出 sides。任务等待只通过结构化 q 表达，不接受独立 WaitNode。

## 指令示例

### 单一编队

```
Have UAVs 1 through 5 form a circle centered at [2,9,3] with a radius of 3 meters in 12 seconds.
```

### 并行编队（不同 UAV 集合同时变阵）

```
In parallel, UAVs 1 to 5 form a circle centered at [0,0,5] with radius 3 meters, while UAVs 6 to 8 form a line centered at [0,0,8] with 2-meter spacing.
```

### 串行变阵（同一组 UAV 连续变换）

```
First form a smooth line with 4-meter spacing centered at [10,0,5] in 10 seconds. After it stabilizes, form an aggressive circle centered at [0,0,5] with radius 4 meters in 8 seconds.
```

### 运动风格

- `smooth`（平滑）、`normal`（标准）、`aggressive`（激进）是冻结的任务语义标签。
- 当前 `paper-current-v1` policy 对三种 style 使用 neutral identity baseline：`auto_style_factors` 和 `style_gains` 均为 `1.0`，不会仅因 style 不同而改变基础时长因子或 LADRC 带宽。
- style-dependent timing、LADRC gain 和 task-intensity adaptation 的非恒等映射仍属 provisional，须经后续实验标定后通过显式 policy 配置启用。

新路径不允许 LLM 输出 LADRC gain。Execution Profile Compiler 以 `m`、assignment 后的 `D_i` 和唯一的 `T_exec` 为确定性输入，但当前 Paper policy 对 style/task adaptation 保持恒等映射。未来的非恒等映射及数值仍为 provisional，必须通过显式配置注入。旧消息中的 motion style 仅记录，控制器使用 YAML baseline。

控制适应数据可通过 topic 和 CSV 查看：

```bash
ros2 topic echo /uav1/control_adaptation
tail -f src/LLM-UAVswarm-performance/logs/control_adaptation_log.csv
```

### 避障系数

LLM 默认 `safety_factor=1.0`（标准避障），可在指令中添加如"避障系数 2.0"单独调节。

### IAPF 实验分析

`/uav{id}/odom` 话题导出的 CSV 可用离线脚本统计机间距离：

```bash
python3 experiments/scripts/analyze_pairwise_distance.py bag_csv \
  --out-dir pairwise_distance_analysis \
  --safety-distance 1.5
```

输出包括：

- `min_distance.csv`：每个时间点的全局最小机间距离
- `pairwise_distance_plot.pdf`：两两无人机距离时序曲线
- `safety_violation_summary.csv`：安全冲突和危险接近汇总

## 目录结构

```
LLM_swarm_ws/
├── src/LLM-UAVswarm-performance/
│   ├── uav_swarm_interfaces/          # 自定义 ROS 2 消息
│   │   └── msg/
│   │       ├── UAVSwarmCommand.msg    # 调度层→执行层指令
│   │       ├── UAVStatus.msg          # 执行层→调度层反馈
│   │       └── ControlAdaptationLog.msg # LADRC 控制适应日志
│   ├── location_allocate/             # Python 调度层
│   │   └── location_allocate/
│   │       ├── location_allocate.py   # ROS 2 wiring + 显式 Paper/Legacy mode dispatch
│   │       ├── paper_candidate_parser.py # 正式 Paper Candidate LLM parser
│   │       ├── paper_lfs_validator.py # Paper static/runtime validation
│   │       ├── paper_runtime.py       # Paper late-resolution 执行链
│   │       ├── mission_compiler.py    # Candidate Mission → Mission Graph/FSM
│   │       ├── mission_executor.py    # ready task/group 调度
│   │       ├── legacy/                # v1 parser/runtime/scheduler/validator 兼容层
│   │       ├── no_location.py         # legacy parser public-entry compatibility shim
│   │       └── visualize_goals.py     # 可视化工具
│   ├── schemas/
│   │   ├── paper_candidate_schema_v2.json # Paper research interface
│   │   └── legacy/lfs_schema_v1.json       # legacy compatibility schema
│   ├── lfs_policy/                    # typed paper-current/legacy policy loader
│   ├── minisnap_LADRC/
│   │   └── ladrc_controller/          # C++ 执行层
│   │       ├── src/
│   │       │   ├── ladrc_position_controller_node.cpp  # 主控制节点
│   │       │   ├── ladrc_core.cpp     # LADRC 控制器封装
│   │       │   ├── leso.cpp           # 线性扩张状态观测器
│   │       │   └── lsef.cpp           # 线性状态误差反馈
│   │       ├── include/ladrc_controller/
│   │       │   ├── minimum_jerk_trajectory.hpp  # 5次多项式轨迹
│   │       │   ├── ladrc_core.hpp
│   │       │   ├── leso.hpp
│   │       │   └── lsef.hpp
│   │       ├── config/
│   │       │   └── ladrc_params.yaml  # 统一参数配置
│   │       └── launch/
│   │           └── swarm_launch.py    # 多机一键启动
│   └── px4_msgs/                      # PX4 ROS 2 消息定义
├── build/
├── install/
├── llm_env/                           # Python 虚拟环境
└── Claude.md                          # 项目开发文档
```

## 关键参数 (`ladrc_params.yaml`)

```yaml
# 外部平动控制模式（稳定演示默认使用 PX4 位置基线）
control_mode: "px4_position"  # 可显式切换为 "ladrc_acceleration"
idle_hover_safety_factor: 1.0       # 首次任务前悬停避障系数

# X/Y 轴 LADRC
omega_o_x: 10.0    # 观测器带宽
omega_c_x: 3.0     # 控制器带宽
b0_x: 1.0          # 控制增益估计

# Z 轴 LADRC（更高带宽应对重力）
omega_o_z: 15.0
omega_c_z: 3.5
b0_z: 1.0

# 加速度限制
max_acceleration_x: 5.0  # m/s²
max_acceleration_z: 8.0

# IAPF 避障
iapf_violation_distance: 1.0 # 碰撞风险阈值 (m)
iapf_enter_distance: 1.5     # 进入避障阈值 (m)
iapf_exit_distance: 1.65     # 退出避障阈值 (m)
iapf_filter_alpha: 0.2       # 偏移低通滤波系数
iapf_repulsion_gain: 20.0    # 斥力增益
```

两种控制模式：

- `ladrc_acceleration`：Minimum Jerk → IAPF 安全参考 → LADRC → `TrajectorySetpoint.acceleration`。PX4 继续执行姿态、角速度和电机内环。
- `px4_position`：保留 Minimum Jerk + IAPF + PX4 位置控制器路径，用于论文基线对照。

可在启动时切换，例如：

```bash
ros2 launch ladrc_controller swarm_launch.py \
  uav_ids:=[1,2,3] control_mode:=px4_position
```

## 数据协议

### UAVSwarmCommand

```text
std_msgs/Header header
uint32 mission_id                   # 全局任务编号，对应 task_sequence_id
uint8 uav_id                        # 无人机编号
geometry_msgs/Point target_pos      # 全局 ENU 目标坐标 [x, y, z]
float32 duration                    # 期望飞行时间 (s)
string motion_style                 # "smooth" / "normal" / "aggressive"
float32 safety_factor               # 安全裕度系数；迁移路径强制 >= 1
```

### UAVExecutionCommand（Candidate 新路径）

```text
std_msgs/Header header
uint32 mission_id
uint32 task_id
uint32 group_id
uint8 uav_id
geometry_msgs/Point target_pos
uav_swarm_interfaces/ExecutionProfile profile
```

`profile.duration` 是新路径唯一时长源；外层不重复保存 duration。`profile` 的 LADRC、运动限幅和 IAPF soft 参数由中央 Compiler 确定性生成，控制器不会从 style 重新推导。

### ControlAdaptationLog

```text
std_msgs/Header header
uint32 mission_id
uint8 uav_id
string motion_style
float32 target_distance
float32 duration
float32 average_speed
float32 gain_multiplier
float32 omega_o_x/y/z
float32 omega_c_x/y/z
float32 peak_velocity
float32 peak_acceleration
float32 settling_time
float32 tracking_rmse
```

### ControlTrackingDebug

`/uav{N}/control_tracking_debug` 以控制频率发布结构化数据，包含标称/安全位置、速度和加速度参考、LADRC 输出、LESO `z1/z2/z3`、实际位置/速度、跟踪误差，以及实际写入 PX4 的 NED setpoint。实验时可直接记录：

```bash
ros2 bag record /uav1/control_tracking_debug \
  /px4_1/fmu/in/offboard_control_mode /px4_1/fmu/in/trajectory_setpoint
```

### UAVStatus

```text
uint8 uav_id
bool is_hover_stable                # 到达目标且稳定悬停时为 true
```

## 数据流

```
LLM API → Candidate Mission → Mission Graph / FSM
    ↓
fresh snapshot → deterministic late resolution → safety-aware allocation
    ↓
Executable LFS + ResolutionTrace → Execution Profile Compiler
    ↓
UAVExecutionCommand → /uav{N}/execution_command
    ↓
Minimum Jerk nominal reference → IAPF safe reference → LADRC tracking
    ↓
PX4 Offboard acceleration setpoint（ENU → NED）→ PX4 inner loops
    ↓
Gazebo 物理仿真
    ↓
UAVStatus + /uav{N}/swarm_state (nav_msgs/Odometry, world ENU)
→ Candidate 调度器闭环反馈
```

稳定演示暂以 `px4_position` 为默认模式。显式选择 `ladrc_acceleration` 时，PX4 setpoint 的 position/velocity 字段为 NaN，acceleration 字段为 LADRC 输出经 ENU→NED 转换后的结果。无任务时锁定当前位置，任务结束后保持最终目标，并持续运行 IAPF 与 LADRC。旧 `/uavN/odom : geometry_msgs/Point` 继续供 legacy scheduler 使用。

## 已知限制

1. **Z 轴收敛速度**：PX4 下降速率受限（约 1.5 m/s），Z 轴向上过冲后收敛较慢（~0.3m 稳态误差），由放宽后的悬停阈值（0.3m）覆盖。
2. **Gazebo Classic 性能**：10 机时 RTF 可能低于 1.0，建议 5-8 机确保实时仿真。
3. **LLM API 依赖**：Paper parser 需网络连接及通过环境变量提供的有效 `LLM_API_KEY`（兼容 `MINIMAX_API_KEY`）；入口为 `paper_candidate_parser.py`。
4. **多机 spawn 偏移**：`sitl_multiple_run.sh` 默认沿 Y 轴排列（间隔 3m），调度器已自动补偿。

## 排障指南

| 问题 | 原因 | 解决 |
|------|------|------|
| C++ 节点收不到里程计 | QoS 不匹配 | 确保发布/订阅均使用 `SensorDataQoS()` |
| 无人机不响应指令 | `target_system` 错误 | 已改为 0 (广播) |
| IAPF 不触发 | `safety_factor=0` | LLM 默认设为 1.0 |
| 调度器跳过子任务 | 旧悬停状态残留 | 已修复：入口处重置 + 2s 排空 |
| `ros2 run` 找不到 openai | 系统 Python | 用 `python3 -m` 模块方式运行 |
| 复合指令子任务吞掉 | DDS 旧消息 | v1.1 已修复 |

## 引用

如果本项目对你的研究有帮助，请引用：

```
@software{LLM_UAVswarm_2024,
  author = {yihuanghuan},
  title = {LLM-Driven Multi-UAV Swarm Control System},
  year = {2024},
  url = {https://github.com/yihuanghuan/LLM-UAVswarm-performance}
}
```

## License

MIT License
