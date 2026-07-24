import copy
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    from jsonschema import Draft202012Validator
except ModuleNotFoundError:
    Draft202012Validator = None


DEFAULT_CONSTRAINTS = [
    "minimal_topology_change",
    "no_trajectory_cross",
    "keep_safety_distance",
]

LEGACY_TRIGGER_BY_LFS = {
    "direct": "direct_execution",
    "hover-and-wait": "hover_and_wait",
    "continuous": "continuous_transit",
}

LEGACY_REQUIRED_FIELDS = [
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
]

LFS_REQUIRED_FIELDS = ["U", "F", "c", "r", "T", "m", "s", "q"]

SAFETY_TERMS = ("安全系数", "避障系数", "安全裕度", "safety factor", "safety_factor")


class LFSValidationError(ValueError):
    """Raised when an LFS payload fails schema or semantic validation."""


def _schema_candidates() -> List[Path]:
    candidates: List[Path] = []
    env_path = os.getenv("LFS_SCHEMA_PATH")
    if env_path:
        candidates.append(Path(env_path))

    here = Path(__file__).resolve()
    candidates.extend(
        [
            here.parents[2] / "schemas" / "lfs_schema.json",
            here.parents[3] / "schemas" / "lfs_schema.json",
            Path.cwd() / "schemas" / "lfs_schema.json",
            Path.cwd().parent / "schemas" / "lfs_schema.json",
        ]
    )

    try:
        from ament_index_python.packages import get_package_share_directory

        share_dir = Path(get_package_share_directory("location_allocate"))
        candidates.append(share_dir / "schemas" / "lfs_schema.json")
    except Exception:
        pass

    return candidates


def load_lfs_schema() -> Dict[str, Any]:
    for candidate in _schema_candidates():
        if candidate.is_file():
            with candidate.open("r", encoding="utf-8") as schema_file:
                return json.load(schema_file)
    searched = ", ".join(str(path) for path in _schema_candidates())
    raise FileNotFoundError(f"未找到 LFS schema，已搜索: {searched}")


def validate_schema(payload: Dict[str, Any], schema: Optional[Dict[str, Any]] = None) -> None:
    if Draft202012Validator is None:
        raise LFSValidationError("缺少 jsonschema 依赖，请安装 python3-jsonschema 或在虚拟环境中执行 pip install jsonschema")

    validator = Draft202012Validator(schema or load_lfs_schema())
    errors = sorted(validator.iter_errors(payload), key=lambda err: list(err.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "<root>"
        raise LFSValidationError(f"JSON schema 校验失败: {location}: {first.message}")


def parse_available_uav_ids(ros_aux_info: str) -> Optional[List[int]]:
    if not ros_aux_info:
        return None

    import re

    match = re.search(r"\[([0-9,\s]+)\]", ros_aux_info)
    if not match:
        return None

    ids = [int(item.strip()) for item in match.group(1).split(",") if item.strip()]
    return ids or None


def estimate_field_accuracy(payload: Dict[str, Any]) -> float:
    tasks = _payload_tasks(payload)
    required = LFS_REQUIRED_FIELDS if _is_formal_lfs(payload) else LEGACY_REQUIRED_FIELDS
    if not tasks:
        return 0.0

    total = len(tasks) * len(required)
    present = 0
    for task in tasks:
        present += sum(1 for field in required if field in task)
    return round(present / total, 4) if total else 0.0


def canonicalize_lfs_payload(
    payload: Dict[str, Any],
    source_command: Optional[str] = None,
) -> Dict[str, Any]:
    """Normalize a draft LFS before schema validation and compilation.

    The LLM extracts explicit task semantics. Defaults, aliases, and transition
    behavior are deterministic compiler concerns so they cannot drift with the
    wording of a prompt.
    """
    canonical = copy.deepcopy(payload)
    if not _is_formal_lfs(canonical):
        for task in canonical.get("task_sequences", []):
            parametric = task.get("parametric_data", {})
            if parametric.get("formation_type") == "Lineup":
                parametric["formation_type"] = "Line"
        return canonical

    tasks = _payload_tasks(canonical)
    safety_is_explicit = source_command is None or any(
        term in source_command.lower() for term in SAFETY_TERMS
    )
    for task in tasks:
        if task.get("F") == "Lineup":
            task["F"] = "Line"
        task.setdefault("m", "normal")
        if safety_is_explicit:
            task.setdefault("s", 1.0)
        else:
            task["s"] = 1.0

    _reject_style_only_task_splits(tasks)
    _derive_transition_modes(tasks)
    return canonical


def _derive_transition_modes(tasks: Sequence[Dict[str, Any]]) -> None:
    for index, task in enumerate(tasks):
        if task.get("q") == "hover-and-wait":
            continue
        current_uavs = set(task.get("U", []))
        has_sequential_successor = False
        for later in tasks[index + 1:]:
            later_uavs = set(later.get("U", []))
            same_parallel_group = (
                task.get("parallel_group") is not None
                and task.get("parallel_group") == later.get("parallel_group")
            )
            dependency = task.get("task_id", index + 1) in later.get("depends_on", [])
            if dependency or (current_uavs & later_uavs and not same_parallel_group):
                has_sequential_successor = True
                break
        task["q"] = "continuous" if has_sequential_successor else "direct"


def _reject_style_only_task_splits(tasks: Sequence[Dict[str, Any]]) -> None:
    for previous, current in zip(tasks, tasks[1:]):
        same_target = all(
            previous.get(field) == current.get(field)
            for field in ("U", "F", "c", "r")
        )
        if same_target and previous.get("m", "normal") != current.get("m", "normal"):
            raise LFSValidationError(
                "style_split_as_task: 相同目标不能仅因 motion style 不同拆成多个任务；"
                "请保留一个任务并把 m 设置为用户指定的风格"
            )


def validate_and_compile_lfs(
    payload: Dict[str, Any],
    available_uav_ids: Optional[Sequence[int]] = None,
    schema: Optional[Dict[str, Any]] = None,
    source_command: Optional[str] = None,
) -> Dict[str, Any]:
    canonical = canonicalize_lfs_payload(payload, source_command)
    validate_schema(canonical, schema)

    compiled = _compile_formal_lfs(canonical) if _is_formal_lfs(canonical) else _normalize_legacy_payload(canonical)
    _validate_semantics(compiled, available_uav_ids)
    return compiled


def _is_formal_lfs(payload: Dict[str, Any]) -> bool:
    return "tasks" in payload or "M" in payload


def _payload_tasks(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    if "task_sequences" in payload:
        return payload.get("task_sequences") or []
    if "tasks" in payload:
        return payload.get("tasks") or []
    if "M" in payload:
        return payload.get("M") or []
    return []


def _compile_formal_lfs(payload: Dict[str, Any]) -> Dict[str, Any]:
    tasks = payload.get("tasks", payload.get("M", []))
    compiled_tasks = []
    for index, task in enumerate(tasks, start=1):
        task_id = int(task.get("task_sequence_id", task.get("task_id", index)))
        trigger_condition = LEGACY_TRIGGER_BY_LFS[task["q"]]
        wait_time = task.get("wait_time")
        if wait_time is None and trigger_condition != "hover_and_wait":
            wait_time = None

        compiled = {
            "task_sequence_id": task_id,
            "duration_seconds": float(task["T"]),
            "uav_id": [int(uid) for uid in task["U"]],
            "uav_count": len(task["U"]),
            "trigger_condition": trigger_condition,
            "wait_time": None if wait_time is None else float(wait_time),
            "iapf_safety_margin_factor": float(task["s"]),
            "motion_profile": task["m"],
            "constraints": list(task.get("constraints", DEFAULT_CONSTRAINTS)),
            "global_center": [float(value) for value in task["c"]],
            "generation_mode": "parametric",
            "parametric_data": {
                "formation_type": task["F"],
                "formation_radius": float(task["r"]),
            },
        }
        if "parallel_group" in task:
            compiled["parallel_group"] = task["parallel_group"]
        compiled_tasks.append(compiled)

    return {"task_sequences": compiled_tasks}


def _normalize_legacy_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = copy.deepcopy(payload)
    normalized_tasks = []
    for task in normalized["task_sequences"]:
        task["uav_id"] = [int(uid) for uid in task["uav_id"]]
        task["uav_count"] = int(task["uav_count"])
        task["duration_seconds"] = float(task["duration_seconds"])
        task["global_center"] = [float(value) for value in task["global_center"]]
        task["wait_time"] = _none_or_float(task.get("wait_time"))
        task["iapf_safety_margin_factor"] = _none_or_float(task.get("iapf_safety_margin_factor"))
        task["parametric_data"]["formation_radius"] = float(task["parametric_data"]["formation_radius"])
        normalized_tasks.append(task)
    normalized["task_sequences"] = normalized_tasks
    return normalized


def _none_or_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() in {"none", "null", ""}:
        return None
    return float(value)


def _validate_semantics(payload: Dict[str, Any], available_uav_ids: Optional[Sequence[int]]) -> None:
    tasks = payload.get("task_sequences", [])
    available_ids = set(int(uid) for uid in available_uav_ids) if available_uav_ids else None

    for task in tasks:
        task_label = task.get("task_sequence_id", "未知")
        uav_ids = task["uav_id"]

        if task["uav_count"] != len(uav_ids):
            raise LFSValidationError(f"任务 {task_label} 的 uav_count 与 uav_id 数量不一致")
        if len(set(uav_ids)) != len(uav_ids):
            raise LFSValidationError(f"任务 {task_label} 的 uav_id 存在重复")
        if available_ids is not None:
            unknown = sorted(set(uav_ids) - available_ids)
            if unknown:
                raise LFSValidationError(f"任务 {task_label} 包含不存在的 UAV ID: {unknown}")

        if task["duration_seconds"] <= 0:
            raise LFSValidationError(f"任务 {task_label} 的 duration_seconds 必须大于 0")
        if task["parametric_data"]["formation_radius"] <= 0:
            raise LFSValidationError(f"任务 {task_label} 的 formation_radius 必须大于 0")
        if task.get("iapf_safety_margin_factor") is not None and task["iapf_safety_margin_factor"] < 0:
            raise LFSValidationError(f"任务 {task_label} 的 iapf_safety_margin_factor 不能小于 0")

    _validate_parallel_groups(tasks)


def _validate_parallel_groups(tasks: Iterable[Dict[str, Any]]) -> None:
    groups: Dict[Any, Tuple[int, set]] = {}
    for task in tasks:
        if "parallel_group" not in task:
            continue

        group_id = task["parallel_group"]
        task_ids = set(task["uav_id"])
        if group_id not in groups:
            groups[group_id] = (task.get("task_sequence_id", 0), task_ids)
            continue

        first_task_id, existing_ids = groups[group_id]
        overlap = sorted(existing_ids & task_ids)
        if overlap:
            current_task_id = task.get("task_sequence_id", 0)
            raise LFSValidationError(
                f"parallel_group={group_id} 中任务 {first_task_id} 与任务 {current_task_id} 的 UAV 集合重叠: {overlap}"
            )
        existing_ids.update(task_ids)
