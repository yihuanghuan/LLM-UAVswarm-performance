"""Experiment-only E2 commitment-stage manipulation.

This module never replaces or patches production resolution.  It calls the
frozen resolver once at the interpretation snapshot, then copies only c/r/T
into an otherwise identical Candidate task for the Early Commitment arm.
The Late Commitment arm is the untouched Candidate task.
"""

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict

from location_allocate.late_resolution import (
    LateResolutionPolicy,
    ResolvedExecutionTask,
    resolve_execution_task,
)
from location_allocate.lfs_types import StateSnapshot


@dataclass(frozen=True)
class CommitmentPair:
    late_candidate: Dict[str, Any]
    early_candidate: Dict[str, Any]
    interpretation_resolution: ResolvedExecutionTask


def build_commitment_pair(
    candidate_task: Dict[str, Any],
    interpretation_snapshot: StateSnapshot,
    policy: LateResolutionPolicy,
) -> CommitmentPair:
    """Return paired Candidates differing only in c/r/T commitment stage."""
    interpretation = resolve_execution_task(
        deepcopy(candidate_task), interpretation_snapshot, policy
    )
    executable = interpretation.executable_lfs
    early = deepcopy(candidate_task)
    early["c"] = {"mode": "absolute", "value": list(executable.center)}
    early["r"] = {"mode": "explicit", "value": executable.radius}
    early["T"] = {"mode": "explicit", "value": executable.duration}
    late = deepcopy(candidate_task)

    for field in ("task_id", "U", "F", "m", "s", "q"):
        if early[field] != late[field]:
            raise AssertionError(f"E2 wrapper changed non-c/r/T field {field}")
    return CommitmentPair(late, early, interpretation)


def resolve_paired_at_execution(
    pair: CommitmentPair,
    execution_snapshot: StateSnapshot,
    policy: LateResolutionPolicy,
) -> tuple[ResolvedExecutionTask, ResolvedExecutionTask]:
    """Resolve Early and Late arms through the same frozen production API."""
    early = resolve_execution_task(
        deepcopy(pair.early_candidate), execution_snapshot, policy
    )
    late = resolve_execution_task(
        deepcopy(pair.late_candidate), execution_snapshot, policy
    )
    return early, late
