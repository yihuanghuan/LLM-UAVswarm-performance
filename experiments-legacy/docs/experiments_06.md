# 8. 实验 6：Gazebo 中的轨迹跟踪对比

## 目的

证明 Minimum Jerk + LADRC 在仿真中可以实际跟踪，而不是只有参考轨迹好看。

---

## 实验设计

在 Gazebo 中执行单机和多机轨迹：

| 场景 | 说明 |
| --- | --- |
| single-UAV point-to-point | 单机点到点 |
| 5-UAV circle formation | 5机圆形 |
| 8-UAV line-to-circle | 8机变阵 |

---

## Baseline

| 方法 | 说明 |
| --- | --- |
| PX4 default position setpoint only | 只发目标点 |
| Linear reference + controller | 线性参考 |
| Minimum Jerk + LADRC | 你的方法 |

---

## 收集数据

| 数据 | 说明 |
| --- | --- |
| `p_ref(t)` | 参考位置 |
| `p_actual(t)` | 实际位置 |
| tracking RMSE | 跟踪均方根误差 |
| max tracking error | 最大误差 |
| settling time | 稳定时间 |
| overshoot | 超调 |
| velocity / acceleration | 速度加速度 |
| arrival time | 到达时间 |

---

## 展示形式

| 图/表 | 内容 |
| --- | --- |
| 3D plot | 参考轨迹 vs 实际轨迹 |
| Line plot | tracking error over time |
| Table | RMSE / max error / settling time |
| Box plot | 多次 trial 的 RMSE 分布 |
