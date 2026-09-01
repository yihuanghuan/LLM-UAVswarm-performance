#!/usr/bin/env python3
"""Extract current-paper F0 metrics and fail-closed deviation delivery evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from typing import Any

import numpy as np

TOOLING_DIR = Path(__file__).resolve().parent
E3_DIR = TOOLING_DIR.parent
FORMAL_DIR = E3_DIR.parent
ANALYSIS_TOOLS = FORMAL_DIR / "analysis_freeze" / "tooling"
WORKSPACE = Path("/home/yihuang/learning/LLM_swarm_ws")
INTERFACE_PREFIX = WORKSPACE / "formal_install_v1" / "uav_swarm_interfaces"
INTERFACE_PYTHON = INTERFACE_PREFIX / "local/lib/python3.10/dist-packages"
INTERFACE_LIB = INTERFACE_PREFIX / "lib"
sys.path.insert(0, str(INTERFACE_PYTHON))
os.environ["LD_LIBRARY_PATH"] = ":".join(filter(None, (
    str(INTERFACE_LIB), os.environ.get("LD_LIBRARY_PATH", "")
)))
sys.path.insert(0, str(ANALYSIS_TOOLS))

from live_metric_helpers import pairwise_distance_metrics  # noqa: E402
from rosbag_evidence import read_bag  # noqa: E402


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()


def raw_inventory(raw_dir: Path) -> tuple[dict[str, str], str]:
    files = {
        path.relative_to(raw_dir).as_posix(): sha256_file(path)
        for path in sorted(raw_dir.rglob("*")) if path.is_file()
    }
    return files, canonical_sha256(files)


def point(value) -> np.ndarray:
    return np.asarray([float(value.x), float(value.y), float(value.z)])


def vector(value) -> np.ndarray:
    return np.asarray([float(value.x), float(value.y), float(value.z)])


def command_records(records, uid: int, mission: int):
    return [
        record for record in records
        if record.topic == f"/uav{uid}/execution_command"
        and int(record.message.mission_id) == mission
    ]


def acceptance_records(records, uid: int, mission: int):
    return [
        record for record in records
        if record.topic == f"/uav{uid}/startup_event"
        and int(record.message.mission_id) == mission
        and str(record.message.event) == "command_accepted"
    ]


def debug_records(records, uid: int, mission: int):
    return [
        record for record in records
        if record.topic == f"/uav{uid}/control_tracking_debug"
        and int(record.message.mission_id) == mission
    ]


def command_payload(record) -> dict[str, Any]:
    msg = record.message
    return {
        "timestamp_s": float(record.timestamp),
        "bag_timestamp_s": float(record.bag_timestamp),
        "mission_id": int(msg.mission_id),
        "task_id": int(msg.task_id),
        "uav_id": int(msg.uav_id),
        "target_m": point(msg.target_pos).tolist(),
        "duration_s": float(msg.profile.duration),
        "configuration_id": str(msg.profile.configuration_id),
    }


def planning_commitment(records, spec: dict, t0: float) -> dict[str, Any]:
    parsed = []
    for record in records:
        if record.topic != "/e3_v4/manipulation_event":
            continue
        try:
            value = json.loads(record.message.data)
        except (TypeError, ValueError, AttributeError):
            continue
        if value.get("event") == "planning_committed":
            parsed.append(value)
    matching = [
        value for value in parsed
        if value.get("runtime_spec_sha256") == spec["runtime_spec_sha256"]
        and value.get("assignment") == spec["allocator_diagnostics"]["final_assignment"]
        and float(value.get("ros_time_s", math.inf)) <= t0 + 1e-6
        and t0 - float(value.get("ros_time_s", -math.inf)) <= 1.0 + 1e-6
        and value.get("phase", "interaction") == "interaction"
    ]
    return {
        "verified": len(matching) == 1,
        "matching_event_count": len(matching),
        "events": parsed,
        "commit_before_first_nominal_command": bool(matching),
    }


def verify_delay(records, spec: dict, interaction: dict) -> dict[str, Any]:
    manipulation = spec["manipulation"]
    mission = int(interaction["mission_id"])
    affected = [int(value) for value in manipulation["affected_uavs"]]
    reference = [int(value) for value in manipulation["reference_uavs"]]
    commands = {uid: command_records(records, uid, mission) for uid in spec["uav_ids"]}
    one_each = all(len(commands[int(uid)]) == 1 for uid in spec["uav_ids"])
    reference_times = [commands[uid][0].timestamp for uid in reference if len(commands[uid]) == 1]
    affected_times = [commands[uid][0].timestamp for uid in affected if len(commands[uid]) == 1]
    common_reference = bool(reference_times) and max(reference_times) - min(reference_times) <= 1e-6
    actual_delay = (
        min(affected_times) - min(reference_times)
        if affected_times and reference_times else None
    )
    registered = float(manipulation["delay_s"])
    tolerance = float(spec["delivery_tolerances"]["command_delay_s"])
    timing_ok = (
        actual_delay is not None and abs(actual_delay - registered) <= tolerance
    )
    acknowledgments = {
        str(uid): [float(value.timestamp) for value in acceptance_records(records, uid, mission)]
        for uid in spec["uav_ids"]
    }
    ack_ok = all(len(value) >= 1 for value in acknowledgments.values())
    payloads = {
        str(uid): [command_payload(value) for value in commands[int(uid)]]
        for uid in spec["uav_ids"]
    }
    t0_sim = min(reference_times) if reference_times else math.inf
    commitment = planning_commitment(records, spec, t0_sim)
    return {
        "mechanism": "command_delay",
        "verified": bool(
            one_each and common_reference and timing_ok and ack_ok
            and commitment["verified"]
        ),
        "registered_delay_s": registered,
        "actual_delay_s": actual_delay,
        "absolute_timing_error_s": (
            abs(actual_delay - registered) if actual_delay is not None else None
        ),
        "tolerance_s": tolerance,
        "exactly_one_nominal_command_per_uav": one_each,
        "common_reference_command_timestamp": common_reference,
        "controller_acceptance_verified": ack_ok,
        "acceptance_timestamps_s": acknowledgments,
        "command_payloads": payloads,
        "authoritative_timing_basis": "execution-command ROS simulation-time header",
        "planning_commitment": commitment,
    }


def estimate_global_nominal_endpoint(records, uid: int, debug) -> tuple[np.ndarray, dict]:
    swarm = [record for record in records if record.topic == f"/uav{uid}/swarm_state"]
    if not swarm:
        raise ValueError("swarm-state evidence missing for reference-frame verification")
    swarm_t = np.asarray([record.timestamp for record in swarm])
    offsets = []
    for sample in debug:
        index = int(np.argmin(np.abs(swarm_t - sample.timestamp)))
        if abs(float(swarm_t[index] - sample.timestamp)) <= 0.05:
            offsets.append(
                point(swarm[index].message.pose.pose.position)
                - point(sample.message.actual_position)
            )
    if not offsets:
        raise ValueError("cannot align global swarm state with local debug evidence")
    offset = np.median(np.asarray(offsets), axis=0)
    endpoint = point(debug[-1].message.nominal_position) + offset
    return endpoint, {
        "estimated_enu_offset_m": offset.tolist(),
        "aligned_sample_count": len(offsets),
        "last_debug_timestamp_s": float(debug[-1].timestamp),
    }


def verify_reference(records, spec: dict, interaction: dict) -> dict[str, Any]:
    manipulation = spec["manipulation"]
    uid = int(manipulation["affected_uav"])
    nominal_mission = int(interaction["mission_id"])
    bias_mission = int(interaction["bias_mission_id"])
    reset_mission = int(interaction["reset_mission_id"])
    nominal_by_uav = {
        int(value): command_records(records, int(value), nominal_mission)
        for value in spec["uav_ids"]
    }
    nominal_one_each = all(len(value) == 1 for value in nominal_by_uav.values())
    t0 = min(
        record.timestamp for values in nominal_by_uav.values() for record in values
    ) if nominal_one_each else math.inf
    bias_commands = command_records(records, uid, bias_mission)
    reset_commands = command_records(records, uid, reset_mission)
    exact_generation_counts = len(bias_commands) == 1 and len(reset_commands) == 1
    activation = bias_commands[0].timestamp if len(bias_commands) == 1 else None
    reset = reset_commands[0].timestamp if len(reset_commands) == 1 else None
    registered_start = float(manipulation["start_s"])
    registered_duration = float(manipulation["duration_s"])
    start_error = abs((activation - t0) - registered_start) if activation is not None else None
    duration_error = abs((reset - activation) - registered_duration) if reset is not None and activation is not None else None
    start_tolerance = float(spec["delivery_tolerances"]["reference_activation_time_s"])
    duration_tolerance = float(spec["delivery_tolerances"]["reference_duration_s"])
    timing_ok = (
        start_error is not None and duration_error is not None
        and start_error <= start_tolerance and duration_error <= duration_tolerance
    )
    payload_ok = False
    payload_detail = {}
    if exact_generation_counts:
        bias_payload = command_payload(bias_commands[0])
        reset_payload = command_payload(reset_commands[0])
        initial = np.asarray(spec["initial_positions_m"][spec["uav_ids"].index(uid)])
        target = np.asarray(spec["assigned_targets_m"][spec["uav_ids"].index(uid)])
        u = (registered_start + registered_duration) / float(spec["duration_s"])
        progress = 10.0 * u**3 - 15.0 * u**4 + 6.0 * u**5
        counterfactual = initial + progress * (target - initial)
        registered_offset = np.asarray(manipulation["offset_m"])
        expected_bias = counterfactual + registered_offset
        coordinate_tolerance = float(spec["delivery_tolerances"]["target_coordinate_m"])
        payload_ok = bool(
            np.max(np.abs(np.asarray(bias_payload["target_m"]) - expected_bias))
            <= coordinate_tolerance
            and np.max(np.abs(np.asarray(reset_payload["target_m"]) - target))
            <= coordinate_tolerance
            and abs(bias_payload["duration_s"] - registered_duration) <= 1e-6
        )
        payload_detail = {
            "bias": bias_payload,
            "reset": reset_payload,
            "expected_bias_target_m": expected_bias.tolist(),
            "counterfactual_nominal_endpoint_m": counterfactual.tolist(),
            "registered_offset_m": registered_offset.tolist(),
        }
    bias_ack = acceptance_records(records, uid, bias_mission)
    reset_ack = acceptance_records(records, uid, reset_mission)
    ack_ok = len(bias_ack) >= 1 and len(reset_ack) >= 1
    bias_debug = debug_records(records, uid, bias_mission)
    reset_debug = debug_records(records, uid, reset_mission)
    effective = False
    effective_detail: dict[str, Any] = {
        "bias_debug_sample_count": len(bias_debug),
        "reset_debug_sample_count": len(reset_debug),
    }
    if bias_debug and reset_debug and payload_detail:
        global_endpoint, frame_detail = estimate_global_nominal_endpoint(
            records, uid, bias_debug
        )
        endpoint_error = float(np.linalg.norm(
            global_endpoint - np.asarray(payload_detail["expected_bias_target_m"])
        ))
        endpoint_tolerance = float(
            spec["delivery_tolerances"]["effective_reference_endpoint_tolerance_m"]
        )
        effective = endpoint_error <= endpoint_tolerance
        effective_detail.update({
            **frame_detail,
            "last_bias_nominal_reference_global_m": global_endpoint.tolist(),
            "bias_endpoint_error_m": endpoint_error,
            "endpoint_tolerance_m": endpoint_tolerance,
            "reset_mission_reference_seen": True,
        })
    commitment = planning_commitment(records, spec, t0)
    return {
        "mechanism": "reference_deviation",
        "verified": bool(
            nominal_one_each and exact_generation_counts and timing_ok and payload_ok
            and ack_ok and effective and commitment["verified"]
        ),
        "nominal_exactly_one_command_per_uav": nominal_one_each,
        "exactly_one_bias_and_reset_command": exact_generation_counts,
        "registered_start_s": registered_start,
        "actual_start_s": activation - t0 if activation is not None else None,
        "start_error_s": start_error,
        "start_tolerance_s": start_tolerance,
        "registered_duration_s": registered_duration,
        "actual_duration_s": reset - activation if reset is not None and activation is not None else None,
        "duration_error_s": duration_error,
        "duration_tolerance_s": duration_tolerance,
        "exact_payload_verified": payload_ok,
        "payload": payload_detail,
        "activation_acknowledged": bool(bias_ack),
        "reset_acknowledged": bool(reset_ack),
        "activation_ack_timestamps_s": [float(value.timestamp) for value in bias_ack],
        "reset_ack_timestamps_s": [float(value.timestamp) for value in reset_ack],
        "effective_runtime_reference_verified": effective,
        "effective_runtime_reference": effective_detail,
        "authoritative_timing_basis": "execution-command ROS simulation-time header",
        "planning_commitment": commitment,
    }


def extract(raw_dir: Path) -> dict[str, Any]:
    raw_dir = raw_dir.resolve()
    spec = json.loads((raw_dir / "runtime_spec.json").read_text())
    interaction = json.loads((raw_dir / "interaction_result.json").read_text())
    physical = json.loads((raw_dir / "physical_result.json").read_text())
    if spec.get("dataset_class") != "calibration_pilot":
        raise ValueError("extractor refuses non-pilot data")
    if spec.get("avoidance_mode") != "off" or spec.get("condition") not in ("P0_F0", "P1_F0"):
        raise ValueError("extractor refuses feedback-on data")
    suffixes = (
        "/execution_command", "/startup_event", "/control_tracking_debug",
        "/swarm_state", "/status", "/manipulation_event",
    )
    records = read_bag(raw_dir / "rosbag", lambda topic: topic.endswith(suffixes))
    mechanism = spec["manipulation"]["type"]
    delivery = (
        verify_delay(records, spec, interaction)
        if mechanism == "command_delay"
        else verify_reference(records, spec, interaction)
    )
    nominal_mission = int(interaction["mission_id"])
    nominal_commands = [
        record for record in records
        if record.topic.endswith("/execution_command")
        and int(record.message.mission_id) == nominal_mission
    ]
    if not nominal_commands:
        raise ValueError("nominal interaction command evidence missing")
    # The experiment driver uses /clock for registered manipulation scheduling
    # and stamps commands in simulation time.  The frozen production controller
    # deliberately retains its existing ROS system clock, so its swarm/debug and
    # StartupEvent headers are in the production system-time domain.  Use the
    # controller's first command_accepted event to align realized signals;
    # manipulation timing itself remains verified from the authoritative command
    # simulation-time headers.  Recorder receipt time is deliberately not used
    # because DDS discovery/queueing can delay it without delaying the controller.
    nominal_acceptances = [
        record for uid in spec["uav_ids"]
        for record in acceptance_records(records, int(uid), nominal_mission)
    ]
    if not nominal_acceptances:
        raise ValueError("nominal controller-acceptance evidence missing")
    t0 = min(record.timestamp for record in nominal_acceptances)
    end = t0 + float(spec["duration_s"]) + 2.0
    distance, coverage = pairwise_distance_metrics(
        records, [int(value) for value in spec["uav_ids"]], t0, end,
        float(spec["allocator_diagnostics"]["d_hard"]),
    )
    risk = distance["hard_risk_pair_diagnostics"]
    intended_pair = "-".join(map(str, sorted(spec["intended_pair"])))
    intended = risk[intended_pair]
    event_pairs = [
        pair for pair, detail in risk.items() if int(detail["event_count"]) > 0
    ]
    minimum = distance["actual_d_min"]
    if mechanism == "command_delay":
        manipulation_start = t0
    else:
        bias_mission = int(interaction["bias_mission_id"])
        affected = int(spec["manipulation"]["affected_uav"])
        bias_acceptances = acceptance_records(records, affected, bias_mission)
        if not bias_acceptances:
            raise ValueError("cannot align realized signals without bias acceptance")
        manipulation_start = min(record.timestamp for record in bias_acceptances)
    pre_activation = None
    if mechanism == "reference_deviation":
        pre_distance, pre_coverage = pairwise_distance_metrics(
            records, [int(value) for value in spec["uav_ids"]], t0,
            manipulation_start, float(spec["allocator_diagnostics"]["d_hard"]),
        )
        pre_activation = {
            "d_min_m": float(pre_distance["actual_d_min"]["value"]),
            "d_min_pair": pre_distance["actual_d_min"]["pair"],
            "hard_risk_event_count": int(pre_distance["hard_risk_event_count"]["value"]),
            "hard_risk_exposure_pair_s": float(
                pre_distance["hard_risk_exposure_duration"]["value"]
            ),
            "coverage": pre_coverage,
        }
    statuses = [record for record in records if record.topic.endswith("/status")]
    failsafe = any(bool(record.message.failsafe) for record in statuses)
    debug_scored = [
        record for record in records
        if record.topic.endswith("/control_tracking_debug")
        and t0 <= record.timestamp <= end
    ]
    near_limit = []
    limit = 5.0
    for record in debug_scored:
        output = np.abs(vector(record.message.ladrc_output))
        near_limit.append(bool(np.any(output >= 0.99 * limit)))
    saturation_fraction = (
        float(sum(near_limit) / len(near_limit)) if near_limit else None
    )
    mission_success = bool(
        physical.get("attempt_status") == "success"
        and interaction.get("success")
        and interaction.get("termination_reason") == "SUCCESS"
        and not failsafe
    )
    inventory, inventory_sha = raw_inventory(raw_dir)
    result = {
        "schema": "E3_v4_execution_deviation_metrics_v1",
        "dataset_class": "calibration_pilot",
        "accepted_formal_result": False,
        "formal_cursor_consumed": False,
        "result_notice": "NOT_FORMAL_RESULT",
        "trial_id": spec["trial_id"],
        "candidate_id": spec["candidate_id"],
        "scenario_id": spec["scenario_id"],
        "condition": spec["condition"],
        "seed": int(spec["seed"]),
        "feedback": "F0",
        "predicted": {
            "d_min_m": float(spec["allocator_metrics"]["min_distance"]),
            "hard_violations": int(spec["allocator_metrics"]["hard_violations"]),
            "assignment": spec["allocator_diagnostics"]["final_assignment"],
        },
        "manipulation_delivery": delivery,
        "realized": {
            "d_min_m": float(minimum["value"]),
            "d_min_pair": minimum["pair"],
            "d_min_time_relative_s": float(minimum["timestamp"] - t0),
            "hard_risk_event_count": int(distance["hard_risk_event_count"]["value"]),
            "hard_risk_exposure_pair_s": float(
                distance["hard_risk_exposure_duration"]["value"]
            ),
            "any_pair_hard_risk_duration_s": float(
                distance["any_pair_hard_risk_duration"]["value"]
            ),
            "pair_diagnostics": risk,
        },
        "attribution": {
            "intended_pair": intended_pair,
            "intended_pair_is_global_minimum": minimum["pair"] == intended_pair,
            "intended_pair_event_count": int(intended["event_count"]),
            "intended_pair_exposure_s": float(intended["exposure_duration_s"]),
            "pairs_with_hard_events": event_pairs,
            "only_intended_pair_has_hard_events": event_pairs in ([], [intended_pair]),
            "intended_events_after_manipulation_start": all(
                float(event["start"]) >= manipulation_start
                for event in intended["events"]
            ),
        },
        "pre_activation": pre_activation,
        "stability": {
            "mission_success": mission_success,
            "physical_attempt_status": physical.get("attempt_status"),
            "interaction_termination_reason": interaction.get("termination_reason"),
            "failsafe_seen": failsafe,
            "actual_d_min_le_0p25_m": float(minimum["value"]) <= 0.25,
            "control_debug_sample_count": len(debug_scored),
            "near_acceleration_limit_sample_fraction": saturation_fraction,
            "saturation_dominated": (
                saturation_fraction is None or saturation_fraction >= 0.20
            ),
        },
        "coverage": coverage,
        "timing_bases": {
            "manipulation_delivery": "execution-command ROS simulation-time headers",
            "realized_signal_alignment": "controller command_accepted header in frozen production ROS system-time domain",
            "realized_t0_s": t0,
            "manipulation_start_realized_time_s": manipulation_start,
        },
        "runtime_spec_sha256": sha256_file(raw_dir / "runtime_spec.json"),
        "raw_inventory": inventory,
        "raw_inventory_sha256": inventory_sha,
    }
    if not math.isfinite(result["realized"]["d_min_m"]):
        raise ValueError("non-finite realized minimum distance")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw_dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = extract(args.raw_dir)
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")
    args.output.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
