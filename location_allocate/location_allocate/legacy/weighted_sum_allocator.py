"""Historical weighted-sum assignment retained for explicit legacy use only."""

import itertools
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
from scipy.optimize import linear_sum_assignment


@dataclass(frozen=True)
class LegacyAssignmentMetrics:
    total: float
    distance: float
    xy_crossings: int
    proximity_crossings: int
    safety: float
    min_distance: float


class LegacyWeightedSumAllocator:
    """Frozen v1 distance/crossing/proximity/inverse-distance objective."""

    def __init__(
        self,
        sample_hz=20.0,
        d_safe=2.0,
        alpha=1.0,
        beta=10.0,
        beta_xy=None,
        beta_prox=None,
        gamma=1.0,
        epsilon=1e-3,
        min_improvement=1e-6,
    ):
        values = (d_safe, d_safe, sample_hz, min_improvement)
        if not all(math.isfinite(value) and value > 0.0 for value in values):
            raise ValueError(
                "allocator thresholds and sampling values must be finite "
                "and positive"
            )
        self.sample_hz = float(sample_hz)
        self.d_safe = float(d_safe)
        self.alpha = float(alpha)
        self.beta = float(beta)
        self.beta_xy = self.beta if beta_xy is None else float(beta_xy)
        self.beta_prox = self.beta if beta_prox is None else float(beta_prox)
        self.gamma = float(gamma)
        self.epsilon = float(epsilon)
        self.min_improvement = float(min_improvement)
        self.last_metrics: Optional[LegacyAssignmentMetrics] = None
        self.last_iterations = 0
        self.last_initial_assignment: List[int] = []
        self.last_assignment: List[int] = []

    @staticmethod
    def _positions(
        initial: Sequence[Sequence[float]],
        targets: Sequence[Sequence[float]],
    ) -> tuple[np.ndarray, np.ndarray]:
        initial_np = np.asarray(initial, dtype=float)
        targets_np = np.asarray(targets, dtype=float)
        if initial_np.shape != targets_np.shape:
            raise ValueError("initial and targets must have the same shape")
        if initial_np.ndim != 2 or initial_np.shape[1] != 3:
            raise ValueError("positions must be shaped as N x 3")
        if (
            not np.all(np.isfinite(initial_np))
            or not np.all(np.isfinite(targets_np))
        ):
            raise ValueError("positions must be finite")
        return initial_np, targets_np

    @staticmethod
    def _minimum_jerk_progress(normalized_time: np.ndarray) -> np.ndarray:
        return (
            10.0 * normalized_time**3
            - 15.0 * normalized_time**4
            + 6.0 * normalized_time**5
        )

    def sample_nominal_trajectories(self, initial, assigned_targets, duration):
        initial_np, target_np = self._positions(initial, assigned_targets)
        if not np.isfinite(duration) or duration <= 0.0:
            raise ValueError("duration must be finite and positive")
        count = max(2, int(np.ceil(duration * self.sample_hz)) + 1)
        progress = self._minimum_jerk_progress(
            np.linspace(0.0, 1.0, count)
        )
        return initial_np[:, None, :] + progress[None, :, None] * (
            target_np - initial_np
        )[:, None, :]

    def sample_nominal_trajectories_variable(
        self,
        initial: Sequence[Sequence[float]],
        assigned_targets: Sequence[Sequence[float]],
        durations: Sequence[float],
    ) -> np.ndarray:
        initial_np, targets_np = self._positions(initial, assigned_targets)
        duration_np = np.asarray(durations, dtype=float)
        if duration_np.shape != (len(initial_np),):
            raise ValueError("durations must contain one value per UAV")
        if not np.all(np.isfinite(duration_np)) or np.any(duration_np <= 0.0):
            raise ValueError("durations must be finite and positive")
        horizon = float(duration_np.max())
        sample_count = max(2, int(np.ceil(horizon * self.sample_hz)) + 1)
        times = np.linspace(0.0, horizon, sample_count)
        normalized = np.minimum(times[None, :] / duration_np[:, None], 1.0)
        progress = self._minimum_jerk_progress(normalized)
        return initial_np[:, None, :] + progress[:, :, None] * (
            targets_np - initial_np
        )[:, None, :]

    @staticmethod
    def _orientation(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
        return (
            (b[0] - a[0]) * (c[1] - a[1])
            - (b[1] - a[1]) * (c[0] - a[0])
        )

    @classmethod
    def _xy_segments_cross(cls, p1, p2, p3, p4) -> bool:
        if any(
            np.allclose(left[:2], right[:2])
            for left, right in (
                (p1, p3),
                (p1, p4),
                (p2, p3),
                (p2, p4),
            )
        ):
            return False
        a, b, c, d = p1[:2], p2[:2], p3[:2], p4[:2]
        if (
            max(a[0], b[0]) < min(c[0], d[0])
            or max(c[0], d[0]) < min(a[0], b[0])
            or max(a[1], b[1]) < min(c[1], d[1])
            or max(c[1], d[1]) < min(a[1], b[1])
        ):
            return False
        return (
            cls._orientation(a, b, c) * cls._orientation(a, b, d) < 0.0
            and cls._orientation(c, d, a) * cls._orientation(c, d, b) < 0.0
        )

    @staticmethod
    def _empty_metrics():
        return LegacyAssignmentMetrics(
            0.0, 0.0, 0, 0, 0.0, float("inf")
        )

    def _legacy_metrics(self, initial_np, assigned, trajectories):
        distance = float(np.linalg.norm(assigned - initial_np, axis=1).sum())
        crossings = proximity = 0
        safety = 0.0
        min_distance = float("inf")
        for i, j in itertools.combinations(range(len(initial_np)), 2):
            crossings += self._xy_segments_cross(
                initial_np[i], assigned[i], initial_np[j], assigned[j]
            )
            pair_min = float(
                np.linalg.norm(trajectories[i] - trajectories[j], axis=1).min()
            )
            min_distance = min(min_distance, pair_min)
            if pair_min < self.d_safe:
                proximity += 1
                safety += 1.0 / (pair_min + self.epsilon)
        total = (
            self.alpha * distance
            + self.beta_xy * crossings
            + self.beta_prox * proximity
            + self.gamma * safety
        )
        return LegacyAssignmentMetrics(
            total, distance, int(crossings), proximity, safety, min_distance
        )

    def evaluate(self, initial, targets, assignment, duration=3.0):
        initial_np, target_np = self._positions(initial, targets)
        assigned = target_np[np.asarray(assignment, dtype=int)]
        return self._legacy_metrics(
            initial_np,
            assigned,
            self.sample_nominal_trajectories(initial_np, assigned, duration),
        )

    def evaluate_variable(self, initial, targets, assignment, durations):
        initial_np, target_np = self._positions(initial, targets)
        assigned = target_np[np.asarray(assignment, dtype=int)]
        return self._legacy_metrics(
            initial_np,
            assigned,
            self.sample_nominal_trajectories_variable(
                initial_np, assigned, durations
            ),
        )

    def lexicographically_better(self, candidate, current):
        return candidate.total < current.total - self.min_improvement

    @staticmethod
    def _hungarian_assignment(initial, targets) -> List[int]:
        initial_np, target_np = LegacyWeightedSumAllocator._positions(
            initial, targets
        )
        cost = np.linalg.norm(
            initial_np[:, None, :] - target_np[None, :, :], axis=2
        )
        rows, columns = linear_sum_assignment(cost)
        assignment = [0] * len(initial_np)
        for row, column in zip(rows, columns):
            assignment[int(row)] = int(column)
        return assignment

    @staticmethod
    def _swap(assignment, i, j) -> List[int]:
        result = list(assignment)
        result[i], result[j] = result[j], result[i]
        return result

    def _refine(self, assignment, evaluator, swappable_ranges):
        initial_assignment = list(assignment)
        best = evaluator(assignment)
        iterations = 0
        while True:
            improved = False
            for group_range in swappable_ranges:
                for i, j in itertools.combinations(group_range, 2):
                    candidate = self._swap(assignment, i, j)
                    metrics = evaluator(candidate)
                    if self.lexicographically_better(metrics, best):
                        assignment, best, improved = candidate, metrics, True
            if not improved:
                break
            iterations += 1
        self.last_initial_assignment = initial_assignment
        self.last_assignment = list(assignment)
        self.last_metrics = best
        self.last_iterations = iterations
        return assignment, best

    def allocate_with_metrics(self, initial, targets, duration=3.0):
        if len(initial) != len(targets):
            raise ValueError(
                "initial and targets must contain the same number of positions"
            )
        if len(initial) == 0:
            empty = self._empty_metrics()
            self.last_initial_assignment = self.last_assignment = []
            self.last_metrics, self.last_iterations = empty, 0
            return [], empty
        assignment = self._hungarian_assignment(initial, targets)
        assignment, metrics = self._refine(
            assignment,
            lambda value: self.evaluate(initial, targets, value, duration),
            [range(len(initial))],
        )
        return np.asarray(targets, dtype=float)[assignment].tolist(), metrics

    def allocate_mode_with_metrics(
        self, initial, targets, duration=3.0, mode="safety_aware"
    ):
        if mode == "safety_aware":
            return self.allocate_with_metrics(initial, targets, duration)
        if len(initial) != len(targets):
            raise ValueError(
                "initial and targets must contain the same number of positions"
            )
        if mode == "fixed":
            assignment = list(range(len(initial)))
        elif mode == "distance_hungarian":
            assignment = self._hungarian_assignment(initial, targets)
        else:
            raise ValueError(
                "assignment_mode must be fixed, distance_hungarian, "
                "or safety_aware"
            )
        metrics = self.evaluate(initial, targets, assignment, duration)
        self.last_initial_assignment = self.last_assignment = list(assignment)
        self.last_metrics, self.last_iterations = metrics, 0
        return np.asarray(targets, dtype=float)[assignment].tolist(), metrics

    def allocate_grouped(
        self,
        groups: Sequence[Dict[str, Any]],
        duration: Optional[float] = None,
        mode: str = "safety_aware",
        durations: Optional[Sequence[float]] = None,
    ):
        if not groups:
            empty = self._empty_metrics()
            self.last_initial_assignment = self.last_assignment = []
            self.last_metrics, self.last_iterations = empty, 0
            return [], empty
        group_durations = (
            [float(duration)] * len(groups)
            if durations is None
            else [float(value) for value in durations]
        )
        if len(group_durations) != len(groups) or any(
            not math.isfinite(value) or value <= 0.0
            for value in group_durations
        ):
            raise ValueError(
                "durations must contain one finite positive value per group"
            )
        initial, targets, uav_durations, ranges = [], [], [], []
        seen, cursor = set(), 0
        for group, group_duration in zip(groups, group_durations):
            ids = [int(value) for value in group.get("uav_ids", [])]
            starts, goals = group.get("initial", []), group.get("targets", [])
            if len(ids) != len(starts) or len(ids) != len(goals):
                raise ValueError(
                    "each group needs equal uav_ids, initial, and targets "
                    "lengths"
                )
            if seen.intersection(ids):
                raise ValueError(
                    "uav_ids must not appear in more than one group"
                )
            seen.update(ids)
            initial.extend(starts)
            targets.extend(goals)
            uav_durations.extend([group_duration] * len(ids))
            ranges.append(range(cursor, cursor + len(ids)))
            cursor += len(ids)
        assignment = list(range(len(initial)))
        if mode != "fixed":
            for group_range in ranges:
                indices = list(group_range)
                local = self._hungarian_assignment(
                    [initial[index] for index in indices],
                    [targets[index] for index in indices],
                )
                for row, target in enumerate(local):
                    assignment[indices[row]] = indices[target]
        if max(uav_durations) - min(uav_durations) <= 1e-12:

            def evaluator(value):
                return self.evaluate(
                    initial, targets, value, uav_durations[0]
                )

        else:

            def evaluator(value):
                return self.evaluate_variable(
                    initial, targets, value, uav_durations
                )

        if mode == "safety_aware":
            assignment, metrics = self._refine(assignment, evaluator, ranges)
        elif mode in ("fixed", "distance_hungarian"):
            metrics = evaluator(assignment)
            self.last_initial_assignment = self.last_assignment = list(
                assignment
            )
            self.last_metrics, self.last_iterations = metrics, 0
        else:
            raise ValueError(
                "assignment_mode must be fixed, distance_hungarian, "
                "or safety_aware"
            )
        flat = np.asarray(targets, dtype=float)[assignment].tolist()
        return [flat[item.start:item.stop] for item in ranges], metrics

    def allocate(self, initial, targets, duration=3.0):
        return self.allocate_with_metrics(initial, targets, duration)[0]

    def metrics_dict(self):
        metrics = self.last_metrics
        return {
            "total": None if metrics is None else metrics.total,
            "distance": None if metrics is None else metrics.distance,
            "xy_crossings": None if metrics is None else metrics.xy_crossings,
            "proximity_crossings": (
                None if metrics is None else metrics.proximity_crossings
            ),
            "safety": None if metrics is None else metrics.safety,
            "min_distance": None if metrics is None else metrics.min_distance,
            "iterations": self.last_iterations,
        }
