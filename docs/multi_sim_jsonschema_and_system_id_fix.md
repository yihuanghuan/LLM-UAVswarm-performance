# 多机仿真解析依赖与 PX4 目标系统修复

## 背景

按 README 的多机仿真流程启动第三个 Python 终端并输入自然语言编队指令时，调度节点可能报错：

```text
第2次解析失败：缺少 jsonschema 依赖，请安装 python3-jsonschema 或在虚拟环境中执行 pip install jsonschema
```

修复该依赖后，多机控制链路还暴露出 PX4 多实例中 `VehicleCommand.target_system` 默认值不匹配的问题，导致部分多机实例无法可靠响应解锁和 Offboard 指令。

## 修改内容

1. 在 README 的 Python 虚拟环境依赖安装命令中加入 `jsonschema`，保证按文档新建环境后可直接使用 LFS schema 校验逻辑。
2. 在当前工作区的 `llm_env` 中安装 `jsonschema`，修复现有环境的运行错误。
3. 为 `ladrc_position_controller_node` 增加 `px4_target_system` 参数，并在发布 `VehicleCommand` 时使用该参数设置 PX4 目标系统 ID。
4. 在 `swarm_launch.py` 中为多机实例设置 `px4_target_system = uid + 1`，匹配 `sitl_multiple_run.sh` 中 instance N 对应 `MAV_SYS_ID=N+1` 的行为。

## 验证记录

按 README 多机仿真流程启动：

- `MicroXRCEAgent udp4 -p 8888`
- `./Tools/simulation/gazebo-classic/sitl_multiple_run.sh -m iris -n 5`
- `ros2 launch ladrc_controller swarm_launch.py uav_ids:=[1,2,3,4,5]`
- `python3 -m location_allocate.location_allocate`

输入自然语言指令：

```text
无人机1到5号机以[2,9,3]为中心，变换成圆形编队，半径为3米，限时12秒
```

验证结果：

- LLM 解析第一次调用即通过 JSON schema 校验，不再出现 `jsonschema` 缺失错误。
- 调度节点成功向 UAV1-UAV5 发布 `swarm_command`。
- PX4 多机实例均进入 armed/offboard 状态，其中 `/px4_1` 到 `/px4_5` 的 `system_id` 分别为 2 到 6。
- UAV2-UAV5 能够到达目标并报告悬停稳定。

备注：本轮验证中 PX41 的运动表现存在单实例异常，按用户确认不纳入本次问题继续处理。
