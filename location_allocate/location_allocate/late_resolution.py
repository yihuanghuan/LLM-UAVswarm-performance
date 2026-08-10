"""Composition root for one late-bound Candidate LFS task."""

from dataclasses import dataclass
from typing import Callable, Sequence, Tuple

from .execution_profile_compiler import (
    ExecutionProfilePolicy,
    SoftSafetyParameters,
    compile_execution_profiles,
)
from .formation_geometry import (
    ScalePolicy,
    build_final_geometry,
    build_unit_geometry,
    resolve_scale,
)
from .lfs_resolver import resolve_candidate_task
from .lfs_validator import runtime_validate_candidate_task
from .lfs_types import (
    ExecutableLFS,
    ExecutionProfile,
    ResolutionTrace,
    StateSnapshot,
    Vector3,
)
from .safety_aware_allocator import AssignmentMetrics, SafetyAwareTopologyAllocator
from .timing_resolution import (
    TimingPolicy,
    build_executable_lfs,
    estimate_planning_duration,
    resolve_final_duration,
    timing_requires_recheck,
)


class LateResolutionError(RuntimeError):
    """Raised when a task fails a deterministic late-resolution gate."""


@dataclass(frozen=True)
class SafetyResolution:
    """Hard and soft safety values resolved outside the LFS tuple."""

    d_hard: float
    d_plan: float
    soft_iapf: SoftSafetyParameters


@dataclass(frozen=True)
class LateResolutionPolicy:
    """All provisional choices are explicit dependencies."""

    scale: ScalePolicy
    timing: TimingPolicy
    profile: ExecutionProfilePolicy
    resolve_safety: Callable[[float], SafetyResolution]
    planning_distance_bound: Callable[
        [Sequence[Sequence[float]], Sequence[Sequence[float]]], float
    ]
    timing_recheck_tolerance: float
    allocator_factory: Callable[[float], SafetyAwareTopologyAllocator]


@dataclass(frozen=True)
class ResolvedExecutionTask:
    executable_lfs: ExecutableLFS
    assigned_targets: Tuple[Vector3, ...]
    profiles: Tuple[ExecutionProfile, ...]
    planning_metrics: AssignmentMetrics
    final_metrics: AssignmentMetrics
    trace: ResolutionTrace


def resolve_execution_task(
    candidate_task: dict,
    snapshot: StateSnapshot,
    policy: LateResolutionPolicy,
) -> ResolvedExecutionTask:
    """Resolve one task exactly once through each independent stage."""
    runtime_validate_candidate_task(candidate_task, snapshot)
    intent, trace = resolve_candidate_task(candidate_task, snapshot)
    safety = policy.resolve_safety(intent.safety_factor)
    if safety.d_hard <= 0.0 or safety.d_plan < safety.d_hard:
        raise LateResolutionError("resolved safety violates d_plan >= d_hard")
    trace.d_hard = safety.d_hard
    trace.d_plan = safety.d_plan

    unit = build_unit_geometry(intent.formation, len(intent.uav_ids))
    radius = resolve_scale(
        intent, unit, safety.d_plan, policy.scale, trace
    )
    targets = build_final_geometry(
        intent.center,
        unit,
        radius,
        policy.scale.workspace_bounds,
        safety.d_plan,
    )
    initial = snapshot.positions(intent.uav_ids)
    t_plan = estimate_planning_duration(
        intent,
        initial,
        targets,
        policy.timing,
        policy.planning_distance_bound,
        trace,
    )

    allocator = policy.allocator_factory(safety.d_plan)
    assigned, planning_metrics = allocator.allocate_with_metrics(
        initial, targets, duration=t_plan
    )
    t_exec = resolve_final_duration(
        intent, initial, assigned, policy.timing, trace
    )
    final_metrics = planning_metrics
    if timing_requires_recheck(
        t_plan, t_exec, policy.timing_recheck_tolerance
    ):
        final_metrics = allocator.evaluate(
            initial,
            assigned,
            list(range(len(assigned))),
            duration=t_exec,
        )
        trace.corrections.append("final assignment safety re-evaluated once")
    if final_metrics.min_distance < safety.d_plan:
        trace.rejection_reason = "final assignment violates d_plan(s)"
        raise LateResolutionError(trace.rejection_reason)

    executable = build_executable_lfs(intent, radius, t_exec)
    profiles = compile_execution_profiles(
        executable, initial, assigned, policy.profile, safety.soft_iapf
    )
    return ResolvedExecutionTask(
        executable_lfs=executable,
        assigned_targets=tuple(tuple(value for value in target) for target in assigned),
        profiles=profiles,
        planning_metrics=planning_metrics,
        final_metrics=final_metrics,
        trace=trace,
    )
