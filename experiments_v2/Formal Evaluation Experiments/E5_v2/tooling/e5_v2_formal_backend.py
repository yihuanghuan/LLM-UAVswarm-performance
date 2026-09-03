#!/usr/bin/env python3
"""Physical N-UAV E5-v2 backend; callable only after every fail-closed gate."""

from __future__ import annotations

import csv
import json
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from e5_v2_formal_adapter import assert_formal_attempt
from e5_v2_formal_common import (
    REPO_ROOT, FormalInfrastructureError, build_launch_plan, exclusive_json,
    load_json, load_yaml, runtime_submission, validate_external_launch_authorization,
    verify_final_tooling_bundle, verify_runtime_environment,
)


def sourced_environment(install: Path, additions: Dict[str, str]) -> Dict[str, str]:
    command = f"source /opt/ros/humble/setup.bash && source {install}/setup.bash && env -0"
    raw = subprocess.check_output(["bash", "-lc", command])
    environment = {}
    for item in raw.split(b"\0"):
        if b"=" in item:
            key, value = item.split(b"=", 1)
            environment[key.decode()] = value.decode()
    environment.update(additions)
    environment["PYTHONPATH"] = ":".join((
        str(REPO_ROOT / "location_allocate"), str(REPO_ROOT / "lfs_policy"),
        environment.get("PYTHONPATH", "")))
    return environment


def start_process(command: List[str], log_path: Path, *, cwd: Path | None,
                  environment: Dict[str, str]):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(command, cwd=None if cwd is None else str(cwd),
                               env=environment, stdout=handle,
                               stderr=subprocess.STDOUT, start_new_session=True,
                               text=True)
    return process, handle


def stop_process(process: subprocess.Popen, grace: float = 12.0) -> int:
    if process.poll() is not None:
        return int(process.returncode)
    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, signum)
            return int(process.wait(timeout=grace))
        except ProcessLookupError:
            return int(process.wait())
        except subprocess.TimeoutExpired:
            continue
    raise FormalInfrastructureError(f"could not stop process group {process.pid}")


def _pids(pattern: str, exact: bool = False) -> List[int]:
    command = ["pgrep", "-x" if exact else "-f", pattern]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode not in (0, 1):
        raise FormalInfrastructureError(f"pgrep failed: {pattern}")
    return [int(value) for value in completed.stdout.split()]


def process_counts() -> Dict[str, int]:
    return {
        "gzserver": len(_pids("gzserver", True)),
        "px4": len(_pids("px4", True)),
        "controllers": len(_pids("ladrc_position_controller_node")),
        "agent": len(_pids("MicroXRCEAgent")),
    }


def _wait_spawn(n: int, timeout: float) -> Dict[str, Any]:
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        counts = process_counts()
        if counts["gzserver"] == 1 and counts["px4"] == n:
            return {"success": True, "elapsed_s": time.monotonic() - started,
                    "process_counts": counts}
        time.sleep(1.0)
    return {"success": False, "elapsed_s": time.monotonic() - started,
            "process_counts": process_counts()}


def _copy_log_suffix(source: Path, offset: int, target: Path) -> None:
    if not source.is_file() or source.stat().st_size <= offset:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as stream:
        stream.seek(offset)
        data = stream.read()
    target.write_bytes(data)


def run_physical_trial(spec: Dict[str, Any], completed_attempt_ids: List[str],
                       transaction_root: Path, launch_authorization: Path) -> Dict[str, Any]:
    """Execute one physical attempt. The orchestrator owns durable commit."""
    # These checks precede directory creation, process launch, or command submission.
    assert_formal_attempt(
        order_position=spec["campaign_position"], trial_id=spec["attempt_id"],
        seed=spec["seed"], n=spec["N"], scenario_id=spec["scenario_id"],
        substudy=spec["substudy"], task_family=spec.get("task_family"),
        completed_attempt_ids=completed_attempt_ids)
    validate_external_launch_authorization(launch_authorization)
    bundle = verify_final_tooling_bundle()
    runtime_pin = verify_runtime_environment()
    initial = process_counts()
    if any(initial.values()):
        raise FormalInfrastructureError(f"pre-existing scoped runtime process: {initial}")

    transaction_root = Path(transaction_root)
    transaction_root.mkdir(parents=True, exist_ok=False)
    plan = build_launch_plan(spec, transaction_root)
    exclusive_json(Path(plan["runtime_submission_path"]), runtime_submission(spec))
    config = load_yaml(Path(__file__).parents[1] / "E5_v2_formal_execution_config.yaml")
    runtime = config["runtime"]
    env = sourced_environment(Path(runtime["install_root"]), plan["environment"])
    px4_root = Path(runtime["px4_root"])
    processes: List[Tuple[str, subprocess.Popen, Any]] = []
    result = {
        "schema": "E5_v2_physical_backend_result_v1",
        "spec": spec, "launch_plan": plan, "runtime_pin": runtime_pin,
        "formal_execution_tooling_bundle_sha256": bundle["bundle_sha256"],
        "raw_acquisition_started": False, "stage_outcomes": {},
        "process_counts_before": initial, "timestamps_ns": {"started": time.time_ns()},
    }
    parse_log = REPO_ROOT / "logs/llm_parse_log.csv"
    raw_log = REPO_ROOT / "logs/llm_raw_responses.jsonl"
    offsets = {parse_log: parse_log.stat().st_size if parse_log.exists() else 0,
               raw_log: raw_log.stat().st_size if raw_log.exists() else 0}
    try:
        for label, command, cwd in (
            ("agent", plan["agent"], None), ("sitl", plan["sitl"], px4_root)):
            process, handle = start_process(command, transaction_root / f"{label}.log",
                                            cwd=cwd, environment=env)
            processes.append((label, process, handle))
        spawn = _wait_spawn(int(spec["N"]), float(runtime["simulator_spawn_timeout_s"]))
        result["stage_outcomes"]["infrastructure_spawn"] = spawn
        if not spawn["success"]:
            raise FormalInfrastructureError("N-UAV simulator spawn gate failed")
        controller, handle = start_process(plan["controllers"],
                                           transaction_root / "controllers.log",
                                           cwd=REPO_ROOT, environment=env)
        processes.append(("controllers", controller, handle))
        ready = subprocess.run(plan["readiness"], cwd=REPO_ROOT, env=env,
                               capture_output=True, text=True,
                               timeout=float(runtime["readiness_timeout_s"]) + 10)
        (transaction_root / "readiness.stdout.json").write_text(
            ready.stdout, encoding="utf-8")
        (transaction_root / "readiness.stderr.log").write_text(
            ready.stderr, encoding="utf-8")
        try:
            readiness_report = json.loads(ready.stdout)
        except json.JSONDecodeError:
            readiness_report = {"ready": False, "parse_error": True}
        readiness_report["success"] = ready.returncode == 0 and bool(
            readiness_report.get("ready"))
        result["stage_outcomes"]["infrastructure_readiness"] = readiness_report
        if not readiness_report["success"]:
            raise FormalInfrastructureError("all-UAV fresh-state readiness failed")

        raw_pending = Path(plan["raw_pending_root"])
        raw_pending.parent.mkdir(parents=True, exist_ok=True)
        if raw_pending.exists():
            raise FormalInfrastructureError(f"raw pending path already exists: {raw_pending}")
        raw_pending.mkdir()
        bag, handle = start_process(plan["rosbag"], transaction_root / "rosbag.log",
                                    cwd=REPO_ROOT, environment=env)
        processes.append(("rosbag", bag, handle))
        time.sleep(2.0)
        if bag.poll() is not None:
            raise FormalInfrastructureError("raw rosbag exited before command submission")
        result["raw_acquisition_started"] = True
        result["timestamps_ns"]["raw_acquisition_started"] = time.time_ns()

        semantic, handle = start_process(plan["semantic_worker"],
                                         transaction_root / "semantic_worker.log",
                                         cwd=REPO_ROOT, environment=env)
        processes.append(("semantic_worker", semantic, handle))
        maximum = float(spec["mission_timeout_s"]) + 260.0
        try:
            semantic_returncode = semantic.wait(timeout=maximum)
        except subprocess.TimeoutExpired:
            stop_process(semantic, float(runtime["process_shutdown_timeout_s"]))
            semantic_returncode = 124
        result["semantic_worker_returncode"] = semantic_returncode
        semantic_path = Path(plan["semantic_result_path"])
        result["semantic_result"] = (load_json(semantic_path) if semantic_path.is_file()
                                     else {"success": False, "candidate": None,
                                           "terminal_error": {"reason": "worker result missing"}})
        result["stage_outcomes"].update(result["semantic_result"].get("stages", {}))
    except Exception as exc:
        result["backend_error"] = {"type": type(exc).__name__, "reason": str(exc)}
        result["stage_outcomes"].setdefault(
            "infrastructure_readiness", {"success": False, "reason": str(exc)})
    finally:
        for label, process, _handle in reversed(processes):
            if label != "semantic_worker" or process.poll() is None:
                try:
                    stop_process(process, float(runtime["process_shutdown_timeout_s"]))
                except Exception as exc:
                    result.setdefault("cleanup_errors", []).append(
                        {"process": label, "reason": str(exc)})
        for _label, _process, handle in processes:
            handle.close()
        _copy_log_suffix(parse_log, offsets[parse_log], transaction_root / "llm_parse_log.csv")
        _copy_log_suffix(raw_log, offsets[raw_log], transaction_root / "llm_raw_responses.jsonl")
        trace = transaction_root / "ros_home/candidate_resolution_trace.jsonl"
        result["resolution_trace_path"] = str(trace) if trace.is_file() else None
        result["process_counts_after_cleanup"] = process_counts()
        result["timestamps_ns"]["finished"] = time.time_ns()
        exclusive_json(transaction_root / "backend_result.json", result)
    return result
