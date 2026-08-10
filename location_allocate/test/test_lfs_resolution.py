import math

import pytest

from location_allocate.formation_geometry import (
    GeometryError,
    ScalePolicy,
    build_final_geometry,
    build_unit_geometry,
    resolve_scale,
)
from location_allocate.lfs_resolver import resolve_candidate_task
from location_allocate.state_snapshot import FreshStateSnapshotManager, SnapshotError


def candidate_task(**overrides):
    task = {
        "task_id": 1,
        "U": [1, 2, 3],
        "F": "Circle",
        "c": {"mode": "maintain_current_centroid"},
        "r": {"mode": "qualitative", "value": "normal"},
        "T": {"mode": "auto"},
        "m": "normal",
        "s": 1.0,
        "q": "direct",
    }
    task.update(overrides)
    return task


def snapshot_manager():
    manager = FreshStateSnapshotManager(state_timeout=1.0, snapshot_skew=0.2)
    manager.update(1, [0.0, 0.0, 1.0], receive_timestamp=9.9)
    manager.update(2, [2.0, 0.0, 1.0], receive_timestamp=9.8)
    manager.update(3, [100.0, 100.0, 1.0], receive_timestamp=9.85)
    return manager


def scale_policy():
    return ScalePolicy(
        nominal_spacing=2.0,
        qualitative_multipliers={
            "compact": 0.75,
            "normal": 1.0,
            "spacious": 1.5,
        },
        workspace_bounds=((-10.0, -10.0, 0.0), (10.0, 10.0, 10.0)),
        configuration_id="test-only",
    )


def test_snapshot_requires_every_participant_to_be_fresh():
    manager = snapshot_manager()
    manager.update(2, [2.0, 0.0, 1.0], receive_timestamp=7.0)

    with pytest.raises(SnapshotError, match=r"stale UAV states: \[2\]"):
        manager.snapshot([1, 2], now=10.0)
    with pytest.raises(SnapshotError, match="missing UAV states"):
        manager.snapshot([1, 4], now=10.0)


def test_snapshot_rejects_mixed_epochs():
    manager = snapshot_manager()
    manager.update(2, [2.0, 0.0, 1.0], receive_timestamp=9.5)

    with pytest.raises(SnapshotError, match="snapshot_skew"):
        manager.snapshot([1, 2], now=10.0)


def test_current_centroid_uses_only_current_task_u():
    snapshot = snapshot_manager().snapshot([1, 2, 3], now=10.0)
    task = candidate_task(U=[1, 2])

    intent, trace = resolve_candidate_task(task, snapshot)

    assert intent.center == (1.0, 0.0, 1.0)
    assert trace.center_source == "snapshot.participant_centroid"


def test_relative_center_reuses_participant_centroid():
    snapshot = snapshot_manager().snapshot([1, 2], now=10.0)
    task = candidate_task(
        U=[1, 2],
        c={
            "mode": "relative",
            "reference": "current_swarm_centroid",
            "offset": [3.0, -1.0, 2.0],
            "frame": "world",
        },
    )

    intent, _ = resolve_candidate_task(task, snapshot)

    assert intent.center == (4.0, -1.0, 3.0)


def test_unit_geometry_is_independent_of_center_and_scale():
    triangle = build_unit_geometry("Triangle", 3)
    polygon = build_unit_geometry("Polygon", 4)

    assert len(triangle.offsets) == 3
    assert len(polygon.offsets) == 4
    assert triangle.geometry_version == "unit-v1"
    assert triangle.delta_min == pytest.approx(math.sqrt(3.0))


@pytest.mark.parametrize("label", ["compact", "normal", "spacious"])
def test_qualitative_scale_uses_injected_multiplier(label):
    snapshot = snapshot_manager().snapshot([1, 2, 3], now=10.0)
    intent, trace = resolve_candidate_task(
        candidate_task(
            c={"mode": "absolute", "value": [0.0, 0.0, 2.0]},
            r={"mode": "qualitative", "value": label},
        ),
        snapshot,
    )
    unit = build_unit_geometry("Circle", 3)
    policy = scale_policy()

    radius = resolve_scale(intent, unit, d_plan=1.0, policy=policy, trace=trace)
    targets = build_final_geometry(
        intent.center, unit, radius, policy.workspace_bounds, d_plan=1.0
    )

    expected_nominal = policy.nominal_spacing / unit.delta_min
    expected_requested = expected_nominal * policy.qualitative_multipliers[label]
    assert radius == pytest.approx(max(expected_requested, 1.0 / unit.delta_min))
    assert min(math.dist(a, b) for a in targets for b in targets if a != b) >= 1.0


def test_r_safe_uses_d_plan_not_d_hard():
    snapshot = snapshot_manager().snapshot([1, 2, 3], now=10.0)
    intent, trace = resolve_candidate_task(
        candidate_task(
            c={"mode": "absolute", "value": [0.0, 0.0, 2.0]},
            r={"mode": "explicit", "value": 0.1},
        ),
        snapshot,
    )
    unit = build_unit_geometry("Circle", 3)

    radius = resolve_scale(
        intent, unit, d_plan=2.4, policy=scale_policy(), trace=trace
    )

    assert radius == pytest.approx(2.4 / unit.delta_min)
    assert trace.d_hard is None
    assert "d_plan(s)" in trace.corrections[0]


def test_workspace_never_shrinks_below_safety_lower_bound():
    snapshot = snapshot_manager().snapshot([1, 2, 3], now=10.0)
    intent, trace = resolve_candidate_task(
        candidate_task(
            c={"mode": "absolute", "value": [9.5, 0.0, 2.0]},
            r={"mode": "explicit", "value": 0.1},
        ),
        snapshot,
    )

    with pytest.raises(GeometryError, match="workspace scale limit conflicts"):
        resolve_scale(
            intent,
            build_unit_geometry("Circle", 3),
            d_plan=2.0,
            policy=scale_policy(),
            trace=trace,
        )


def test_candidate_free_is_pending_not_silently_reinterpreted():
    with pytest.raises(GeometryError, match="pending confirmation"):
        build_unit_geometry("Free", 3)
