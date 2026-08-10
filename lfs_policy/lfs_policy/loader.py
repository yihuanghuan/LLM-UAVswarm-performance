"""Fail-fast typed loading for Candidate production policies."""

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple

import yaml


class PolicyLoadError(ValueError):
    pass


Vector3 = Tuple[float, float, float]


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise PolicyLoadError(f"{path} must be a mapping")
    return value


def _required(mapping: Mapping[str, Any], key: str, path: str) -> Any:
    if key not in mapping:
        raise PolicyLoadError(f"missing key: {path}.{key}")
    value = mapping[key]
    if value is None:
        raise PolicyLoadError(f"null is not allowed: {path}.{key}")
    return value


def _number(value: Any, path: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PolicyLoadError(f"{path} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise PolicyLoadError(f"{path} must be finite")
    if minimum is not None and result < minimum:
        raise PolicyLoadError(f"{path} must be >= {minimum}")
    return result


def _positive(value: Any, path: str) -> float:
    result = _number(value, path)
    if result <= 0.0:
        raise PolicyLoadError(f"{path} must be positive")
    return result


def _vector(value: Any, path: str) -> Vector3:
    if not isinstance(value, list) or len(value) != 3:
        raise PolicyLoadError(f"{path} must contain exactly three values")
    return tuple(_number(item, f"{path}[{index}]") for index, item in enumerate(value))


def _labels(mapping: Mapping[str, Any], path: str) -> Dict[str, float]:
    expected = {"smooth", "normal", "aggressive"}
    if set(mapping) != expected:
        raise PolicyLoadError(f"{path} must define exactly {sorted(expected)}")
    return {key: _positive(mapping[key], f"{path}.{key}") for key in expected}


@dataclass(frozen=True)
class StatePolicy:
    state_timeout: float
    snapshot_skew: float
    fresh_state_wait_timeout: float
    allow_receive_time_fallback: bool
    require_velocity: bool


@dataclass(frozen=True)
class ControllerHardClamps:
    smoothing_alpha: float
    omega_c_min: Vector3
    omega_c_max: Vector3
    omega_o_min: Vector3
    omega_o_max: Vector3
    velocity_max: float
    acceleration_max: float
    jerk_max: float
    iapf_enter_min: float
    iapf_enter_max: float
    iapf_exit_max: float
    iapf_repulsion_max: float

    def ros_parameters(self) -> Dict[str, Any]:
        return {
            "enable_execution_profiles": True,
            "execution_profile_smoothing_alpha": self.smoothing_alpha,
            "execution_profile_omega_c_min": list(self.omega_c_min),
            "execution_profile_omega_c_max": list(self.omega_c_max),
            "execution_profile_omega_o_min": list(self.omega_o_min),
            "execution_profile_omega_o_max": list(self.omega_o_max),
            "execution_profile_velocity_max": self.velocity_max,
            "execution_profile_acceleration_max": self.acceleration_max,
            "execution_profile_jerk_max": self.jerk_max,
            "execution_profile_iapf_enter_min": self.iapf_enter_min,
            "execution_profile_iapf_enter_max": self.iapf_enter_max,
            "execution_profile_iapf_exit_max": self.iapf_exit_max,
            "execution_profile_iapf_repulsion_max": self.iapf_repulsion_max,
        }


@dataclass(frozen=True)
class LoadedPolicy:
    configuration_id: str
    status: str
    state: StatePolicy
    geometry: Mapping[str, Any]
    safety: Mapping[str, Any]
    timing: Mapping[str, Any]
    allocator: Mapping[str, Any]
    execution_profile: Mapping[str, Any]
    controller: ControllerHardClamps
    provenance: Mapping[str, str]


def _validate_policy(data: Mapping[str, Any], production: bool) -> LoadedPolicy:
    status = str(_required(data, "policy_status", "policy"))
    configuration_id = str(_required(data, "configuration_id", "policy")).strip()
    if not configuration_id:
        raise PolicyLoadError("configuration_id must not be empty")
    if production and status != "migration":
        raise PolicyLoadError("production requires policy_status=migration")

    state_raw = _mapping(_required(data, "state_snapshot", "policy"), "state_snapshot")
    fallback = _required(state_raw, "allow_receive_time_fallback", "state_snapshot")
    require_velocity = _required(state_raw, "require_velocity", "state_snapshot")
    if not isinstance(fallback, bool) or not isinstance(require_velocity, bool):
        raise PolicyLoadError("state fallback/velocity flags must be boolean")
    state = StatePolicy(
        _positive(_required(state_raw, "state_timeout", "state_snapshot"), "state_snapshot.state_timeout"),
        _number(_required(state_raw, "snapshot_skew", "state_snapshot"), "state_snapshot.snapshot_skew", minimum=0.0),
        _positive(_required(state_raw, "fresh_state_wait_timeout", "state_snapshot"), "state_snapshot.fresh_state_wait_timeout"),
        fallback,
        require_velocity,
    )

    geometry = dict(_mapping(_required(data, "geometry", "policy"), "geometry"))
    bounds = _mapping(_required(geometry, "workspace_bounds", "geometry"), "geometry.workspace_bounds")
    lower = _vector(_required(bounds, "lower", "geometry.workspace_bounds"), "geometry.workspace_bounds.lower")
    upper = _vector(_required(bounds, "upper", "geometry.workspace_bounds"), "geometry.workspace_bounds.upper")
    if any(a >= b for a, b in zip(lower, upper)):
        raise PolicyLoadError("workspace lower must be strictly below upper")
    geometry["workspace_bounds"] = {"lower": lower, "upper": upper}
    geometry["nominal_spacing"] = _positive(_required(geometry, "nominal_spacing", "geometry"), "geometry.nominal_spacing")
    qualitative = _mapping(_required(geometry, "qualitative_multipliers", "geometry"), "geometry.qualitative_multipliers")
    if set(qualitative) != {"compact", "normal", "spacious"}:
        raise PolicyLoadError("qualitative multipliers must define compact/normal/spacious")
    geometry["qualitative_multipliers"] = {key: _positive(value, f"geometry.qualitative_multipliers.{key}") for key, value in qualitative.items()}

    safety = dict(_mapping(_required(data, "safety", "policy"), "safety"))
    for key in ("d_hard", "d_plan_base", "d_plan_margin", "iapf_enter_base", "iapf_enter_margin", "iapf_exit_base", "iapf_exit_margin", "repulsion_scale", "s_min", "s_max"):
        safety[key] = _positive(_required(safety, key, "safety"), f"safety.{key}")
    if safety["s_min"] < 1.0 or safety["s_max"] < safety["s_min"]:
        raise PolicyLoadError("safety s range must satisfy 1 <= min <= max")
    d_plan_min = safety["d_plan_base"] + safety["d_plan_margin"] * safety["s_min"]
    enter_min = safety["iapf_enter_base"] + safety["iapf_enter_margin"] * safety["s_min"]
    exit_min = safety["iapf_exit_base"] + safety["iapf_exit_margin"] * safety["s_min"]
    if not safety["d_hard"] <= d_plan_min or not safety["d_hard"] < enter_min < exit_min:
        raise PolicyLoadError("safety ordering or IAPF hysteresis is invalid")

    timing = dict(_mapping(_required(data, "timing", "policy"), "timing"))
    if _required(timing, "policy_type", "timing") != "minimum_jerk":
        raise PolicyLoadError("unsupported timing.policy_type")
    for key in ("velocity_limit", "acceleration_limit", "jerk_limit", "minimum_duration"):
        timing[key] = _positive(_required(timing, key, "timing"), f"timing.{key}")
    timing["auto_style_factors"] = _labels(_mapping(_required(timing, "auto_style_factors", "timing"), "timing.auto_style_factors"), "timing.auto_style_factors")
    if _required(timing, "planning_distance_bound_type", "timing") != "max_pairwise":
        raise PolicyLoadError("unsupported planning distance bound")
    timing["final_recheck_tolerance"] = _number(_required(timing, "final_recheck_tolerance", "timing"), "timing.final_recheck_tolerance", minimum=0.0)

    allocator = dict(_mapping(_required(data, "allocator", "policy"), "allocator"))
    for key in ("sample_hz", "alpha", "beta_xy", "beta_proximity", "gamma", "epsilon", "minimum_improvement"):
        allocator[key] = _positive(_required(allocator, key, "allocator"), f"allocator.{key}")
    if _required(allocator, "parallel_d_plan_aggregation", "allocator") != "max":
        raise PolicyLoadError("parallel_d_plan_aggregation must be max")

    profile = dict(_mapping(_required(data, "execution_profile", "policy"), "execution_profile"))
    if _required(profile, "task_adaptation_type", "execution_profile") != "identity":
        raise PolicyLoadError("migration task adaptation must be identity")
    profile["baseline_omega_c"] = _vector(_required(profile, "baseline_omega_c", "execution_profile"), "execution_profile.baseline_omega_c")
    profile["baseline_omega_o"] = _vector(_required(profile, "baseline_omega_o", "execution_profile"), "execution_profile.baseline_omega_o")
    profile["style_gains"] = _labels(_mapping(_required(profile, "style_gains", "execution_profile"), "execution_profile.style_gains"), "execution_profile.style_gains")
    for key in ("velocity_limit", "acceleration_limit", "jerk_limit"):
        profile[key] = _positive(_required(profile, key, "execution_profile"), f"execution_profile.{key}")

    hard = _mapping(_required(data, "controller_hard_clamps", "policy"), "controller_hard_clamps")
    controller = ControllerHardClamps(
        _number(_required(hard, "smoothing_alpha", "controller_hard_clamps"), "controller_hard_clamps.smoothing_alpha"),
        _vector(_required(hard, "omega_c_min", "controller_hard_clamps"), "controller_hard_clamps.omega_c_min"),
        _vector(_required(hard, "omega_c_max", "controller_hard_clamps"), "controller_hard_clamps.omega_c_max"),
        _vector(_required(hard, "omega_o_min", "controller_hard_clamps"), "controller_hard_clamps.omega_o_min"),
        _vector(_required(hard, "omega_o_max", "controller_hard_clamps"), "controller_hard_clamps.omega_o_max"),
        *[_positive(_required(hard, key, "controller_hard_clamps"), f"controller_hard_clamps.{key}") for key in ("velocity_max", "acceleration_max", "jerk_max", "iapf_enter_min", "iapf_enter_max", "iapf_exit_max", "iapf_repulsion_max")],
    )
    if not 0.0 < controller.smoothing_alpha <= 1.0:
        raise PolicyLoadError("smoothing_alpha must be in (0, 1]")
    for low, high in zip(controller.omega_c_min, controller.omega_c_max):
        if low <= 0.0 or high < low:
            raise PolicyLoadError("invalid omega_c clamps")
    for low, high in zip(controller.omega_o_min, controller.omega_o_max):
        if low <= 0.0 or high < low:
            raise PolicyLoadError("invalid omega_o clamps")
    max_enter = safety["iapf_enter_base"] + safety["iapf_enter_margin"] * safety["s_max"]
    max_exit = safety["iapf_exit_base"] + safety["iapf_exit_margin"] * safety["s_max"]
    if controller.iapf_enter_min > enter_min or controller.iapf_enter_max < max_enter or controller.iapf_exit_max < max_exit:
        raise PolicyLoadError("controller IAPF clamps do not cover safety mapping")
    if controller.velocity_max < profile["velocity_limit"] or controller.acceleration_max < profile["acceleration_limit"] or controller.jerk_max < profile["jerk_limit"]:
        raise PolicyLoadError("controller dynamics clamps do not cover profile")

    provenance_raw = _mapping(_required(data, "provenance", "policy"), "provenance")
    provenance = {str(key): str(value) for key, value in provenance_raw.items() if str(value).strip()}
    if not provenance:
        raise PolicyLoadError("provenance must not be empty")
    return LoadedPolicy(configuration_id, status, state, geometry, safety, timing, allocator, profile, controller, provenance)


def load_policy(path: str | Path, *, production: bool = True) -> LoadedPolicy:
    policy_path = Path(path)
    if not policy_path.is_file():
        raise PolicyLoadError(f"policy file not found: {policy_path}")
    try:
        data = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PolicyLoadError(f"failed to read policy: {exc}") from exc
    return _validate_policy(_mapping(data, "policy"), production)
