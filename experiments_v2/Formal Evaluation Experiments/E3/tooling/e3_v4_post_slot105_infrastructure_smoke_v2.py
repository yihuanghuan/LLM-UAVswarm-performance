#!/usr/bin/env python3
"""Run exactly one non-formal eight-UAV startup/readiness smoke v2."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import subprocess
import time
from typing import Any

import yaml

from e3_physical_trial import (
    POLICY, PX4, READY, REPO, VENV_PYTHON, WORKSPACE,
    clean_residuals, ros_environment, start, stop,
)
from e3_v4_trial_registry import registered_trial_ids, sha256_file


SMOKE_ID = "E3-V4-INFRASTRUCTURE-SMOKE-AFTER-SLOT105-v2"
SMOKE_SEED = 3047956
IDS = list(range(1, 9))
E3 = Path(__file__).resolve().parent.parent
PROTOCOL = E3 / "E3_v4_post_slot105_smoke_v2_protocol.yaml"
RESULTS = E3 / "results/formal_v4"
JOURNAL = RESULTS / "campaign_journal.jsonl"
STORAGE_LEDGER = RESULTS / "raw_archive_ledger.jsonl"
SEED_REGISTRIES = (
    E3 / "E3_v4_formal_paired_seeds.yaml",
    E3 / "E3_v4_qualification_seeds.yaml",
    E3 / "E3_v4_B02_holdout_qualification_seeds.yaml",
)
CORE_CHECKS = (
    "px4_gazebo_launcher_alive_before_controllers",
    "readiness_process_returned_zero",
    "readiness_reported_true",
    "readiness_uav_count_is_8",
    "all_8_present",
    "all_8_fresh_under_existing_readiness_gate",
    "all_8_system_ready",
    "all_8_armed",
    "all_8_offboard",
    "all_8_failsafe_false",
    "all_8_finite_altitude",
    "gazebo_master_alive",
    "at_least_8_px4_processes_alive",
    "at_least_8_controller_processes_alive",
    "micro_xrce_agent_alive",
    "residual_simulator_controller_processes_absent",
    "campaign_journal_unchanged",
    "raw_storage_ledger_unchanged",
    "formal_attempt_directories_unchanged",
    "formal_contexts_unchanged",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def all_integers(value: Any) -> list[int]:
    if isinstance(value, bool):
        return []
    if isinstance(value, int):
        return [value]
    if isinstance(value, list):
        return [item for child in value for item in all_integers(child)]
    if isinstance(value, dict):
        return [item for child in value.values() for item in all_integers(child)]
    return []


def durable_json(path: Path, value: Any) -> None:
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary.exists():
            temporary.unlink()


def process_snapshot() -> dict[str, list[str]]:
    lines = subprocess.check_output(["ps", "-eo", "pid=,args="], text=True).splitlines()
    return {
        "gzserver": [line.strip() for line in lines if "gzserver" in line],
        "px4": [line.strip() for line in lines if "/px4" in line and "px4-rc" not in line],
        "controllers": [line.strip() for line in lines
                        if "ladrc_position_controller_node" in line],
        "micro_xrce_agent": [line.strip() for line in lines if "MicroXRCEAgent" in line],
    }


def parse_readiness(text: str) -> dict:
    values = [line for line in text.splitlines() if line.strip().startswith("{")]
    return json.loads(values[-1]) if values else {}


def diagnostic_topic_union(output: Path, env: dict[str, str]) -> dict[str, Any]:
    snapshots = []
    union: set[str] = set()
    for index in range(1, 6):
        observed = subprocess.run(
            ["ros2", "topic", "list"], cwd=WORKSPACE, env=env,
            text=True, capture_output=True, timeout=20,
        )
        names = sorted(set(observed.stdout.splitlines()))
        union.update(names)
        snapshots.append({
            "observation": index,
            "returncode": observed.returncode,
            "topics": names,
            "stderr": observed.stderr,
        })
        if index < 5:
            time.sleep(1.0)
    expected = {f"/px4_{uid}/fmu/out/vehicle_odometry" for uid in IDS}
    value = {
        "diagnostic_only": True,
        "observation_count": 5,
        "observation_interval_s": 1.0,
        "snapshots": snapshots,
        "union": sorted(union),
        "expected_vehicle_odometry_topics": sorted(expected),
        "union_has_all_expected_vehicle_odometry_topics": expected <= union,
    }
    durable_json(output / "dds_topic_discovery.json", value)
    return value


def diagnostic_model_queries(output: Path, env: dict[str, str]) -> dict[str, Any]:
    queries = []
    for uid in IDS:
        name = f"iris_{uid}"
        query = subprocess.run(
            ["gz", "model", "--model-name", name, "--info"],
            cwd=WORKSPACE, env=env, text=True, capture_output=True, timeout=10,
        )
        queries.append({
            "model": name,
            "returncode": query.returncode,
            "stdout": query.stdout,
            "stderr": query.stderr,
            "query_succeeded": query.returncode == 0,
        })
    value = {
        "diagnostic_only": True,
        "command_template": "gz model --model-name iris_<id> --info",
        "queries": queries,
        "successful_query_count": sum(item["query_succeeded"] for item in queries),
    }
    durable_json(output / "gazebo_model_queries.json", value)
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    protocol = yaml.safe_load(PROTOCOL.read_text())
    if protocol["smoke_id"] != SMOKE_ID or protocol["engineering_seed"]["value"] != SMOKE_SEED:
        raise SystemExit("v2 tool does not match frozen protocol")
    if tuple(protocol["core_checks"]) != CORE_CHECKS:
        raise SystemExit("v2 core checks do not match frozen protocol")
    if output.exists():
        raise SystemExit("v2 smoke output already exists; exactly one run is permitted")
    if output.parent.resolve() != RESULTS.resolve():
        raise SystemExit("v2 smoke output must be directly under results/formal_v4")
    if SMOKE_ID in registered_trial_ids():
        raise SystemExit("engineering v2 smoke ID unexpectedly matches formal registry")
    seed_hits = [str(path) for path in SEED_REGISTRIES
                 if SMOKE_SEED in all_integers(yaml.safe_load(path.read_text()))]
    if seed_hits:
        raise SystemExit(f"engineering v2 seed collides with registered seed: {seed_hits}")

    journal_before = sha256_file(JOURNAL)
    ledger_before = sha256_file(STORAGE_LEDGER)
    formal_attempts_before = sorted(path.name for path in (RESULTS / "attempts").iterdir())
    formal_contexts_before = sorted(path.name for path in (RESULTS / "contexts").iterdir())
    output.mkdir(parents=True)
    env = ros_environment(SMOKE_SEED)
    processes = []
    streams = []
    result: dict[str, Any] = {
        "schema": "E3_v4_post_slot105_infrastructure_smoke_v2",
        "smoke_id": SMOKE_ID,
        "protocol_sha256": sha256_file(PROTOCOL),
        "status": "FAIL",
        "dataset_class": "engineering_validation",
        "accepted_formal_result": False,
        "registered_formal_trial_id": None,
        "campaign_position": None,
        "formal_launch_authorized": False,
        "scientific_scene_executed": False,
        "scientific_interaction_executed": False,
        "rosbag_acquisition_started": False,
        "smoke_seed": SMOKE_SEED,
        "seed_registry_collision": False,
        "seed_registries_checked": [str(path.relative_to(REPO)) for path in SEED_REGISTRIES],
        "started_utc": utc_now(),
        "core_checks": {},
        "diagnostic_only": {},
    }
    try:
        clean_residuals()
        for name, command, cwd in (
            ("agent", ["MicroXRCEAgent", "udp4", "-p", "8888"], None),
            ("sitl", [
                "bash", str(PX4 / "Tools/simulation/gazebo-classic/sitl_multiple_run.sh"),
                "-n", "8", "-m", "iris", "-w", "empty",
            ], PX4),
        ):
            process, stream = start(command, output / f"{name}.log", cwd=cwd, env=env)
            processes.append(process)
            streams.append(stream)
        time.sleep(20)
        result["core_checks"]["px4_gazebo_launcher_alive_before_controllers"] = (
            processes[-1].poll() is None
        )
        if not result["core_checks"]["px4_gazebo_launcher_alive_before_controllers"]:
            raise RuntimeError("PX4/Gazebo launcher exited before controller startup")

        ids_arg = "[" + ",".join(map(str, IDS)) + "]"
        controller = [
            "ros2", "launch", "ladrc_controller", "swarm_launch.py",
            f"uav_ids:={ids_arg}", "control_mode:=ladrc_acceleration",
            "avoidance_mode:=off", "iapf_escape_mode:=id_order",
            "iapf_filter_alpha:=0.20", f"lfs_policy_file:={POLICY}",
        ]
        process, stream = start(controller, output / "controllers.log", cwd=WORKSPACE, env=env)
        processes.append(process)
        streams.append(stream)
        ready = subprocess.run(
            [str(VENV_PYTHON), str(READY), "--uav-ids", "1,2,3,4,5,6,7,8",
             "--timeout", "150"],
            cwd=WORKSPACE, env=env, text=True, capture_output=True, timeout=165,
        )
        (output / "readiness.log").write_text(ready.stdout + ready.stderr)
        readiness = parse_readiness(ready.stdout + ready.stderr)
        result["readiness"] = readiness
        diagnostics = readiness.get("diagnostics", {})
        values = list(diagnostics.values()) if set(diagnostics) == set(map(str, IDS)) else []
        result["core_checks"].update({
            "readiness_process_returned_zero": ready.returncode == 0,
            "readiness_reported_true": readiness.get("ready") is True,
            "readiness_uav_count_is_8": readiness.get("uav_count") == 8,
            "all_8_present": len(values) == 8 and all(item.get("present") is True for item in values),
            "all_8_fresh_under_existing_readiness_gate": len(values) == 8 and all(
                math.isfinite(float(item.get("age_s", float("nan"))))
                and float(item["age_s"]) <= 0.5 for item in values
            ),
            "all_8_system_ready": len(values) == 8 and all(
                item.get("system_ready") is True for item in values
            ),
            "all_8_armed": len(values) == 8 and all(item.get("armed") is True for item in values),
            "all_8_offboard": len(values) == 8 and all(item.get("offboard") is True for item in values),
            "all_8_failsafe_false": len(values) == 8 and all(
                item.get("failsafe") is False for item in values
            ),
            "all_8_finite_altitude": len(values) == 8 and all(
                math.isfinite(float(item.get("altitude", float("nan")))) for item in values
            ),
        })
        if ready.returncode:
            raise RuntimeError("frozen eight-UAV readiness utility failed")

        snapshot = process_snapshot()
        result["live_process_snapshot"] = snapshot
        result["core_checks"].update({
            "gazebo_master_alive": len(snapshot["gzserver"]) >= 1,
            "at_least_8_px4_processes_alive": len(snapshot["px4"]) >= 8,
            "at_least_8_controller_processes_alive": len(snapshot["controllers"]) >= 8,
            "micro_xrce_agent_alive": len(snapshot["micro_xrce_agent"]) >= 1,
        })
        result["diagnostic_only"]["dds_topic_discovery"] = diagnostic_topic_union(output, env)
        result["diagnostic_only"]["gazebo_model_introspection"] = diagnostic_model_queries(output, env)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        for process in reversed(processes):
            stop(process)
        for stream in streams:
            stream.close()
        clean_residuals()
        residual = process_snapshot()
        result["post_cleanup_process_snapshot"] = residual
        result["core_checks"]["residual_simulator_controller_processes_absent"] = not any(
            residual[name] for name in ("gzserver", "px4", "controllers", "micro_xrce_agent")
        )
        result["journal_sha256_before"] = journal_before
        result["journal_sha256_after"] = sha256_file(JOURNAL)
        result["raw_storage_ledger_sha256_before"] = ledger_before
        result["raw_storage_ledger_sha256_after"] = sha256_file(STORAGE_LEDGER)
        result["core_checks"].update({
            "campaign_journal_unchanged": result["journal_sha256_after"] == journal_before,
            "raw_storage_ledger_unchanged": result["raw_storage_ledger_sha256_after"] == ledger_before,
            "formal_attempt_directories_unchanged": formal_attempts_before == sorted(
                path.name for path in (RESULTS / "attempts").iterdir()
            ),
            "formal_contexts_unchanged": formal_contexts_before == sorted(
                path.name for path in (RESULTS / "contexts").iterdir()
            ),
        })
        missing = [name for name in CORE_CHECKS if name not in result["core_checks"]]
        result["missing_core_checks"] = missing
        result["status"] = "PASS" if not missing and all(
            result["core_checks"][name] is True for name in CORE_CHECKS
        ) else "FAIL"
        result["finished_utc"] = utc_now()
        durable_json(output / "smoke_result.json", result)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
