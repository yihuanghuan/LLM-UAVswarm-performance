#!/usr/bin/env python3
"""Execute exactly one C0-A v3 schedule entry from a full cold start."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import time


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parents[2]
WORKSPACE = REPOSITORY.parents[1]
PX4 = Path("/home/yihuang/PX4-Autopilot")
VENV_PYTHON = WORKSPACE / "llm_env" / "bin" / "python"
RENDER = ROOT / "scripts" / "render_trial.py"
DRIVER = ROOT / "scripts" / "trial_driver.py"
RESOURCE_MONITOR = ROOT / "scripts" / "resource_monitor.py"
READINESS = REPOSITORY / "experiments" / "system_8uav" / "scripts" / "wait_swarm_ready.py"
LAUNCH = ROOT / "scripts" / "c0a_controller_launch.py"
SITL = PX4 / "Tools" / "simulation" / "gazebo-classic" / "sitl_multiple_run.sh"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ros_environment():
    command = (
        "source /opt/ros/humble/setup.bash && "
        f"source {WORKSPACE}/install/setup.bash && env -0"
    )
    result = subprocess.run(
        ["bash", "-lc", command], stdout=subprocess.PIPE, check=True
    )
    environment = {}
    for item in result.stdout.split(b"\0"):
        if b"=" in item:
            key, value = item.split(b"=", 1)
            environment[key.decode()] = value.decode()
    return environment


def start(command, log_path, *, cwd=None, env=None):
    log = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        text=True,
    )
    return process, log


def stop(process, *, timeout=20.0):
    if process is None or process.poll() is not None:
        return None if process is None else process.returncode
    os.killpg(process.pid, signal.SIGINT)
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
    try:
        return process.wait(timeout=10.0)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        return process.wait(timeout=5.0)


def residual_pids():
    result = subprocess.run(
        ["pgrep", "-a", "-f", "(^|/)(px4|gzserver|gzclient|MicroXRCEAgent|ladrc_position_controller_node)( |$)"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.stdout.strip().splitlines() if result.stdout.strip() else []


def cleanup_residuals():
    patterns = (
        "(^|/)px4( |$)",
        "(^|/)gzserver( |$)",
        "(^|/)gzclient( |$)",
        "(^|/)MicroXRCEAgent( |$)",
        "(^|/)ladrc_position_controller_node( |$)",
    )
    before = residual_pids()
    for signal_name in ("INT", "TERM"):
        for pattern in patterns:
            subprocess.run(
                ["pkill", f"-{signal_name}", "-f", pattern],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        time.sleep(2.0)
        if not residual_pids():
            break
    after = residual_pids()
    if after:
        raise RuntimeError(f"residual processes after cleanup: {after}")
    return before


def sitl_spawn_script(spec):
    if spec["layout"] == "single_origin":
        return "iris:1:0:0"
    return ",".join(
        f"iris:1:-4:{3 * uid}" for uid in spec["uav_ids"]
    )


def bag_topics(spec):
    topics = []
    for uid in spec["uav_ids"]:
        topics.extend((
            f"/uav{uid}/status",
            f"/uav{uid}/startup_event",
            f"/uav{uid}/execution_command",
            f"/uav{uid}/trajectory_metrics",
            f"/uav{uid}/control_adaptation",
            f"/uav{uid}/control_tracking_debug",
            f"/uav{uid}/iapf_debug",
            f"/uav{uid}/swarm_state",
            f"/px4_{uid}/fmu/out/vehicle_status",
            f"/px4_{uid}/fmu/out/vehicle_odometry",
            f"/px4_{uid}/fmu/out/vehicle_attitude",
        ))
    return topics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial-id", required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()
    trial_dir = args.artifact_root.resolve() / "raw" / args.trial_id
    ros_env = ros_environment()
    render = subprocess.run(
        [
            str(VENV_PYTHON), str(RENDER),
            "--trial-id", args.trial_id,
            "--state", str(args.state.resolve()),
            "--output", str(trial_dir),
        ],
        cwd=REPOSITORY,
        env=ros_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if render.returncode != 0:
        raise SystemExit(render.stdout)
    spec = json.loads((trial_dir / "trial_spec.json").read_text(encoding="utf-8"))
    manifest = {
        **{key: spec[key] for key in (
            "calibration_id", "protocol_version", "dataset_class", "control_mode",
            "motion_style", "policy_configuration_id", "policy_sha256",
            "controller_config_sha256",
        )},
        "trial_id": args.trial_id,
        "stage": spec["entry"]["stage"],
        "candidate_id": spec["entry"]["candidate_id"],
        "scenario_id": spec["entry"]["scenario_id"],
        "signed_displacement_id": spec["entry"]["signed_displacement_id"],
        "seed": spec["entry"]["seed"],
        "repetition": spec["entry"]["repetition"],
        "duration_condition": spec["entry"]["duration_condition"],
        "explicit_duration_s": spec["explicit_duration_s"],
        "cold_start": True,
        "success": False,
        "termination_reason": "STARTUP_FAILED",
        "started_utc": utc_now(),
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPOSITORY, text=True
        ).strip(),
        "branch": subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=REPOSITORY, text=True
        ).strip(),
        "paper_algorithm_freeze_tag": "paper-algorithm-freeze-v1",
        "paper_algorithm_freeze_commit": "56e8d2c8e59fc3513769e21910b7a20b2b43088d",
        "host": platform.node(),
        "platform": platform.platform(),
        "seed_support": spec["seed_support"],
        "commands": {},
        "process_exit_status": {},
    }
    processes = {name: None for name in ("agent", "sitl", "controllers", "bag", "resource")}
    logs = []
    try:
        manifest["residual_processes_cleaned"] = cleanup_residuals()
        agent_command = ["MicroXRCEAgent", "udp4", "-p", "8888"]
        manifest["commands"]["agent"] = agent_command
        processes["agent"], log = start(agent_command, trial_dir / "agent.log", env=ros_env)
        logs.append(log)

        sitl_command = ["bash", str(SITL), "-s", sitl_spawn_script(spec), "-m", "iris"]
        manifest["commands"]["sitl"] = sitl_command
        processes["sitl"], log = start(
            sitl_command, trial_dir / "sitl.log", cwd=PX4, env=ros_env
        )
        logs.append(log)
        time.sleep(10.0)
        if processes["sitl"].poll() is not None:
            raise RuntimeError("PX4/Gazebo exited during startup")

        ids_arg = "[" + ",".join(str(value) for value in spec["uav_ids"]) + "]"
        controller_command = [
            "ros2", "launch", str(LAUNCH),
            f"uav_ids:={ids_arg}",
            f"layout:={spec['layout']}",
            f"lfs_policy_file:={spec['policy_path']}",
            f"params_file:={spec['controller_params_path']}",
        ]
        manifest["commands"]["controllers"] = controller_command
        processes["controllers"], log = start(
            controller_command, trial_dir / "controllers.log", cwd=WORKSPACE, env=ros_env
        )
        logs.append(log)
        readiness_command = [
            str(VENV_PYTHON), str(READINESS),
            "--uav-ids", ",".join(str(value) for value in spec["uav_ids"]),
            "--timeout", "60",
        ]
        manifest["commands"]["readiness"] = readiness_command
        readiness = subprocess.run(
            readiness_command,
            cwd=REPOSITORY,
            env=ros_env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=65,
            check=False,
        )
        (trial_dir / "readiness.log").write_text(readiness.stdout, encoding="utf-8")
        if readiness.returncode != 0:
            raise RuntimeError("startup did not reach READY within 60 s")
        ready_monotonic = time.monotonic()
        manifest["ready_utc"] = utc_now()

        bag_command = [
            "ros2", "bag", "record", "-o", str(trial_dir / "rosbag"),
            *bag_topics(spec),
        ]
        manifest["commands"]["rosbag"] = bag_command
        processes["bag"], log = start(
            bag_command, trial_dir / "rosbag.log", cwd=WORKSPACE, env=ros_env
        )
        logs.append(log)
        resource_command = [
            str(VENV_PYTHON), str(RESOURCE_MONITOR),
            "--output", str(trial_dir / "resources.csv"),
        ]
        processes["resource"], log = start(
            resource_command, trial_dir / "resource_monitor.log", env=ros_env
        )
        logs.append(log)
        time.sleep(2.0)
        if processes["bag"].poll() is not None:
            raise RuntimeError("rosbag exited before command")

        wall_deadline = ready_monotonic + 120.0
        remaining = max(0.0, wall_deadline - time.monotonic())
        driver_command = [
            str(VENV_PYTHON), str(DRIVER),
            "--spec", str(trial_dir / "trial_spec.json"),
            "--output", str(trial_dir / "driver_result.json"),
            "--wall-deadline-monotonic", str(wall_deadline),
        ]
        manifest["commands"]["driver"] = driver_command
        driver = subprocess.run(
            driver_command,
            cwd=REPOSITORY,
            env=ros_env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=remaining + 10.0,
            check=False,
        )
        (trial_dir / "driver.log").write_text(driver.stdout, encoding="utf-8")
        driver_result = json.loads((trial_dir / "driver_result.json").read_text(encoding="utf-8"))
        manifest["driver_returncode"] = driver.returncode
        manifest["driver_result"] = driver_result
        manifest["success"] = driver.returncode == 0 and driver_result["success"]
        manifest["termination_reason"] = driver_result["termination_reason"]
    except subprocess.TimeoutExpired as error:
        manifest["termination_reason"] = "TIMEOUT"
        manifest["error"] = f"{type(error).__name__}: {error}"
    except Exception as error:
        manifest["error"] = f"{type(error).__name__}: {error}"
        if "READY" in str(error):
            manifest["termination_reason"] = "STARTUP_FAILED"
        elif "rosbag" in str(error):
            manifest["termination_reason"] = "MANDATORY_TOPIC_MISSING"
        elif "PX4/Gazebo" in str(error):
            manifest["termination_reason"] = "PROCESS_CRASH"
        else:
            manifest["termination_reason"] = "INFRASTRUCTURE_ERROR"
    finally:
        for name, timeout in (
            ("bag", 20.0), ("resource", 5.0), ("controllers", 20.0),
            ("sitl", 25.0), ("agent", 10.0),
        ):
            manifest["process_exit_status"][name] = stop(processes[name], timeout=timeout)
        for log in logs:
            log.close()
        try:
            manifest["residual_processes_after"] = cleanup_residuals()
        except Exception as error:
            manifest["cleanup_error"] = f"{type(error).__name__}: {error}"
            manifest["success"] = False
            manifest["termination_reason"] = "PROCESS_CLEANUP_FAILED"
        bag_metadata = trial_dir / "rosbag" / "metadata.yaml"
        manifest["rosbag"] = {
            "path": str((trial_dir / "rosbag").resolve()),
            "metadata_present": bag_metadata.is_file(),
        }
        if bag_metadata.is_file():
            files = sorted(path for path in (trial_dir / "rosbag").iterdir() if path.is_file())
            manifest["rosbag"]["files"] = [
                {"path": str(path.resolve()), "size": path.stat().st_size, "sha256": sha256(path)}
                for path in files
            ]
        manifest["finished_utc"] = utc_now()
        (trial_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(json.dumps({
        "trial_id": args.trial_id,
        "success": manifest["success"],
        "termination_reason": manifest["termination_reason"],
        "trial_dir": str(trial_dir),
    }, sort_keys=True))
    return 0 if manifest["success"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
