#!/usr/bin/env python3
"""Run one non-formal 8-UAV startup/readiness smoke after formal slot 105."""

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


SMOKE_ID = "E3-V4-INFRASTRUCTURE-SMOKE-AFTER-SLOT105-v1"
SMOKE_SEED = 8105105
IDS = list(range(1, 9))
E3 = Path(__file__).resolve().parent.parent
RESULTS = E3 / "results/formal_v4"
JOURNAL = RESULTS / "campaign_journal.jsonl"
STORAGE_LEDGER = RESULTS / "raw_archive_ledger.jsonl"
SEED_REGISTRIES = (
    E3 / "E3_v4_formal_paired_seeds.yaml",
    E3 / "E3_v4_qualification_seeds.yaml",
    E3 / "E3_v4_B02_holdout_qualification_seeds.yaml",
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
    lines = subprocess.check_output(
        ["ps", "-eo", "pid=,args="], text=True
    ).splitlines()
    return {
        "gzserver": [line.strip() for line in lines if "gzserver" in line],
        "px4": [line.strip() for line in lines
                if "/px4" in line and "px4-rc" not in line],
        "controllers": [line.strip() for line in lines
                        if "ladrc_position_controller_node" in line],
        "micro_xrce_agent": [line.strip() for line in lines
                             if "MicroXRCEAgent" in line],
    }


def parse_readiness(text: str) -> dict:
    values = [line for line in text.splitlines() if line.strip().startswith("{")]
    if not values:
        return {}
    return json.loads(values[-1])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit("smoke output already exists; exactly one run is permitted")
    if output.parent.resolve() != RESULTS.resolve():
        raise SystemExit("smoke output must be directly under results/formal_v4")
    if SMOKE_ID in registered_trial_ids():
        raise SystemExit("engineering smoke ID unexpectedly matches formal registry")
    seed_hits = []
    for registry in SEED_REGISTRIES:
        if SMOKE_SEED in all_integers(yaml.safe_load(registry.read_text())):
            seed_hits.append(str(registry))
    if seed_hits:
        raise SystemExit(f"engineering seed collides with registered seed: {seed_hits}")

    journal_before = sha256_file(JOURNAL)
    ledger_before = sha256_file(STORAGE_LEDGER)
    formal_attempts_before = sorted(path.name for path in (RESULTS / "attempts").iterdir())
    formal_contexts_before = sorted(path.name for path in (RESULTS / "contexts").iterdir())
    output.mkdir(parents=True)
    env = ros_environment(SMOKE_SEED)
    processes = []
    streams = []
    result: dict[str, Any] = {
        "schema": "E3_v4_post_slot105_infrastructure_smoke_v1",
        "smoke_id": SMOKE_ID,
        "status": "FAIL",
        "dataset_class": "engineering_validation",
        "accepted_formal_result": False,
        "registered_formal_trial_id": None,
        "campaign_position": None,
        "formal_launch_authorized": False,
        "scientific_scene_executed": False,
        "scientific_interaction_executed": False,
        "smoke_seed": SMOKE_SEED,
        "seed_registry_collision": False,
        "seed_registries_checked": [str(path.relative_to(REPO)) for path in SEED_REGISTRIES],
        "started_utc": utc_now(),
        "checks": {},
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
        result["checks"]["px4_gazebo_launcher_alive_before_controllers"] = (
            processes[-1].poll() is None
        )
        if not result["checks"]["px4_gazebo_launcher_alive_before_controllers"]:
            raise RuntimeError("PX4/Gazebo launcher exited before controller startup")

        ids_arg = "[" + ",".join(map(str, IDS)) + "]"
        controller = [
            "ros2", "launch", "ladrc_controller", "swarm_launch.py",
            f"uav_ids:={ids_arg}", "control_mode:=ladrc_acceleration",
            "avoidance_mode:=off", "iapf_escape_mode:=id_order",
            "iapf_filter_alpha:=0.20", f"lfs_policy_file:={POLICY}",
        ]
        process, stream = start(
            controller, output / "controllers.log", cwd=WORKSPACE, env=env
        )
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
        result["checks"].update({
            "readiness_process_returned_zero": ready.returncode == 0,
            "readiness_reported_true": readiness.get("ready") is True,
            "readiness_uav_count_is_8": readiness.get("uav_count") == 8,
            "all_8_system_ready": len(diagnostics) == 8 and all(
                item.get("system_ready") is True for item in diagnostics.values()
            ),
            "all_8_valid_odometry_altitudes": len(diagnostics) == 8 and all(
                math.isfinite(float(item.get("altitude", float("nan"))))
                for item in diagnostics.values()
            ),
        })
        if ready.returncode:
            raise RuntimeError("8-UAV readiness smoke failed")

        topics = subprocess.run(
            ["ros2", "topic", "list"], cwd=WORKSPACE, env=env,
            text=True, capture_output=True, timeout=20,
        )
        (output / "ros_topics.log").write_text(topics.stdout + topics.stderr)
        topic_set = set(topics.stdout.splitlines())
        odometry_topics = {
            f"/px4_{uid}/fmu/out/vehicle_odometry" for uid in IDS
        }
        result["checks"]["all_8_vehicle_odometry_topics_present"] = (
            topics.returncode == 0 and odometry_topics <= topic_set
        )

        models = subprocess.run(
            ["gz", "model", "--list"], cwd=WORKSPACE, env=env,
            text=True, capture_output=True, timeout=20,
        )
        (output / "gazebo_models.log").write_text(models.stdout + models.stderr)
        model_lines = [line.strip() for line in models.stdout.splitlines() if line.strip()]
        iris_models = [line for line in model_lines if "iris" in line.lower()]
        result["checks"]["gazebo_model_query_succeeded"] = models.returncode == 0
        result["checks"]["at_least_8_iris_models_present"] = len(iris_models) >= 8
        result["gazebo_models"] = model_lines

        snapshot = process_snapshot()
        result["live_process_snapshot"] = snapshot
        result["checks"].update({
            "gazebo_master_alive": len(snapshot["gzserver"]) >= 1,
            "at_least_8_px4_processes_alive": len(snapshot["px4"]) >= 8,
            "at_least_8_controller_processes_alive": len(snapshot["controllers"]) >= 8,
            "micro_xrce_agent_alive": len(snapshot["micro_xrce_agent"]) >= 1,
        })
        result["status"] = "PASS" if all(result["checks"].values()) else "FAIL"
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
        result["checks"]["residual_simulator_controller_processes_absent"] = not any(
            residual[name] for name in ("gzserver", "px4", "controllers", "micro_xrce_agent")
        )
        result["journal_sha256_before"] = journal_before
        result["journal_sha256_after"] = sha256_file(JOURNAL)
        result["storage_ledger_sha256_before"] = ledger_before
        result["storage_ledger_sha256_after"] = sha256_file(STORAGE_LEDGER)
        result["checks"]["campaign_journal_unchanged"] = (
            result["journal_sha256_after"] == journal_before
        )
        result["checks"]["raw_storage_ledger_unchanged_by_smoke"] = (
            result["storage_ledger_sha256_after"] == ledger_before
        )
        result["checks"]["formal_attempt_directories_unchanged"] = (
            formal_attempts_before == sorted(
                path.name for path in (RESULTS / "attempts").iterdir()
            )
        )
        result["checks"]["formal_contexts_unchanged"] = (
            formal_contexts_before == sorted(
                path.name for path in (RESULTS / "contexts").iterdir()
            )
        )
        if not all(result["checks"].values()):
            result["status"] = "FAIL"
        result["finished_utc"] = utc_now()
        durable_json(output / "smoke_result.json", result)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
