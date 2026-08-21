from types import SimpleNamespace

import pytest

from location_allocate.paper_runtime import PaperMissionRuntime
from location_allocate.state_snapshot import FreshStateSnapshotManager


class Clock:
    def __init__(self, timestamp=100.0):
        self.timestamp = timestamp

    def now(self):
        return SimpleNamespace(nanoseconds=int(self.timestamp * 1e9))


class Node:
    def __init__(self, clock):
        self.clock = clock

    def get_clock(self):
        return self.clock


class Monotonic:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value


def runtime(manager, timeout=0.01, clock=None):
    return PaperMissionRuntime(
        Node(clock or Clock()),
        SimpleNamespace(state=SimpleNamespace(fresh_state_wait_timeout=timeout)),
        None, manager, {}, None, [1],
    )


def test_fresh_snapshot_is_returned_without_spinning(monkeypatch):
    manager = FreshStateSnapshotManager(0.1, 0.1)
    manager.update(1, [0, 0, 1], 100.0, source_timestamp=100.0)
    calls = []
    monkeypatch.setattr(
        "location_allocate.paper_runtime.rclpy.spin_once",
        lambda *_args, **_kwargs: calls.append(True),
    )

    assert runtime(manager)._fresh_snapshot([1]).states[1].position == (0.0, 0.0, 1.0)
    assert calls == []


def test_unavailable_snapshot_becomes_fresh_before_deadline(monkeypatch):
    manager = FreshStateSnapshotManager(0.1, 0.1)
    clock = Clock()
    monotonic = Monotonic()
    requested = []

    def spin(_node, timeout_sec):
        requested.append(timeout_sec)
        monotonic.value += 0.003
        manager.update(1, [0, 0, 1], 100.0, source_timestamp=100.0)

    monkeypatch.setattr("location_allocate.paper_runtime.time.monotonic", monotonic)
    monkeypatch.setattr("location_allocate.paper_runtime.rclpy.spin_once", spin)

    assert runtime(manager, clock=clock)._fresh_snapshot([1]).states[1].position[2] == 1.0
    assert requested == [pytest.approx(0.01)]


def test_unavailable_snapshot_never_spins_past_deadline(monkeypatch):
    manager = FreshStateSnapshotManager(0.1, 0.1)
    monotonic = Monotonic()
    requested = []

    def spin(_node, timeout_sec):
        requested.append(timeout_sec)
        monotonic.value += timeout_sec

    monkeypatch.setattr("location_allocate.paper_runtime.time.monotonic", monotonic)
    monkeypatch.setattr("location_allocate.paper_runtime.rclpy.spin_once", spin)

    with pytest.raises(RuntimeError, match="fresh state wait timed out"):
        runtime(manager)._fresh_snapshot([1])
    assert requested == [pytest.approx(0.01)]
    assert monotonic.value == pytest.approx(0.01)
