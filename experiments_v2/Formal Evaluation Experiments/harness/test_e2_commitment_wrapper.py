"""Static preflight checks; these are not formal E2 trials."""

from copy import deepcopy

from e2_commitment_wrapper import build_commitment_pair
from location_allocate.lfs_types import StateSnapshot, UAVState
from location_allocate.policy_adapter import load_runtime_policy


def _snapshot():
    positions = [(-3, 6, 3), (-1, 6, 3), (1, 6, 3), (3, 6, 3)]
    return StateSnapshot(
        100.0,
        {
            uid: UAVState(position, 100.0, (0, 0, 0), 100.0, "source_time")
            for uid, position in enumerate(positions, 1)
        },
    )


def test_wrapper_changes_only_commitment_fields():
    _, candidate_policy = load_runtime_policy(
        "lfs_policy/config/lfs_policy.paper_current.yaml"
    )
    task = {
        "task_id": 1,
        "U": [1, 2, 3, 4],
        "F": {"type": "Circle"},
        "c": {"mode": "auto"},
        "r": {"mode": "qualitative", "value": "normal"},
        "T": {"mode": "auto"},
        "m": "normal",
        "s": 1.0,
        "q": {"mode": "direct"},
    }
    before = deepcopy(task)
    pair = build_commitment_pair(task, _snapshot(), candidate_policy)
    assert task == before
    assert pair.late_candidate == before
    assert pair.early_candidate["c"]["mode"] == "absolute"
    assert pair.early_candidate["r"]["mode"] == "explicit"
    assert pair.early_candidate["T"]["mode"] == "explicit"
    for field in ("task_id", "U", "F", "m", "s", "q"):
        assert pair.early_candidate[field] == pair.late_candidate[field]
