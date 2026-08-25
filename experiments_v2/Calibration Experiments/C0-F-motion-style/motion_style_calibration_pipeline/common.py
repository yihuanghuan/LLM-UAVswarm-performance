#!/usr/bin/env python3
"""Shared immutable definitions for the C0-F calibration harness."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import yaml


PIPELINE = Path(__file__).resolve().parent
STAGE_ROOT = PIPELINE.parent
REPO = PIPELINE.parents[3]
WORKSPACE = Path(os.environ.get("C0F_WORKSPACE", "/home/yihuang/learning/LLM_swarm_ws"))
PX4 = Path(os.environ.get("C0F_PX4", "/home/yihuang/PX4-Autopilot"))
PYTHON = Path(os.environ.get("C0F_PYTHON", str(WORKSPACE / "llm_env/bin/python")))
RESULTS = STAGE_ROOT / "results" / "C0-F_motion_style_freeze"
RAW = RESULTS / "runtime_raw"
SCENES_FILE = PIPELINE / "scene_definitions.yaml"
CANONICAL_POLICY = REPO / "lfs_policy/config/lfs_policy.paper_current.yaml"
START_SHA = "1e58f78ae3678eafdf9d0213e59514879601d461"
STYLES = ("smooth", "normal", "aggressive")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected YAML mapping: {path}")
    return value


def task(task_id: int, scene: dict[str, Any], style: str, *, staging: bool) -> dict[str, Any]:
    common = load_yaml(SCENES_FILE)["common"]
    center = scene["staging_center"] if staging else scene["target_center"]
    duration = (
        {"mode": "explicit", "value": common["staging_duration_s"]}
        if staging else scene["time_request"]
    )
    return {
        "task_id": task_id,
        "U": scene["participants"],
        "F": scene["formation"],
        "c": {"mode": "absolute", "value": center},
        "r": common["formation_scale"],
        "T": duration,
        "m": common["staging_style"] if staging else style,
        "s": common["safety_factor"],
        "q": {"mode": "direct"},
    }


def materialize_scene(scene_id: str, style: str) -> tuple[dict[str, Any], list[int]]:
    definitions = load_yaml(SCENES_FILE)
    scene = definitions["scenes"][scene_id]
    mission = {
        "lfs_version": "2.1",
        "mission": {"nodes": [
            {"type": "task", "task": task(1, scene, "normal", staging=True)},
            {"type": "task", "task": task(2, scene, style, staging=False)},
        ]},
    }
    return mission, [2]


def materialize_style_switch() -> tuple[dict[str, Any], list[int]]:
    definitions = load_yaml(SCENES_FILE)
    base = definitions["style_switch"]
    common = definitions["common"]
    stage_scene = dict(base, target_center=base["staging_center"],
                       time_request={"mode": "explicit", "value": common["staging_duration_s"]})
    nodes = [{"type": "task", "task": task(1, stage_scene, "normal", staging=True)}]
    score_ids = []
    for task_id, item in enumerate(base["sequence"], start=2):
        scene = dict(base, target_center=item["center"])
        nodes.append({"type": "task", "task": task(task_id, scene, item["style"], staging=False)})
        score_ids.append(task_id)
    return {"lfs_version": "2.1", "mission": {"nodes": nodes}}, score_ids


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
