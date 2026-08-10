"""Unit geometry, scale resolution, and final world geometry."""

import itertools
import math
from dataclasses import dataclass
from typing import Mapping, Sequence, Tuple

from .lfs_types import ResolutionTrace, ResolvedTaskIntent, UnitGeometry, Vector3


class GeometryError(ValueError):
    """Raised when formation geometry has no safe workspace solution."""


@dataclass(frozen=True)
class ScalePolicy:
    """Explicitly injected policy; production values remain externally owned."""

    nominal_spacing: float
    qualitative_multipliers: Mapping[str, float]
    workspace_bounds: Tuple[Vector3, Vector3]
    configuration_id: str


def _minimum_distance(points: Sequence[Vector3]) -> float:
    if len(points) < 2:
        raise GeometryError("unit geometry needs at least two distinct points")
    result = min(
        math.dist(first, second)
        for first, second in itertools.combinations(points, 2)
    )
    if not math.isfinite(result) or result <= 0.0:
        raise GeometryError("unit geometry has no positive pairwise separation")
    return result


def build_unit_geometry(formation: str, count: int) -> UnitGeometry:
    """Build shape-only offsets; no center or scale is accepted here."""
    if count < 1:
        raise GeometryError("formation needs at least one UAV")
    points = []
    if formation == "Line":
        if count < 2:
            raise GeometryError("Line unit geometry needs at least two UAVs")
        points = [(index - (count - 1) / 2.0, 0.0, 0.0) for index in range(count)]
    elif formation == "Triangle":
        if count != 3:
            raise GeometryError("Triangle requires exactly three UAVs")
        points = [
            (math.cos(2.0 * math.pi * index / 3.0),
             math.sin(2.0 * math.pi * index / 3.0), 0.0)
            for index in range(3)
        ]
    elif formation in ("Circle", "Polygon"):
        if count < 3:
            raise GeometryError(f"{formation} requires at least three UAVs")
        points = [
            (math.cos(2.0 * math.pi * index / count),
             math.sin(2.0 * math.pi * index / count), 0.0)
            for index in range(count)
        ]
    elif formation == "Sphere":
        if count < 2:
            raise GeometryError("Sphere requires at least two UAVs")
        golden_angle = math.pi * (3.0 - math.sqrt(5.0))
        for index in range(count):
            y_value = 1.0 - 2.0 * index / float(count - 1)
            radial = math.sqrt(max(0.0, 1.0 - y_value * y_value))
            theta = golden_angle * index
            points.append((math.cos(theta) * radial, y_value,
                           math.sin(theta) * radial))
    elif formation in ("Lineup", "Free"):
        raise GeometryError(
            f"{formation} Candidate geometry is pending confirmation"
        )
    else:
        raise GeometryError(f"unsupported formation: {formation}")
    tuple_points = tuple(points)
    return UnitGeometry(
        formation=formation,
        offsets=tuple_points,
        delta_min=_minimum_distance(tuple_points),
        geometry_version="unit-v1",
    )


def _workspace_scale_limit(
    center: Vector3, geometry: UnitGeometry, bounds: Tuple[Vector3, Vector3]
) -> float:
    lower, upper = bounds
    if any(lower[axis] > upper[axis] for axis in range(3)):
        raise GeometryError("workspace lower bounds exceed upper bounds")
    if any(
        center[axis] < lower[axis] or center[axis] > upper[axis]
        for axis in range(3)
    ):
        raise GeometryError("resolved center lies outside workspace")
    limit = float("inf")
    for offset in geometry.offsets:
        for axis, component in enumerate(offset):
            if component > 0.0:
                limit = min(limit, (upper[axis] - center[axis]) / component)
            elif component < 0.0:
                limit = min(limit, (lower[axis] - center[axis]) / component)
    return limit


def resolve_scale(
    intent: ResolvedTaskIntent,
    geometry: UnitGeometry,
    d_plan: float,
    policy: ScalePolicy,
    trace: ResolutionTrace,
) -> float:
    """Resolve scale after delta_F is known; d_hard is intentionally absent."""
    if not math.isfinite(d_plan) or d_plan <= 0.0:
        raise GeometryError("d_plan must be finite and positive")
    if policy.nominal_spacing <= 0.0:
        raise GeometryError("nominal_spacing must be positive")
    r_nominal = policy.nominal_spacing / geometry.delta_min
    r_safe = d_plan / geometry.delta_min
    request = intent.radius_request
    if request["mode"] == "explicit":
        requested = float(request["value"])
    elif request["mode"] == "qualitative":
        label = request["value"]
        if label not in policy.qualitative_multipliers:
            raise GeometryError(f"missing qualitative multiplier: {label}")
        requested = r_nominal * float(policy.qualitative_multipliers[label])
    else:
        raise GeometryError(f"unsupported radius mode: {request['mode']}")
    if not math.isfinite(requested) or requested <= 0.0:
        raise GeometryError("requested scale must be finite and positive")
    r_exec = max(requested, r_safe)
    if r_exec > requested:
        trace.corrections.append("radius raised to d_plan(s) safety lower bound")
    workspace_limit = _workspace_scale_limit(
        intent.center, geometry, policy.workspace_bounds
    )
    if r_exec > workspace_limit + 1e-9:
        raise GeometryError(
            "workspace scale limit conflicts with d_plan(s) or requested scale"
        )
    trace.unit_geometry = geometry.geometry_version
    trace.delta_min = geometry.delta_min
    trace.r_nominal = r_nominal
    trace.r_safe = r_safe
    trace.r_exec = r_exec
    trace.d_plan = d_plan
    trace.configuration_id = policy.configuration_id
    return r_exec


def build_final_geometry(
    center: Vector3,
    geometry: UnitGeometry,
    scale: float,
    workspace_bounds: Tuple[Vector3, Vector3],
    d_plan: float,
) -> Tuple[Vector3, ...]:
    """Translate and scale unit points, then validate every final target."""
    targets = tuple(
        tuple(center[axis] + scale * offset[axis] for axis in range(3))
        for offset in geometry.offsets
    )
    lower, upper = workspace_bounds
    for target in targets:
        if not all(math.isfinite(value) for value in target):
            raise GeometryError("final geometry contains non-finite targets")
        if any(
            target[axis] < lower[axis] - 1e-9
            or target[axis] > upper[axis] + 1e-9
            for axis in range(3)
        ):
            raise GeometryError("final target lies outside workspace")
    if _minimum_distance(targets) + 1e-9 < d_plan:
        raise GeometryError("final geometry violates d_plan(s)")
    return targets  # type: ignore[return-value]
