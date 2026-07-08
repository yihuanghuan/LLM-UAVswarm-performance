# IAPF 实验工具与前馈开关优化

## 背景

`需要修的问题.md` 建议补齐 IAPF 对比实验的两类能力：

1. 离线统计两两无人机距离、全局最小距离、安全冲突次数和危险接近持续时间。
2. 规范 `enable_iapf_accel_feedforward` 的实验切换方式，让位置环 IAPF 与位置+加速度前馈 IAPF 可以一键切换。

## 修改内容

### 离线距离分析脚本

新增脚本：

```text
experiments/scripts/analyze_pairwise_distance.py
```

支持输入：

- `ros2 topic echo --csv /uavN/odom` 导出的单机 CSV
- `tools/trajectory_metrics/rosbag_to_csv.py` 从 `/uav*/odom` 导出的扁平 CSV

输出：

- `min_distance.csv`
- `pairwise_distance_plot.pdf`
- `safety_violation_summary.csv`

示例：

```bash
python3 experiments/scripts/analyze_pairwise_distance.py bag_csv \
  --out-dir pairwise_distance_analysis \
  --safety-distance 1.5
```

### IAPF 加速度前馈 launch 开关

`swarm_launch.py` 和 `ladrc_controller.launch.py` 均新增参数：

```text
enable_iapf_accel_feedforward
```

默认值为 `true`，保持原有行为。对比实验可直接传参覆盖：

```bash
ros2 launch ladrc_controller swarm_launch.py uav_ids:=[1,2,3,4,5] enable_iapf_accel_feedforward:=false
ros2 launch ladrc_controller swarm_launch.py uav_ids:=[1,2,3,4,5] enable_iapf_accel_feedforward:=true
```

## 验证记录

- 使用合成 3 机 `/uav{id}/odom` CSV 验证分析脚本，确认生成 `min_distance.csv`、`pairwise_distance_plot.pdf` 和 `safety_violation_summary.csv`。
- 运行 `python3 -m py_compile` 检查两个 launch 文件语法。
- 运行 `colcon build --symlink-install --packages-select ladrc_controller`，目标包编译成功。
- 运行 `ros2 launch ladrc_controller swarm_launch.py --show-args` 和 `ros2 launch ladrc_controller ladrc_controller.launch.py --show-args`，确认 `enable_iapf_accel_feedforward` 参数可见。
- 按 README 多机流程启动 `MicroXRCEAgent`、5 机 PX4 Gazebo 和 `swarm_launch.py`，并使用 `enable_iapf_accel_feedforward:=false` 覆盖参数。验证 `/uav1` 到 `/uav5` 控制节点参数均为 `False`，`/px4_1` 到 `/px4_5` 均进入 `arming_state: 2`、`nav_state: 14`，且 `failsafe: false`。

备注：colcon 在扫描工作区 `llm_env` 内 NumPy 示例目录时仍会打印 Cython/limited_api 的包识别噪声，但 `ladrc_controller` 目标包构建成功。
