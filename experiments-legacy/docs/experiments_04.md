# 6. 实验 4：目标分配 baseline 对比

## 目的

支撑 Contribution 2：

```
安全感知拓扑分配比普通目标分配更适合多机变阵。
```

---

## 实验设计

在 Gazebo 前先做离线分配实验。
随机生成多组 UAV 起点和目标阵型：

| 场景 | UAV 数 |
| --- | --- |
| small | 3 |
| medium | 5 |
| large | 8 |
| dense | 8，目标半径较小 |
| crossing-prone | 起点和目标相对反向 |

每个场景至少 50–100 次随机测试。

---

## Baseline

| 方法 | 说明 |
| --- | --- |
| Random | 随机分配 |
| Nearest Neighbor | 贪心最近目标 |
| Hungarian-Distance | 仅按总距离进行 Hungarian 分配 |
| Legacy Weighted-Sum Safety-Aware | 历史 weighted-sum allocator，仅用于复现实验 |
| Ours: Lexicographic Safety-Aware Assignment | Hungarian-Distance 初始化，加 pairwise target-swap local refinement |

当前 Ours 按以下三元组进行严格的 lexicographic 最小化：

```text
(N_hard, J_margin, J_distance)
```

其中 XY crossing 只作为 diagnostic 记录，不是当前 Ours 的优化项。

---

## 收集数据

| 数据 | 说明 |
| --- | --- |
| total path length | 所有 UAV 轨迹长度之和 |
| average path length | 平均单机路径 |
| crossing count | 轨迹交叉次数 |
| min inter-agent distance | 名义轨迹最小机间距 |
| safety violation count | 小于安全阈值次数 |
| assignment compute time | 分配耗时 |
| arrival time variance | 到达时间方差 |
| failed assignment ratio | 不安全分配比例 |

---

## 展示形式

| 图/表 | 内容 |
| --- | --- |
| Table | 各方法平均路径、交叉次数、最小距离、计算时间 |
| Box plot | 不同方法 min distance 分布 |
| Bar chart | crossing count 对比 |
| Qualitative figure | 同一场景下不同方法的路径示意 |
| Pareto plot | path length vs min distance |
