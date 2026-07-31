#!/usr/bin/env python3
"""Shared configuration, validation, and I/O helpers for experiment 10."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

import yaml


SCRIPT_DIR = Path(__file__).resolve().parent
EXPERIMENT_ROOT = SCRIPT_DIR.parent
REPO_ROOT = EXPERIMENT_ROOT.parents[1]
WORKSPACE_ROOT = REPO_ROOT.parents[1]
CONFIG_PATH = EXPERIMENT_ROOT / "configs" / "full_system.yaml"
COMMAND_ROOT = EXPERIMENT_ROOT / "commands"
TASK_NAMES = (
    "task_a_simple",
    "task_b_sequential",
    "task_c_grouped",
    "task_d_dense",
    "task_e_mixed",
)


@dataclass(frozen=True)
class Stage:
    stage_id: int
    parallel_group: str
    uav_ids: tuple[int, ...]
    formation_type: str
    center: tuple[float, float, float]
    radius: float
    duration: float
    motion_style: str

    def to_lfs_task(self, task_sequence_id: int) -> Dict[str, Any]:
        return {
            "task_sequence_id": task_sequence_id,
            "uav_id": list(self.uav_ids),
            "uav_count": len(self.uav_ids),
            "global_center": list(self.center),
            "parametric_data": {
                "formation_type": self.formation_type,
                "formation_radius": self.radius,
            },
            "duration_seconds": self.duration,
            "motion_profile": self.motion_style,
            "iapf_safety_margin_factor": 1.0,
            "trigger_condition": (
                "direct_execution" if self.stage_id == 1 else "hover_and_wait"
            ),
            "wait_time": 0.0,
        }


@dataclass(frozen=True)
class TaskDefinition:
    task_type: str
    command_text: str
    stages: tuple[Stage, ...]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_yaml(path: Path = CONFIG_PATH) -> Dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"configuration does not exist: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"configuration must be a mapping: {path}")
    return payload


def load_task(task_type: str) -> TaskDefinition:
    if task_type not in TASK_NAMES:
        raise ValueError(f"unknown task_type: {task_type}")
    path = COMMAND_ROOT / f"{task_type}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    stages = tuple(
        Stage(
            stage_id=int(row["stage_id"]),
            parallel_group=str(row["parallel_group"]),
            uav_ids=tuple(int(value) for value in row["uav_ids"]),
            formation_type=str(row["formation_type"]),
            center=tuple(float(value) for value in row["center"]),
            radius=float(row["radius"]),
            duration=float(row["duration"]),
            motion_style=str(row["motion_style"]),
        )
        for row in payload["stages"]
    )
    task = TaskDefinition(
        task_type=str(payload["task_type"]),
        command_text=str(payload["command_text"]),
        stages=stages,
    )
    validate_task(task)
    return task


def validate_task(task: TaskDefinition) -> None:
    if task.task_type not in TASK_NAMES:
        raise ValueError(f"unsupported task type: {task.task_type}")
    if not task.command_text.strip() or not task.stages:
        raise ValueError(f"{task.task_type}: command and stages are required")
    stage_ids = sorted({stage.stage_id for stage in task.stages})
    if stage_ids != list(range(1, max(stage_ids) + 1)):
        raise ValueError(f"{task.task_type}: stage ids must be contiguous")
    for stage_id in stage_ids:
        members: set[int] = set()
        durations: set[float] = set()
        groups = [stage for stage in task.stages if stage.stage_id == stage_id]
        for stage in groups:
            overlap = members.intersection(stage.uav_ids)
            if overlap:
                raise ValueError(
                    f"{task.task_type}: stage {stage_id} overlaps UAVs {overlap}")
            members.update(stage.uav_ids)
            durations.add(stage.duration)
            if len(stage.center) != 3 or stage.radius <= 0 or stage.duration <= 0:
                raise ValueError(f"{task.task_type}: invalid stage geometry")
            if stage.motion_style not in {"smooth", "normal", "aggressive"}:
                raise ValueError(f"{task.task_type}: invalid motion style")
        if len(groups) > 1 and len(durations) != 1:
            raise ValueError(
                f"{task.task_type}: parallel durations must match in stage {stage_id}")
    expected = set(range(1, 9))
    for stage_id in stage_ids:
        members = {
            uid for stage in task.stages if stage.stage_id == stage_id
            for uid in stage.uav_ids
        }
        if members != expected:
            raise ValueError(
                f"{task.task_type}: stage {stage_id} must cover UAV1-8")
    if task.task_type == "task_d_dense":
        radius = task.stages[0].radius
        if radius < 2.2:
            raise ValueError("dense task radius must be at least 2.2 m")


def stage_groups(task: TaskDefinition) -> List[List[Stage]]:
    return [
        [stage for stage in task.stages if stage.stage_id == stage_id]
        for stage_id in sorted({stage.stage_id for stage in task.stages})
    ]


def expected_lfs(task: TaskDefinition) -> Dict[str, Any]:
    tasks: List[Dict[str, Any]] = []
    for index, stage in enumerate(task.stages, start=1):
        row = {
            "task_sequence_id": index,
            "U": list(stage.uav_ids),
            "F": stage.formation_type,
            "c": list(stage.center),
            "r": stage.radius,
            "T": stage.duration,
            "m": stage.motion_style,
            "s": 1.0,
            "q": "direct" if stage.stage_id == 1 else "hover-and-wait",
        }
        if len([
            item for item in task.stages if item.stage_id == stage.stage_id
        ]) > 1:
            row["parallel_group"] = stage.parallel_group
        tasks.append(row)
    return {"tasks": tasks}


def semantic_signature(lfs: Dict[str, Any]) -> List[Dict[str, Any]]:
    signature = []
    for task in lfs.get("task_sequences", []):
        signature.append({
            "uav_ids": tuple(sorted(int(value) for value in task.get("uav_id", []))),
            "formation_type": task.get("parametric_data", {}).get("formation_type"),
            "center": tuple(round(float(value), 3) for value in task.get("global_center", [])),
            "radius": round(float(
                task.get("parametric_data", {}).get("formation_radius", math.nan)), 3),
            "duration": round(float(task.get("duration_seconds", math.nan)), 3),
            "motion_style": task.get("motion_profile"),
        })
    return signature


def expected_signature(task: TaskDefinition) -> List[Dict[str, Any]]:
    return [{
        "uav_ids": tuple(sorted(stage.uav_ids)),
        "formation_type": stage.formation_type,
        "center": tuple(round(value, 3) for value in stage.center),
        "radius": round(stage.radius, 3),
        "duration": round(stage.duration, 3),
        "motion_style": stage.motion_style,
    } for stage in task.stages]


def verify_llm_intent(task: TaskDefinition, lfs: Dict[str, Any]) -> tuple[bool, str]:
    actual = semantic_signature(lfs)
    expected = expected_signature(task)
    if actual != expected:
        return False, (
            "compiled LFS does not match the frozen command configuration: "
            f"expected={expected}, actual={actual}")
    return True, ""


def config_checksum(paths: Sequence[Path] | None = None) -> str:
    selected = list(paths or [CONFIG_PATH] + [
        COMMAND_ROOT / f"{task}.json" for task in TASK_NAMES
    ])
    digest = hashlib.sha256()
    for path in selected:
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    def safe(value: Any) -> Any:
        if isinstance(value, float) and not math.isfinite(value):
            return None
        if isinstance(value, dict):
            return {key: safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [safe(item) for item in value]
        return value

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(safe(payload), indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, rows: Iterable[Dict[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(fields), extrasaction="ignore",
            lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"required CSV is missing: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def finite(values: Iterable[Any]) -> List[float]:
    result: List[float] = []
    for value in values:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            result.append(number)
    return result


def quantile(values: Iterable[Any], probability: float) -> float:
    items = sorted(finite(values))
    if not items:
        return math.nan
    if len(items) == 1:
        return items[0]
    position = (len(items) - 1) * probability
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return items[lower]
    return items[lower] + (items[upper] - items[lower]) * (position - lower)


def mean(values: Iterable[Any]) -> float:
    items = finite(values)
    return statistics.fmean(items) if items else math.nan


def stddev(values: Iterable[Any]) -> float:
    items = finite(values)
    return statistics.stdev(items) if len(items) > 1 else 0.0 if items else math.nan


def bool_value(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "success"}
