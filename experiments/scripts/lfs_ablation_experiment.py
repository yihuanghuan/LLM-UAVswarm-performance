#!/usr/bin/env python3
"""Prompts, adapters, execution checks, and metrics for experiment 02."""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_SRC = REPO_ROOT / "location_allocate"

import sys

if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from location_allocate.lfs_validator import (  # noqa: E402
    compile_lfs,
    validate_and_compile_lfs,
    validate_schema,
)


METHODS = (
    "direct_waypoint",
    "task_json_no_schema",
    "lfs_schema",
    "lfs_schema_semantic",
)
ERROR_CATEGORIES = ("unrelated", "unknown_uav", "missing_formation", "ambiguous")
FORMATIONS = {"Circle", "Line", "Sphere", "Free", "Triangle", "Polygon", "Lineup"}
STYLES = {"smooth", "normal", "aggressive"}
TRIGGERS = {"direct", "hover-and-wait", "continuous"}

DIRECT_FIELDS = ("task_id", "formation_type", "duration", "motion_style", "safety_factor", "trigger", "uav_to_goal")
JSON_FIELDS = (
    "task_sequence_id",
    "duration_seconds",
    "uav_id",
    "uav_count",
    "trigger_condition",
    "wait_time",
    "iapf_safety_margin_factor",
    "motion_profile",
    "constraints",
    "global_center",
    "generation_mode",
    "parametric_data",
)
LFS_FIELDS = ("U", "F", "c", "r", "T", "m", "s", "q")
REQUIRED_FIELDS = {
    "direct_waypoint": DIRECT_FIELDS,
    "task_json_no_schema": JSON_FIELDS,
    "lfs_schema": LFS_FIELDS,
    "lfs_schema_semantic": LFS_FIELDS,
}


COMMON_ERROR_RULES = """
若指令与无人机编队无关、使用不存在的无人机、缺少编队类型或存在互相冲突的歧义，
只返回 {"error":{"category":"unrelated|unknown_uav|missing_formation|ambiguous"}}。
ROS 信息给出的编号是全部可用无人机。只返回纯 JSON，不要解释或使用 Markdown。
""".strip()

DIRECT_PROMPT = """
你负责把自然语言无人机编队指令直接转换为逐机目标点，不经过参数化编队编译器。
输出 {"tasks":[...]}，每个任务严格包含：
task_id、formation_type、duration、motion_style、safety_factor、trigger、uav_to_goal。
uav_to_goal 是 [{"uav_id":1,"goal":[x,y,z]}, ...]，必须覆盖任务涉及的每架无人机且编号唯一。
formation_type 仅限 Circle/Line/Sphere/Triangle/Polygon/Lineup/Free；
motion_style 仅限 smooth/normal/aggressive；trigger 仅限 direct/hover-and-wait/continuous。
请自行计算满足指令中心、半径或间距的目标点。并行任务添加相同 parallel_group。
默认 motion_style="normal"、safety_factor=1.0、trigger="direct"。

示例：1到3号机以[0,0,3]为中心组成半径2米的圆形编队，5秒完成
输出：{"tasks":[{"task_id":1,"formation_type":"Circle","duration":5,
"motion_style":"normal","safety_factor":1.0,"trigger":"direct","uav_to_goal":[
{"uav_id":1,"goal":[2,0,3]},{"uav_id":2,"goal":[-1,1.732,3]},
{"uav_id":3,"goal":[-1,-1.732,3]}]}]}
""".strip() + "\n\n" + COMMON_ERROR_RULES

TASK_JSON_PROMPT = """
你负责把自然语言无人机编队指令转换成调度器可直接读取的普通 JSON，不使用 LFS。
输出 {"task_sequences":[...]}。每个任务严格包含：
task_sequence_id、duration_seconds、uav_id、uav_count、trigger_condition、wait_time、
iapf_safety_margin_factor、motion_profile、constraints、global_center、generation_mode、parametric_data。
generation_mode 固定为 "parametric"；parametric_data 包含 formation_type 和 formation_radius。
formation_type 仅限 Circle/Line/Sphere/Triangle/Polygon/Lineup/Free；
trigger_condition 仅限 direct_execution/hover_and_wait/continuous_transit；
motion_profile 仅限 smooth/normal/aggressive。并行任务添加相同 parallel_group。
默认 motion_profile="normal"、iapf_safety_margin_factor=1.0、trigger_condition="direct_execution"。
constraints 默认 ["minimal_topology_change","no_trajectory_cross","keep_safety_distance"]。

示例：1到3号机以[0,0,3]为中心组成半径2米的圆形编队，5秒完成
输出：{"task_sequences":[{"task_sequence_id":1,"duration_seconds":5,"uav_id":[1,2,3],
"uav_count":3,"trigger_condition":"direct_execution","wait_time":null,
"iapf_safety_margin_factor":1.0,"motion_profile":"normal",
"constraints":["minimal_topology_change","no_trajectory_cross","keep_safety_distance"],
"global_center":[0,0,3],"generation_mode":"parametric",
"parametric_data":{"formation_type":"Circle","formation_radius":2}}]}
""".strip() + "\n\n" + COMMON_ERROR_RULES

LFS_PROMPT = """
你是无人机集群 Language-to-Formation Specification (LFS) 解析器。
有效输出必须是 {"lfs_version":"1.0","tasks":[...]}，每个任务严格包含：
task_id、U、F、c、r、T、m、s、q。
U 是无人机整数数组；F 仅限 Circle/Line/Sphere/Triangle/Polygon/Lineup/Free；
c 是三维中心；r 是正的半径或间距；T 是正的秒数；
m 仅限 smooth/normal/aggressive；s 是非负安全系数；
q 仅限 direct/hover-and-wait/continuous。并行任务添加相同 parallel_group。
默认 m="normal"、s=1.0、q="direct"；不得输出逐机目标点。

示例：1到3号机以[0,0,3]为中心组成半径2米的圆形编队，5秒完成
输出：{"lfs_version":"1.0","tasks":[{"task_id":1,"U":[1,2,3],"F":"Circle",
"c":[0,0,3],"r":2,"T":5,"m":"normal","s":1.0,"q":"direct"}]}

示例：1到4号机先用5秒在[3,0,4]组成间距2米的直线，随后用7秒在[0,3,4]组成半径3米的圆形
输出：{"lfs_version":"1.0","tasks":[
{"task_id":1,"U":[1,2,3,4],"F":"Line","c":[3,0,4],"r":2,"T":5,
"m":"normal","s":1.0,"q":"continuous"},
{"task_id":2,"U":[1,2,3,4],"F":"Circle","c":[0,3,4],"r":3,"T":7,
"m":"normal","s":1.0,"q":"direct"}]}
""".strip() + "\n\n" + COMMON_ERROR_RULES

PROMPTS = {
    "direct_waypoint": DIRECT_PROMPT,
    "task_json_no_schema": TASK_JSON_PROMPT,
    "lfs_schema": LFS_PROMPT,
    "lfs_schema_semantic": LFS_PROMPT,
}


@dataclass(frozen=True)
class RunConfig:
    model: str
    max_retries: int = 3
    timeout: float = 60.0
    temperature: float = 0.0
    top_p: float = 0.01
    max_tokens: int = 4000


def prompt_manifest() -> Dict[str, Dict[str, str]]:
    return {
        method: {
            "sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "prompt": prompt,
        }
        for method, prompt in PROMPTS.items()
    }


def prompt_for(method: str, item: Dict[str, Any], repair_feedback: str = "") -> str:
    return (
        PROMPTS[method]
        + "\n\n【ROS实时情报】\n" + str(item.get("ros_aux_info", ""))
        + "\n【用户指令】\n" + str(item["command"])
        + "\n【输出】\n"
        + repair_feedback
    )


def purify_json_content(raw: str) -> str:
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"```(?:json)?|```", "", cleaned, flags=re.IGNORECASE).strip()
    decoder = json.JSONDecoder()
    candidates: List[Tuple[int, int, str]] = []
    for start, char in enumerate(cleaned):
        if char not in "[{":
            continue
        try:
            _value, length = decoder.raw_decode(cleaned[start:])
        except json.JSONDecodeError:
            continue
        candidates.append((length, start, cleaned[start:start + length]))
    return max(candidates, key=lambda value: (value[0], value[1]))[2] if candidates else cleaned


def parse_available_uavs(text: str) -> List[int]:
    match = re.search(r"\[([0-9,\s]+)\]", text or "")
    if not match:
        return []
    return [int(value.strip()) for value in match.group(1).split(",") if value.strip()]


def normalize_error(payload: Any) -> Optional[str]:
    if not isinstance(payload, dict) or "error" not in payload:
        return None
    error = payload["error"]
    value = error.get("category") if isinstance(error, dict) else error
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "irrelevant": "unrelated",
        "off_topic": "unrelated",
        "invalid_uav": "unknown_uav",
        "nonexistent_uav": "unknown_uav",
        "missing_information": "missing_formation",
        "missing_field": "missing_formation",
        "conflict": "ambiguous",
        "ambiguity": "ambiguous",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in ERROR_CATEGORIES else None


def raw_tasks(method: str, payload: Any) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    key = "task_sequences" if method == "task_json_no_schema" else "tasks"
    tasks = payload.get(key)
    return [task for task in tasks if isinstance(task, dict)] if isinstance(tasks, list) else []


def task_uavs(method: str, task: Dict[str, Any]) -> List[int]:
    try:
        if method == "direct_waypoint":
            entries = task.get("uav_to_goal", [])
            return [int(entry["uav_id"]) for entry in entries if isinstance(entry, dict) and "uav_id" in entry]
        if method == "task_json_no_schema":
            return [int(value) for value in task.get("uav_id", [])]
        return [int(value) for value in task.get("U", [])]
    except (TypeError, ValueError):
        return []


def task_formation(method: str, task: Dict[str, Any]) -> Optional[str]:
    if method == "direct_waypoint":
        value = task.get("formation_type")
    elif method == "task_json_no_schema":
        data = task.get("parametric_data")
        value = data.get("formation_type") if isinstance(data, dict) else None
    else:
        value = task.get("F")
    return str(value) if value is not None else None


def _finite_number(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("布尔值不是有效坐标")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("坐标必须为有限数值")
    return result


def _direct_goals(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    result = []
    tasks = raw_tasks("direct_waypoint", payload)
    if not tasks:
        raise ValueError("direct output 缺少非空 tasks")
    for task in tasks:
        entries = task.get("uav_to_goal")
        if not isinstance(entries, list) or not entries:
            raise ValueError("uav_to_goal 必须为非空数组")
        ids: List[int] = []
        goals: List[List[float]] = []
        for entry in entries:
            if not isinstance(entry, dict) or "uav_id" not in entry:
                raise ValueError("目标项缺少 uav_id")
            goal = entry.get("goal")
            if not isinstance(goal, list) or len(goal) != 3:
                raise ValueError("目标项必须包含三维 goal")
            ids.append(int(entry["uav_id"]))
            goals.append([_finite_number(value) for value in goal])
        if len(ids) != len(set(ids)):
            raise ValueError("直接目标包含重复 UAV")
        result.append({"uav_ids": ids, "goals": goals})
    return result


def _formation_generator(center: List[float], radius: float, formation: str, count: int) -> List[List[float]]:
    # Import the scheduler's real implementation lazily so data/metric helpers
    # remain importable in non-ROS unit tests.
    from location_allocate.location_allocate import FormationGenerator

    goals = FormationGenerator(center, radius).generate(formation, count)
    if formation == "Free":
        raise ValueError("Free 任务需要运行时初始点，不能离线编译")
    return [[float(value) for value in goal] for goal in goals]


def _compiled_goals(compiled: Dict[str, Any]) -> List[Dict[str, Any]]:
    tasks = compiled.get("task_sequences")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("编译结果缺少非空 task_sequences")
    result = []
    for task in tasks:
        uavs = [int(value) for value in task["uav_id"]]
        count = int(task["uav_count"])
        data = task["parametric_data"]
        formation = str(data["formation_type"])
        center = [_finite_number(value) for value in task["global_center"]]
        if len(center) != 3:
            raise ValueError("global_center 必须是三维坐标")
        radius = _finite_number(data["formation_radius"])
        goals = _formation_generator(center, radius, formation, count)
        if len(goals) != count:
            raise ValueError("目标点数量与 uav_count 不一致")
        result.append({"uav_ids": uavs, "goals": goals})
    return result


def _runtime_check(compiled: Dict[str, Any], available_uavs: Sequence[int]) -> None:
    available = set(available_uavs)
    tasks = compiled.get("task_sequences")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("调度器输入缺少任务")
    for task in tasks:
        missing = [field for field in JSON_FIELDS if field not in task]
        if missing:
            raise ValueError(f"调度任务缺少字段: {missing}")
        uavs = [int(value) for value in task["uav_id"]]
        if not uavs or len(uavs) != len(set(uavs)):
            raise ValueError("UAV 列表为空或重复")
        if int(task["uav_count"]) != len(uavs):
            raise ValueError("uav_count 不一致")
        if available and not set(uavs).issubset(available):
            raise ValueError("包含不可用 UAV")
        if task_formation("task_json_no_schema", task) not in FORMATIONS:
            raise ValueError("编队类型不受支持")
        if float(task["duration_seconds"]) <= 0:
            raise ValueError("任务时长必须为正")
    _compiled_goals(compiled)


def _direct_runtime_check(payload: Dict[str, Any], available_uavs: Sequence[int]) -> None:
    available = set(available_uavs)
    tasks = raw_tasks("direct_waypoint", payload)
    goals = _direct_goals(payload)
    for task, task_goals in zip(tasks, goals):
        missing = [field for field in DIRECT_FIELDS if field not in task]
        if missing:
            raise ValueError(f"直接目标任务缺少字段: {missing}")
        if task_formation("direct_waypoint", task) not in FORMATIONS:
            raise ValueError("编队类型不受支持")
        if available and not set(task_goals["uav_ids"]).issubset(available):
            raise ValueError("直接目标包含不可用 UAV")
        if float(task["duration"]) <= 0:
            raise ValueError("任务时长必须为正")
        if str(task["motion_style"]) not in STYLES or str(task["trigger"]) not in TRIGGERS:
            raise ValueError("直接目标包含非法枚举")
        if float(task["safety_factor"]) < 0:
            raise ValueError("安全系数不能为负")


def inspect_payload(method: str, payload: Dict[str, Any], available_uavs: Sequence[int]) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "rejected": False,
        "rejection_category": "",
        "schema_valid": False,
        "semantic_valid": False,
        "compilation_success": False,
        "executable": False,
        "compiled": None,
        "goals": None,
        "error_stage": "",
        "error_detail": "",
    }
    rejection = normalize_error(payload)
    if rejection:
        result.update(rejected=True, rejection_category=rejection)
        return result

    try:
        if method == "direct_waypoint":
            result["goals"] = _direct_goals(payload)
            result["compilation_success"] = True
            _direct_runtime_check(payload, available_uavs)
            result["executable"] = True
            return result

        if method == "task_json_no_schema":
            result["compiled"] = payload
            result["goals"] = _compiled_goals(payload)
            result["compilation_success"] = True
            _runtime_check(payload, available_uavs)
            result["executable"] = True
            return result

        validate_schema(payload)
        result["schema_valid"] = True
        if method == "lfs_schema":
            compiled = compile_lfs(payload)
        else:
            compiled = validate_and_compile_lfs(payload, available_uavs)
            result["semantic_valid"] = True
        result["compiled"] = compiled
        result["goals"] = _compiled_goals(compiled)
        result["compilation_success"] = True
        _runtime_check(compiled, available_uavs)
        result["executable"] = True
        return result
    except Exception as exc:
        if method.startswith("lfs") and not result["schema_valid"]:
            stage = "schema"
        elif method == "lfs_schema_semantic" and not result["semantic_valid"]:
            stage = "semantic"
        elif not result["compilation_success"]:
            stage = "compilation"
        else:
            stage = "execution"
        result["error_stage"] = stage
        result["error_detail"] = f"{type(exc).__name__}: {exc}"
        return result


def _missing_fields(method: str, payload: Any, expected_task_count: int) -> Tuple[int, int]:
    fields = REQUIRED_FIELDS[method]
    tasks = raw_tasks(method, payload)
    slots = max(expected_task_count, len(tasks), 1) * len(fields)
    missing = 0
    for index in range(max(expected_task_count, len(tasks), 1)):
        if index >= len(tasks):
            missing += len(fields)
        else:
            missing += sum(field not in tasks[index] for field in fields)
    return missing, slots


def _prediction_tasks(method: str, payload: Any) -> List[Dict[str, Any]]:
    result = []
    for task in raw_tasks(method, payload):
        result.append({
            "U": task_uavs(method, task),
            "F": task_formation(method, task),
            "raw": task,
        })
    return result


def _pair_predictions(expected: List[Dict[str, Any]], predicted: List[Dict[str, Any]]) -> List[Tuple[Dict[str, Any], Optional[Dict[str, Any]]]]:
    remaining = set(range(len(predicted)))
    pairs = []
    for expected_task in expected:
        expected_uavs = set(int(value) for value in expected_task["U"])
        best = None
        best_score = -1
        for index in remaining:
            predicted_uavs = set(predicted[index]["U"])
            score = len(expected_uavs & predicted_uavs)
            if score > best_score:
                best, best_score = index, score
        if best is None:
            pairs.append((expected_task, None))
        else:
            pairs.append((expected_task, predicted[best]))
            remaining.remove(best)
    return pairs


def _direct_geometry_matches(expected: Dict[str, Any], predicted: Dict[str, Any]) -> bool:
    entries = predicted["raw"].get("uav_to_goal")
    if not isinstance(entries, list) or len(entries) != len(expected["U"]):
        return False
    try:
        points = [[_finite_number(value) for value in entry["goal"]] for entry in entries]
    except Exception:
        return False
    center = [float(value) for value in expected["c"]]
    radius = float(expected["r"])
    tolerance = max(0.15, 0.08 * radius)
    formation = expected["F"]
    if formation in {"Circle", "Polygon", "Triangle"}:
        radial = [math.hypot(point[0] - center[0], point[1] - center[1]) for point in points]
        return all(abs(value - radius) <= tolerance for value in radial) and all(
            abs(point[2] - center[2]) <= tolerance for point in points
        )
    if formation in {"Line", "Lineup"}:
        ordered = sorted(points, key=lambda point: point[0])
        spacing = [ordered[index + 1][0] - ordered[index][0] for index in range(len(ordered) - 1)]
        mean_x = sum(point[0] for point in points) / len(points)
        return (
            abs(mean_x - center[0]) <= tolerance
            and all(abs(point[1] - center[1]) <= tolerance and abs(point[2] - center[2]) <= tolerance for point in points)
            and all(abs(value - radius) <= tolerance for value in spacing)
        )
    if formation == "Sphere":
        distances = [
            math.sqrt(sum((point[axis] - center[axis]) ** 2 for axis in range(3)))
            for point in points
        ]
        return all(abs(value - radius) <= tolerance for value in distances)
    return formation == "Free"


def calculate_metrics(method: str, item: Dict[str, Any], payload: Any, inspection: Dict[str, Any]) -> Dict[str, Any]:
    expected_tasks = list((item.get("expected_lfs") or {}).get("tasks", []))
    valid_input = bool(expected_tasks)
    missing_count, missing_slots = _missing_fields(method, payload, len(expected_tasks))
    predictions = _prediction_tasks(method, payload)
    available = set(parse_available_uavs(str(item.get("ros_aux_info", ""))))
    references = [uav for task in predictions for uav in task["U"]]
    invalid_uavs = sum(uav not in available for uav in references) if available else 0

    invalid_formations = 0
    formation_slots = len(expected_tasks)
    if valid_input:
        for expected, predicted in _pair_predictions(expected_tasks, predictions):
            if predicted is None or predicted["F"] != expected["F"] or predicted["F"] not in FORMATIONS:
                invalid_formations += 1
            elif method == "direct_waypoint" and not _direct_geometry_matches(expected, predicted):
                invalid_formations += 1

    expected_error = str(item.get("expected_error", ""))
    rejection = inspection["rejection_category"]
    return {
        "valid_input": valid_input,
        "expected_error": expected_error,
        "correct_rejection": bool(not valid_input and rejection == expected_error),
        "false_executable": bool(not valid_input and inspection["executable"]),
        "missing_field_count": missing_count,
        "required_field_slots": missing_slots,
        "invalid_uav_count": invalid_uavs,
        "uav_reference_count": len(references),
        "invalid_formation_count": invalid_formations,
        "formation_task_count": formation_slots,
    }


def _usage(response: Any, field: str) -> int:
    usage = getattr(response, "usage", None)
    return int(getattr(usage, field, 0) or 0)


def _accepted(method: str, inspection: Dict[str, Any]) -> bool:
    if inspection["rejected"]:
        return True
    if method == "direct_waypoint":
        return bool(inspection["executable"])
    if method == "task_json_no_schema":
        return True  # Valid JSON is the only gate in the no-validation ablation.
    if method == "lfs_schema":
        return bool(inspection["schema_valid"])
    return bool(inspection["semantic_valid"] and inspection["executable"])


def call_method(
    client: Any,
    method: str,
    item: Dict[str, Any],
    config: RunConfig,
    sleep_fn=time.sleep,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    attempts: List[Dict[str, Any]] = []
    total_latency = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    final_payload: Optional[Dict[str, Any]] = None
    final_inspection: Dict[str, Any] = inspect_payload(method, {}, parse_available_uavs(str(item.get("ros_aux_info", ""))))
    repair_feedback = ""
    last_error = ""
    available = parse_available_uavs(str(item.get("ros_aux_info", "")))

    for attempt_index in range(config.max_retries):
        response = None
        raw_response = ""
        payload: Optional[Dict[str, Any]] = None
        started = time.perf_counter()
        try:
            response = client.chat.completions.create(
                model=config.model,
                messages=[{"role": "user", "content": prompt_for(method, item, repair_feedback)}],
                temperature=config.temperature,
                top_p=config.top_p,
                max_tokens=config.max_tokens,
                response_format={"type": "json_object"},
                timeout=config.timeout,
            )
            raw_response = response.choices[0].message.content or ""
            decoded = json.loads(purify_json_content(raw_response))
            if not isinstance(decoded, dict):
                raise ValueError("顶层 JSON 必须是对象")
            payload = decoded
            final_payload = payload
            final_inspection = inspect_payload(method, payload, available)
            last_error = final_inspection["error_stage"]
            accepted = _accepted(method, final_inspection)
            error_detail = final_inspection["error_detail"]
        except json.JSONDecodeError as exc:
            accepted = False
            last_error = "invalid_json"
            error_detail = f"{type(exc).__name__}: {exc}"
        except Exception as exc:
            accepted = False
            last_error = "api_error" if response is None else "response_error"
            error_detail = f"{type(exc).__name__}: {exc}"

        latency = int((time.perf_counter() - started) * 1000)
        prompt_tokens = _usage(response, "prompt_tokens") if response else 0
        completion_tokens = _usage(response, "completion_tokens") if response else 0
        total_latency += latency
        total_prompt_tokens += prompt_tokens
        total_completion_tokens += completion_tokens
        attempts.append({
            "command_id": item["id"],
            "method": method,
            "attempt": attempt_index + 1,
            "latency_ms": latency,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "valid_json": payload is not None,
            "accepted": accepted,
            "error_type": "" if accepted else last_error,
            "error_detail": "" if accepted else error_detail,
            "raw_response": raw_response,
            "parsed_payload": payload,
        })
        if accepted:
            last_error = ""
            break
        if attempt_index + 1 < config.max_retries:
            repair_feedback = (
                "\n【上次输出不能被当前方法接受】\n"
                + error_detail
                + "\n请只修正该错误并重新输出完整 JSON，不要解释。\n"
            )
            sleep_fn(2 ** attempt_index)

    payload_for_metrics: Dict[str, Any] = final_payload or {}
    metrics = calculate_metrics(method, item, payload_for_metrics, final_inspection)
    result = {
        "command_id": item["id"],
        "command_type": item.get("type", ""),
        "complexity": item.get("complexity", ""),
        "method": method,
        "valid_json": bool(final_payload is not None),
        "rejected": final_inspection["rejected"],
        "rejection_category": final_inspection["rejection_category"],
        "schema_valid": final_inspection["schema_valid"],
        "semantic_valid": final_inspection["semantic_valid"],
        "compilation_success": final_inspection["compilation_success"],
        "executable": final_inspection["executable"],
        "retry_count": max(0, len(attempts) - 1),
        "attempt_count": len(attempts),
        "latency_ms": total_latency,
        "prompt_tokens": total_prompt_tokens,
        "completion_tokens": total_completion_tokens,
        "error_type": last_error,
        "error_detail": final_inspection["error_detail"],
        "payload_json": json.dumps(final_payload, ensure_ascii=False, separators=(",", ":")) if final_payload else "",
        "compiled_json": json.dumps(final_inspection["compiled"], ensure_ascii=False, separators=(",", ":")) if final_inspection["compiled"] else "",
        "goals_json": json.dumps(final_inspection["goals"], ensure_ascii=False, separators=(",", ":")) if final_inspection["goals"] else "",
        **metrics,
    }
    return result, attempts
