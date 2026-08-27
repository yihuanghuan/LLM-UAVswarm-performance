#!/usr/bin/env python3
"""Fail-closed E3 exact-trial adapter for rehearsal and future formal use.

The adapter owns no suite cursor or journal.  It durably publishes one attempt
directory and returns its descriptor; only the global launcher may register it.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Dict

from e3_trial_registry import (
    ORDER_PATH, ORDER_SHA256, POLICY_SHA256, PROTOCOL_SHA256, REGISTRY_SHA256,
    build_exact_spec, registered_trial_ids, sha256_file,
)


ADAPTER_BRANCH = "formal/E3-formal-adapter-v1"
VALIDATED_CONTRACT_BRANCH = "formal/E3-planning-feedback-safety-v1"
VALIDATED_CONTRACT_COMMIT = "dc1c7e82dd02341994eabd60e5585f99777a0954"
PREFLIGHT_COMMIT = "36dba68c6b16681ec98500b49c5a83095de4b634"
BASELINE_TAG = "paper-final-sim-v3"
BASELINE_COMMIT = "6cf402debf23851b1eff3edc6f3ab49eae7127c4"
ENTRYPOINT = "experiments_v2/Formal Evaluation Experiments/E3/tooling/e3_formal_adapter.py"
NOTICE = "NOT_FORMAL_RESULT"
FORMAL_DATASET = "formal_evaluation"
NONFORMAL_DATASETS = {"synthetic_validation", "engineering_validation"}


class FormalAdapterError(RuntimeError):
    """An exact-trial or launch-gate invariant failed."""


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=_repo_root(), text=True).strip()


def _position(trial_id: str) -> int:
    order = ORDER_PATH.read_text(encoding="utf-8").splitlines()
    if len(order) != 610 or sha256_file(ORDER_PATH) != ORDER_SHA256:
        raise FormalAdapterError("sealed global order mismatch")
    try:
        return order.index(trial_id) + 1
    except ValueError as exc:
        raise FormalAdapterError("trial absent from sealed global order") from exc


def adapter_identity() -> Dict[str, str]:
    source = Path(__file__).resolve()
    return {
        "branch": _git("branch", "--show-current"),
        "commit": _git("rev-parse", "HEAD"),
        "entrypoint": ENTRYPOINT,
        "source_sha256": sha256_file(source),
    }


def _validate_context(trial_id: str, context: Dict[str, Any]) -> tuple[str, int, Dict[str, str]]:
    if trial_id not in set(registered_trial_ids()):
        raise FormalAdapterError(f"unregistered E3 trial: {trial_id}")
    position = _position(trial_id)
    if context.get("trial_id") != trial_id:
        raise FormalAdapterError("campaign_context trial_id mismatch")
    if context.get("global_trial_position") != position:
        raise FormalAdapterError("campaign_context global position mismatch")
    mode = context.get("execution_mode")
    if mode not in {"spec_rehearsal", "formal"}:
        raise FormalAdapterError("execution_mode must be spec_rehearsal or formal")
    identity = adapter_identity()
    expected_commit = context.get("runner_commit")
    expected_source = context.get("runner_source_sha256")
    if not expected_commit or expected_commit != identity["commit"]:
        raise FormalAdapterError("pinned adapter commit mismatch")
    if not expected_source or expected_source != identity["source_sha256"]:
        raise FormalAdapterError("pinned adapter source hash mismatch")
    if context.get("policy_sha256") != POLICY_SHA256:
        raise FormalAdapterError("canonical policy hash mismatch")
    if context.get("protocol_sha256") != PROTOCOL_SHA256:
        raise FormalAdapterError("sealed protocol hash mismatch")
    if context.get("registry_sha256") != REGISTRY_SHA256:
        raise FormalAdapterError("sealed registry hash mismatch")
    if context.get("global_trial_order_sha256") != ORDER_SHA256:
        raise FormalAdapterError("sealed global order hash mismatch")
    if mode == "formal":
        if context.get("dataset_class") != FORMAL_DATASET:
            raise FormalAdapterError("formal dataset_class required")
        if context.get("formal_launch_authorized") is not True:
            raise FormalAdapterError("formal launch authorization required")
        if context.get("launch_gate_status") != "READY_FOR_FORMAL_LAUNCH":
            raise FormalAdapterError("formal launch gate is not READY")
    else:
        if context.get("dataset_class") not in NONFORMAL_DATASETS:
            raise FormalAdapterError("rehearsal requires a non-formal dataset_class")
        if context.get("formal_launch_authorized") is not False:
            raise FormalAdapterError("rehearsal may not carry formal authorization")
    return mode, position, identity


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")


def _durable_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FormalAdapterError(f"duplicate retained attempt: {path}")
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(temporary, flags, 0o444)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_canonical_bytes(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


def _run_backend(spec: Dict[str, Any], raw_dir: Path) -> Dict[str, Any]:
    from e3_formal_backend import execute_registered_trial
    return execute_registered_trial(spec, raw_dir)


def run_exact_trial(trial_id: str, campaign_context: Dict[str, Any]) -> Dict[str, Any]:
    """Execute exactly one supplied registered trial and retain it durably."""
    mode, position, identity = _validate_context(trial_id, campaign_context)
    output = Path(campaign_context["attempt_output_dir"]).resolve()
    if output.exists():
        raise FormalAdapterError(f"duplicate retained attempt directory: {output}")
    output.mkdir(parents=True, exist_ok=False)
    spec = build_exact_spec(trial_id)
    raw_dir = output / "raw"
    raw_dir.mkdir()
    status, backend = "success", None
    if mode == "spec_rehearsal":
        backend = {
            "backend": "E3_pinned_adapter_spec_rehearsal_v1",
            "physical_execution_performed": False,
            "scientific_outcomes": None,
            "failure_injection": campaign_context.get("failure_injection"),
        }
        if backend["failure_injection"]:
            status = str(backend["failure_injection"])
    else:
        try:
            backend = _run_backend(spec, raw_dir)
            status = str(backend.get("attempt_status", "success"))
        except TimeoutError as exc:
            status, backend = "timeout", {"error": f"TimeoutError: {exc}"}
        except Exception as exc:  # a formal infrastructure failure is retained
            status = "infrastructure_failure"
            backend = {"error": f"{type(exc).__name__}: {exc}"}
    accepted = mode == "formal"
    artifact = {
        "record_type": "E3_formal_capable_exact_trial_attempt_v1",
        "dataset_class": FORMAL_DATASET if accepted else campaign_context["dataset_class"],
        "accepted_formal_result": accepted,
        "result_notice": None if accepted else NOTICE,
        "trial_id": trial_id,
        "experiment": "E3",
        "global_trial_position": position,
        "attempt_status": status,
        "replacement_attempt": False,
        "execution_mode": mode,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "execution_spec": spec,
        "backend_result": backend,
        "adapter": identity,
        "provenance": {
            "source_preflight_commit": PREFLIGHT_COMMIT,
            "baseline_tag": BASELINE_TAG,
            "baseline_commit": BASELINE_COMMIT,
            "policy_sha256": POLICY_SHA256,
            "protocol_sha256": PROTOCOL_SHA256,
            "registry_sha256": REGISTRY_SHA256,
            "global_trial_order_sha256": ORDER_SHA256,
        },
    }
    artifact_path = output / "attempt.json"
    _durable_write(artifact_path, artifact)
    digest = sha256_file(artifact_path)
    return {
        "trial_id": trial_id, "experiment": "E3", "attempt_status": status,
        "artifact_path": str(artifact_path), "artifact_sha256": digest,
        "dataset_class": artifact["dataset_class"],
        "accepted_formal_result": accepted,
        "runner_commit": identity["commit"],
        "runner_source_sha256": identity["source_sha256"],
        "suite_journal_mutated": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial-id", required=True)
    parser.add_argument("--campaign-context", type=Path, required=True)
    args = parser.parse_args()
    context = json.loads(args.campaign_context.read_text(encoding="utf-8"))
    print(json.dumps(run_exact_trial(args.trial_id, context), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
