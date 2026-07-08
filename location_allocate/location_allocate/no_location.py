#----------------------------------------------命令一 基础时空变阵指令---------------------------------------------------
# 正多边形编队变换，最大数量：>8
# 一字长蛇编队变换，最大数量：>8
#圆形编队变换，最大数量：>8
#隐形指令（散开），最大数量：>8
# test_cmd = "UVA1-6 以[3.4.5]为中心，变换成圆形编队，半径为1.5米，限时3秒"
#起始点为圆形，耗时为8s
# test_cmd = "现在的阵型太密集了，以UVA4为中心，横向拉开距离，变成一字长蛇阵，间距保持在 2 米，限时 3 秒完成"
# 10个UAV,起始点为圆形+矩形，耗时8s

#----------------------------------------------命令二 集群裂变与多目标调度----------------------------------------------------
# test_cmd = "队形一分为二。1到6号机以[3,4,5]为中心变成圆形；7号到10号机在圆形正上方2米形成正方形掩护阵型。两组动作必须在 5 秒内同步完成"
# 输出两任务 耗时 15s(起始点杂乱）,

#----------------------------------------------命令二 连续状态机时序指令----------------------------------------------------
#test_cmd = "准备谢幕表演：首先用 3 秒钟聚拢成一个以[2,2,10]为球形的最紧凑的球形编队并稳定悬停 2 秒钟后，然后全体向外发散，各自用 4 秒时间飞回初始起飞点降落"
#输出两任务（悬停+直接执行），球形为圆+上下两机，10个UAV耗时：起始点是一字排开为25s.
# 原来的指令:准备谢幕表演：首先用 3 秒钟聚拢成一个最紧凑的球形编队；稳定悬停 2 秒钟后；全体向外发散，各自用 4 秒时间飞回初始起飞点降落,ai通过断句会把悬停判给第二个任务







from openai import OpenAI
import re
import json
import time
import os
import uuid
import httpx

from .llm_parse_logger import append_llm_parse_log
from .lfs_validator import (
    estimate_field_accuracy,
    parse_available_uav_ids,
    validate_and_compile_lfs,
)

# -------------------------- 配置项 --------------------------
API_KEY = os.getenv("LLM_API_KEY") or os.getenv("MINIMAX_API_KEY")
BASE_URL = "https://api.minimax.chat/v1"
MODEL_NAME = "MiniMax-M2.7-highspeed"
# -------------------------------------------------------------------------

# ====================== 固定系统Prompt（LFS格式） ======================
SYSTEM_PROMPT = """
# 角色定位
你是无人机集群编队变换专属指令解析专家，唯一职责是将操作人员输入的自然语言指令，严格解析为 Language-to-Formation Specification (LFS) JSON，禁止处理任何与无人机编队任务无关的请求。

# 核心任务
1. 无遗漏、无篡改提取指令中的时间、编队类型、中心、半径/间距、触发条件等核心参数；
2. 严格按【固定LFS-JSON输出规范】生成内容，禁止修改字段名、枚举值；
3. 禁止编造信息，严格遵循预定义知识库；
4. 异常指令必须按规范返回错误码。

# 【LFS任务定义】
单个任务形式化为 tau = (U, F, c, r, T, m, s, q)：
- U：参与无人机编号数组，格式为整数数组，如 [1,2,3]
- F：编队类型，枚举仅限：Circle/Line/Sphere/Free/Triangle/Polygon/Lineup
- c：编队中心，3D坐标数组 [x,y,z]
- r：半径或间距，正数；Circle/Sphere/Polygon/Triangle 表示半径，Line/Lineup 表示机间距
- T：任务时长，单位秒，正数
- m：运动风格，枚举仅限：smooth/normal/aggressive
- s：安全系数，非负数；指令未提及时默认 1.0
- q：触发条件，枚举仅限：direct/hover-and-wait/continuous

# 【字段映射规则】
- 指令出现「圆形」→ F="Circle"
- 指令出现「球形」→ F="Sphere"
- 指令出现「直线、一字长蛇阵、横向拉开、纵向拉开」→ F="Line"
- 指令出现「正三角形」→ F="Triangle"
- 指令出现「正四边形、正多边形」→ F="Polygon"
- 指令出现「回初始点、降落、散开、自由」→ F="Free"
- 指令未明确 UAV 编号时，U 使用 ROS实时情报中的全部可用无人机编号
- 指令未明确中心时，c 默认 [0.0, 0.0, 1.5]
- 指令未明确半径或间距时，r 默认 1.5
- 指令未明确时长时，T 默认 3.0
- 指令未明确运动风格时，m 默认 "normal"
- 指令提到「柔和、平滑、舒缓」时，m="smooth"
- 指令提到「快速、激进、尽快」时，m="aggressive"
- 单任务或立即执行任务默认 q="direct"
- 明确要求到达后悬停等待时，q="hover-and-wait"，并额外输出 wait_time
- 多任务中间途经目标点不停车时，q="continuous"

# 固定LFS-JSON输出规范
【强制输出格式】无论单任务还是多任务，必须统一输出以下外层结构：
{
  "lfs_version": "1.0",
  "tasks": [
    {
      "task_id": 1,
      "U": [1,2,3],
      "F": "Circle",
      "c": [0.0,0.0,1.5],
      "r": 1.5,
      "T": 5.0,
      "m": "normal",
      "s": 1.0,
      "q": "direct"
    }
  ]
}

# 输出铁则（零容忍）
1. 必须输出纯JSON，无任何解释、无markdown、无代码块、无多余符号；
2. 必须统一包裹在 { "lfs_version": "1.0", "tasks": [ ... ] } 内，单任务也必须放在数组里；
3. 禁止输出 task_sequences、uav_allocations、target_pos、global_center、parametric_data 等旧版调度字段；
4. 禁止计算每架无人机目标坐标，只输出抽象任务参数；
5. 禁止输出 schema 中不存在的枚举值。

# 错误处理规则
1. 正常解析：error_code=0，error_msg=""
2. 信息缺失：未明确编队类型、未提供中心坐标，error_code=1
3. 实体不存在：使用了非法枚举值，error_code=2
4. 无关请求：与无人机编队任务无关，error_code=3
5. 解析失败：无法按规范解析，error_code=4
"""

# ====================== Few-Shot 示例（LFS格式） ======================
FEW_SHOT_EXAMPLES = """
【示例1：单任务标准图形】
用户指令：UAV1-6 以[3,4,5]为中心，变换成圆形编队，半径为1.5米，限时3秒
ROS信息：当前可用无人机编号: [1,2,3,4,5,6,7,8,9,10]，总数: 10
输出：
{
  "lfs_version": "1.0",
  "tasks": [
    {
      "task_id": 1,
      "U": [1,2,3,4,5,6],
      "F": "Circle",
      "c": [3.0, 4.0, 5.0],
      "r": 1.5,
      "T": 3.0,
      "m": "normal",
      "s": 1.0,
      "q": "direct"
    }
  ]
}

【示例2：多任务连续执行】
用户指令：准备谢幕表演：首先用 3 秒钟聚拢成一个以[2,2,10]为中心的球形编队，稳定悬停 2 秒钟后，全体向外发散，各自用 4 秒时间飞回初始起飞点
ROS信息：当前可用无人机编号: [1,2,3,4,5,6,7,8,9,10]，总数: 10
输出：
{
  "lfs_version": "1.0",
  "tasks": [
    {
      "task_id": 1,
      "U": [1,2,3,4,5,6,7,8,9,10],
      "F": "Sphere",
      "c": [2.0, 2.0, 10.0],
      "r": 1.5,
      "T": 3.0,
      "m": "normal",
      "s": 1.0,
      "q": "hover-and-wait",
      "wait_time": 2.0
    },
    {
      "task_id": 2,
      "U": [1,2,3,4,5,6,7,8,9,10],
      "F": "Free",
      "c": [0.0, 0.0, 0.0],
      "r": 1.5,
      "T": 4.0,
      "m": "normal",
      "s": 1.0,
      "q": "direct"
    }
  ]
}

【示例3：一字长蛇阵（隐性指令）】
用户指令：现在的阵型太密集了，以[1.0, 4.0, 5.0]为中心，横向拉开距离，变成一字长蛇阵，间距保持在 2 米，限时 3 秒完成
ROS信息：当前可用无人机编号: [1,2,3,4,5,6,7,8,9,10]，总数: 10
输出：
{
  "lfs_version": "1.0",
  "tasks": [
    {
      "task_id": 1,
      "U": [1,2,3,4,5,6,7,8,9,10],
      "F": "Line",
      "c": [1.0, 4.0, 5.0],
      "r": 2.0,
      "T": 3.0,
      "m": "normal",
      "s": 1.0,
      "q": "direct"
    }
  ]
}
"""


# ====================== 工具函数 ======================
def purify_json_content(raw_content: str) -> str:
    raw_content = re.sub(r"```json|```", "", raw_content).strip()
    match = re.search(r"\{.*\}", raw_content, re.DOTALL)
    return match.group(0) if match else raw_content


def classify_command_type(llm_output: dict) -> str:
    tasks = llm_output.get("task_sequences", [])
    if not tasks:
        return "invalid"
    if len(tasks) == 1:
        return "simple"

    seen_ids = set()
    has_overlap = False
    for task in tasks:
        task_ids = set(task.get("uav_id", []))
        if seen_ids & task_ids:
            has_overlap = True
            break
        seen_ids |= task_ids
    return "sequential" if has_overlap else "grouped"


def _usage_tokens(response, field_name: str) -> int:
    usage = getattr(response, "usage", None)
    return int(getattr(usage, field_name, 0) or 0)


def _log_parse_attempt(command_id: str, raw_command: str, retry_count: int, **kwargs):
    append_llm_parse_log({
        "command_id": command_id,
        "command_type": kwargs.get("command_type", "invalid"),
        "raw_command": raw_command,
        "prompt_tokens": kwargs.get("prompt_tokens", 0),
        "completion_tokens": kwargs.get("completion_tokens", 0),
        "latency_ms": kwargs.get("latency_ms", 0),
        "valid_json": kwargs.get("valid_json", False),
        "schema_valid": kwargs.get("schema_valid", False),
        "field_accuracy": kwargs.get("field_accuracy", 0.0),
        "retry_count": retry_count,
        "error_type": kwargs.get("error_type", ""),
    })


# ====================== 核心解析函数（新格式） ======================
def parse_uav_command(user_command: str, ros_aux_info: str = ""):
    command_id = uuid.uuid4().hex[:12]

    if not API_KEY:
        _log_parse_attempt(
            command_id,
            user_command,
            0,
            error_type="missing_api_key",
        )
        return {
            "task_sequences": [],
            "error_code": 4,
            "error_msg": "缺少 LLM API Key，请设置 LLM_API_KEY 或 MINIMAX_API_KEY 环境变量"
        }

    full_prompt = (
            SYSTEM_PROMPT + "\n"
            + FEW_SHOT_EXAMPLES + "\n"
            + "【ROS实时情报】\n" + ros_aux_info + "\n"
            + "【用户指令】\n" + user_command + "\n"
            + "【输出】\n"
    )

    client = OpenAI(
    api_key=API_KEY, 
    base_url=BASE_URL,
    http_client=httpx.Client(trust_env=False)
    )

    max_retries = 3

    for attempt in range(max_retries):
        response = None
        start_time = time.time()
        valid_json = False
        schema_valid = False
        field_accuracy = 0.0
        try:
            print(f"第{attempt + 1}次调用API解析指令...")
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": full_prompt}],
                temperature=0,
                top_p=0.01,
                max_tokens=4000,
                response_format={"type": "json_object"},
                timeout=60
            )
            latency_ms = int((time.time() - start_time) * 1000)

            raw_result = response.choices[0].message.content
            pure_json_str = purify_json_content(raw_result)
            cfr_result = json.loads(pure_json_str)
            valid_json = True
            field_accuracy = estimate_field_accuracy(cfr_result)
            available_uav_ids = parse_available_uav_ids(ros_aux_info)
            cfr_result = validate_and_compile_lfs(cfr_result, available_uav_ids)
            schema_valid = True

            _log_parse_attempt(
                command_id,
                user_command,
                attempt,
                command_type=classify_command_type(cfr_result),
                prompt_tokens=_usage_tokens(response, "prompt_tokens"),
                completion_tokens=_usage_tokens(response, "completion_tokens"),
                latency_ms=latency_ms,
                valid_json=valid_json,
                schema_valid=schema_valid,
                field_accuracy=field_accuracy,
            )
            print(" 解析结果校验通过！")
            return cfr_result

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            _log_parse_attempt(
                command_id,
                user_command,
                attempt,
                prompt_tokens=_usage_tokens(response, "prompt_tokens") if response else 0,
                completion_tokens=_usage_tokens(response, "completion_tokens") if response else 0,
                latency_ms=latency_ms,
                valid_json=valid_json,
                schema_valid=schema_valid,
                field_accuracy=field_accuracy,
                error_type=type(e).__name__,
            )
            print(f" 第{attempt + 1}次解析失败：{str(e)}")
            if attempt == max_retries - 1:
                return {
                    "task_sequences": [],
                    "error_code": 4,
                    "error_msg": f"解析失败（重试{max_retries}次）：{str(e)}"
                }
            time.sleep(2)


# ====================== 测试 ======================
if __name__ == "__main__":
    test_cmd = "准备谢幕表演：首先用 3 秒钟聚拢成一个以[2,2,10]为球形的最紧凑的球形编队并稳定悬停 2 秒钟后，然后全体向外发散，各自用 4 秒时间飞回初始起飞点降落"
    test_ros = "当前可用无人机编号: [1,2,3,4,5,6,7,8,9,10]，总数: 10"
    result = parse_uav_command(test_cmd, test_ros)
    print("\n" + "=" * 50)
    print("最终解析结果：")
    print("=" * 50)
    print(json.dumps(result, indent=2, ensure_ascii=False))
