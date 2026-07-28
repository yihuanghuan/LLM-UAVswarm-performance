#!/usr/bin/env python3
"""Configuration and assignment helpers for experiment 08."""

from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Mapping

import numpy as np
import yaml

from location_allocate.safety_aware_allocator import SafetyAwareTopologyAllocator


EXPERIMENT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = EXPERIMENT_ROOT.parents[1]
CONFIG_ROOT = EXPERIMENT_ROOT / "configs"
RESULTS_ROOT = Path(os.environ.get(
    "EXPERIMENT_08_RESULTS_ROOT",
    REPO_ROOT / "experiments" / "results" / "experiments_08"))


def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(encoding="utf-8") as handle:
        value = yaml.safe_load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a mapping")
    return value


def load_configuration(
    scenario_name: str, method_name: str
) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    defaults = load_yaml(CONFIG_ROOT / "experiment_defaults.yaml")
    methods = load_yaml(CONFIG_ROOT / "methods.yaml").get("methods", {})
    if method_name not in methods:
        raise ValueError(f"unknown method: {method_name}")
    scenario = load_yaml(CONFIG_ROOT / "scenarios" / f"{scenario_name}.yaml")
    return defaults, dict(methods[method_name]), scenario


def circle_targets(formation: Mapping[str, Any], count: int) -> List[List[float]]:
    center = np.asarray(formation["center"], dtype=float)
    radius = float(formation["radius"])
    return [
        (
            center
            + np.asarray([
                radius * math.cos(2.0 * math.pi * index / count),
                radius * math.sin(2.0 * math.pi * index / count),
                0.0,
            ])
        ).tolist()
        for index in range(count)
    ]


def scenario_groups(scenario: Mapping[str, Any]) -> List[Dict[str, Any]]:
    if "groups" in scenario:
        return [
            {
                "uav_ids": [int(value) for value in group["uav_ids"]],
                "initial": [list(map(float, point)) for point in group["initial_positions"]],
                "targets": [list(map(float, point)) for point in group["target_positions"]],
            }
            for group in scenario["groups"]
        ]
    uav_ids = [int(value) for value in scenario["uav_ids"]]
    targets = scenario.get("target_positions")
    if targets is None:
        formation = scenario["formation"]
        if formation.get("type") != "circle":
            raise ValueError("only circle formation generation is supported")
        targets = circle_targets(formation, len(uav_ids))
    return [{
        "uav_ids": uav_ids,
        "initial": [list(map(float, point)) for point in scenario["initial_positions"]],
        "targets": [list(map(float, point)) for point in targets],
    }]


def perturb_groups(
    groups: List[Dict[str, Any]], seed: int, randomization_range: float
) -> List[Dict[str, Any]]:
    generator = np.random.default_rng(seed)
    result = []
    for group in groups:
        initial = np.asarray(group["initial"], dtype=float)
        if randomization_range > 0.0:
            initial += generator.uniform(
                -randomization_range, randomization_range, size=initial.shape)
        result.append({
            "uav_ids": list(group["uav_ids"]),
            "initial": initial.tolist(),
            "targets": [list(point) for point in group["targets"]],
        })
    return result


def assignment_mode(
    scenario: Mapping[str, Any], method: Mapping[str, Any]
) -> str:
    if method["assignment"] == "safety_aware":
        return "safety_aware"
    return "fixed" if scenario.get("fixed_assignment", False) else "distance_hungarian"


def allocate_targets(
    groups: List[Dict[str, Any]],
    duration: float,
    mode: str,
    d_assignment: float,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    allocator = SafetyAwareTopologyAllocator(d_safe=d_assignment)
    if len(groups) > 1 and mode == "safety_aware":
        allocated, metrics = allocator.allocate_grouped(
            groups, duration=duration, mode=mode)
    else:
        allocated = []
        metric_values = []
        for group in groups:
            group_allocated, group_metrics = allocator.allocate_mode_with_metrics(
                group["initial"], group["targets"], duration=duration, mode=mode)
            allocated.append(group_allocated)
            metric_values.append(group_metrics)
        flattened_initial = [
            point for group in groups for point in group["initial"]]
        flattened_targets = [
            point for group in allocated for point in group]
        metrics = allocator.evaluate(
            flattened_initial, flattened_targets,
            list(range(len(flattened_initial))), duration)
    resolved = []
    for group, targets in zip(groups, allocated):
        resolved.append({
            "uav_ids": list(group["uav_ids"]),
            "initial": [list(point) for point in group["initial"]],
            "targets": targets,
        })
    return resolved, {
        "total": metrics.total,
        "distance": metrics.distance,
        "xy_crossings": metrics.xy_crossings,
        "proximity_crossings": metrics.proximity_crossings,
        "safety": metrics.safety,
        "min_distance": metrics.min_distance,
        "iterations": allocator.last_iterations,
    }


def experiment_id(
    batch_id: str, scenario: str, method: str, trial: int, seed: int
) -> str:
    source = f"{batch_id}:{scenario}:{method}:{trial}:{seed}".encode()
    suffix = hashlib.sha256(source).hexdigest()[:10]
    return f"{scenario}-{method}-t{trial:02d}-{suffix}"
