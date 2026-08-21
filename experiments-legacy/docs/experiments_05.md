# 7. 实验 5：Minimum Jerk 轨迹生成对比

## 目的

证明你的轨迹层不是随便插值，而是：

```
在 LFS 时间边界约束下生成平滑、同步、可执行的轨迹。
```

---

## 实验设计

选固定起点/终点组合，比较不同轨迹生成方式。

### Baseline

| 方法 | 说明 |
| --- | --- |
| Step setpoint | 直接跳目标点 |
| Linear interpolation | 线性插值 |
| Trapezoidal velocity | 梯形速度 |
| Minimum Jerk | 你的方法 |

---

## 收集数据

| 数据 | 说明 |
| --- | --- |
| position reference | 位置参考 |
| velocity reference | 速度参考 |
| acceleration reference | 加速度参考 |
| jerk | jerk 曲线 |
| max velocity | 最大速度 |
| max acceleration | 最大加速度 |
| integrated squared jerk | 平滑性 |
| synchronization error | 多机到达时间误差 |
| final position error | 终点误差 |

---

## 展示形式

| 图/表 | 内容 |
| --- | --- |
| Line plot | position / velocity / acceleration / jerk 曲线 |
| Table | max acc / max jerk / integrated jerk |
| Bar chart | 不同轨迹方法平滑性对比 |
| 3D trajectory plot | 多机同步轨迹 |
