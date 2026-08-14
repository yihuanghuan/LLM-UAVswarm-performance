# IAPF 实验工具与前馈开关

当前 IAPF 对比实验提供两类能力：

1. 离线统计两两无人机距离、全局最小距离、安全冲突次数和危险接近持续时间。
2. 通过 `avoidance_mode` 一键切换位置 IAPF 与位置+加速度 IAPF。

### 离线距离分析脚本

新增脚本：

```text
experiments/scripts/analyze_pairwise_distance.py
```

输入为 `timestamp,uav_id,x,y,z` 字段的 odom CSV。

输出：

- `pairwise_distance_timeseries.csv`
- `pairwise_distance_summary.csv`

示例：

```bash
python3 experiments/scripts/analyze_pairwise_distance.py \
  --input experiments/logs/odom.csv \
  --output-dir experiments/results \
  --safety-threshold 1.5 \
  --experiment-id exp001
```

### IAPF 模式 launch 开关

当前入口使用 `avoidance_mode`：

```text
avoidance_mode
```

可选 `off`、`classic_position`、`iapf_position`、`iapf_dual`。对比实验可直接覆盖：

```bash
ros2 launch ladrc_controller swarm_launch.py uav_ids:=[1,2,3,4] avoidance_mode:=off
ros2 launch ladrc_controller swarm_launch.py uav_ids:=[1,2,3,4] avoidance_mode:=iapf_position
ros2 launch ladrc_controller swarm_launch.py uav_ids:=[1,2,3,4] avoidance_mode:=iapf_dual
```

旧参数 `enable_iapf_accel_feedforward` 只为兼容历史 launch 保留，已弃用；不要与
`avoidance_mode` 同时设置。motion-style 本轮实验保持当前 IAPF 算法不变，并选用
无主动避障触发的低冲突几何，避免把 style effect 与 IAPF effect 混淆。
