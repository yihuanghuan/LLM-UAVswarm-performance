# 10. 实验 8：IAPF 避障仿真对比

## 目的

支撑安全层：

```
IAPF local safety modulation 能提高最小机间距，减少近距离风险。
```

---

## 实验场景

![image.png](%E5%AE%9E%E9%AA%8C/image.png)

至少做四类：

| 场景 | 说明 |
| --- | --- |
| head-on crossing | 两机同高度相向交叉 |
| multi-UAV dense formation | 多机聚拢成小半径圆形 |
| vertical interaction | 一机上方/下方穿越 |
| grouped reconfiguration | 两组无人机同时变阵 |

---

## Baseline

| 方法 | 说明 |
| --- | --- |
| No avoidance | 无避障，仅仿真中做 |
| Classic APF | 标准人工势场 |
| Ours: IAPF position modulation | 当前安全层 |
| Ours + safety-aware assignment | 分配层和 IAPF 共同作用 |

---

## 收集数据

| 数据 | 说明 |
| --- | --- |
| pairwise distance over time | 任意两机距离 |
| minimum inter-agent distance | 全程最小机间距 |
| safety violation count | 小于安全阈值次数 |
| near-miss duration | 低于阈值附近的持续时间 |
| IAPF activation time | 避障激活时长 |
| trajectory deviation | 避障带来的轨迹偏移 |
| mission success rate | 任务成功率 |
| recovery time | 避障后恢复轨迹时间 |
| local minima / stall events | 是否出现卡死 |

---

## 展示形式

| 图/表 | 内容 |
| --- | --- |
| Line plot | pairwise distance over time |
| Bar chart | safety violation count |
| Box plot | minimum distance 分布 |
| 3D trajectory plot | 有/无 IAPF 的轨迹对比 |
| Table | success rate / min distance / recovery time |
