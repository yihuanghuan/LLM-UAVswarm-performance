"""Historical weighted-sum assignment retained for explicit legacy use only."""

import itertools
from dataclasses import dataclass

import numpy as np

from ..safety_aware_allocator import SafetyAwareTopologyAllocator


@dataclass(frozen=True)
class LegacyAssignmentMetrics:
    total: float
    distance: float
    xy_crossings: int
    proximity_crossings: int
    safety: float
    min_distance: float


class LegacyWeightedSumAllocator(SafetyAwareTopologyAllocator):
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
        super().__init__(d_safe, d_safe, sample_hz, min_improvement)
        self.d_safe = float(d_safe)
        self.alpha = float(alpha)
        self.beta = float(beta)
        self.beta_xy = self.beta if beta_xy is None else float(beta_xy)
        self.beta_prox = self.beta if beta_prox is None else float(beta_prox)
        self.gamma = float(gamma)
        self.epsilon = float(epsilon)
        self.min_improvement = float(min_improvement)

    def sample_nominal_trajectories(self, initial, assigned_targets, duration):
        initial_np, target_np = self._positions(initial, assigned_targets)
        if not np.isfinite(duration) or duration <= 0.0:
            raise ValueError("duration must be finite and positive")
        count = max(2, int(np.ceil(duration * self.sample_hz)) + 1)
        progress = self._minimum_jerk_progress(np.linspace(0.0, 1.0, count))
        return initial_np[:, None, :] + progress[None, :, None] * (
            target_np - initial_np
        )[:, None, :]

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
            pair_min = float(np.linalg.norm(
                trajectories[i] - trajectories[j], axis=1
            ).min())
            min_distance = min(min_distance, pair_min)
            if pair_min < self.d_safe:
                proximity += 1
                safety += 1.0 / (pair_min + self.epsilon)
        total = (
            self.alpha * distance + self.beta_xy * crossings
            + self.beta_prox * proximity + self.gamma * safety
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
