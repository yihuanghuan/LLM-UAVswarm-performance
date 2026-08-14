# 三项 P0 最小修复与分层验收报告

## 1. 结论

基于 `main@e550e15f` 完成了 `fix 3 P0 problems.md` 要求的最小必要修复。LLM parser、PX4 启动闭环和稳定的 `px4_position` 全链路已恢复：4/4 条英文回归指令可解析，单机与 8 机 PX4 cold start 均为 3/3 成功，一次真实 8 UAV 英文自然语言到圆形编队完成的全链路实验成功。

`ladrc_acceleration` 仍是 blocker，且没有在本轮擅自修改 LADRC 参数或公式。按约定的“每层 3 次、3/3 才升级”门禁，单 UAV 层 0/3 通过，因此停止了 2/4/8 UAV LADRC 升级实验。当前默认/推荐模式继续保持为 `px4_position`，LADRC 路径完整保留并可显式开启。

## 2. 根因与最小修复

### P0-1：LLM JSON 协议与 parser

根因是 parser 用跨全文的贪婪 `\{.*\}` 抽取对象；当 provider 返回 `<think>` 且思考内容含伪 JSON 时，会拼出多个对象并解码失败。3 次重试重复相同失败路径。

修复内容：

- Candidate prompt 增加零容忍输出协议，并在 `Output:` 前再次提醒只输出一个 JSON object。
- 删除任意文本中的对象扫描。统一 normalization 只允许 trim、删除一个完整的前置 `<think>...</think>` block，以及去掉恰好包住整份回答的 `json` code fence；随后直接 `json.loads` 并要求顶层为 object。
- Candidate 与 legacy baseline 共用同一 normalization 和 `format_compliant` 定义。
- 保留原指标并新增 `format_compliant`；每次调用的原始 final content 写入 `logs/llm_raw_responses.jsonl`，不记录 API key。
- 增加纯 JSON、think wrapper、完整 code fence、普通解释、多对象、think 内伪 JSON 等固定回归测试。

### P0-2：ARM/OFFBOARD 状态机

根因是原实现按固定延时打印“解锁成功/Offboard 已激活”，既不订阅 `VehicleStatus`，也不在切换前发送完整合法的 setpoint，任务计时可能在 PX4 未 ready 时提前开始。

修复内容：

- 每机订阅并正确 remap `fmu/out/vehicle_status`，使用消息常量判断 armed 与 offboard。
- 启动流程改为 `WAIT_ODOM -> PRESTREAM -> WAIT_CONFIRMATION -> RUNNING/FAILED`。
- 在请求模式前预发送 1.5 s 的 `OffboardControlMode + TrajectorySetpoint`：position 模式保持当前点；acceleration 模式禁用 position/velocity 并发送零加速度安全值。
- ARM 与 OFFBOARD 每 1 s 最多重试 5 次，并设置 30 s 总预算；无法确认时进入显式 FAILED，永不伪装成 RUNNING。
- ready 前只缓存“最新一条合法命令”；收到 armed+offboard 双确认后才激活命令并设置 `command_start_time`。

### P0-3：LADRC acceleration 可靠性边界

根因之一是每次新任务和 idle hover 都会无条件把 LESO 重置到 `(position, 0, 0)`，破坏悬停到任务的连续估计；旧握手又混淆了启动失败和控制失败。

修复内容：

- 全链路默认改为 `px4_position`，显式 `control_mode:=ladrc_acceleration` 仍可运行。
- LESO 只在首次有效 odometry 到达时初始化，速度使用实测值；删除新任务和 idle hover 的 observer reset。
- 没有修改 `omega_c/omega_o/b0`、LESO/LSEF 数学、Minimum Jerk 或 IAPF 核心算法。

## 3. 代码与单元测试

主要修改文件：

- `location_allocate/prompts/paper_candidate_en_v2_system.txt`
- `location_allocate/location_allocate/{paper_candidate_parser.py,strict_json_normalizer.py,raw_response_logger.py,llm_parse_logger.py}`
- `location_allocate/location_allocate/legacy/parser_v1.py`
- `location_allocate/test/test_candidate_parser.py`
- `experiments/scripts/eval_llm_parser.py`
- `minisnap_LADRC/ladrc_controller/include/ladrc_controller/startup_state_machine.hpp`
- `minisnap_LADRC/ladrc_controller/src/ladrc_position_controller_node.cpp`
- `minisnap_LADRC/ladrc_controller/{launch,config,test,CMakeLists.txt}` 相关启动默认值、remap 和测试
- `README.md`

`colcon build --packages-select location_allocate ladrc_controller --symlink-install` 成功。`colcon test` 汇总为 179 tests、0 errors、0 failures、1 skipped；跳过项是仓库原有 copyright 占位测试。新增启动状态机 4 个 GTest 全部通过。colcon 扫描工作区内 `llm_env` 时会输出 numpy 示例缺少 Cython 的 package-discovery 警告，但两个目标包构建和测试均成功。

## 4. LLM 四条在线英文回归

模型为 `MiniMax-M2.7-highspeed`。四条指令均在第 1 次调用后通过严格 JSON parse 与 Candidate schema。表中的 `field_accuracy=1.0` 沿用项目现有的 schema/语义完整性二值代理，不是与人工 gold fields 对齐后的字段准确率。

| 指令 | 格式合规 | 有效 JSON | Schema | field_accuracy | 延迟 | tokens (prompt/completion) | retry | error |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| 单圆形 | 0 | 1 | 1 | 1.0 | 14.188 s | 1812 / 863 | 0 | - |
| 同义单圆形 | 0 | 1 | 1 | 1.0 | 33.019 s | 1832 / 1957 | 0 | - |
| 顺序直线→圆形 | 0 | 1 | 1 | 1.0 | 32.054 s | 1847 / 2019 | 0 | - |
| 并行双组→合并 | 0 | 1 | 1 | 1.0 | 32.753 s | 1875 / 2056 | 0 | - |

`format_compliant=0/4` 表明 provider 原始 final content 仍含 `<think>` 外围包装，prompt 协议遵从性没有改善；`valid_json/schema_valid=4/4` 表明统一的极薄 wrapper normalization 可去掉完整包装，且没有从任意解释文字中猜取 JSON。与修复前 0/4、12/12 次解码失败相比，parser 阻断已消除。

## 5. PX4 cold-start 验收

### 单机

执行 3 次完整 Gazebo/PX4/控制节点冷启动，结果 3/3。每次都先获得 odometry、预发送约 1.5 s，然后在第 1 次 ARM/OFFBOARD 请求后约 0.1 s 收到 `VehicleStatus` 双确认，之后才打印进入 RUNNING。

### 8 机

执行 3 次完整 8 PX4 + 8 控制节点 cold start，结果 3/3；每次最终 8/8 的 `arming_state=ARMING_STATE_ARMED` 且 `nav_state=NAVIGATION_STATE_OFFBOARD`。所有节点均在实际双确认后才进入 RUNNING，没有固定时间“假成功”。个别实例 odometry 晚到时会继续等待并独立完成预发送，不影响其他实例。

第三次验收还独立读取了 8 个 `/px4_N/fmu/out/vehicle_status`，均为 `arming_state=2`、`nav_state=14`，对应消息常量 ARMED/OFFBOARD。

## 6. px4_position 8 UAV 全链路

在第三次 8 机 cold start 的真实 Gazebo/PX4 栈中，从交互入口输入：

`Have UAVs 1 through 8 form a circle of radius 4 meters centered at [0, 13.5, 5] in 12 seconds using normal motion and safety factor 1.0.`

链路实际经过 LLM Candidate v2.1、Validator/Resolver、Circle Geometry、Safety-aware Allocator、Execution Profile、Minimum Jerk、8 个 PX4 position controller 和 8 机完成反馈。LLM 调用为一次成功，延迟 17.366 s；从 Candidate 开始执行到 `Candidate mission 1 completed` 约 15.7 s，总交互耗时约 33.0 s。8/8 UAV 满足完成判据，最终控制日志中的位置误差约为厘米到 0.1 m 量级。该实验通过，说明稳定 baseline 的完整功能已恢复。

## 7. ladrc_acceleration 分层验收

门禁是每层 3 次且必须 3/3 才升级。

| 单 UAV 试次 | startup | 任务 | 50 s 稳定完成 | 结论 |
|---|---|---|---:|---|
| L1 | armed+offboard confirmed | cold hover → `[0,3,2]` 三轴起飞 | 否 | 控制未稳定 |
| L2 | armed+offboard confirmed | cold hover → `[0,3,2]` 三轴起飞 | 否 | 控制未稳定 |
| L3 | offboard confirmed；ARM 5 次未确认 | 未启动任务 | 否 | 正确进入 STARTUP_FAILED |

L1/L2 的 ROS bag 分别保存了 3852/3803 条 `control_tracking_debug`。任务阶段统计如下：

| 指标 | L1 | L2 |
|---|---:|---:|
| 最大位置误差 | 0.451 m | 0.830 m |
| 最大实际速度 | 1.813 m/s | 2.630 m/s |
| LADRC 任一轴限幅样本占比 | 70.95% | 2.52% |
| 最后 10 s 平均位置误差 | 0.204 m | 0.039 m |
| 最后 10 s 平均速度 | 1.114 m/s | 0.442 m/s |
| 最终位置误差 | 0.221 m | 0.023 m |
| 最终速度 | 0.883 m/s | 0.440 m/s |

两次最终位置误差都可进入 0.3 m 带，但速度持续高于 0.3 m/s 稳定阈值，因此任务未完成。L1 的 70.95% 限幅占比和 1.114 m/s 末段平均速度是持续振荡/饱和的直接证据；L2 的位置已很小但末段速度仍为 0.442 m/s。L3 则证明新的闭环状态机能把真实 ARM 失败隔离出来。

由于单 UAV 结果为 0/3，按门禁未执行 2 UAV、4 UAV 和 8 UAV circle，避免把已知不稳定控制路径扩展到集群。未进行任何未经验证的 LADRC 参数调整。

## 8. 最终评估与剩余 blocker

- LLM parser P0：修复通过。provider 原始格式仍不合规，但能被统一、有限、可审计的 wrapper normalization 处理。
- ARM/OFFBOARD P0：反馈闭环与失败隔离修复通过；单机与 8 机 baseline cold start 均 3/3。LADRC 第三次启动暴露一次真实 ARM 失败，系统正确阻止了任务执行。
- 全链路 baseline：通过。当前推荐运行方式为 `px4_position`。
- LADRC acceleration：仍为 blocker。证据指向单机任务末段速度不收敛、试次间饱和比例差异大，且存在一次有限重试内 ARM 未确认。下一步应单独做控制器诊断与参数实验设计；本轮不应凭一次结果修改控制公式或带宽参数。
