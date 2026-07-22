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
