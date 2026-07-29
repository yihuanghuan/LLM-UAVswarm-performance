# Experiment 8 补丁指导：执行层 IAPF 安全兜底验证

## 1. 修改目标

不要继续把 Experiment 8 设计成 IAPF 算法性能竞赛。本实验只验证：

1. 正常安全任务中，IAPF 是否基本不干扰原始轨迹；
2. 当执行延迟、轨迹暂停或位置偏差引入剩余冲突时，IAPF 是否能降低风险；
3. Safety-aware assignment 是否能减少执行层 IAPF 的介入频率和强度。

保留现有结果，但将原来的完全正碰、垂直交换、8 机中心交叉等场景归类为 stress/failure-boundary，不再作为核心主实验。

---

## 2. IAPF 算法补丁


### 2.1 使用相对速度判断接近状态

在邻机状态中增加速度，并计算 closing speed。正在接近时正常施加斥力；已经远离且距离高于违规阈值时，逐渐减弱斥力，避免任务结束后持续排斥。

### 2.2 修正逃逸方向

不要固定向正 Z 方向破局。根据相对位置和相对速度选择一个与冲突方向垂直的确定性逃逸方向，并通过 UAV ID 确保同一对 UAV 获得相反方向。

### 2.3 增加滞回和平滑

新增参数（该指南中的数据仅供参考，你可以调整参数）：

```yaml
iapf_enter_distance: 1.50
iapf_exit_distance: 1.65
iapf_filter_alpha: 0.20
```

要求：

- 进入和退出阈值不同，避免频繁开关；
- 对位置偏置和加速度偏置进行低通平滑；
- 保留现有 epsilon、position/acceleration limit、neighbor freshness 和 debug 日志。

---

## 3. 重新组织实验方法

主实验只保留最终系统配置的开关比较：

```text
IAPF_OFF  : safety-aware assignment + avoidance off
IAPF_ON   : safety-aware assignment + iapf_dual
```

仅在一个两机代表场景中补充小型消融：

```text
off vs iapf_position vs iapf_dual
```

Classic APF、参数灵敏度和现有 M0–M5 全矩阵移到附录或补充结果，不再作为主实验重点。

---

## 4. 新增主实验

### 4.1 Non-intrusive test

使用两个名义轨迹本身安全的任务，例如：

- 宽间距 line → circle；
- 两组无人机平行移动。

比较 IAPF_OFF 和 IAPF_ON，验证：

- IAPF activation ratio 接近 0；
- success rate 不下降；
- path length、completion time 和 formation error 不明显增加。

现有 `dense_feasible` 可以改造成该类实验。

### 4.2 Execution-deviation fallback test

先生成名义安全轨迹，再人为注入可重复执行偏差。至少支持以下三种 disturbance：

```yaml
command_delay:
  uav_id: 1
  delay_sec: 1.0

temporary_hold:
  uav_id: 2
  trigger_time: 2.5
  duration: 0.8

reference_bias:
  uav_id: 3
  start_time: 2.0
  duration: 1.0
  offset: [0.4, 0.0, 0.0]
```

新增三个场景：

1. 两机带时序错开的交叉轨迹；
2. 四机两组交叉；
3. 可行密集编队中的单机局部暂停或偏移。

每个场景使用同一 seed 成对运行 IAPF_OFF 和 IAPF_ON。

### 4.3 Assignment–IAPF complement test

只在目标允许交换的编队重构场景中比较：

```text
distance assignment + IAPF off
distance assignment + IAPF on
safety-aware assignment + IAPF off
safety-aware assignment + IAPF on
```

重点检查 safety-aware assignment 是否降低：

- IAPF activation ratio；
- activation event count；
- mean/max repulsion；
- trajectory deviation；
- risk integral。

不要在固定身份 head-on 场景中比较 safety-aware assignment。

---

## 5. 指标和统计补丁

保留现有指标，并新增：

```text
paired_min_distance_improvement
paired_risk_reduction
fallback_rescue_rate
unnecessary_intervention_rate
intervention_latency
```

定义：

```text
paired_risk_reduction = risk_off - risk_on
fallback_rescue_rate = off 失败但对应 on 安全完成的配对试验数 / off 失败试验数
```

统计方式：

- 连续配对指标：Wilcoxon signed-rank test；
- 配对成功/失败：McNemar test；
- 报告 paired median difference 和 95% bootstrap CI；
- 不再对所有方法做无目的的全量两两比较。

---

## 6. 运行规模

建议正式实验：

```text
Non-intrusive: 2 scenarios × 2 modes × 10 trials = 40
Fallback:      3 scenarios × 2 modes × 10 trials = 60
Complement:    2 scenarios × 4 modes × 10 trials = 80
Stress:        2–4 scenarios × 2 modes × 5 trials = 20–40
```

总计约 200–220 trials。所有 off/on 对必须复用相同初始状态、扰动参数和随机 seed。

---

## 7. 需要修改的文件

Codex 应检查并修改：

```text
experiments/08-iapf/configs/
experiments/08-iapf/scripts/run_experiment.py
experiments/08-iapf/scripts/aggregate_trials.py
experiments/08-iapf/scripts/plot_iapf_results.py
执行层 IAPF 控制节点
IAPF debug message / CSV logger
experiments/08-iapf/README.md
```

完成后新增一份简短报告，说明：

1. 修改了哪些 IAPF 工程逻辑；
2. 新增了哪些 disturbance 和场景；
3. 新旧实验矩阵如何对应；
4. 如何运行 pilot、正式实验和结果聚合；
5. 现有旧结果如何保留并重新归类。
