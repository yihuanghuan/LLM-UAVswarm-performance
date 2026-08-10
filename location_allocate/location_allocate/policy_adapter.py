"""Construct existing Candidate pipeline policies from one loaded YAML."""

from pathlib import Path

from lfs_policy import LoadedPolicy, load_policy

from .execution_profile_compiler import (
    ExecutionProfilePolicy,
    SoftSafetyParameters,
)
from .formation_geometry import ScalePolicy
from .late_resolution import LateResolutionPolicy, SafetyResolution
from .safety_aware_allocator import SafetyAwareTopologyAllocator
from .timing_resolution import (
    ConfiguredMinimumJerkTimingPolicy,
    max_pairwise_distance_bound,
)


def build_late_resolution_policy(config: LoadedPolicy) -> LateResolutionPolicy:
    geometry = config.geometry
    safety = config.safety
    timing = config.timing
    allocator = config.allocator
    profile = config.execution_profile

    scale_policy = ScalePolicy(
        nominal_spacing=geometry["nominal_spacing"],
        qualitative_multipliers=geometry["qualitative_multipliers"],
        workspace_bounds=(
            geometry["workspace_bounds"]["lower"],
            geometry["workspace_bounds"]["upper"],
        ),
        configuration_id=config.configuration_id,
    )
    timing_policy = ConfiguredMinimumJerkTimingPolicy(
        velocity_limit=timing["velocity_limit"],
        acceleration_limit=timing["acceleration_limit"],
        jerk_limit=timing["jerk_limit"],
        minimum_duration=timing["minimum_duration"],
        auto_style_factors=timing["auto_style_factors"],
        configuration_id=config.configuration_id,
    )
    profile_policy = ExecutionProfilePolicy(
        base_omega_c=profile["baseline_omega_c"],
        base_omega_o=profile["baseline_omega_o"],
        style_gains=profile["style_gains"],
        task_adaptation_type=profile["task_adaptation_type"],
        task_reference_speed=None,
        task_gain_intercept=None,
        task_gain_slope=None,
        task_gain_range=None,
        total_gain_range=(1.0, 1.0),
        velocity_limit=profile["velocity_limit"],
        acceleration_limit=profile["acceleration_limit"],
        jerk_limit=profile["jerk_limit"],
        configuration_id=config.configuration_id,
    )

    def resolve_safety(s_value: float) -> SafetyResolution:
        if not safety["s_min"] <= s_value <= safety["s_max"]:
            raise ValueError(
                f"s={s_value} outside migration range "
                f"[{safety['s_min']}, {safety['s_max']}]"
            )
        return SafetyResolution(
            d_hard=safety["d_hard"],
            d_plan=safety["d_plan_base"] + safety["d_plan_margin"] * s_value,
            soft_iapf=SoftSafetyParameters(
                enter_distance=(
                    safety["iapf_enter_base"]
                    + safety["iapf_enter_margin"] * s_value
                ),
                exit_distance=(
                    safety["iapf_exit_base"]
                    + safety["iapf_exit_margin"] * s_value
                ),
                repulsion_scale=safety["repulsion_scale"],
            ),
        )

    def allocator_factory(d_plan: float) -> SafetyAwareTopologyAllocator:
        return SafetyAwareTopologyAllocator(
            sample_hz=allocator["sample_hz"],
            d_safe=d_plan,
            alpha=allocator["alpha"],
            beta=None,
            beta_xy=allocator["beta_xy"],
            beta_prox=allocator["beta_proximity"],
            gamma=allocator["gamma"],
            epsilon=allocator["epsilon"],
            min_improvement=allocator["minimum_improvement"],
        )

    return LateResolutionPolicy(
        scale=scale_policy,
        timing=timing_policy,
        profile=profile_policy,
        resolve_safety=resolve_safety,
        planning_distance_bound=max_pairwise_distance_bound,
        timing_recheck_tolerance=timing["final_recheck_tolerance"],
        allocator_factory=allocator_factory,
    )


def load_runtime_policy(path: str | Path):
    config = load_policy(path, production=True)
    return config, build_late_resolution_policy(config)
