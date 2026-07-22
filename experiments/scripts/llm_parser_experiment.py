#!/usr/bin/env python3
"""Shared prompts, adapters, API runner, and metrics for experiment 01."""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from jsonschema import Draft202012Validator


METHODS = ("plain_json", "few_shot_json", "lfs_schema", "dense_waypoints")
ERROR_CATEGORIES = ("unrelated", "unknown_uav", "missing_formation", "ambiguous")
NUMERIC_TOLERANCE = 1e-6


PLAIN_PROMPT = """
你负责把无人机编队指令转换成普通 JSON。请提取每个任务的无人机编号、编队类型、中心、
半径或间距、时长、运动风格、安全系数和执行关系。不要解释，只返回 JSON。
可以使用直观的英文键名。若指令无关、引用不存在的无人机、缺少编队类型或含冲突歧义，
返回 {"error": "unrelated|unknown_uav|missing_formation|ambiguous"} 中对应的一类。
默认运动风格 normal，默认安全系数 1.0，单任务默认 direct。
""".strip()


FEW_SHOT_PROMPT = """
你负责把无人机编队指令转换成 legacy task_sequences JSON。只返回 JSON，不要解释。
每个任务使用 task_sequence_id、duration_seconds、uav_id、uav_count、trigger_condition、
wait_time、iapf_safety_margin_factor、motion_profile、global_center、generation_mode 和
parametric_data。formation_type 取 Circle/Line/Sphere/Free/Triangle/Polygon/Lineup；
trigger_condition 取 direct_execution/hover_and_wait/continuous_transit。
无效指令返回 {"error": {"category": "unrelated|unknown_uav|missing_formation|ambiguous"}}。

示例：1到3号机以[0,0,3]为中心组成半径2米的圆形编队，5秒完成
输出：{"task_sequences":[{"task_sequence_id":1,"duration_seconds":5,"uav_id":[1,2,3],
"uav_count":3,"trigger_condition":"direct_execution","wait_time":null,
"iapf_safety_margin_factor":1.0,"motion_profile":"normal","global_center":[0,0,3],
"generation_mode":"parametric","parametric_data":{"formation_type":"Circle",
"formation_radius":2}}]}

示例：1到4号机先在[3,0,4]组成间距2米的直线，随后在[0,3,4]组成半径3米的圆形
输出：{"task_sequences":[{"task_sequence_id":1,"duration_seconds":3,"uav_id":[1,2,3,4],
"uav_count":4,"trigger_condition":"continuous_transit","wait_time":null,
"iapf_safety_margin_factor":1.0,"motion_profile":"normal","global_center":[3,0,4],
"generation_mode":"parametric","parametric_data":{"formation_type":"Line","formation_radius":2}},
{"task_sequence_id":2,"duration_seconds":3,"uav_id":[1,2,3,4],"uav_count":4,
"trigger_condition":"direct_execution","wait_time":null,"iapf_safety_margin_factor":1.0,
"motion_profile":"normal","global_center":[0,3,4],"generation_mode":"parametric",
"parametric_data":{"formation_type":"Circle","formation_radius":3}}]}
""".strip()


LFS_PROMPT = """
你是无人机集群 Language-to-Formation Specification (LFS) 解析器。只返回纯 JSON。
有效输出必须是 {"lfs_version":"1.0","tasks":[...]}，每个任务严格包含：
U（无人机整数数组）、F（Circle/Line/Sphere/Free/Triangle/Polygon/Lineup）、
c（三维中心）、r（半径或间距）、T（秒）、m（smooth/normal/aggressive）、
s（非负安全系数）、q（direct/hover-and-wait/continuous）。并行任务添加相同 parallel_group。
默认 m="normal"、s=1.0、q="direct"；连续任务的中间任务 q="continuous"。
不得输出逐机坐标。无效指令严格返回
{"error":{"category":"unrelated|unknown_uav|missing_formation|ambiguous"}}。
""".strip()


DENSE_PROMPT = """
你负责直接生成无人机目标点。只返回纯 JSON。有效输出必须是
{"lfs_version":"1.0","tasks":[...]}。每个任务包含 U、F、c、r、T、m、s、q，
并额外包含 waypoints，格式为 [{"uav_id":1,"position":[x,y,z]}, ...]，必须覆盖 U 中每架无人机。
F 取 Circle/Line/Sphere/Free/Triangle/Polygon/Lineup，m 取 smooth/normal/aggressive，
q 取 direct/hover-and-wait/continuous。并行任务添加相同 parallel_group。
默认 m="normal"、s=1.0、q="direct"。无效指令严格返回
{"error":{"category":"unrelated|unknown_uav|missing_formation|ambiguous"}}。
""".strip()


PROMPTS = {
    "plain_json": PLAIN_PROMPT,
    "few_shot_json": FEW_SHOT_PROMPT,
    "lfs_schema": LFS_PROMPT,
    "dense_waypoints": DENSE_PROMPT,
}


TRIGGER_FROM_LEGACY = {
    "direct_execution": "direct",
    "hover_and_wait": "hover-and-wait",
    "continuous_transit": "continuous",
}


@dataclass
class RunConfig:
    model: str
    max_retries: int = 3
    timeout: float = 60.0
    temperature: float = 0.0
    top_p: float = 0.01
    max_tokens: int = 4000


def prompt_for(method: str, item: Dict[str, Any]) -> str:
    if method not in PROMPTS:
        raise ValueError(f"未知方法: {method}")
    return (
        PROMPTS[method]
        + "\n\n【ROS实时情报】\n" + str(item.get("ros_aux_info", ""))
        + "\n【用户指令】\n" + str(item["command"])
        + "\n【输出】\n"
    )


def prompt_manifest() -> Dict[str, Any]:
    return {
        method: {
            "sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "prompt": prompt,
        }
        for method, prompt in PROMPTS.items()
    }


def purify_json_content(raw: str) -> str:
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"```(?:json)?|```", "", cleaned, flags=re.IGNORECASE).strip()
    decoder = json.JSONDecoder()
    candidates: List[Tuple[int, int, str]] = []
    for start, character in enumerate(cleaned):
        if character not in "[{":
            continue
        try:
            _value, length = decoder.raw_decode(cleaned[start:])
        except json.JSONDecodeError:
            continue
        candidates.append((length, start, cleaned[start:start + length]))
    if not candidates:
        return cleaned
    return max(candidates, key=lambda candidate: (candidate[0], candidate[1]))[2]


def parse_available_uavs(text: str) -> Optional[List[int]]:
    match = re.search(r"\[([0-9,\s]+)\]", text or "")
    if not match:
        return None
    return [int(value.strip()) for value in match.group(1).split(",") if value.strip()]


def normalize_error(payload: Any) -> Optional[str]:
    if not isinstance(payload, dict) or "error" not in payload:
        return None
    error = payload["error"]
    if isinstance(error, dict):
        value = error.get("category") or error.get("code") or error.get("type")
    else:
        value = error
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "irrelevant": "unrelated", "off_topic": "unrelated", "3": "unrelated",
        "invalid_uav": "unknown_uav", "nonexistent_uav": "unknown_uav", "2": "unknown_uav",
        "missing_information": "missing_formation", "missing_field": "missing_formation", "1": "missing_formation",
        "conflict": "ambiguous", "ambiguity": "ambiguous",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in ERROR_CATEGORIES else None


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} 不能是布尔值")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} 必须为数值") from exc
    if not math.isfinite(result):
        raise ValueError(f"{field} 必须为有限数值")
    return result


def _canonical_task(raw: Dict[str, Any]) -> Dict[str, Any]:
    required = ("U", "F", "c", "r", "T", "m", "s", "q")
    missing = [field for field in required if field not in raw]
    if missing:
        raise ValueError(f"LFS task 缺少字段: {missing}")
    center = raw["c"]
    if not isinstance(center, list) or len(center) != 3:
        raise ValueError("c 必须是三维数组")
    uavs = [int(value) for value in raw["U"]]
    formation_aliases = {
        "circle": "Circle", "circular": "Circle", "line": "Line", "linear": "Line",
        "sphere": "Sphere", "spherical": "Sphere", "free": "Free", "triangle": "Triangle",
        "triangular": "Triangle", "polygon": "Polygon", "polygonal": "Polygon", "lineup": "Lineup",
    }
    trigger_aliases = {
        "direct_execution": "direct", "direct": "direct",
        "hover_and_wait": "hover-and-wait", "hover-and-wait": "hover-and-wait",
        "continuous_transit": "continuous", "continuous": "continuous",
    }
    formation = str(raw["F"])
    style = str(raw["m"]).lower()
    trigger = str(raw["q"]).lower()
    result: Dict[str, Any] = {
        "U": uavs,
        "F": formation_aliases.get(formation.lower(), formation),
        "c": [_number(value, "c") for value in center],
        "r": _number(raw["r"], "r"),
        "T": _number(raw["T"], "T"),
        "m": style,
        "s": _number(raw["s"], "s"),
        "q": trigger_aliases.get(trigger, trigger),
    }
    for optional in ("parallel_group", "wait_time"):
        if optional in raw:
            result[optional] = raw[optional]
    return result


def _plain_tasks(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        raw_tasks = payload
    elif isinstance(payload, dict):
        raw_tasks = payload.get("tasks") or payload.get("formations") or payload.get("commands")
        if raw_tasks is None and any(key in payload for key in ("U", "uav_ids", "drone_ids", "uavs")):
            raw_tasks = [payload]
    else:
        raw_tasks = None
    if not isinstance(raw_tasks, list):
        raise ValueError("plain JSON 缺少任务数组")
    tasks = []
    for raw in raw_tasks:
        if not isinstance(raw, dict):
            raise ValueError("plain JSON 任务不是对象")
        tasks.append(_canonical_task({
            "U": raw.get("U", raw.get("uav_ids", raw.get("drone_ids", raw.get("uavs")))),
            "F": raw.get("F", raw.get("formation", raw.get("formation_type"))),
            "c": raw.get("c", raw.get("center")),
            "r": raw.get("r", raw.get("radius", raw.get("spacing", raw.get("size")))),
            "T": raw.get("T", raw.get("duration", raw.get("duration_seconds"))),
            "m": raw.get("m", raw.get("style", raw.get("motion_style", raw.get("motion_profile", "normal")))),
            "s": raw.get("s", raw.get("safety_factor", raw.get("safety", 1.0))),
            "q": raw.get("q", raw.get("trigger", raw.get("execution", raw.get("relationship", "direct")))),
            **({"parallel_group": raw["parallel_group"]} if "parallel_group" in raw else {}),
        }))
    return tasks


def _legacy_tasks(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_tasks = payload.get("task_sequences")
    if not isinstance(raw_tasks, list):
        raise ValueError("few-shot JSON 缺少 task_sequences")
    tasks = []
    for raw in raw_tasks:
        parametric = raw.get("parametric_data") or {}
        task = {
            "U": raw.get("uav_id"),
            "F": parametric.get("formation_type"),
            "c": raw.get("global_center"),
            "r": parametric.get("formation_radius"),
            "T": raw.get("duration_seconds"),
            "m": raw.get("motion_profile", "normal"),
            "s": raw.get("iapf_safety_margin_factor") if raw.get("iapf_safety_margin_factor") is not None else 1.0,
            "q": TRIGGER_FROM_LEGACY.get(raw.get("trigger_condition"), raw.get("trigger_condition")),
        }
        if "parallel_group" in raw:
            task["parallel_group"] = raw["parallel_group"]
        tasks.append(_canonical_task(task))
    return tasks


def _validate_dense(raw_tasks: Sequence[Dict[str, Any]]) -> None:
    for raw in raw_tasks:
        waypoints = raw.get("waypoints")
        if not isinstance(waypoints, list):
            raise ValueError("dense task 缺少 waypoints")
        ids = []
        for waypoint in waypoints:
            position = waypoint.get("position") if isinstance(waypoint, dict) else None
            if not isinstance(position, list) or len(position) != 3:
                raise ValueError("dense waypoint 必须包含三维 position")
            [_number(value, "position") for value in position]
            ids.append(int(waypoint.get("uav_id")))
        if set(ids) != set(int(value) for value in raw.get("U", [])):
            raise ValueError("dense waypoints 未完整覆盖 U")


def validate_normalized_lfs(payload: Dict[str, Any], available_uavs: Optional[Sequence[int]]) -> None:
    schema_path = Path(__file__).resolve().parents[2] / "schemas" / "lfs_schema.json"
    with schema_path.open(encoding="utf-8") as handle:
        schema = json.load(handle)
    schema_errors = sorted(Draft202012Validator(schema).iter_errors(payload), key=lambda error: list(error.path))
    if schema_errors:
        raise ValueError(f"公共 LFS schema 校验失败: {schema_errors[0].message}")
    formations = {"Circle", "Line", "Sphere", "Free", "Triangle", "Polygon", "Lineup"}
    styles = {"smooth", "normal", "aggressive"}
    triggers = {"direct", "hover-and-wait", "continuous"}
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("规范化 LFS 必须包含非空 tasks")
    available = set(available_uavs or [])
    for raw in tasks:
        canonical = _canonical_task(raw)
        if not canonical["U"] or len(set(canonical["U"])) != len(canonical["U"]):
            raise ValueError("U 必须非空且无重复")
        if available and not set(canonical["U"]).issubset(available):
            raise ValueError("输出包含不存在的 UAV")
        if canonical["F"] not in formations or canonical["m"] not in styles or canonical["q"] not in triggers:
            raise ValueError("输出包含非法枚举")
        if canonical["r"] <= 0 or canonical["T"] <= 0 or canonical["s"] < 0:
            raise ValueError("r/T/s 数值范围非法")


def normalize_response(method: str, payload: Any, available_uavs: Optional[Sequence[int]]) -> Dict[str, Any]:
    error = normalize_error(payload)
    if error:
        return {"error": error}
    if method == "plain_json":
        tasks = _plain_tasks(payload)
    elif method == "few_shot_json":
        tasks = _legacy_tasks(payload)
    elif method in {"lfs_schema", "dense_waypoints"}:
        raw_tasks = payload.get("tasks")
        if not isinstance(raw_tasks, list):
            raise ValueError("formal LFS 缺少 tasks")
        if method == "dense_waypoints":
            _validate_dense(raw_tasks)
        tasks = [_canonical_task(raw) for raw in raw_tasks]
    else:
        raise ValueError(f"未知方法: {method}")
    normalized = {"lfs_version": "1.0", "tasks": tasks}
    validate_normalized_lfs(normalized, available_uavs)
    return normalized


def _usage(response: Any, name: str) -> int:
    usage = getattr(response, "usage", None)
    return int(getattr(usage, name, 0) or 0)


def call_method(client: Any, method: str, item: Dict[str, Any], config: RunConfig) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    prompt = prompt_for(method, item)
    attempts: List[Dict[str, Any]] = []
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_latency_ms = 0
    final_payload: Optional[Dict[str, Any]] = None
    normalized: Optional[Dict[str, Any]] = None
    last_error = ""
    available_uavs = parse_available_uavs(str(item.get("ros_aux_info", "")))

    for attempt_index in range(config.max_retries):
        response = None
        raw_content = ""
        started = time.perf_counter()
        valid_json = False
        schema_valid = False
        try:
            response = client.chat.completions.create(
                model=config.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=config.temperature,
                top_p=config.top_p,
                max_tokens=config.max_tokens,
                response_format={"type": "json_object"},
                timeout=config.timeout,
            )
            raw_content = response.choices[0].message.content or ""
            final_payload = json.loads(purify_json_content(raw_content))
            valid_json = True
            normalized = normalize_response(method, final_payload, available_uavs)
            schema_valid = True
            last_error = ""
        except json.JSONDecodeError as exc:
            last_error = "invalid_json"
            final_payload = None
            error_detail = str(exc)
        except Exception as exc:  # API errors and structural failures are experiment outcomes
            error_detail = f"{type(exc).__name__}: {exc}"
            if response is None and ("(2056)" in error_detail or "Token Plan 用量上限" in error_detail):
                last_error = "quota_exhausted"
            else:
                last_error = "api_error" if response is None else "normalization_error"
        latency_ms = int((time.perf_counter() - started) * 1000)
        prompt_tokens = _usage(response, "prompt_tokens") if response else 0
        completion_tokens = _usage(response, "completion_tokens") if response else 0
        total_prompt_tokens += prompt_tokens
        total_completion_tokens += completion_tokens
        total_latency_ms += latency_ms
        attempts.append({
            "attempt": attempt_index + 1,
            "latency_ms": latency_ms,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "valid_json": valid_json,
            "schema_valid": schema_valid,
            "error_type": last_error,
            "error_detail": "" if not last_error else error_detail,
            "raw_response": raw_content,
        })
        if schema_valid:
            break
        if last_error == "quota_exhausted":
            break
        if attempt_index + 1 < config.max_retries:
            time.sleep(2 ** attempt_index)

    result = {
        "valid_json": bool(attempts and attempts[-1]["valid_json"]),
        "schema_valid": bool(attempts and attempts[-1]["schema_valid"]),
        "compiled_success": bool(normalized and normalized.get("tasks")),
        "normalized": normalized,
        "prompt_tokens": total_prompt_tokens,
        "completion_tokens": total_completion_tokens,
        "latency_ms": total_latency_ms,
        "retry_count": max(0, len(attempts) - 1),
        "error_type": last_error,
    }
    return result, attempts


def _close(left: Any, right: Any) -> bool:
    try:
        return math.isclose(float(left), float(right), abs_tol=NUMERIC_TOLERANCE, rel_tol=0.0)
    except (TypeError, ValueError):
        return False


def _center_error(expected: Sequence[Any], actual: Sequence[Any]) -> float:
    return math.sqrt(sum((float(left) - float(right)) ** 2 for left, right in zip(expected, actual)))


def _pair_tasks(expected: List[Dict[str, Any]], actual: List[Dict[str, Any]], grouped: bool) -> List[Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]]:
    if not grouped:
        count = max(len(expected), len(actual))
        return [
            (expected[index] if index < len(expected) else None, actual[index] if index < len(actual) else None)
            for index in range(count)
        ]
    remaining = list(actual)
    pairs: List[Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]] = []
    for expected_task in expected:
        if not remaining:
            pairs.append((expected_task, None))
            continue
        scores = []
        for candidate in remaining:
            score = 4 * (set(expected_task["U"]) == set(candidate["U"]))
            score += 2 * (expected_task["F"] == candidate["F"])
            score += sum(_close(a, b) for a, b in zip(expected_task["c"], candidate["c"]))
            scores.append(score)
        best_index = max(range(len(remaining)), key=lambda index: (scores[index], -index))
        pairs.append((expected_task, remaining.pop(best_index)))
    pairs.extend((None, extra) for extra in remaining)
    return pairs


def evaluate_prediction(item: Dict[str, Any], normalized: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    empty_metrics = {
        "matched_task_coverage": "", "uav_set_accuracy": "", "formation_accuracy": "",
        "center_error": "", "radius_error": "", "duration_error": "",
        "motion_style_accuracy": "", "safety_factor_error": "", "trigger_accuracy": "",
        "field_accuracy": "", "exact_task_accuracy": "", "rejection_accuracy": "",
    }
    if "expected_error" in item:
        actual_error = normalized.get("error") if normalized else None
        empty_metrics["rejection_accuracy"] = float(actual_error == item["expected_error"])
        return empty_metrics

    expected = item["expected_lfs"]["tasks"]
    actual = normalized.get("tasks", []) if normalized else []
    grouped = item.get("type") == "grouped"
    pairs = _pair_tasks(expected, actual, grouped)
    denominator = max(len(expected), len(actual), 1)
    matched = [(left, right) for left, right in pairs if left is not None and right is not None]
    discrete = {"U": 0, "F": 0, "m": 0, "q": 0}
    numeric_correct = {"c": 0, "r": 0, "T": 0, "s": 0}
    center_errors: List[float] = []
    radius_errors: List[float] = []
    duration_errors: List[float] = []
    safety_errors: List[float] = []
    for expected_task, actual_task in matched:
        discrete["U"] += set(expected_task["U"]) == set(actual_task["U"])
        discrete["F"] += expected_task["F"] == actual_task["F"]
        discrete["m"] += expected_task["m"] == actual_task["m"]
        discrete["q"] += expected_task["q"] == actual_task["q"]
        center_error = _center_error(expected_task["c"], actual_task["c"])
        radius_error = abs(float(expected_task["r"]) - float(actual_task["r"]))
        duration_error = abs(float(expected_task["T"]) - float(actual_task["T"]))
        safety_error = abs(float(expected_task["s"]) - float(actual_task["s"]))
        center_errors.append(center_error)
        radius_errors.append(radius_error)
        duration_errors.append(duration_error)
        safety_errors.append(safety_error)
        numeric_correct["c"] += center_error <= NUMERIC_TOLERANCE
        numeric_correct["r"] += radius_error <= NUMERIC_TOLERANCE
        numeric_correct["T"] += duration_error <= NUMERIC_TOLERANCE
        numeric_correct["s"] += safety_error <= NUMERIC_TOLERANCE
    correct_fields = sum(discrete.values()) + sum(numeric_correct.values())
    exact = len(expected) == len(actual) and correct_fields == denominator * 8
    return {
        "matched_task_coverage": len(matched) / denominator,
        "uav_set_accuracy": discrete["U"] / denominator,
        "formation_accuracy": discrete["F"] / denominator,
        "center_error": sum(center_errors) / len(center_errors) if center_errors else "",
        "radius_error": sum(radius_errors) / len(radius_errors) if radius_errors else "",
        "duration_error": sum(duration_errors) / len(duration_errors) if duration_errors else "",
        "motion_style_accuracy": discrete["m"] / denominator,
        "safety_factor_error": sum(safety_errors) / len(safety_errors) if safety_errors else "",
        "trigger_accuracy": discrete["q"] / denominator,
        "field_accuracy": correct_fields / (denominator * 8),
        "exact_task_accuracy": float(exact),
        "rejection_accuracy": "",
    }
