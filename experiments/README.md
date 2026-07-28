# 实验 7：Semantic-Conditioned LADRC 动态响应

## 实验目的

验证自然语言中的 `smooth`、`normal`、`aggressive` 是否通过任务条件化
LADRC 带宽改变 Gazebo 中的实际物理响应，而不只是改变消息标签。

本实验比较：

- `fixed_gain`：三种风格均固定 `gain_multiplier=1.0`；
- `task_conditioned`：使用距离、时长和 motion style 共同计算带宽倍率。

两种方法均把 LADRC 输出作为 PX4 位置控制的加速度前馈，关闭 IAPF。

## 实验流程

使用 UAV1 单机冷启动，从约 `[0,3,0]` 飞向 `[6,3,5]`。三条自然语言
指令只改变风格措辞，不显式给出时长；LFS prompt 统一补全为 3 秒。

每个正式 trial 均执行：

1. 冷启动 Micro XRCE-DDS、PX4 SITL、Gazebo 和控制节点；
2. 等待 PX4 armed、OFFBOARD 且非 failsafe；
3. 调用 MiniMax LLM，将自然语言编译为 LFS；
4. 校验 UAV、中心、阵型、时长和 style 是否符合预注册任务；
5. 经过编队坐标生成和分配后发布 ROS 指令；
6. 记录命令后 15 秒的 rosbag，并导出完整 CSV。

固定随机种子 `20260728`，运行
`2 methods × 3 styles × 5 repeats = 30` 个有效 trial。LLM 输出若偏离
预注册任务，原尝试应移入 `rejected/` 后补跑；本次没有发生 gate rejection。

复现命令：

```bash
cd ~/learning/LLM_swarm_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
source llm_env/bin/activate

python src/LLM-UAVswarm-performance/experiments/scripts/run_experiment_07.py \
  --output-dir \
  src/LLM-UAVswarm-performance/experiments/results/experiments_07

python src/LLM-UAVswarm-performance/experiments/scripts/analyze_experiment_07.py \
  src/LLM-UAVswarm-performance/experiments/results/experiments_07
```

## 实验结果

所有数值为 5 次独立冷启动的 `mean ± sample std`。

| 方法 | style | gain | peak velocity (m/s) | peak acceleration (m/s²) | peak jerk (m/s³) | tracking RMSE (m) | overshoot (m) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| fixed | smooth | 1.000 ± 0.000 | 3.668 ± 0.102 | 9.246 ± 0.149 | 136.071 ± 22.481 | 1.253 ± 0.021 | 0.063 ± 0.010 |
| fixed | normal | 1.000 ± 0.000 | 3.590 ± 0.079 | 9.247 ± 0.881 | 147.319 ± 37.304 | 1.184 ± 0.053 | 0.087 ± 0.020 |
| fixed | aggressive | 1.000 ± 0.000 | 3.637 ± 0.145 | 9.171 ± 0.270 | 134.640 ± 16.469 | 1.218 ± 0.087 | 0.074 ± 0.021 |
| conditioned | smooth | 1.048 ± 0.006 | 3.569 ± 0.104 | 10.752 ± 0.943 | 141.355 ± 26.908 | 1.176 ± 0.083 | 0.093 ± 0.009 |
| conditioned | normal | 1.114 ± 0.005 | 3.731 ± 0.170 | 9.594 ± 0.258 | 133.724 ± 31.490 | 1.232 ± 0.081 | 0.080 ± 0.015 |
| conditioned | aggressive | 1.302 ± 0.006 | 3.736 ± 0.209 | 9.862 ± 0.386 | 120.429 ± 5.621 | 1.209 ± 0.105 | 0.123 ± 0.096 |

30 次 trial 均未在 15 秒观测窗口内连续 1 秒满足
`position error < 0.3 m` 且 `speed < 0.3 m/s`，因此 settling time 按预注册
规则保留为 N/A，没有事后放宽阈值。

LLM 共发生 40 次 API 尝试：30 次 schema-valid，10 次因响应尾部存在额外
JSON 而产生 `JSONDecodeError`，均在既有三次重试范围内恢复。30 个最终
解析结果全部通过任务 gate。

## 结果分析

数据支持“motion style 会改变物理响应”这一有限结论，但不支持
“带宽越高就必然更平滑或更快稳定”：

- aggressive 条件化倍率比 baseline 高约 30.2%，对应 peak velocity
  增加 2.7%、peak acceleration 增加 7.5%、最大 roll 增加 23.2%、
  最大 pitch 增加 48.5%，说明语义带宽确实进入了真实控制链路；
- normal 的 peak velocity 和 peak acceleration 分别增加约 3.9% 和 3.8%；
- smooth 的 peak velocity 降低约 2.7%、RMSE 降低约 6.1%，但 peak
  acceleration 增加约 16.3%，并非所有平滑性指标都改善；
- aggressive 和 smooth 的超调分别增加约 65.8% 和 48.0%；
- 全部条件均未满足严格 settling 判据，位置曲线显示持续的小幅横向振荡。

因此，本实验确认语义条件化增益不是空标签；同时也暴露出 LADRC 加速度
前馈与 PX4 内部位置环叠加后的振荡问题。后续若要主张“smooth 更平滑”或
“aggressive 更快收敛”，需要重新整定带宽/前馈结构，而不能由本批数据推出。

完整原始数据、汇总表和图位于
`experiments/results/experiments_07/`。
