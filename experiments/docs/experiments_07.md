# 9. 实验 7：semantic-conditioned LADRC 动态响应实验

## 目的

支撑 Contribution 3：

```
自然语言中的 smooth/aggressive 不是标签，而是会改变真实/仿真的物理响应。
```

---

## 实验设计

在 Gazebo 中对同一段位移分别执行：

```
smooth
normal
aggressive
```

每组重复：

```
至少 5 次
```

---

## Baseline

| 方法 | 说明 |
| --- | --- |
| Fixed LADRC gain | 不随 motion_style 改变 |
| Ours: semantic-conditioned LADRC | 按 motion_style 调节带宽 |

---

## 收集数据

| 数据 | 说明 |
| --- | --- |
| motion_style | smooth / normal / aggressive |
| gain_multiplier | 0.7 / 1.0 / 1.5 |
| peak velocity | 峰值速度 |
| peak acceleration | 峰值加速度 |
| jerk | jerk |
| settling time | 收敛时间 |
| tracking RMSE | 跟踪误差 |
| overshoot | 超调 |
| pitch / roll | 姿态响应 |

---

## 展示形式

| 图/表 | 内容 |
| --- | --- |
| Line plot | smooth / normal / aggressive 位置响应 |
| Line plot | 速度和加速度曲线 |
| Line plot | pitch / roll 曲线 |
| Table | mean ± std 指标统计 |
| Box plot | 多次重复实验的 peak velocity / settling time |
