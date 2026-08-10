# 命令一：基础时空变阵指令。
# 正多边形编队变换，最大数量：>8
# 一字长蛇编队变换，最大数量：>8
# 圆形编队变换，最大数量：>8
# 隐形指令（散开），最大数量：>8
# test_cmd = "UVA1-6 以[3.4.5]为中心，变换成圆形编队，半径为1.5米，限时3秒"
# 起始点为圆形，耗时为8s
# test_cmd = "现在的阵型太密集了，以UVA4为中心，横向拉开距离，变成一字长蛇阵，间距保持在 2 米，限时 3 秒完成"
# 10个UAV,起始点为圆形+矩形，耗时8s

# 命令二：集群裂变与多目标调度。
# test_cmd = "队形一分为二。1到6号机以[3,4,5]为中心变成圆形；7号到10号机在圆形正上方2米形成正方形掩护阵型。两组动作必须在 5 秒内同步完成"
# 输出两任务 耗时 15s(起始点杂乱）,

# 命令三：连续状态机时序指令。
# test_cmd 为准备谢幕表演的复合指令。
# 输出两任务（悬停+直接执行），10 个 UAV 耗时约 25s。
# 原来的指令:准备谢幕表演：首先用 3 秒钟聚拢成一个最紧凑的球形编队；稳定悬停 2 秒钟后；全体向外发散，各自用 4 秒时间飞回初始起飞点降落,ai通过断句会把悬停判给第二个任务
import re
import json
import time
import os
import uuid
try:
    import httpx
except ModuleNotFoundError:  # OpenAI can still use its default HTTP client.
    httpx = None

try:
    from openai import OpenAI
except ModuleNotFoundError:  # Allows schema/parser unit tests without SDK.
    OpenAI = None

from .llm_parse_logger import append_llm_parse_log
from .lfs_validator import (
    LFSValidationError,
    early_validate_candidate_mission,
    estimate_field_accuracy,
    is_candidate_mission,
    parse_available_uav_ids,
    validate_and_compile_lfs,
)

# -------------------------- 配置项 --------------------------
API_KEY = os.getenv("LLM_API_KEY") or os.getenv("MINIMAX_API_KEY")
BASE_URL = "https://api.minimax.chat/v1"
MODEL_NAME = "MiniMax-M2.7-highspeed"
# -------------------------------------------------------------------------

# ====================== 固定系统Prompt（LFS格式） ======================
LEGACY_SYSTEM_PROMPT = """
# 角色定位
你是无人机集群编队变换专属指令解析专家，唯一职责是将操作人员输入的自然语言指令，
严格解析为 Language-to-Formation Specification (LFS) JSON，禁止处理任何无关请求。

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
LEGACY_FEW_SHOT_EXAMPLES = """
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

CANDIDATE_SYSTEM_PROMPT = r"""
# Role
You are a semantic parser for UAV formation missions. Return JSON only. Your
output is a Candidate Mission: it describes user intent and task relations,
but never computes executable coordinates, controller gains, safety-critical
parameters, allocation weights, per-UAV targets, or velocity/acceleration/jerk
limits.

# Envelope and graph
Return exactly:
{"lfs_version":"2.0","mission":{"nodes":[...]}}
Every node is one of:
- {"type":"task","task": TASK}
- {"type":"parallel","completion_mode":"independent|synchronized","tasks":[TASK,...]}
- {"type":"wait","condition":"elapsed","duration":SECONDS}
Use a parallel node only when the language explicitly expresses simultaneous
execution. Never infer parallelism merely because UAV sets do not overlap.
completion_mode defaults to independent. Use synchronized only when the user
explicitly requires simultaneous completion.

# TASK = tau_candidate(U,F,c,r,T,m,s,q)
- task_id: unique positive integer
- U: participating UAV IDs; when omitted by the user use all IDs from the ROS
  availability information
- F: Circle, Line, Sphere, Triangle, Polygon, Lineup, or Free. Lineup and Free
  remain compatibility vocabulary and may be rejected later by deterministic
  Candidate geometry; do not reinterpret them as another formation.
- c:
  * explicit world center: {"mode":"absolute","value":[x,y,z]}
  * explicit offset: {"mode":"relative","reference":"current_swarm_centroid",
    "offset":[dx,dy,dz],"frame":"world"}
  * user explicitly asks to keep the current center:
    {"mode":"maintain_current_centroid"}
  * user gives no center: {"mode":"auto"}
- r:
  * explicit scale: {"mode":"explicit","value":POSITIVE_NUMBER}
  * explicit qualitative wording: {"mode":"qualitative",
    "value":"compact|normal|spacious"}
  * user gives no scale: {"mode":"auto"}
- T: explicit {"mode":"explicit","value":POSITIVE_SECONDS}; otherwise
  {"mode":"auto"}
- m: smooth, normal, aggressive. If no style is expressed, use normal. This is
  a semantic label, not a request to generate gains.
- s: safety factor >= 1. If absent, use 1.0.
- q: direct, hover-and-wait, continuous. q is only task completion/wait intent.
  hover-and-wait requires a non-negative wait_time. Use direct for "after this
  formation becomes stable, start the next task" when no extra timed hold was
  requested. Use continuous only for a stated no-stop transition.

# Hard restrictions
- Do not invent numeric c, r, or T when the user omitted them; use auto.
- Do not output LADRC gains, IAPF parameters, safety distances, allocator
  parameters, dynamics limits, target_pos, global_center, parametric_data, or
  task_sequences.
- Do not add explanatory text, markdown, error recovery payloads, or fields not
  defined above.
"""

CANDIDATE_FEW_SHOT_EXAMPLES = r"""
User: 让1到5号无人机组成圆形
Output:
{"lfs_version":"2.0","mission":{"nodes":[{"type":"task","task":{"task_id":1,"U":[1,2,3,4,5],"F":"Circle","c":{"mode":"auto"},"r":{"mode":"auto"},"T":{"mode":"auto"},"m":"normal","s":1.0,"q":"direct"}}]}}

User: 1到3号机以[2,3,4]为中心、半径2米，在5秒内组成三角形；同时4到6号机保持当前中心组成紧凑圆形，两组同时完成
Output:
{"lfs_version":"2.0","mission":{"nodes":[{"type":"parallel","completion_mode":"synchronized","tasks":[{"task_id":1,"U":[1,2,3],"F":"Triangle","c":{"mode":"absolute","value":[2,3,4]},"r":{"mode":"explicit","value":2},"T":{"mode":"explicit","value":5},"m":"normal","s":1.0,"q":"direct"},{"task_id":2,"U":[4,5,6],"F":"Circle","c":{"mode":"maintain_current_centroid"},"r":{"mode":"qualitative","value":"compact"},"T":{"mode":"auto"},"m":"normal","s":1.0,"q":"direct"}]}]}}

User: 全体先组成圆形，稳定后以当前位置中心上方2米组成正方形
Output:
{"lfs_version":"2.0","mission":{"nodes":[{"type":"task","task":{"task_id":1,"U":[1,2,3,4],"F":"Circle","c":{"mode":"auto"},"r":{"mode":"auto"},"T":{"mode":"auto"},"m":"normal","s":1.0,"q":"direct"}},{"type":"task","task":{"task_id":2,"U":[1,2,3,4],"F":"Polygon","c":{"mode":"relative","reference":"current_swarm_centroid","offset":[0,0,2],"frame":"world"},"r":{"mode":"auto"},"T":{"mode":"auto"},"m":"normal","s":1.0,"q":"direct"}}]}}
"""


class CandidateParseError(RuntimeError):
    """Candidate parsing failed without permission to enter the legacy path."""


# ====================== 工具函数 ======================
def purify_json_content(raw_content: str) -> str:
    raw_content = re.sub(r"```json|```", "", raw_content).strip()
    match = re.search(r"\{.*\}", raw_content, re.DOTALL)
    return match.group(0) if match else raw_content


def classify_command_type(llm_output: dict) -> str:
    if is_candidate_mission(llm_output):
        nodes = llm_output["mission"].get("nodes", [])
        if any(node.get("type") == "parallel" for node in nodes):
            return "candidate_parallel"
        return "candidate_sequential" if len(nodes) > 1 else "candidate_simple"
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
def parse_uav_command(
    user_command: str,
    ros_aux_info: str = "",
    runtime_mode: str = "legacy_v1",
):
    """Parse one command in an explicitly selected, non-fallback mode."""
    if runtime_mode not in ("candidate_v2", "legacy_v1"):
        raise ValueError("runtime_mode must be candidate_v2 or legacy_v1")
    command_id = uuid.uuid4().hex[:12]

    if not API_KEY or OpenAI is None:
        _log_parse_attempt(
            command_id,
            user_command,
            0,
            error_type="missing_api_key",
        )
        error = {
            "task_sequences": [],
            "error_code": 4,
            "error_msg": (
                "LLM client unavailable; install openai and set "
                "LLM_API_KEY or MINIMAX_API_KEY"
            )
        }
        if runtime_mode == "candidate_v2":
            raise CandidateParseError(error["error_msg"])
        return error

    if runtime_mode == "candidate_v2":
        system_prompt = CANDIDATE_SYSTEM_PROMPT
        examples = CANDIDATE_FEW_SHOT_EXAMPLES
    else:
        system_prompt = LEGACY_SYSTEM_PROMPT
        examples = LEGACY_FEW_SHOT_EXAMPLES

    full_prompt = (
        system_prompt + "\n"
        + examples + "\n"
        + "【ROS实时情报】\n" + ros_aux_info + "\n"
        + "【用户指令】\n" + user_command + "\n"
        + "【输出】\n"
    )

    client_options = {"api_key": API_KEY, "base_url": BASE_URL}
    if httpx is not None:
        client_options["http_client"] = httpx.Client(trust_env=False)
    client = OpenAI(**client_options)

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
            if runtime_mode == "candidate_v2":
                if not is_candidate_mission(cfr_result):
                    raise CandidateParseError(
                        "Candidate parser returned a non-Candidate payload"
                    )
                cfr_result = early_validate_candidate_mission(cfr_result)
            else:
                if is_candidate_mission(cfr_result):
                    raise LFSValidationError(
                        "legacy parser returned a Candidate payload"
                    )
                available_uav_ids = parse_available_uav_ids(ros_aux_info)
                cfr_result = validate_and_compile_lfs(
                    cfr_result, available_uav_ids
                )
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
                if runtime_mode == "candidate_v2":
                    raise CandidateParseError(
                        f"Candidate 解析失败（重试{max_retries}次）：{str(e)}"
                    ) from e
                return {
                    "task_sequences": [],
                    "error_code": 4,
                    "error_msg": f"解析失败（重试{max_retries}次）：{str(e)}"
                }
            time.sleep(2)


def parse_candidate_mission(user_command: str, ros_aux_info: str = ""):
    return parse_uav_command(user_command, ros_aux_info, "candidate_v2")


def parse_legacy_uav_command(user_command: str, ros_aux_info: str = ""):
    return parse_uav_command(user_command, ros_aux_info, "legacy_v1")


# ====================== 测试 ======================
if __name__ == "__main__":
    test_cmd = "准备谢幕表演：首先用 3 秒钟聚拢成一个以[2,2,10]为球形的最紧凑的球形编队并稳定悬停 2 秒钟后，然后全体向外发散，各自用 4 秒时间飞回初始起飞点降落"
    test_ros = "当前可用无人机编号: [1,2,3,4,5,6,7,8,9,10]，总数: 10"
    result = parse_uav_command(test_cmd, test_ros)
    print("\n" + "=" * 50)
    print("最终解析结果：")
    print("=" * 50)
    print(json.dumps(result, indent=2, ensure_ascii=False))
