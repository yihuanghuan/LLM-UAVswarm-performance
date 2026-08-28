"""Fail-closed observation of the deployed E5 controller runtime.

This module only observes installed artifacts and the ROS graph.  It does not
publish commands or alter controller, allocator, trajectory, or timing policy
state.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import subprocess
import time
from typing import Any, Dict, Iterable


SOURCE_PREFLIGHT = "36dba68c6b16681ec98500b49c5a83095de4b634"
EXPECTED_CONTROLLER_NODE = "ladrc_position_controller"
CONTROLLER_LAUNCH = "minisnap_LADRC/ladrc_controller/launch/swarm_launch.py"
POLICY_RELATIVE = "lfs_policy/config/lfs_policy.paper_current.yaml"
POLICY_SHA256 = "6b47d27f4253d7311e79ea51f6dd1cf0d0182e6df24374a94abae0aa6a135858"
DISCOVERY_MAX_ATTEMPTS = 4
DISCOVERY_RETRY_INTERVAL_S = 1.0
FORMAL_INSTALL = Path("/home/yihuang/learning/LLM_swarm_ws/formal_install_v1")
FORMAL_PX4 = Path("/home/yihuang/PX4-Autopilot-formal-v1")


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _run(command, *, env: Dict[str, str], cwd: Path) -> Dict[str, Any]:
    started = datetime.now(timezone.utc).isoformat()
    completed = subprocess.run(
        command, env=env, cwd=cwd, text=True, capture_output=True, timeout=20,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "started_at_utc": started,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def _controller_observation(repo: Path, env: Dict[str, str], uav_id: int,
                            sequence: int) -> Dict[str, Any]:
    namespace = f"/uav{uav_id}"
    node = f"{namespace}/{EXPECTED_CONTROLLER_NODE}"
    topic = f"{namespace}/execution_command"
    node_info = _run(["ros2", "node", "info", node], env=env, cwd=repo)
    parameter = _run(
        ["ros2", "param", "get", node, "enable_execution_profiles"],
        env=env, cwd=repo,
    )
    topic_info = _run(["ros2", "topic", "info", "-v", topic], env=env, cwd=repo)
    subscription = node_info["returncode"] == 0 and topic in node_info["stdout"]
    endpoint = (
        topic_info["returncode"] == 0
        and f"Node name: {EXPECTED_CONTROLLER_NODE}" in topic_info["stdout"]
        and f"Node namespace: {namespace}" in topic_info["stdout"]
    )
    profiles = parameter["returncode"] == 0 and "True" in parameter["stdout"]
    return {
        "sequence": sequence,
        "node": node,
        "execution_command_topic": topic,
        "node_info": node_info,
        "enable_execution_profiles": parameter,
        "topic_info_verbose": topic_info,
        "node_subscription_present": subscription,
        "controller_endpoint_present_in_topic_info": endpoint,
        "enable_execution_profiles_true": profiles,
        "observation_pass": subscription and endpoint and profiles,
    }


def collect_controller_runtime_evidence(
    repo: Path, env: Dict[str, str], uav_ids: Iterable[int], *,
    max_attempts: int = DISCOVERY_MAX_ATTEMPTS,
    retry_interval_s: float = DISCOVERY_RETRY_INTERVAL_S,
) -> Dict[str, Any]:
    ids = [int(value) for value in uav_ids]
    if max_attempts < 1 or retry_interval_s < 0:
        raise ValueError("invalid discovery stabilization bounds")
    attempts = {str(uid): [] for uid in ids}
    pending = set(ids)
    for sequence in range(1, max_attempts + 1):
        for uid in ids:
            if uid not in pending:
                continue
            observation = _controller_observation(repo, env, uid, sequence)
            attempts[str(uid)].append(observation)
            if observation["observation_pass"]:
                pending.remove(uid)
        if not pending:
            break
        if sequence < max_attempts and retry_interval_s:
            time.sleep(retry_interval_s)
    result = {}
    for uid in ids:
        records = attempts[str(uid)]
        selected = next((item for item in records if item["observation_pass"]), records[-1])
        result[str(uid)] = {
            **{key: selected[key] for key in (
                "node", "execution_command_topic", "node_info",
                "enable_execution_profiles", "topic_info_verbose",
                "node_subscription_present", "controller_endpoint_present_in_topic_info",
                "enable_execution_profiles_true",
            )},
            "discovery_converged": selected["observation_pass"],
            "selected_observation_sequence": selected["sequence"],
            "observation_count": len(records),
            "observation_attempts": records,
            "stabilization_bounds": {
                "max_attempts": max_attempts,
                "retry_interval_s": retry_interval_s,
            },
        }
    return result


def collect_runtime_provenance(repo: Path, env: Dict[str, str],
                               uav_ids: Iterable[int]) -> Dict[str, Any]:
    repo = Path(repo).resolve()
    prefixes = {}
    prefix_commands = {}
    for package in ("ladrc_controller", "uav_swarm_interfaces", "lfs_policy"):
        command = _run(["ros2", "pkg", "prefix", package], env=env, cwd=repo)
        prefix_commands[package] = command
        prefixes[package] = Path(command["stdout"].strip()).resolve() if command["returncode"] == 0 else Path("/")
    launch = prefixes["ladrc_controller"] / "share/ladrc_controller/launch/swarm_launch.py"
    policy = prefixes["lfs_policy"] / "share/lfs_policy/config/lfs_policy.paper_current.yaml"
    executable = prefixes["ladrc_controller"] / "lib/ladrc_controller/ladrc_position_controller_node"
    px4_binary = FORMAL_PX4 / "build/px4_sitl_default/bin/px4"
    jinja = _run(["/usr/bin/python3", "-c", "import jinja2"], env=env, cwd=repo)
    source_launch = subprocess.run(
        ["git", "show", f"{SOURCE_PREFLIGHT}:{CONTROLLER_LAUNCH}"], cwd=repo,
        check=True, capture_output=True,
    ).stdout
    source_policy = subprocess.run(
        ["git", "show", f"{SOURCE_PREFLIGHT}:{POLICY_RELATIVE}"], cwd=repo,
        check=True, capture_output=True,
    ).stdout
    dynamic = collect_controller_runtime_evidence(repo, env, uav_ids)
    checks = {
        "package_prefixes_are_formal_install_v1": all(
            path.is_relative_to(FORMAL_INSTALL) for path in prefixes.values()
        ),
        "installed_launch_matches_frozen_source": launch.is_file()
            and hashlib.sha256(source_launch).hexdigest() == _sha256(launch),
        "installed_policy_matches_frozen_source": policy.is_file()
            and hashlib.sha256(source_policy).hexdigest() == _sha256(policy),
        "installed_policy_hash_matches": policy.is_file() and _sha256(policy) == POLICY_SHA256,
        "installed_controller_binary_exists": executable.resolve().is_file(),
        "formal_px4_binary_exists": px4_binary.is_file(),
        "px4_sdf_generator_python_ready": jinja["returncode"] == 0,
        "every_controller_node_subscribes": all(
            item["node_subscription_present"] for item in dynamic.values()
        ),
        "every_controller_endpoint_visible": all(
            item["controller_endpoint_present_in_topic_info"] for item in dynamic.values()
        ),
        "execution_profiles_enabled_for_every_controller": all(
            item["enable_execution_profiles_true"] for item in dynamic.values()
        ),
    }
    return {
        "manifest_type": "E5_runtime_provenance_v1",
        "change_classification": "instrumentation_or_provenance_only",
        "scientific_semantics_changed": False,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "package_prefixes": {key: str(value) for key, value in prefixes.items()},
        "package_prefix_commands": prefix_commands,
        "installed_launch": {"path": str(launch), "sha256": _sha256(launch) if launch.is_file() else None},
        "installed_policy": {"path": str(policy), "sha256": _sha256(policy) if policy.is_file() else None},
        "installed_controller": {"path": str(executable.resolve()), "exists": executable.resolve().is_file()},
        "formal_px4_binary": {
            "path": str(px4_binary),
            "sha256": _sha256(px4_binary) if px4_binary.is_file() else None,
        },
        "px4_sdf_generator_python": jinja,
        "dynamic_runtime_checks": dynamic,
        "checks": checks,
    }


def runtime_provenance_gate(report: Dict[str, Any]) -> bool:
    checks = report.get("checks", {})
    return report.get("status") == "PASS" and bool(checks) and all(checks.values())
