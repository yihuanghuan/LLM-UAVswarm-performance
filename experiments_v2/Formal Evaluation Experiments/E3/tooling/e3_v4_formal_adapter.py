#!/usr/bin/env python3
"""Standalone exact-trial adapter for the candidate E3-v4 campaign."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import yaml

from e3_v4_execution_deviation_qualification import _metrics_environment
from e3_v4_trial_registry import (
    E3, ORDER, ORDER_SHA256, POLICY_SHA256, REGISTRY, REGISTRY_SHA256,
    SEEDS_SHA256, build_exact_runtime_spec, build_exact_spec,
    registered_trial_ids, sha256_file,
)

REPO = E3.parents[2]
HARNESS = Path(__file__).with_name("e3_v4_execution_deviation_trial.py")
METRICS = Path(__file__).with_name("e3_v4_formal_metrics.py")
ENTRYPOINT = "experiments_v2/Formal Evaluation Experiments/E3/tooling/e3_v4_formal_adapter.py"
NOTICE = "NOT_FORMAL_RESULT"
FORMAL_DATASET = "formal_evaluation"
TOOLING_PATHS = (
    ENTRYPOINT,
    "experiments_v2/Formal Evaluation Experiments/E3/tooling/e3_v4_trial_registry.py",
    "experiments_v2/Formal Evaluation Experiments/E3/tooling/e3_v4_formal_metrics.py",
    "experiments_v2/Formal Evaluation Experiments/E3/tooling/e3_v4_campaign_journal.py",
    "experiments_v2/Formal Evaluation Experiments/E3/tooling/e3_v4_execution_deviation_trial.py",
    "experiments_v2/Formal Evaluation Experiments/E3/tooling/e3_v4_execution_deviation_metrics.py",
    "experiments_v2/Formal Evaluation Experiments/E3/tooling/e3_formal_backend.py",
    "experiments_v2/Formal Evaluation Experiments/E3/tooling/e3_physical_trial.py",
    "experiments_v2/Formal Evaluation Experiments/E3/tooling/e3_runtime_diagnostics.py",
)


class AdapterError(RuntimeError):
    pass


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO, text=True).strip()


def tooling_identity() -> dict[str, Any]:
    files = {path: sha256_file(REPO / path) for path in sorted(TOOLING_PATHS)}
    payload = {"schema": "E3_v4_execution_tooling_bundle_v1", "files": files}
    digest = hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    return {**payload, "bundle_sha256": digest}


def adapter_identity() -> dict[str, Any]:
    tooling = tooling_identity()
    return {
        "branch": git("branch", "--show-current"),
        "commit": git("log", "-1", "--format=%H", "--", ENTRYPOINT),
        "entrypoint": ENTRYPOINT,
        "source_sha256": sha256_file(Path(__file__)),
        "execution_tooling": tooling,
    }


def durable_write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise AdapterError(f"refusing to overwrite retained artifact: {path}")
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary.exists():
            temporary.unlink()


def validate_context(trial_id: str, context: dict) -> tuple[str, int, dict]:
    order = registered_trial_ids()
    if trial_id not in set(order):
        raise AdapterError("unregistered E3-v4 trial")
    position = order.index(trial_id) + 1
    if context.get("trial_id") != trial_id or context.get("campaign_position") != position:
        raise AdapterError("standalone campaign context mismatch")
    mode = context.get("execution_mode")
    if mode not in ("spec_rehearsal", "formal"):
        raise AdapterError("execution_mode must be spec_rehearsal or formal")
    identity = adapter_identity()
    if context.get("runner_commit") != identity["commit"]:
        raise AdapterError("pinned runner commit mismatch")
    if context.get("runner_source_sha256") != identity["source_sha256"]:
        raise AdapterError("pinned runner source mismatch")
    if context.get("runner_tooling_bundle_sha256") != identity["execution_tooling"]["bundle_sha256"]:
        raise AdapterError("pinned tooling bundle mismatch")
    if context.get("registry_sha256") != REGISTRY_SHA256:
        raise AdapterError("registry hash mismatch")
    if context.get("formal_seed_registry_sha256") != SEEDS_SHA256:
        raise AdapterError("formal seed hash mismatch")
    if context.get("order_sha256") != ORDER_SHA256:
        raise AdapterError("standalone order hash mismatch")
    if context.get("policy_sha256") != POLICY_SHA256:
        raise AdapterError("policy hash mismatch")
    if mode == "formal":
        # This candidate commit is deliberately unable to start formal data.
        # A later human-reviewed activation must version and repin the registry.
        registry = yaml.safe_load(REGISTRY.read_text())
        if registry.get("status") != "SEALED_FOR_FORMAL_EXECUTION":
            raise AdapterError("formal launch blocked pending human registry activation")
        if context.get("formal_launch_authorized") is not True:
            raise AdapterError("explicit formal launch authorization missing")
        if context.get("dataset_class") != FORMAL_DATASET:
            raise AdapterError("formal dataset class missing")
    else:
        if context.get("formal_launch_authorized") is not False:
            raise AdapterError("spec rehearsal cannot carry formal authorization")
        if context.get("dataset_class") != "engineering_validation":
            raise AdapterError("spec rehearsal dataset class mismatch")
    return mode, position, identity


def run_exact_trial(trial_id: str, context: dict) -> dict:
    mode, position, identity = validate_context(trial_id, context)
    output = Path(context["attempt_output_dir"]).resolve()
    if output.exists():
        raise AdapterError(f"duplicate attempt directory: {output}")
    output.mkdir(parents=True)
    spec = build_exact_spec(trial_id)
    status = "success"
    backend: dict[str, Any]
    metrics = None
    if mode == "spec_rehearsal":
        runtime = build_exact_runtime_spec(trial_id)
        backend = {
            "physical_execution_performed": False,
            "runtime_spec_sha256": runtime["runtime_spec_sha256"],
            "allocator_diagnostics": runtime["allocator_diagnostics"],
            "manipulation": runtime["manipulation"],
        }
    else:
        raw = output / "raw"
        raw.mkdir()
        runtime = build_exact_runtime_spec(trial_id)
        runtime_path = raw / "runtime_spec.json"
        runtime_path.write_text(json.dumps(runtime, indent=2, sort_keys=True) + "\n")
        physical_path = raw / "physical_result.json"
        run = subprocess.run(
            [sys.executable, str(HARNESS), "--runtime-spec", str(runtime_path),
             "--output", str(raw), "--result", str(physical_path)],
            cwd=REPO, text=True, capture_output=True,
            timeout=float(runtime["timeout_after_t0_s"]) + 300.0,
        )
        (raw / "harness.stdout.log").write_text(run.stdout)
        (raw / "harness.stderr.log").write_text(run.stderr)
        if not physical_path.is_file():
            status = "infrastructure_failure"
            backend = {"error": "physical result missing", "returncode": run.returncode}
        else:
            backend = json.loads(physical_path.read_text())
            status = str(backend.get("attempt_status", "infrastructure_failure"))
        if status == "success":
            metrics_path = output / "metrics.json"
            metric_run = subprocess.run(
                [sys.executable, str(METRICS), str(raw), "--output", str(metrics_path)],
                cwd=REPO, env=_metrics_environment(), text=True, capture_output=True,
            )
            (output / "metrics.log").write_text(metric_run.stdout + metric_run.stderr)
            if metric_run.returncode:
                status = "infrastructure_failure"
                backend["metric_error"] = "formal metric/delivery verification failed"
            else:
                metrics = json.loads(metrics_path.read_text())
    accepted = mode == "formal"
    artifact = {
        "schema": "E3_v4_exact_trial_attempt_v1",
        "dataset_class": FORMAL_DATASET if accepted else "engineering_validation",
        "accepted_formal_result": accepted,
        "result_notice": None if accepted else NOTICE,
        "trial_id": trial_id,
        "campaign_position": position,
        "attempt_status": status,
        "replacement_attempt": False,
        "execution_mode": mode,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "execution_spec": spec,
        "backend_result": backend,
        "metrics": metrics,
        "adapter": identity,
        "provenance": {
            "registry_sha256": REGISTRY_SHA256,
            "formal_seed_registry_sha256": SEEDS_SHA256,
            "order_sha256": ORDER_SHA256,
            "policy_sha256": POLICY_SHA256,
        },
    }
    durable_write(output / "attempt.json", artifact)
    return {
        "trial_id": trial_id, "campaign_position": position,
        "attempt_status": status, "accepted_formal_result": accepted,
        "artifact_sha256": sha256_file(output / "attempt.json"),
        "suite_journal_mutated": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial-id", required=True)
    parser.add_argument("--campaign-context", type=Path, required=True)
    args = parser.parse_args()
    context = json.loads(args.campaign_context.read_text())
    print(json.dumps(run_exact_trial(args.trial_id, context), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
