#!/usr/bin/env python3
"""Run the offline target-assignment baseline experiment."""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Sequence

import numpy as np
from scipy.optimize import linear_sum_assignment


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_SRC = REPO_ROOT / "location_allocate"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from location_allocate.safety_aware_allocator import (  # noqa: E402
    AssignmentMetrics,
    SafetyAwareTopologyAllocator,
)


SCENARIOS = ["small", "medium", "large", "dense", "crossing-prone"]
METHODS = [
    "random",
    "nearest_neighbor",
    "hungarian_distance",
    "hungarian_crossing_penalty",
    "safety_aware_local_swap",
]
RESULT_FIELDS = [
    "trial_id",
    "scenario",
    "scenario_seed",
    "num_uav",
    "method",
    "assignment",
    "total_path_length",
    "avg_path_length",
    "xy_crossings",
    "proximity_crossings",
    "min_distance",
    "safety_cost",
    "safety_violation_count",
    "critical_violation_count",
    "arrival_time_variance",
    "failed_assignment",
    "critical_failed_assignment",
    "total_cost",
    "compute_time_ms",
]


@dataclass(frozen=True)
class ExtendedMetrics:
    assignment_metrics: AssignmentMetrics
    safety_violation_count: int
    critical_violation_count: int
    arrival_time_variance: float
    failed_assignment: int
    critical_failed_assignment: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare five offline UAV assignment baselines.")
    parser.add_argument("--trials", type=int, default=100, help="Trials per scenario.")
    parser.add_argument(
        "--output-dir",
        default=str(REPO_ROOT / "experiments" / "results" / "experiments_04"),
        help="Directory for raw results and run configuration.",
    )
    parser.add_argument("--seed", type=int, default=20260708, help="Master random seed.")
    parser.add_argument("--duration", type=float, default=8.0, help="Nominal trajectory duration in seconds.")
    parser.add_argument("--sample-hz", type=float, default=20.0, help="Trajectory evaluation sample rate.")
    parser.add_argument("--safety-distance", type=float, default=2.0, help="Safety threshold in metres.")
    parser.add_argument(
        "--critical-distance",
        type=float,
        default=1.5,
        help="Secondary severe-violation threshold in metres.",
    )
    parser.add_argument(
        "--scenario-min-distance",
        type=float,
        default=2.1,
        help="Minimum allowed distance within initial and target point sets.",
    )
    parser.add_argument("--nominal-speed", type=float, default=1.0, help="Speed used to estimate arrival times.")
    parser.add_argument(
        "--scenarios",
        nargs="+",
        choices=SCENARIOS,
        default=SCENARIOS,
        help="Scenario subset; defaults to all scenarios.",
    )
    return parser.parse_args()


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_output_dir(requested: Path) -> Path:
    """Never overwrite a non-empty experiment result directory."""
    if requested.exists() and any(requested.iterdir()):
        run_name = datetime.now(timezone.utc).strftime("run_%Y%m%dT%H%M%SZ")
        return requested / run_name
    return requested


def minimum_pair_distance(points: np.ndarray) -> float:
    if len(points) < 2:
        return float("inf")
    return min(
        float(np.linalg.norm(points[i] - points[j]))
        for i, j in itertools.combinations(range(len(points)), 2)
    )


def feasible_random_points(
    rng: np.random.Generator,
    n: int,
    xy_span: float,
    z: float,
    min_distance: float,
    max_attempts: int = 10000,
) -> np.ndarray:
    """Generate planar points using sequential hard-core rejection sampling."""
    accepted: List[np.ndarray] = []
    for _ in range(max_attempts):
        candidate = np.asarray([
            rng.uniform(-xy_span, xy_span),
            rng.uniform(-xy_span, xy_span),
            z,
        ])
        if all(float(np.linalg.norm(candidate - point)) >= min_distance for point in accepted):
            accepted.append(candidate)
            if len(accepted) == n:
                return np.asarray(accepted)
    raise RuntimeError(
        f"Could not place {n} points at least {min_distance} m apart "
        f"inside xy_span={xy_span}"
    )


def circle_points(n: int, radius: float, z: float, phase: float = 0.0) -> np.ndarray:
    angles = np.linspace(0.0, 2.0 * math.pi, n, endpoint=False) + phase
    return np.column_stack([radius * np.cos(angles), radius * np.sin(angles), np.full(n, z)])


def generate_scenario(
    name: str,
    trial_id: int,
    rng: np.random.Generator,
    min_distance: float = 2.1,
) -> tuple[np.ndarray, np.ndarray]:
    if name == "small":
        initial = feasible_random_points(rng, 3, xy_span=4.0, z=3.0, min_distance=min_distance)
        targets = circle_points(3, radius=3.0, z=3.0, phase=0.2 * trial_id)
    elif name == "medium":
        initial = feasible_random_points(rng, 5, xy_span=6.0, z=4.0, min_distance=min_distance)
        targets = circle_points(5, radius=4.0, z=4.0, phase=0.1 * trial_id)
    elif name == "large":
        initial = feasible_random_points(rng, 8, xy_span=8.0, z=4.0, min_distance=min_distance)
        targets = circle_points(8, radius=5.0, z=4.0, phase=0.07 * trial_id)
    elif name == "dense":
        initial = feasible_random_points(rng, 8, xy_span=4.0, z=3.0, min_distance=min_distance)
        targets = circle_points(8, radius=3.2, z=3.0, phase=0.05 * trial_id)
    elif name == "crossing-prone":
        # Equal-altitude Euclidean bipartite matching naturally uncrosses straight
        # segments. Coupling reversed Y order to matching altitude levels creates a
        # 3-D distance optimum whose XY projection is crossing-prone. The wider
        # Y/Z spacing keeps both endpoint sets feasible before trajectories start.
        n = 5
        y = np.linspace(-3.2, 3.2, n)
        z = np.linspace(2.0, 8.4, n)
        base_initial = np.column_stack([np.full(n, -5.0), y, z])
        base_targets = np.column_stack([np.full(n, 5.0), y[::-1], z])
        for _ in range(10000):
            initial = base_initial + rng.normal(0.0, 0.04, size=base_initial.shape)
            targets = base_targets + rng.normal(0.0, 0.04, size=base_targets.shape)
            if (
                minimum_pair_distance(initial) >= min_distance
                and minimum_pair_distance(targets) >= min_distance
            ):
                break
        else:
            raise RuntimeError("Could not generate a feasible crossing-prone scenario")
    else:
        raise ValueError(f"Unknown scenario: {name}")
    if minimum_pair_distance(initial) < min_distance:
        raise AssertionError(f"{name} initial points violate the scenario distance constraint")
    if minimum_pair_distance(targets) < min_distance:
        raise AssertionError(f"{name} target points violate the scenario distance constraint")
    return initial, targets


def random_assignment(n: int, rng: np.random.Generator) -> List[int]:
    return rng.permutation(n).astype(int).tolist()


def nearest_neighbor_assignment(initial: np.ndarray, targets: np.ndarray) -> List[int]:
    remaining = set(range(len(targets)))
    assignment: List[int] = []
    for point in initial:
        best = min(remaining, key=lambda idx: (float(np.linalg.norm(point - targets[idx])), idx))
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
        best = min(remaining, key=lambda idx: (float(np.linalg.norm(point - targets[idx])), idx))
        assignment.append(int(best))
        remaining.remove(best)
    return assignment


def make_allocator(
    sample_hz: float,
    safety_distance: float,
    *,
    crossing_only: bool = False,
) -> SafetyAwareTopologyAllocator:
    if crossing_only:
        return SafetyAwareTopologyAllocator(
            sample_hz=sample_hz,
            d_safe=safety_distance,
            beta_xy=10.0,
            beta_prox=0.0,
            gamma=0.0,
        )
    return SafetyAwareTopologyAllocator(sample_hz=sample_hz, d_safe=safety_distance)


def compute_assignment(
    method: str,
    initial: np.ndarray,
    targets: np.ndarray,
    duration: float,
    rng: np.random.Generator,
    allocator_factory: Callable[..., SafetyAwareTopologyAllocator],
) -> tuple[List[int], float]:
    crossing_allocator = allocator_factory(crossing_only=True) if method == "hungarian_crossing_penalty" else None
    safety_allocator = allocator_factory() if method == "safety_aware_local_swap" else None

    started = time.perf_counter()
    if method == "random":
        assignment = random_assignment(len(initial), rng)
    elif method == "nearest_neighbor":
        assignment = nearest_neighbor_assignment(initial, targets)
    elif method == "hungarian_distance":
        assignment = hungarian_assignment(initial, targets)
    elif method == "hungarian_crossing_penalty":
        allocated = crossing_allocator.allocate(initial, targets, duration=duration)
        assignment = assignment_from_allocated(allocated, targets)
    elif method == "safety_aware_local_swap":
        allocated = safety_allocator.allocate(initial, targets, duration=duration)
        assignment = assignment_from_allocated(allocated, targets)
    else:
        raise ValueError(f"Unknown method: {method}")
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return assignment, elapsed_ms


def evaluate_assignment(
    evaluator: SafetyAwareTopologyAllocator,
    initial: np.ndarray,
    targets: np.ndarray,
    assignment: Sequence[int],
    duration: float,
    safety_distance: float,
    critical_distance: float,
    nominal_speed: float,
) -> ExtendedMetrics:
    base = evaluator.evaluate(initial, targets, assignment, duration)
    assigned_targets = targets[np.asarray(assignment, dtype=int)]
    trajectories = evaluator.sample_nominal_trajectories(initial, assigned_targets, duration)

    violation_count = 0
    critical_violation_count = 0
    for i, j in itertools.combinations(range(len(initial)), 2):
        distances = np.linalg.norm(trajectories[i] - trajectories[j], axis=1)
        violation_count += int(np.count_nonzero(distances < safety_distance))
        critical_violation_count += int(np.count_nonzero(distances < critical_distance))

    path_lengths = np.linalg.norm(assigned_targets - initial, axis=1)
    arrival_times = path_lengths / nominal_speed
    arrival_variance = float(np.var(arrival_times, ddof=0))
    return ExtendedMetrics(
        assignment_metrics=base,
        safety_violation_count=violation_count,
        critical_violation_count=critical_violation_count,
        arrival_time_variance=arrival_variance,
        failed_assignment=int(violation_count > 0),
        critical_failed_assignment=int(critical_violation_count > 0),
    )


def format_float(value: float) -> str:
    if math.isinf(value):
        return "inf"
    return f"{value:.6f}"


def write_csv(rows: Iterable[Dict[str, object]], output_path: Path) -> None:
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def validate_args(args: argparse.Namespace) -> None:
    positive = {
        "--trials": args.trials,
        "--duration": args.duration,
        "--sample-hz": args.sample_hz,
        "--safety-distance": args.safety_distance,
        "--critical-distance": args.critical_distance,
        "--scenario-min-distance": args.scenario_min_distance,
        "--nominal-speed": args.nominal_speed,
    }
    for name, value in positive.items():
        if value <= 0:
            raise ValueError(f"{name} must be positive")
    if args.critical_distance >= args.safety_distance:
        raise ValueError("--critical-distance must be lower than --safety-distance")
    if args.scenario_min_distance < args.safety_distance:
        raise ValueError("--scenario-min-distance must be at least --safety-distance")


def run_experiment(args: argparse.Namespace) -> Path:
    validate_args(args)
    output_dir = resolve_output_dir(Path(args.output_dir))
    output_dir.mkdir(parents=True, exist_ok=True)

    config = {
        "experiment": "experiments_04",
        "created_at_utc": utc_timestamp(),
        "seed": args.seed,
        "trials_per_scenario": args.trials,
        "scenarios": list(args.scenarios),
        "methods": METHODS,
        "duration_seconds": args.duration,
        "sample_hz": args.sample_hz,
        "safety_distance_m": args.safety_distance,
        "critical_distance_m": args.critical_distance,
        "scenario_min_distance_m": args.scenario_min_distance,
        "nominal_speed_mps": args.nominal_speed,
        "cost_weights": {
            "distance": 1.0,
            "xy_crossing": 10.0,
            "proximity_crossing": 10.0,
            "safety": 1.0,
        },
        "crossing_prone_geometry": {
            "x_m": [-5.0, 5.0],
            "num_uav": 5,
            "y_span_m": [-3.2, 3.2],
            "z_span_m": [2.0, 8.4],
            "noise_std_m": 0.04,
        },
        "dense_geometry": {
            "num_uav": 8,
            "target_shape": "circle",
            "target_radius_m": 3.2,
            "initial_xy_span_m": 4.0,
        },
        "scenario_feasibility_definition": (
            "minimum pairwise distance in both endpoint sets >= scenario_min_distance_m"
        ),
        "safety_violation_definition": "pair-time samples with distance < safety_distance_m",
        "failed_assignment_definition": "safety_violation_count > 0",
        "critical_violation_definition": "pair-time samples with distance < critical_distance_m",
        "critical_failed_assignment_definition": "critical_violation_count > 0",
        "arrival_time_variance_definition": "population variance of path_length / nominal_speed_mps",
    }
    (output_dir / "run_config.json").write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    master_rng = np.random.default_rng(args.seed)

    def allocator_factory(**kwargs: object) -> SafetyAwareTopologyAllocator:
        return make_allocator(
            args.sample_hz,
            args.safety_distance,
            crossing_only=bool(kwargs.get("crossing_only", False)),
        )

    result_rows: List[Dict[str, object]] = []
    scenario_path = output_dir / "scenario_points.jsonl"
    with scenario_path.open("w", encoding="utf-8") as scenario_handle:
        for scenario in args.scenarios:
            for trial_id in range(args.trials):
                scenario_seed = int(master_rng.integers(0, 2**31 - 1))
                scenario_rng = np.random.default_rng(scenario_seed)
                initial, targets = generate_scenario(
                    scenario,
                    trial_id,
                    scenario_rng,
                    min_distance=args.scenario_min_distance,
                )
                scenario_handle.write(json.dumps({
                    "trial_id": trial_id,
                    "scenario": scenario,
                    "scenario_seed": scenario_seed,
                    "initial": initial.tolist(),
                    "targets": targets.tolist(),
                }, separators=(",", ":")) + "\n")

                evaluator = allocator_factory()
                for method_index, method in enumerate(METHODS):
                    method_rng = np.random.default_rng(scenario_seed + method_index)
                    assignment, compute_time_ms = compute_assignment(
                        method,
                        initial,
                        targets,
                        args.duration,
                        method_rng,
                        allocator_factory,
                    )
                    metrics = evaluate_assignment(
                        evaluator,
                        initial,
                        targets,
                        assignment,
                        args.duration,
                        args.safety_distance,
                        args.critical_distance,
                        args.nominal_speed,
                    )
                    base = metrics.assignment_metrics
                    result_rows.append({
                        "trial_id": trial_id,
                        "scenario": scenario,
                        "scenario_seed": scenario_seed,
                        "num_uav": len(initial),
                        "method": method,
                        "assignment": json.dumps(assignment, separators=(",", ":")),
                        "total_path_length": format_float(base.distance),
                        "avg_path_length": format_float(base.distance / len(initial)),
                        "xy_crossings": base.xy_crossings,
                        "proximity_crossings": base.proximity_crossings,
                        "min_distance": format_float(base.min_distance),
                        "safety_cost": format_float(base.safety),
                        "safety_violation_count": metrics.safety_violation_count,
                        "critical_violation_count": metrics.critical_violation_count,
                        "arrival_time_variance": format_float(metrics.arrival_time_variance),
                        "failed_assignment": metrics.failed_assignment,
                        "critical_failed_assignment": metrics.critical_failed_assignment,
                        "total_cost": format_float(base.total),
                        "compute_time_ms": format_float(compute_time_ms),
                    })

    write_csv(result_rows, output_dir / "assignment_trials.csv")
    print(f"Wrote {len(result_rows)} assignment rows to {output_dir}")
    return output_dir


def main() -> int:
    run_experiment(parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
