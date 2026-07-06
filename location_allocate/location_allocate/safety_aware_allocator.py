import itertools
from dataclasses import dataclass
from typing import Dict, List, Sequence

import numpy as np
from scipy.optimize import linear_sum_assignment


@dataclass(frozen=True)
class AssignmentMetrics:
    """Cost breakdown for one assignment candidate."""

    total: float
    distance: float
    xy_crossings: int
    proximity_crossings: int
    safety: float
    min_distance: float


class SafetyAwareTopologyAllocator:
    """Hungarian assignment refined by nominal trajectory safety metrics."""

    def __init__(
        self,
        sample_hz: float = 20.0,
        d_safe: float = 2.0,
        alpha: float = 1.0,
        beta: float = 10.0,
        gamma: float = 1.0,
        epsilon: float = 1e-3,
        min_improvement: float = 1e-6,
    ):
        if sample_hz <= 0.0:
            raise ValueError("sample_hz must be positive")
        if d_safe <= 0.0:
            raise ValueError("d_safe must be positive")
        if epsilon <= 0.0:
            raise ValueError("epsilon must be positive")

        self.sample_hz = float(sample_hz)
        self.d_safe = float(d_safe)
        self.alpha = float(alpha)
        self.beta = float(beta)
        self.gamma = float(gamma)
        self.epsilon = float(epsilon)
        self.min_improvement = float(min_improvement)
        self.last_metrics: AssignmentMetrics | None = None
        self.last_iterations = 0

    @staticmethod
    def _minimum_jerk_progress(samples: int) -> np.ndarray:
        tau = np.linspace(0.0, 1.0, samples)
        return 10.0 * tau**3 - 15.0 * tau**4 + 6.0 * tau**5

    def sample_nominal_trajectories(
        self,
        initial: Sequence[Sequence[float]],
        assigned_targets: Sequence[Sequence[float]],
        duration: float,
    ) -> np.ndarray:
        """Return nominal Minimum Jerk samples shaped as (uav, sample, xyz)."""
        if duration <= 0.0:
            raise ValueError("duration must be positive")

        init_np = np.asarray(initial, dtype=float)
        target_np = np.asarray(assigned_targets, dtype=float)
        if init_np.shape != target_np.shape:
            raise ValueError("initial and assigned_targets must have the same shape")
        if init_np.ndim != 2 or init_np.shape[1] != 3:
            raise ValueError("positions must be shaped as N x 3")

        sample_count = max(2, int(np.ceil(duration * self.sample_hz)) + 1)
        progress = self._minimum_jerk_progress(sample_count)
        delta = target_np - init_np
        return init_np[:, None, :] + progress[None, :, None] * delta[:, None, :]

    @staticmethod
    def _orientation(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    @classmethod
    def _xy_segments_cross(
        cls,
        p1: np.ndarray,
        p2: np.ndarray,
        p3: np.ndarray,
        p4: np.ndarray,
    ) -> bool:
        if np.allclose(p1[:2], p3[:2]) or np.allclose(p1[:2], p4[:2]):
            return False
        if np.allclose(p2[:2], p3[:2]) or np.allclose(p2[:2], p4[:2]):
            return False

        a = p1[:2]
        b = p2[:2]
        c = p3[:2]
        d = p4[:2]
        if max(a[0], b[0]) < min(c[0], d[0]) or max(c[0], d[0]) < min(a[0], b[0]):
            return False
        if max(a[1], b[1]) < min(c[1], d[1]) or max(c[1], d[1]) < min(a[1], b[1]):
            return False

        o1 = cls._orientation(a, b, c)
        o2 = cls._orientation(a, b, d)
        o3 = cls._orientation(c, d, a)
        o4 = cls._orientation(c, d, b)
        return (o1 * o2 < 0.0) and (o3 * o4 < 0.0)

    def evaluate(
        self,
        initial: Sequence[Sequence[float]],
        targets: Sequence[Sequence[float]],
        assignment: Sequence[int],
        duration: float,
    ) -> AssignmentMetrics:
        init_np = np.asarray(initial, dtype=float)
        target_np = np.asarray(targets, dtype=float)
        assignment_np = np.asarray(assignment, dtype=int)
        assigned_targets = target_np[assignment_np]

        distance_cost = float(np.linalg.norm(assigned_targets - init_np, axis=1).sum())
        trajectories = self.sample_nominal_trajectories(init_np, assigned_targets, duration)

        xy_crossings = 0
        proximity_crossings = 0
        safety_cost = 0.0
        min_distance = float("inf")

        for i, j in itertools.combinations(range(len(init_np)), 2):
            if self._xy_segments_cross(init_np[i], assigned_targets[i], init_np[j], assigned_targets[j]):
                xy_crossings += 1

            distances = np.linalg.norm(trajectories[i] - trajectories[j], axis=1)
            pair_min = float(distances.min())
            min_distance = min(min_distance, pair_min)
            if pair_min < self.d_safe:
                proximity_crossings += 1
                safety_cost += 1.0 / (pair_min + self.epsilon)

        if len(init_np) < 2:
            min_distance = float("inf")

        crossing_cost = proximity_crossings
        total = (
            self.alpha * distance_cost
            + self.beta * crossing_cost
            + self.gamma * safety_cost
        )
        return AssignmentMetrics(
            total=float(total),
            distance=distance_cost,
            xy_crossings=xy_crossings,
            proximity_crossings=proximity_crossings,
            safety=float(safety_cost),
            min_distance=min_distance,
        )

    @staticmethod
    def _hungarian_assignment(
        initial: Sequence[Sequence[float]],
        targets: Sequence[Sequence[float]],
    ) -> List[int]:
        init_np = np.asarray(initial, dtype=float)
        target_np = np.asarray(targets, dtype=float)
        cost = np.linalg.norm(init_np[:, None, :] - target_np[None, :, :], axis=2)
        row_ind, col_ind = linear_sum_assignment(cost)
        assignment = [0] * len(init_np)
        for row, col in zip(row_ind, col_ind):
            assignment[int(row)] = int(col)
        return assignment

    @staticmethod
    def _swap(assignment: Sequence[int], i: int, j: int) -> List[int]:
        swapped = list(assignment)
        swapped[i], swapped[j] = swapped[j], swapped[i]
        return swapped

    def allocate_with_metrics(
        self,
        initial: Sequence[Sequence[float]],
        targets: Sequence[Sequence[float]],
        duration: float = 3.0,
    ) -> tuple[List[List[float]], AssignmentMetrics]:
        if len(initial) != len(targets):
            raise ValueError("initial and targets must contain the same number of positions")

        n = len(initial)
        if n == 0:
            metrics = AssignmentMetrics(0.0, 0.0, 0, 0, 0.0, float("inf"))
            self.last_metrics = metrics
            self.last_iterations = 0
            return [], metrics

        target_np = np.asarray(targets, dtype=float)
        assignment = self._hungarian_assignment(initial, targets)
        best_metrics = self.evaluate(initial, targets, assignment, duration)

        improved = True
        iterations = 0
        while improved:
            improved = False
            iterations += 1
            for i, j in itertools.combinations(range(n), 2):
                candidate = self._swap(assignment, i, j)
                candidate_metrics = self.evaluate(initial, targets, candidate, duration)
                if candidate_metrics.total < best_metrics.total - self.min_improvement:
                    assignment = candidate
                    best_metrics = candidate_metrics
                    improved = True

        allocated = target_np[np.asarray(assignment, dtype=int)].tolist()
        self.last_metrics = best_metrics
        self.last_iterations = max(0, iterations - 1)
        return allocated, best_metrics

    def allocate(
        self,
        initial: Sequence[Sequence[float]],
        targets: Sequence[Sequence[float]],
        duration: float = 3.0,
    ) -> List[List[float]]:
        allocated, _ = self.allocate_with_metrics(initial, targets, duration)
        return allocated

    def metrics_dict(self) -> Dict[str, float | int | None]:
        if self.last_metrics is None:
            return {
                "total": None,
                "distance": None,
                "xy_crossings": None,
                "proximity_crossings": None,
                "safety": None,
                "min_distance": None,
                "iterations": self.last_iterations,
            }

        return {
            "total": self.last_metrics.total,
            "distance": self.last_metrics.distance,
            "xy_crossings": self.last_metrics.xy_crossings,
            "proximity_crossings": self.last_metrics.proximity_crossings,
            "safety": self.last_metrics.safety,
            "min_distance": self.last_metrics.min_distance,
            "iterations": self.last_iterations,
        }
