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
    ResolvedTaskIntent,
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


@dataclass(frozen=True)
class ResolvedParallelGroup:
    """Parallel tasks resolved from one snapshot and one joint allocation."""

    tasks: Tuple[ResolvedExecutionTask, ...]
    completion_mode: str
    planning_metrics: AssignmentMetrics
    final_metrics: AssignmentMetrics


@dataclass(frozen=True)
class _PreparedTask:
    intent: ResolvedTaskIntent
    trace: ResolutionTrace
    safety: SafetyResolution
    radius: float
    initial: Tuple[Vector3, ...]
    targets: Tuple[Vector3, ...]
    t_plan: float


def _prepare_task(
    candidate_task: dict,
    snapshot: StateSnapshot,
    policy: LateResolutionPolicy,
    minimum_d_plan: float | None = None,
) -> _PreparedTask:
    """Resolve through T_plan, stopping before any assignment is chosen."""
    runtime_validate_candidate_task(candidate_task, snapshot)
    intent, trace = resolve_candidate_task(candidate_task, snapshot)
    safety = policy.resolve_safety(intent.safety_factor)
    if minimum_d_plan is not None and minimum_d_plan > safety.d_plan:
        safety = SafetyResolution(
            d_hard=safety.d_hard,
            d_plan=float(minimum_d_plan),
            soft_iapf=safety.soft_iapf,
        )
        trace.corrections.append(
            "d_plan raised to ParallelGroup maximum safety margin"
        )
    if safety.d_hard <= 0.0 or safety.d_plan < safety.d_hard:
        raise LateResolutionError("resolved safety violates d_plan >= d_hard")
    trace.d_hard = safety.d_hard
    trace.d_plan = safety.d_plan

    unit = build_unit_geometry(intent.formation, len(intent.uav_ids))
    radius = resolve_scale(intent, unit, safety.d_plan, policy.scale, trace)
    targets = build_final_geometry(
        intent.center,
        unit,
        radius,
        policy.scale.workspace_bounds,
        safety.d_plan,
    )
    initial = tuple(snapshot.positions(intent.uav_ids))
    t_plan = estimate_planning_duration(
        intent,
        initial,
        targets,
        policy.timing,
        policy.planning_distance_bound,
        trace,
    )
    return _PreparedTask(
        intent=intent,
        trace=trace,
        safety=safety,
        radius=radius,
        initial=initial,
        targets=targets,
        t_plan=t_plan,
    )


def resolve_execution_task(
    candidate_task: dict,
    snapshot: StateSnapshot,
    policy: LateResolutionPolicy,
) -> ResolvedExecutionTask:
    """Resolve one task exactly once through each independent stage."""
    prepared = _prepare_task(candidate_task, snapshot, policy)
    intent = prepared.intent
    trace = prepared.trace
    safety = prepared.safety
    initial = prepared.initial
    targets = prepared.targets
    t_plan = prepared.t_plan

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
    if final_metrics.min_distance + 1e-9 < safety.d_plan:
        trace.rejection_reason = "final assignment violates d_plan(s)"
        raise LateResolutionError(trace.rejection_reason)

    executable = build_executable_lfs(intent, prepared.radius, t_exec)
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


def resolve_execution_parallel(
    candidate_tasks: Sequence[dict],
    snapshot: StateSnapshot,
    policy: LateResolutionPolicy,
    completion_mode: str,
    group_d_plan: float,
) -> ResolvedParallelGroup:
    """
    Resolve one parallel group with a shared snapshot and joint safety horizon.

    ``group_d_plan`` is deliberately supplied by the caller: aggregation of
    task-specific planning margins is not frozen by this implementation.
    """
    if completion_mode not in ("independent", "synchronized"):
        raise LateResolutionError("invalid parallel completion_mode")
    if not candidate_tasks:
        raise LateResolutionError("parallel group must not be empty")
    requested_d_plan = tuple(
        policy.resolve_safety(float(task["s"])).d_plan
        for task in candidate_tasks
    )
    if group_d_plan < max(requested_d_plan):
        raise LateResolutionError(
            "group_d_plan must cover every task planning margin"
        )
    prepared = tuple(
        _prepare_task(task, snapshot, policy, group_d_plan)
        for task in candidate_tasks
    )
    hard_values = {item.safety.d_hard for item in prepared}
    if len(hard_values) != 1:
        raise LateResolutionError("d_hard must be constant across a mission")

    groups = [
        {
            "uav_ids": list(item.intent.uav_ids),
            "initial": list(item.initial),
            "targets": list(item.targets),
        }
        for item in prepared
    ]
    allocator = policy.allocator_factory(group_d_plan)
    assigned_groups, planning_metrics = allocator.allocate_grouped(
        groups, durations=[item.t_plan for item in prepared]
    )
    t_exec_values = [
        resolve_final_duration(
            item.intent,
            item.initial,
            assigned,
            policy.timing,
            item.trace,
        )
        for item, assigned in zip(prepared, assigned_groups)
    ]
    if completion_mode == "synchronized":
        synchronized = max(t_exec_values)
        for item, original in zip(prepared, t_exec_values):
            item.trace.t_exec = synchronized
            if synchronized > original:
                item.trace.corrections.append(
                    "duration synchronized by explicit parallel relation"
                )
        t_exec_values = [synchronized] * len(prepared)

    final_metrics = planning_metrics
    needs_recheck = any(
        timing_requires_recheck(
            item.t_plan, t_exec, policy.timing_recheck_tolerance
        )
        for item, t_exec in zip(prepared, t_exec_values)
    )
    if needs_recheck:
        flat_initial = [point for item in prepared for point in item.initial]
        flat_assigned = [point for group in assigned_groups for point in group]
        uav_durations = [
            duration
            for item, duration in zip(prepared, t_exec_values)
            for _ in item.intent.uav_ids
        ]
        final_metrics = allocator.evaluate_variable(
            flat_initial,
            flat_assigned,
            list(range(len(flat_assigned))),
            uav_durations,
        )
        for item in prepared:
            item.trace.corrections.append(
                "parallel assignment safety re-evaluated once"
            )
    if final_metrics.min_distance + 1e-9 < group_d_plan:
        for item in prepared:
            item.trace.rejection_reason = (
                "parallel assignment violates explicit group_d_plan"
            )
        raise LateResolutionError(
            "parallel assignment violates explicit group_d_plan"
        )

    resolved_tasks = []
    for item, assigned, t_exec in zip(
        prepared, assigned_groups, t_exec_values
    ):
        executable = build_executable_lfs(
            item.intent, item.radius, t_exec
        )
        profiles = compile_execution_profiles(
            executable,
            item.initial,
            assigned,
            policy.profile,
            item.safety.soft_iapf,
        )
        resolved_tasks.append(
            ResolvedExecutionTask(
                executable_lfs=executable,
                assigned_targets=tuple(
                    tuple(value for value in target) for target in assigned
                ),
                profiles=profiles,
                planning_metrics=planning_metrics,
                final_metrics=final_metrics,
                trace=item.trace,
            )
        )
    return ResolvedParallelGroup(
        tasks=tuple(resolved_tasks),
        completion_mode=completion_mode,
        planning_metrics=planning_metrics,
        final_metrics=final_metrics,
    )
