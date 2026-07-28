# 实验 07 执行记录

## 状态

- 状态：成功完成
- 分支：`exp/07-semantic-ladrc`
- 基础标签：`gazebo-experiment-v1`
- 基础提交：`df5c5bc9b7a1af695c41dea5744bcb546b7f0a47`
- 实现提交：`11b57c5968f0e80956dd671c9a97c4c53f2f533b`
- 执行日期：2026-07-28（Asia/Shanghai）
- 随机种子：`20260728`
- 数据位置：`experiments/results/experiments_07`

## 固定配置

- UAV：UAV1，PX4 instance 1
- 目标：`[6,3,5]`
- 自然语言中不显式给出时长，LFS 默认 `T=3.0 s`
- 观测窗口：命令后 15 秒
- 方法：`fixed_gain`、`task_conditioned`
- 风格：`smooth`、`normal`、`aggressive`
- 重复：每个方法/style 5 次独立冷启动
- LADRC acceleration feedforward：开启
- IAPF acceleration feedforward：关闭
- settling：误差小于 0.3 m 且速度小于 0.3 m/s，连续保持 1 秒
- 分析采样：50 Hz；三阶、11 点 Savitzky–Golay 导数

## 完成情况

- 正式 trial：30/30
- rosbag：30
- topic CSV：210
- rejected 仿真尝试：0
- LLM API 尝试：40
- schema-valid API 响应：30
- 最终 gate 通过：30/30
- 关键 topic 完整性：通过
- fixed gain 全部等于 1.0：通过
- task-conditioned gain 逐条公式校验：通过

## 运行命令

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

## 环境

- Ubuntu 22.04，Linux `6.8.0-124-generic`，x86_64
- ROS 2 Humble
- Python 3.10.12
- GCC/G++ 11.4.0
