"""E3-only deployment and exact command-handoff diagnostics.

This module observes the frozen runtime.  It does not alter controller,
allocator, resolver, policy, command, or experiment semantics.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import time
from typing import Any, Dict, Iterable


SOURCE_PREFLIGHT = "36dba68c6b16681ec98500b49c5a83095de4b634"
EXPECTED_CONTROLLER_NODE = "ladrc_position_controller"
EXPECTED_RECORDER_NODE = "rosbag2_recorder"
CONTROLLER_SOURCE = "minisnap_LADRC/ladrc_controller/src/ladrc_position_controller_node.cpp"
CONTROLLER_LAUNCH = "minisnap_LADRC/ladrc_controller/launch/swarm_launch.py"
POLICY_RELATIVE = "lfs_policy/config/lfs_policy.paper_current.yaml"
POLICY_SHA256 = "6b47d27f4253d7311e79ea51f6dd1cf0d0182e6df24374a94abae0aa6a135858"
DISCOVERY_MAX_ATTEMPTS = 4
DISCOVERY_RETRY_INTERVAL_S = 1.0


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def expected_controller_namespace(uav_id: int) -> str:
    return f"/uav{int(uav_id)}"


def expected_wrench_topic(uav_id: int) -> str:
    """Frozen sitl_multiple mapping: UAV N -> MAV_SYS_ID N+1."""
    return f"/e3_force/mavlink_{int(uav_id) + 1}/wrench"


def _enum(value: Any) -> str:
    return getattr(value, "name", str(value))


def _qos(qos: Any) -> Dict[str, Any]:
    result = {}
    for field in ("reliability", "durability", "history", "depth", "liveliness"):
        if hasattr(qos, field):
            result[field] = _enum(getattr(qos, field))
    return result


def endpoint_record(endpoint: Any) -> Dict[str, Any]:
    return {
        "node_name": endpoint.node_name,
        "node_namespace": endpoint.node_namespace,
        "topic_type": endpoint.topic_type,
        "endpoint_type": _enum(endpoint.endpoint_type),
        "qos": _qos(endpoint.qos_profile),
    }


def is_expected_controller_endpoint(endpoint: Any, uav_id: int) -> bool:
    return (
        endpoint.node_namespace == expected_controller_namespace(uav_id)
        and endpoint.node_name == EXPECTED_CONTROLLER_NODE
    )


def is_expected_recorder_endpoint(endpoint: Any) -> bool:
    return endpoint.node_namespace == "/" and endpoint.node_name == EXPECTED_RECORDER_NODE


def endpoint_snapshot(node: Any, publisher: Any, topic: str, uav_id: int) -> Dict[str, Any]:
    subscriptions = node.get_subscriptions_info_by_topic(topic)
    publishers = node.get_publishers_info_by_topic(topic)
    return {
        "topic": topic,
        "publisher_endpoint": [endpoint_record(item) for item in publishers],
        "all_subscription_endpoints": [endpoint_record(item) for item in subscriptions],
        "publisher_reported_subscription_count": publisher.get_subscription_count(),
        "expected_controller_node_name": EXPECTED_CONTROLLER_NODE,
        "expected_controller_node_namespace": expected_controller_namespace(uav_id),
        "controller_endpoint_present": any(
            is_expected_controller_endpoint(item, uav_id) for item in subscriptions
        ),
        "recorder_endpoint_present": any(
            is_expected_recorder_endpoint(item) for item in subscriptions
        ),
    }


def _finite_positive(values: Iterable[float]) -> bool:
    return all(math.isfinite(float(value)) and float(value) > 0.0 for value in values)


def validate_command(command: Any, expected_uav_id: int) -> Dict[str, Any]:
    profile = command.profile
    target = [command.target_pos.x, command.target_pos.y, command.target_pos.z]
    scalar_positive = [
        profile.duration, profile.velocity_limit, profile.acceleration_limit,
        profile.jerk_limit, profile.iapf_enter_distance, profile.iapf_exit_distance,
        profile.style_gain, profile.task_gain,
    ]
    checks = {
        "uav_id_matches": int(command.uav_id) == int(expected_uav_id),
        "target_is_finite": all(math.isfinite(float(value)) for value in target),
        "style_present": bool(profile.style),
        "configuration_id_present": bool(profile.configuration_id),
        "positive_finite_scalars": _finite_positive(scalar_positive),
        "omega_c_positive_finite": _finite_positive(profile.omega_c),
        "omega_o_positive_finite": _finite_positive(profile.omega_o),
        "iapf_repulsion_valid": math.isfinite(float(profile.iapf_repulsion_scale))
            and float(profile.iapf_repulsion_scale) >= 0.0,
        "iapf_hysteresis_valid": float(profile.iapf_exit_distance) >
            float(profile.iapf_enter_distance),
    }
    return {
        "uav_id": int(command.uav_id),
        "mission_id": int(command.mission_id),
        "target": target,
        "profile": {
            "duration": float(profile.duration), "style": profile.style,
            "configuration_id": profile.configuration_id,
            "omega_c": [float(value) for value in profile.omega_c],
            "omega_o": [float(value) for value in profile.omega_o],
            "velocity_limit": float(profile.velocity_limit),
            "acceleration_limit": float(profile.acceleration_limit),
            "jerk_limit": float(profile.jerk_limit),
            "iapf_enter_distance": float(profile.iapf_enter_distance),
            "iapf_exit_distance": float(profile.iapf_exit_distance),
            "iapf_repulsion_scale": float(profile.iapf_repulsion_scale),
            "style_gain": float(profile.style_gain), "task_gain": float(profile.task_gain),
        },
        "frozen_controller_metadata_guard_checks": checks,
        "frozen_controller_metadata_guard_pass": all(checks.values()),
    }


def _run(command, *, env, cwd) -> Dict[str, Any]:
    started_at_utc = datetime.now(timezone.utc).isoformat()
    completed = subprocess.run(
        command, env=env, cwd=cwd, text=True, capture_output=True, timeout=20,
    )
    return {
        "command": command, "returncode": completed.returncode,
        "stdout": completed.stdout, "stderr": completed.stderr,
        "started_at_utc": started_at_utc,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def _prefix(package: str, *, env, cwd: Path) -> tuple[Path, Dict[str, Any]]:
    result = _run(["ros2", "pkg", "prefix", package], env=env, cwd=cwd)
    if result["returncode"]:
        raise RuntimeError(f"ros2 pkg prefix failed for {package}")
    return Path(result["stdout"].strip()).resolve(), result


def _controller_observation(repo: Path, env: Dict[str, str], uav_id: int,
                            sequence: int) -> Dict[str, Any]:
    namespace = expected_controller_namespace(uav_id)
    full_node = f"{namespace}/{EXPECTED_CONTROLLER_NODE}"
    topic = f"{namespace}/execution_command"
    started_at_utc = datetime.now(timezone.utc).isoformat()
    node_info = _run(["ros2", "node", "info", full_node], env=env, cwd=repo)
    parameter = _run(
        ["ros2", "param", "get", full_node, "enable_execution_profiles"],
        env=env, cwd=repo,
    )
    topic_info = _run(["ros2", "topic", "info", "-v", topic], env=env, cwd=repo)
    node_subscription_present = (
        node_info["returncode"] == 0 and topic in node_info["stdout"]
    )
    controller_endpoint_present = (
        topic_info["returncode"] == 0
        and f"Node name: {EXPECTED_CONTROLLER_NODE}" in topic_info["stdout"]
        and f"Node namespace: {namespace}" in topic_info["stdout"]
    )
    execution_profiles_enabled = (
        parameter["returncode"] == 0 and "True" in parameter["stdout"]
    )
    return {
        "sequence": sequence,
        "started_at_utc": started_at_utc,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "node_info": node_info,
        "enable_execution_profiles": parameter,
        "topic_info_verbose": topic_info,
        "node_subscription_present": node_subscription_present,
        "controller_endpoint_present_in_topic_info": controller_endpoint_present,
        "enable_execution_profiles_true": execution_profiles_enabled,
        "observation_pass": (
            node_subscription_present
            and controller_endpoint_present
            and execution_profiles_enabled
        ),
    }


def collect_controller_runtime_evidence(
    repo: Path,
    env: Dict[str, str],
    uav_ids: Iterable[int],
    *,
    max_attempts: int = DISCOVERY_MAX_ATTEMPTS,
    retry_interval_s: float = DISCOVERY_RETRY_INTERVAL_S,
) -> Dict[str, Any]:
    """Observe the frozen controller invariant through a bounded retry window.

    Each attempt must jointly establish node subscription, topic endpoint identity,
    and the enabled execution-profile parameter. Every raw failed and successful
    attempt is retained. A controller that never establishes all three facts remains
    a fail-closed provenance failure.
    """
    ids = [int(value) for value in uav_ids]
    if max_attempts < 1 or retry_interval_s < 0.0:
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

    dynamic = {}
    for uid in ids:
        records = attempts[str(uid)]
        selected = next(
            (item for item in records if item["observation_pass"]), records[-1]
        )
        dynamic[str(uid)] = {
            "node": f"{expected_controller_namespace(uid)}/{EXPECTED_CONTROLLER_NODE}",
            "execution_command_topic": f"{expected_controller_namespace(uid)}/execution_command",
            "node_info": selected["node_info"],
            "enable_execution_profiles": selected["enable_execution_profiles"],
            "topic_info_verbose": selected["topic_info_verbose"],
            "node_subscription_present": selected["node_subscription_present"],
            "controller_endpoint_present_in_topic_info":
                selected["controller_endpoint_present_in_topic_info"],
            "enable_execution_profiles_true": selected["enable_execution_profiles_true"],
            "discovery_converged": selected["observation_pass"],
            "selected_observation_sequence": selected["sequence"],
            "observation_count": len(records),
            "observation_attempts": records,
            "stabilization_bounds": {
                "max_attempts": max_attempts,
                "retry_interval_s": retry_interval_s,
            },
        }
    return dynamic


def collect_runtime_provenance(repo: Path, env: Dict[str, str], uav_ids: Iterable[int]) -> Dict[str, Any]:
    repo = Path(repo).resolve()
    prefixes = {}
    prefix_commands = {}
    for package in ("ladrc_controller", "uav_swarm_interfaces", "lfs_policy"):
        prefix, command = _prefix(package, env=env, cwd=repo)
        prefixes[package] = prefix
        prefix_commands[package] = command

    launch = prefixes["ladrc_controller"] / "share/ladrc_controller/launch/swarm_launch.py"
    policy = prefixes["lfs_policy"] / "share/lfs_policy/config/lfs_policy.paper_current.yaml"
    executable_link = prefixes["ladrc_controller"] / "lib/ladrc_controller/ladrc_position_controller_node"
    executable = executable_link.resolve()
    interface_msg = prefixes["uav_swarm_interfaces"] / "share/uav_swarm_interfaces/msg/UAVExecutionCommand.msg"

    source_checks = {}
    for relative in (CONTROLLER_SOURCE, CONTROLLER_LAUNCH, POLICY_RELATIVE):
        current = (repo / relative).read_bytes()
        approved = subprocess.run(
            ["git", "show", f"{SOURCE_PREFLIGHT}:{relative}"], cwd=repo,
            check=True, capture_output=True,
        ).stdout
        source_checks[relative] = {
            "current_sha256": hashlib.sha256(current).hexdigest(),
            "preflight_sha256": hashlib.sha256(approved).hexdigest(),
            "byte_identical_to_preflight": current == approved,
        }

    binary_strings = _run(["strings", str(executable)], env=env, cwd=repo)
    symbols = _run(["nm", "-C", str(executable)], env=env, cwd=repo)
    expected_strings = [
        "enable_execution_profiles", "execution_command", "command_accepted",
        "mission_trajectory_started", "pending_command_received",
    ]
    capability = {
        value: value in binary_strings["stdout"] for value in expected_strings
    }
    capability["executionCommandCallback_symbol"] = "executionCommandCallback" in symbols["stdout"]
    capability["applyExecutionCommand_symbol"] = "applyExecutionCommand" in symbols["stdout"]

    dynamic = collect_controller_runtime_evidence(repo, env, uav_ids)

    checks = {
        "package_prefixes_are_formal_install_v1": all(
            str(path).startswith("/home/yihuang/learning/LLM_swarm_ws/formal_install_v1/")
            for path in prefixes.values()
        ),
        "installed_launch_matches_frozen_source": sha256_file(launch) ==
            source_checks[CONTROLLER_LAUNCH]["preflight_sha256"],
        "installed_policy_hash_matches": sha256_file(policy) == POLICY_SHA256,
        "installed_controller_binary_exists": executable.is_file(),
        "installed_interface_definition_exists": interface_msg.is_file(),
        "production_sources_match_preflight": all(
            item["byte_identical_to_preflight"] for item in source_checks.values()
        ),
        "binary_execution_profile_capability_present": all(capability.values()),
        "every_controller_node_subscribes": all(
            item["node_subscription_present"] for item in dynamic.values()
        ),
        "every_controller_endpoint_visible_separately_from_rosbag": all(
            item["controller_endpoint_present_in_topic_info"] for item in dynamic.values()
        ),
        "execution_profiles_enabled_for_every_controller": all(
            item["enable_execution_profiles_true"] for item in dynamic.values()
        ),
    }
    return {
        "manifest_type": "E3_runtime_provenance_v1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "package_prefixes": {key: str(value) for key, value in prefixes.items()},
        "package_prefix_commands": prefix_commands,
        "installed_launch_file": {"path": str(launch), "sha256": sha256_file(launch)},
        "installed_policy": {"path": str(policy), "sha256": sha256_file(policy)},
        "installed_controller_executable": {
            "link_path": str(executable_link), "resolved_path": str(executable),
            "sha256": sha256_file(executable),
        },
        "installed_execution_command_interface": {
            "path": str(interface_msg), "sha256": sha256_file(interface_msg),
        },
        "production_source_checks": source_checks,
        "binary_capability_evidence": capability,
        "dynamic_runtime_checks": dynamic,
        "checks": checks,
    }


def runtime_provenance_gate(report: Dict[str, Any]) -> bool:
    checks = report.get("checks", {})
    return report.get("status") == "PASS" and bool(checks) and all(checks.values())


def write_json(path: Path, value: Dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
