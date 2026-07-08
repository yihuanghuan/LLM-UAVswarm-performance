# 实验评估工具链修改记录

## 修改范围

本次修改只新增和调整 `experiments/` 下的论文实验评估工具链，没有修改现有控制节点、调度节点、消息定义或核心控制算法。

## 新增能力

- 新增 `eval_assignment_offline.py`，离线比较 random、nearest_neighbor、hungarian_distance、safety_aware_hungarian 四种分配策略。
- 新增 `eval_trajectory_profiles.py`，生成 step、linear、trapezoidal、minimum_jerk 的轨迹时序和指标。
- 重构 `analyze_pairwise_distance.py`，固定输入为 `timestamp,uav_id,x,y,z`，固定输出两两距离时序和安全汇总。
- 新增 `eval_iapf.py`，按四种 IAPF 配置汇总安全、轨迹和任务结果。
- 新增 `eval_semantic_control.py`，按 `motion_style` 汇总 LADRC 语义控制适应日志。
- 新增 `collect_rosbag_topics.sh`，通过 ROS 2 bag 正则记录 `/uav*/odom`、`/uav*/status`、`/uav*/trajectory_metrics`、`/uav*/control_adaptation`、`/uav*/swarm_command`。
- 新增 `plot_all.py`，从 `experiments/results/*.csv` 生成论文 PNG/PDF 图。
- 更新 `experiments/README.md`，补充脚本用途、输入输出、固定字段和示例命令。

## 验证记录

- `eval_assignment_offline.py --trials 2` 已验证可生成固定字段分配结果。
- `eval_trajectory_profiles.py` 已验证可生成 summary 和 timeseries CSV。
- `analyze_pairwise_distance.py` 已用临时 odom CSV 验证固定输入输出。
- `eval_semantic_control.py` 已用 `logs/control_adaptation_log.csv` 验证分组统计。
- `eval_iapf.py` 已用临时 pairwise、trajectory、mission CSV 验证四方法汇总。
- `collect_rosbag_topics.sh` 已通过 `bash -n` 语法检查，并确认本机 ROS 2 Humble 支持 `ros2 bag record --regex`。
- `plot_all.py --all` 已用临时结果目录验证 7 类图均可生成 PNG/PDF。

## 原子提交

- `abfc5e6 Add offline assignment evaluation`
- `afca297 Add trajectory profile evaluation`
- `3e4eee3 Update pairwise distance analysis pipeline`
- `d6bf657 Add IAPF and semantic control summaries`
- `89155a1 Add rosbag collection and plotting tools`

## 后续完整系统验证

完成文档提交后，按项目 README 执行：

```bash
cd ~/learning/LLM_swarm_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install
```

然后启动单机 PX4 Gazebo 验证：

```bash
MicroXRCEAgent udp4 -p 8888
cd ~/PX4-Autopilot && make px4_sitl gazebo-classic
source ~/learning/LLM_swarm_ws/install/setup.bash
ros2 launch ladrc_controller swarm_launch.py uav_ids:=[0]
```

最后发布 README 中的 `/uav0/swarm_command` 示例，确认原控制链路仍可启动和接收指令。
