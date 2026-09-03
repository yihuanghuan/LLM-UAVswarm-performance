"""Static activation and next-slot gate tests; no mission side effects."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


HERE = Path(__file__).resolve()
E5_DIR = HERE.parents[1]
TOOLING = E5_DIR / "tooling"
REPO = HERE.parents[4]
sys.path.insert(0, str(TOOLING))

from e5_v2_activation_common import (  # noqa: E402
    ACTIVATION_MANIFEST_PATH,
    CANDIDATE_COMMIT,
    candidate_scientific_payload_sha256,
    sealed_scientific_payload_sha256,
)
from e5_v2_common import REGISTRY_PATH  # noqa: E402
from e5_v2_formal_adapter import (  # noqa: E402
    FormalActivationError,
    assert_formal_activation,
    assert_formal_attempt,
)


SLOT_1 = {
    "order_position": 1,
    "trial_id": "E5V2-B-S2-N12-R1",
    "seed": 5202036,
    "n": 12,
    "scenario_id": "E5V2-B-S2-N12",
    "substudy": "E5-v2B",
    "task_family": "UNDER_SPECIFIED",
}


def test_scientific_payload_is_identical_across_activation():
    assert candidate_scientific_payload_sha256() == sealed_scientific_payload_sha256()


def test_activation_gate_accepts_exact_sealed_registry_only(tmp_path):
    assert_formal_activation(REGISTRY_PATH, ACTIVATION_MANIFEST_PATH)
    relative = REGISTRY_PATH.relative_to(REPO).as_posix()
    candidate = subprocess.check_output(
        ["git", "show", f"{CANDIDATE_COMMIT}:{relative}"], cwd=REPO
    )
    candidate_path = tmp_path / "candidate.yaml"
    candidate_path.write_bytes(candidate)
    with pytest.raises(FormalActivationError, match="registry status"):
        assert_formal_activation(candidate_path, ACTIVATION_MANIFEST_PATH)

    stale_path = tmp_path / "stale-sealed.yaml"
    stale_path.write_bytes(REGISTRY_PATH.read_bytes() + b"\n")
    with pytest.raises(FormalActivationError, match="sealed registry SHA-256"):
        assert_formal_activation(stale_path, ACTIVATION_MANIFEST_PATH)


def test_slot_1_exact_gate_passes_without_execution():
    result = assert_formal_attempt(**SLOT_1)
    assert result["attempt_id"] == SLOT_1["trial_id"]
    assert result["seed"] == SLOT_1["seed"]


@pytest.mark.parametrize(
    ("field", "wrong"),
    [
        ("order_position", 2),
        ("trial_id", "E5V2-B-S2-N8-R1"),
        ("seed", 5202037),
        ("n", 8),
        ("scenario_id", "E5V2-B-S2-N8"),
        ("substudy", "E5-v2A"),
        ("task_family", "SIMPLE"),
    ],
)
def test_slot_gate_refuses_wrong_registered_identity(field, wrong):
    request = dict(SLOT_1)
    request[field] = wrong
    with pytest.raises(FormalActivationError):
        assert_formal_attempt(**request)


def test_slot_gate_refuses_replacement_and_non_prefix_history():
    replacement = dict(SLOT_1)
    replacement["order_position"] = 2
    with pytest.raises(FormalActivationError, match="replacement"):
        assert_formal_attempt(
            **replacement, completed_attempt_ids=[SLOT_1["trial_id"]]
        )
    with pytest.raises(FormalActivationError, match="order prefix"):
        assert_formal_attempt(
            **SLOT_1, completed_attempt_ids=["E5V2-B-S2-N8-R1"]
        )
