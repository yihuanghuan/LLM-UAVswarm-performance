#!/usr/bin/env python3
"""离线评估不同无人机目标分配策略。"""

from __future__ import annotations

import argparse
import csv
import math
import sys
import time
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Sequence

import numpy as np
from scipy.optimize import linear_sum_assignment


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_SRC = REPO_ROOT / "location_allocate"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from location_allocate.safety_aware_allocator import SafetyAwareTopologyAllocator  # noqa: E402


RESULT_FIELDS = [
    "trial_id",
    "scenario",
    "num_uav",
    "method",
    "total_path_length",
    "avg_path_length",
    "xy_crossings",
    "proximity_crossings",
    "min_distance",
    "safety_cost",
    "total_cost",
    "compute_time_ms",
]

METHODS = [
    "random",
    "nearest_neighbor",
    "hungarian_distance",
    "safety_aware_hungarian",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="离线比较分配基线与安全感知匈牙利分配。")
    parser.add_argument("--trials", type=int, default=50, help="每个场景的随机试验次数。")
    parser.add_argument(
        "--output",
        default=str(REPO_ROOT / "experiments" / "results" / "assignment_results.csv"),
        help="输出 CSV 路径。",
    )
    parser.add_argument("--seed", type=int, default=20260708, help="随机种子。")
    parser.add_argument("--duration", type=float, default=8.0, help="名义轨迹持续时间。")
    parser.add_argument("--safety-distance", type=float, default=2.0, help="安全距离阈值。")
    return parser.parse_args()


def random_points(rng: np.random.Generator, n: int, xy_span: float, z: float) -> np.ndarray:
    xy = rng.uniform(-xy_span, xy_span, size=(n, 2))
    z_col = np.full((n, 1), z)
    return np.hstack([xy, z_col])


def circle_points(n: int, radius: float, z: float, phase: float = 0.0) -> np.ndarray:
    angles = np.linspace(0.0, 2.0 * math.pi, n, endpoint=False) + phase
    return np.column_stack([radius * np.cos(angles), radius * np.sin(angles), np.full(n, z)])


def line_points(n: int, x: float, y_span: float, z: float) -> np.ndarray:
    y = np.linspace(-y_span, y_span, n)
    return np.column_stack([np.full(n, x), y, np.full(n, z)])


def generate_scenario(name: str, trial_id: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    if name == "small":
        n = 3
        initial = random_points(rng, n, xy_span=4.0, z=3.0)
        targets = circle_points(n, radius=3.0, z=3.0, phase=0.2 * trial_id)
    elif name == "medium":
        n = 5
        initial = random_points(rng, n, xy_span=6.0, z=4.0)
        targets = circle_points(n, radius=4.0, z=4.0, phase=0.1 * trial_id)
    elif name == "large":
        n = 8
        initial = random_points(rng, n, xy_span=8.0, z=4.0)
        targets = circle_points(n, radius=5.0, z=4.0, phase=0.07 * trial_id)
    elif name == "dense":
        n = 8
        initial = random_points(rng, n, xy_span=1.8, z=3.0)
        targets = random_points(rng, n, xy_span=2.2, z=3.0)
    elif name == "crossing-prone":
        n = 8
        initial = line_points(n, x=-5.0, y_span=5.0, z=3.5)
        targets = line_points(n, x=5.0, y_span=5.0, z=3.5)[::-1]
        initial += rng.normal(0.0, 0.15, size=initial.shape)
        targets += rng.normal(0.0, 0.15, size=targets.shape)
        initial[:, 2] = 3.5
        targets[:, 2] = 3.5
    else:
        raise ValueError(f"未知场景: {name}")
    return initial, targets


def random_assignment(n: int, rng: np.random.Generator) -> List[int]:
    return rng.permutation(n).astype(int).tolist()


def nearest_neighbor_assignment(initial: np.ndarray, targets: np.ndarray) -> List[int]:
    remaining = set(range(len(targets)))
    assignment: List[int] = []
    for point in initial:
        best = min(remaining, key=lambda idx: float(np.linalg.norm(point - targets[idx])))
        assignment.append(int(best))
        remaining.remove(best)
    return assignment


def hungarian_assignment(initial: np.ndarray, targets: np.ndarray) -> List[int]:
    cost = np.linalg.norm(initial[:, None, :] - targets[None, :, :], axis=2)
    row_ind, col_ind = linear_sum_assignment(cost)
    assignment = [0] * len(initial)
    for row, col in zip(row_ind, col_ind):
        assignment[int(row)] = int(col)
    return assignment


def assignment_from_allocated(allocated: Sequence[Sequence[float]], targets: np.ndarray) -> List[int]:
    remaining = set(range(len(targets)))
    assignment: List[int] = []
    for point in np.asarray(allocated, dtype=float):
        best = min(remaining, key=lambda idx: float(np.linalg.norm(point - targets[idx])))
        assignment.append(int(best))
        remaining.remove(best)
    return assignment


def write_results(rows: Iterable[Dict[str, object]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def format_float(value: float) -> str:
    if math.isinf(value):
        return "inf"
    return f"{value:.6f}"


def evaluate_method(
    method: str,
    initial: np.ndarray,
    targets: np.ndarray,
    duration: float,
    rng: np.random.Generator,
    allocator_factory: Callable[[], SafetyAwareTopologyAllocator],
) -> tuple[List[int], object, float]:
    start = time.perf_counter()
    allocator = allocator_factory()

    if method == "random":
        assignment = random_assignment(len(initial), rng)
        metrics = allocator.evaluate(initial, targets, assignment, duration)
    elif method == "nearest_neighbor":
        assignment = nearest_neighbor_assignment(initial, targets)
        metrics = allocator.evaluate(initial, targets, assignment, duration)
    elif method == "hungarian_distance":
        assignment = hungarian_assignment(initial, targets)
        metrics = allocator.evaluate(initial, targets, assignment, duration)
    elif method == "safety_aware_hungarian":
        allocated, metrics = allocator.allocate_with_metrics(initial, targets, duration)
        assignment = assignment_from_allocated(allocated, targets)
    else:
        raise ValueError(f"未知方法: {method}")

    compute_time_ms = (time.perf_counter() - start) * 1000.0
    return assignment, metrics, compute_time_ms


def main() -> int:
    args = parse_args()
    if args.trials <= 0:
        raise ValueError("--trials 必须大于 0")
    if args.duration <= 0.0:
        raise ValueError("--duration 必须大于 0")
    if args.safety_distance <= 0.0:
        raise ValueError("--safety-distance 必须大于 0")

    master_rng = np.random.default_rng(args.seed)
    scenarios = ["small", "medium", "large", "dense", "crossing-prone"]

    def allocator_factory() -> SafetyAwareTopologyAllocator:
        return SafetyAwareTopologyAllocator(sample_hz=20.0, d_safe=args.safety_distance)

    rows: List[Dict[str, object]] = []
    for scenario in scenarios:
        for trial_id in range(args.trials):
            trial_seed = int(master_rng.integers(0, 2**31 - 1))
            scenario_rng = np.random.default_rng(trial_seed)
            initial, targets = generate_scenario(scenario, trial_id, scenario_rng)
            for method in METHODS:
                method_rng = np.random.default_rng(trial_seed + METHODS.index(method))
                _assignment, metrics, compute_time_ms = evaluate_method(
                    method,
                    initial,
                    targets,
                    args.duration,
                    method_rng,
                    allocator_factory,
                )
                rows.append({
                    "trial_id": trial_id,
                    "scenario": scenario,
                    "num_uav": len(initial),
                    "method": method,
                    "total_path_length": format_float(metrics.distance),
                    "avg_path_length": format_float(metrics.distance / len(initial)),
                    "xy_crossings": metrics.xy_crossings,
                    "proximity_crossings": metrics.proximity_crossings,
                    "min_distance": format_float(metrics.min_distance),
                    "safety_cost": format_float(metrics.safety),
                    "total_cost": format_float(metrics.total),
                    "compute_time_ms": format_float(compute_time_ms),
                })

    write_results(rows, Path(args.output))
    print(f"已写入 {len(rows)} 行分配评估结果: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
