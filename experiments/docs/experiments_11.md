# 13. 实验 11：鲁棒性压力测试

## 目的

顶会审稿人会关心系统在不理想条件下是否稳定。

---

## 测试维度

| 压力类型 | 方法 |
| --- | --- |
| LLM ambiguity | 输入模糊自然语言 |
| odom noise | 给位置反馈加高斯噪声 |
| communication delay | 对 command 或 odom 加延迟 |
| UAV scale | 3 / 5 / 8 机 |
| dense target | 缩小编队半径 |
| repeated commands | 连续输入多个任务 |

---

## 收集数据

| 数据 | 说明 |
| --- | --- |
| success rate | 成功率 |
| parser retry count | LLM 重试 |
| max tracking error | 最大误差 |
| min distance | 安全距离 |
| timeout rate | 超时率 |
| failure mode | 失败类型 |

---

## 展示形式

| 图/表 | 内容 |
| --- | --- |
| Heatmap | noise/delay vs success rate |
| Line plot | UAV 数量 vs compute time |
| Table | failure mode 统计 |
| Box plot | 延迟条件下的 tracking error |