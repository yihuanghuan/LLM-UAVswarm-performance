# 3. 实验 1：LLM 解析可靠性测试

## 目的

支撑 Contribution 1：

```
LFS 是一个低延迟、可验证、稳定的语言到任务中间表示。
```

## 实验设计

构造一个自然语言指令测试集：

| 类型 | 数量建议 | 示例 |
| --- | --- | --- |
| simple | 20 | 5架无人机组成圆形 |
| sequential | 20 | 先直线，后圆形 |
| grouped | 20 | 1-3号圆形，4-5号直线 |
| style-conditioned | 20 | 平稳/快速/激进 |
| safety-conditioned | 10 | 加强避障 |
| invalid / ambiguous | 20 | 缺少编队类型、非法 UAV ID |

总数建议：

```
100 条左右
```

如果时间不够，至少 50 条。

---

## Baseline

| 方法 | 说明 |
| --- | --- |
| Plain prompt JSON | 不使用严格 schema 的普通 JSON prompt |
| Few-shot JSON | 当前类似方案 |
| Ours: LFS + schema validation | 你的方法 |
| Dense waypoint generation | 让 LLM 直接输出每架无人机目标点或航点 |

---

## 收集数据

| 数据 | 说明 |
| --- | --- |
| `latency_ms` | LLM 响应时间 |
| `prompt_tokens` | 输入 token |
| `completion_tokens` | 输出 token |
| `valid_json` | 是否合法 JSON |
| `schema_valid` | 是否通过 LFS schema |
| `field_accuracy` | 字段准确率 |
| `retry_count` | 重试次数 |
| `error_type` | 错误类型 |

---

## 展示形式

| 图/表 | 内容 |
| --- | --- |
| Table 1 | 各方法的 JSON 成功率、schema 成功率、字段准确率、平均延迟 |
| Bar chart | 不同方法 token 数对比 |
| Box plot | 不同指令复杂度下的 latency 分布 |
| Stacked bar | 错误类型分布 |
| Line plot | 指令复杂度 vs 解析成功率 |


# 现存两处核心问题
## 1. 未实现文档定义的四种Baseline方案
现有脚本硬编码调用 `parse_uav_command(...)`，仅支持正式LFS方法进行测试，缺少方法切换入口，无法运行其余基线方案：
- Plain prompt JSON
- Few-shot JSON
- LFS + schema
- Dense waypoint generation

当前执行逻辑为单一固定路径，不存在 `--method` / `--prompt-mode` 命令行参数用于切换不同提示方案。

## 2. field_accuracy 指标并非真实语义准确率
函数 `estimate_field_accuracy()` 当前逻辑仅统计必填字段存在率：
> 字段存在数量 / 必填字段总数

**缺陷**：仅校验key是否存在，不对比LLM输出内容与人工标注真值。
举例：LLM输出错误中心点坐标，只要`c`字段存在，依旧判定得分满分。

### 改造需求
1. 每条指令样本补充人工真值标签：
```json
{
  "expected_lfs": {
    "U": [1,2,3],
    "F": "Circle",
    "c": [0,0,3],
    "r": 2,
    "T": 5,
    "m": "normal"
  }
}
```
2. 新增精细化评估指标：
- UAV set accuracy（无人机集合准确率）
- formation accuracy（编队构型准确率）
- center error（中心点误差）
- radius error（半径误差）
- duration error（时长误差）
- motion style accuracy（运动模式准确率）
- exact task accuracy（任务完全匹配准确率）

## 配套数据集问题
当前simple指令样本仅3条，样本量不足，无法满足计划要求的 **50–100条** 标注指令。
