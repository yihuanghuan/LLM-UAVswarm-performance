# 4. 实验 2：LFS 中间表示消融实验

## 目的

证明你的中间层不是普通 JSON，而是：

```
可验证、可编译、可执行的 formal task representation。
```

## 实验设计

对同一批自然语言指令，比较：

| 方法 | 说明 |
| --- | --- |
| Direct waypoint output | LLM 直接输出 UAV-to-goal |
| Task JSON without schema | 只用 JSON，不验证 |
| LFS with schema | 你的方法 |
| LFS with schema + semantic validator | 完整方法 |

---

## 评估指标

| 指标 | 说明 |
| --- | --- |
| executable rate | 输出能否直接被调度器执行 |
| correction / retry count | 需要重试几次 |
| invalid UAV ratio | UAV 编号错误比例 |
| invalid formation ratio | 编队类型错误比例 |
| missing field ratio | 缺字段比例 |
| compilation success | 能否生成目标点 |

---

## 展示形式

| 图/表 | 内容 |
| --- | --- |
| Table | 不同表示方式的可执行率 |
| Bar chart | missing field / invalid field 错误比例 |
| Flow figure | Natural Language → LFS → Compiler → Goals |

---

## 需先改进的部分

`eval_lfs_compiler.py` 当前仅覆盖：
- Schema 合法/非法测试
- 语义合法/非法测试
- 标准 LFS 编译
- Legacy 格式兼容

仅用于验证工程实现正确性，**不足以支撑文档要求的消融对比**：
- Direct waypoint
- Task JSON without schema
- LFS with schema
- LFS + semantic validator

可选方案：
- 新增脚本 `eval_lfs_ablation.py`
- 或扩展实验1，增加 `--representation-mode` 参数切换表征形式

> 结论：现有脚本偏向单元测试，并非论文所需完整消融实验框架。

需要我把这段整理成正式的**实验待改进条目（可直接粘贴进论文工作展望 / 实验计划）**吗？
