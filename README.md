# LLM-Driven Multi-UAV Swarm Control System

[![ROS2](https://img.shields.io/badge/ROS2-Humble-brightgreen)](https://docs.ros.org/en/humble/)
[![PX4](https://img.shields.io/badge/PX4-v1.14+-blue)](https://px4.io/)
[![Gazebo](https://img.shields.io/badge/Gazebo-Classic%2011-orange)](https://classic.gazebosim.org/)
[![C++](https://img.shields.io/badge/C++-17-blue.svg)](https://en.cppreference.com/w/cpp/17)
[![Python](https://img.shields.io/badge/Python-3.10-yellow.svg)](https://www.python.org/)

基于大型语言模型 (LLM) 和 ROS 2 的多无人机集群编队控制系统。操作员输入自然语言指令，系统自动解析、执行匈牙利防交叉分配，并通过 LADRC 控制器 + IAPF 分布式避障完成平滑编队飞行。

## 系统架构

```
自然语言指令 → LLM 解析 → JSON 蓝图
                              ↓
              Python 调度层（匈牙利防交叉分配）
                              ↓
              UAVSwarmCommand (/uav{N}/swarm_command)
                              ↓
              C++ 执行层（Minimum Jerk 轨迹 + LADRC + IAPF）
                              ↓
              PX4 Offboard 控制 → Gazebo 仿真
                              ↓
              UAVStatus + ENU 位置反馈 → 调度层闭环
```

### 三层解耦

| 层级 | 技术栈 | 职责 |
|------|--------|------|
| **认知层** | Python + LLM API | 自然语言 → 规范 JSON 蓝图（编队类型、参数、时间、运动风格） |
| **调度层** | Python ROS 2 (`location_allocate`) | 坐标生成、匈牙利算法防交叉分配、状态闭环、多任务编排 |
| **执行层** | C++ ROS 2 (`ladrc_controller`) | Minimum Jerk 轨迹生成、LADRC 动态增益控制、IAPF 分布式避障 |

## 核心特性

- **自然语言控制**：支持单一/复合/并行编队指令，如"1到5号机组成圆形，6到8号机组成直线"
- **匈牙利防交叉分配**：全局最优目标分配，避免飞行轨迹交叉
- **LADRC 自抗扰控制**：基于带宽参数化的线性自抗扰控制器，支持 smooth/normal/aggressive 动态增益调节
- **IAPF 分布式避障**：改进的人工势场法，位置+加速度双通道斥力，Z 轴侧向力防止局部极小值死锁
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
pip install openai numpy scipy httpx

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
ros2 launch ladrc_controller swarm_launch.py uav_ids:=[1]

# 终端 4: 发送飞行指令
source ~/learning/LLM_swarm_ws/install/setup.bash
ros2 topic pub --once /uav1/swarm_command uav_swarm_interfaces/msg/UAVSwarmCommand \
  "{header: {stamp: {sec: 0, nanosec: 0}, frame_id: 'world'}, uav_id: 1, \
    target_pos: {x: 3.0, y: 0.0, z: 3.0}, duration: 5.0, \
    motion_style: 'normal', safety_factor: 0.0}"
```

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

# 终端 4: LLM 调度器
source ~/learning/LLM_swarm_ws/llm_env/bin/activate
unset ALL_PROXY all_proxy
source ~/learning/LLM_swarm_ws/install/setup.bash
python3 -m location_allocate.location_allocate
```

## 指令示例

### 单一编队

```
无人机1到5号机以[2,9,3]为中心，变换成圆形编队，半径为3米，限时12秒
```

### 并行编队（不同 UAV 集合同时变阵）

```
1到5号机以[0,0,5]为中心，组成半径为3米的圆形编队；同时，6到8号机以[0,0,8]为中心，组成间隔2米的直线编队
```

### 串行变阵（同一组 UAV 连续变换）

```
首先以[10,0,5]为中心，在10秒内展开为间隔4米的直线编队，使用smooth模式；
完成后转移目标，以[0,0,5]为中心，在8秒内聚拢成半径4米的圆形编队，使用aggressive模式
```

### 运动风格

- `smooth`（平滑）: 增益 ×0.7，平稳优先
- `normal`（标准）: 增益 ×1.0
- `aggressive`（激进）: 增益 ×1.5，速度优先

### 避障系数

LLM 默认 `safety_factor=1.0`（标准避障），可在指令中添加如"避障系数 2.0"单独调节。

## 目录结构

```
LLM_swarm_ws/
├── src/LLM-UAVswarm-performance/
│   ├── uav_swarm_interfaces/          # 自定义 ROS 2 消息
│   │   └── msg/
│   │       ├── UAVSwarmCommand.msg    # 调度层→执行层指令
│   │       └── UAVStatus.msg          # 执行层→调度层反馈
│   ├── location_allocate/             # Python 调度层
│   │   └── location_allocate/
│   │       ├── location_allocate.py   # 匈牙利分配 + ROS2 节点
│   │       ├── no_location.py         # LLM API 解析
│   │       └── visualize_goals.py     # 可视化工具
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
iapf_safe_distance: 2.0   # 安全距离 (m)
iapf_repulsion_gain: 20.0 # 斥力增益
```

## 数据协议

### UAVSwarmCommand

```text
std_msgs/Header header
uint8 uav_id                        # 无人机编号
geometry_msgs/Point target_pos      # 全局 ENU 目标坐标 [x, y, z]
float32 duration                    # 期望飞行时间 (s)
string motion_style                 # "smooth" / "normal" / "aggressive"
float32 safety_factor               # IAPF 避障系数 (0=关闭)
```

### UAVStatus

```text
uint8 uav_id
bool is_hover_stable                # 到达目标且稳定悬停时为 true
```

## 数据流

```
LLM API → JSON 蓝图
    ↓
FormationGenerator（坐标生成）
    ↓
TopologyAllocator（匈牙利防交叉分配）
    ↓
UAVSwarmCommand → /uav{N}/swarm_command
    ↓
MinimumJerkTrajectory（轨迹规划）
    ↓
PX4 Offboard 位置控制（NED 坐标）
    ↓
Gazebo 物理仿真
    ↓
UAVStatus + ENU odom → 调度器闭环反馈
```

## 已知限制

1. **Z 轴收敛速度**：PX4 下降速率受限（约 1.5 m/s），Z 轴向上过冲后收敛较慢（~0.3m 稳态误差），由放宽后的悬停阈值（0.3m）覆盖。
2. **Gazebo Classic 性能**：10 机时 RTF 可能低于 1.0，建议 5-8 机确保实时仿真。
3. **LLM API 依赖**：需网络连接和有效 API Key（`no_location.py` 中配置）。
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
