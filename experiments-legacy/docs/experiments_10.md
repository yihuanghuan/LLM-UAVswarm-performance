# 12. 实验 10：系统级 8 机 Gazebo controlled evaluation

## 目的

把原本的 8 机仿真从 demo 升级为 controlled evaluation。

---

## 任务类型

| 任务 | 说明 |
| --- | --- |
| simple formation | 8机圆形 |
| sequential transformation | 直线 → 圆形 |
| grouped formation | 1-5号圆形，6-8号直线 |
| dense formation | 小半径圆形，触发避障 |
| mixed command | 简单 + 复杂组合 |

---

## 每类任务重复次数

建议：

```
每类 5 次
```

最低：

```
每类 3 次
```

---

## 收集数据

| 数据 | 说明 |
| --- | --- |
| end-to-end latency | 从输入指令到命令下发 |
| mission completion time | 任务完成时间 |
| success rate | 成功率 |
| tracking RMSE | 跟踪误差 |
| arrival time variance | 到达同步性 |
| min inter-agent distance | 安全性 |
| crossing count | 拓扑安全 |
| IAPF activation count | 避障触发次数 |
| CPU / RTF | 仿真实时性 |
| LLM parsing success | LLM 稳定性 |

---

## 展示形式

| 图/表 | 内容 |
| --- | --- |
| 3D trajectory plot | 每类任务轨迹 |
| Table | 任务级指标汇总 |
| Box plot | 多次 trial 的 RMSE / min distance |
| Timeline figure | LLM解析 → 分配 → 轨迹 → 到达 |
| Video frames | 关键任务截图 |
