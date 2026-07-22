# 11. 实验 9：安全层消融实验

## 目的

证明最终系统不是靠某一个模块偶然成功，而是每一层都有贡献。

---

## 消融组合

| Variant | LFS | safety assignment | Minimum Jerk | semantic LADRC | IAPF |
| --- | --- | --- | --- | --- | --- |
| V1 | ✅ | ❌ | ✅ | ✅ | ✅ |
| V2 | ✅ | ✅ | ❌ | ✅ | ✅ |
| V3 | ✅ | ✅ | ✅ | ❌ | ✅ |
| V4 | ✅ | ✅ | ✅ | ✅ | ❌ |
| Full | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## 收集数据

| 数据 | 说明 |
| --- | --- |
| success rate | 成功率 |
| tracking RMSE | 跟踪误差 |
| min distance | 最小机间距 |
| crossing count | 交叉次数 |
| arrival variance | 到达时间方差 |
| mission duration | 总任务耗时 |
| failure reason | 失败原因 |

---

## 展示形式

| 图/表 | 内容 |
| --- | --- |
| Ablation table | 每个模块去掉后的指标下降 |
| Radar chart | 多指标对比 |
| Bar chart | 成功率 / 最小距离 / RMSE |
