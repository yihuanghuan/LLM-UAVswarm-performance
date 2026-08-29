#!/usr/bin/env python3
"""Authoritative E3-v3 attempt-level live-data metric extractor."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from analysis_common import EvidenceError, file_inventory, metric_na, metric_value
from attempt_context import result_envelope, terminal_classification, validate_attempt
from live_metric_helpers import (command_time, deviation_metrics, iapf_burden,
                                 pairwise_distance_metrics)
from rosbag_evidence import read_bag, records_for


RELEVANT = ("/execution_command", "/swarm_state", "/control_tracking_debug",
            "/iapf_debug", "/status", "/startup_event")


def extract(attempt_dir: Path, *, raw_inventory: dict[str, str] | None = None) -> dict[str, Any]:
    attempt_dir = Path(attempt_dir).resolve()
    manifest, spec, dependencies = validate_attempt(attempt_dir, "E3")
    if spec.get("runtime_spec_type") != "E3_registered_physical_runtime_spec_v3":
        raise EvidenceError("E3 extractor accepts active v3 runtime specs only")
    metrics: dict[str, Any] = {}
    coverage: dict[str, Any] = {}
    interval = None
    analysis_status = "COMPLETE"
    interaction_path = attempt_dir / "raw/interaction_result.json"
    if not interaction_path.is_file() or not (attempt_dir / "raw/rosbag/metadata.yaml").is_file():
        analysis_status = "INCOMPLETE_EVIDENCE"
        reason = "interaction result or rosbag absent"
        for name in ("actual_d_min", "hard_risk_event_count", "hard_risk_exposure_duration",
                     "any_pair_hard_risk_duration", "mission_success", "iapf_activation_time",
                     "integral_delta_p", "integral_delta_a", "trajectory_deviation_integral",
                     "trajectory_deviation_rms"):
            metrics[name] = metric_na(reason)
    else:
        interaction = json.loads(interaction_path.read_text())
        mission_id = int(interaction["mission_id"])
        records = read_bag(attempt_dir / "raw/rosbag", lambda topic: topic.endswith(RELEVANT))
        t0 = command_time(records, mission_id)
        duration = float(spec["duration_s"])
        end = t0 + duration + 2.0
        timeout = t0 + duration + 6.0
        if abs(float(spec["scoring"]["end_offset_s"]) - (duration + 2.0)) > 1.0e-12:
            raise EvidenceError("E3 exact spec scored-end rule is inconsistent")
        interval = {"start": t0, "end": end, "duration_s": end - t0,
                    "basis": "interaction execution-command header timestamp",
                    "timeout": timeout, "registered_motion_duration_s": duration}
        uav_ids = [int(x) for x in spec["uav_ids"]]
        d_hard = float(spec["allocator_diagnostics"]["d_hard"])
        distance_metrics, distance_cov = pairwise_distance_metrics(records, uav_ids, t0, end, d_hard)
        metrics.update(distance_metrics); coverage.update(distance_cov)
        predicted = float(spec["allocator_metrics"]["min_distance"])
        metrics["predicted_d_min"] = metric_value(
            predicted, unit="m", assignment=spec["allocator_diagnostics"]["final_assignment"],
            assignment_mode=spec["assignment_mode"], source="raw/runtime_spec.json allocator_metrics",
            runtime_spec_sha256=spec["runtime_spec_sha256"])
        burden, burden_cov = iapf_burden(records, uav_ids, mission_id, t0, end, aggregate="sum")
        metrics["iapf_activation_time"] = metric_value(
            burden["swarm"]["activation_time_s"], unit="UAV-seconds", per_uav=burden["per_uav"])
        metrics["integral_delta_p"] = metric_value(
            burden["swarm"]["integral_delta_p_m_s"], unit="m*s", per_uav=burden["per_uav"])
        metrics["integral_delta_a"] = metric_value(
            burden["swarm"]["integral_delta_a_mps"], unit="m/s", per_uav=burden["per_uav"])
        coverage["iapf"] = burden_cov
        deviation, deviation_cov = deviation_metrics(records, uav_ids, mission_id, t0, end)
        metrics["trajectory_deviation_integral"] = metric_value(
            deviation["swarm_sum_integral_m_s"], unit="m*s", per_uav=deviation["per_uav"],
            aggregation="sum across UAVs")
        metrics["trajectory_deviation_rms"] = metric_value(
            deviation["swarm_equal_uav_pooled_rms_m"], unit="m", per_uav=deviation["per_uav"],
            aggregation="equal-UAV pooled RMS")
        coverage["trajectory_deviation"] = deviation_cov
        statuses = records_for(records, "/status", mission_id=mission_id)
        hard_failure = any(bool(record.message.failsafe) for record in statuses)
        completion = bool(interaction.get("success")) and interaction.get("termination_reason") == "SUCCESS"
        finished_utc_present = bool(interaction.get("finished_utc"))
        within_timeout = completion and finished_utc_present
        metrics["mission_success"] = metric_value(bool(completion and within_timeout and not hard_failure),
            components={"registered_completion": completion, "within_registered_timeout": within_timeout,
                        "no_hard_failure": not hard_failure}, denominator="all retained attempts")
        coverage["completion_and_hard_failure"] = {
            "interaction_result_present": True, "status_sample_count": len(statuses),
            "hard_failure_source": "UAVStatus.failsafe", "completion_source": "interaction_result terminal event set"}
    if "predicted_d_min" not in metrics:
        try:
            metrics["predicted_d_min"] = metric_value(
                float(spec["allocator_metrics"]["min_distance"]), unit="m",
                assignment=spec["allocator_diagnostics"]["final_assignment"], source="raw/runtime_spec.json")
        except Exception as exc:
            metrics["predicted_d_min"] = metric_na(f"allocator prediction unavailable: {exc}")
    return result_envelope(
        attempt_dir, "E3", Path(__file__), manifest, dependencies, scored_interval=interval,
        terminal_classification=terminal_classification(manifest), analysis_status=analysis_status,
        metrics=metrics, source_coverage=coverage,
        raw_inventory=raw_inventory if raw_inventory is not None else file_inventory(attempt_dir))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("attempt_dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = extract(args.attempt_dir)
    text = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
