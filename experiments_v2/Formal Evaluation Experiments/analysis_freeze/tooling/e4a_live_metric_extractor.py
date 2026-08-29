#!/usr/bin/env python3
"""Authoritative E4A attempt-level live-data metric extractor."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from analysis_common import (EvidenceError, acceleration_rise_time, canonical_sha256,
                             clip_series, file_inventory, metric_na, metric_value,
                             normalize_series, time_weighted_rms, trapezoidal_integral,
                             vector_norm)
from attempt_context import result_envelope, terminal_classification, validate_attempt
from live_metric_helpers import command_time, tracking_rmse
from rosbag_evidence import read_bag, records_for, vector


RELEVANT = ("/execution_command", "/control_tracking_debug", "/status", "/trajectory_metrics")


def _reference_identity(spec: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    exact = manifest["execution_spec"]
    identity = {
        "scenario_id": exact["scenario_id"], "seed": exact["seed"],
        "initial_positions_m": exact["initial_positions_m"],
        "assigned_targets_m": exact["assigned_targets_m"],
        "explicit_T_s": exact["requested_T"]["value_s"],
        "polynomial": exact["nominal_reference"]["polynomial"],
    }
    runtime = spec["nominal_reference"]
    if runtime["p0"] != exact["nominal_reference"]["p0"] or runtime["targets"] != exact["nominal_reference"]["targets"]:
        raise EvidenceError("E4A nominal reference identity differs between exact and runtime specs")
    if abs(float(runtime["duration_s"]) - float(identity["explicit_T_s"])) > 1.0e-12:
        raise EvidenceError("E4A runtime nominal reference was retimed")
    if runtime.get("style_may_regenerate_or_retime") is not False:
        raise EvidenceError("E4A reference isolation flag is not frozen false")
    return {"identity": identity, "sha256": canonical_sha256(identity),
            "style_excluded_from_identity": True, "validated": True}


def extract(attempt_dir: Path, *, raw_inventory: dict[str, str] | None = None) -> dict[str, Any]:
    attempt_dir = Path(attempt_dir).resolve()
    manifest, spec, dependencies = validate_attempt(attempt_dir, "E4A")
    reference_identity = _reference_identity(spec, manifest)
    metrics: dict[str, Any] = {"reference_identity": reference_identity}
    coverage: dict[str, Any] = {}
    interaction_path = attempt_dir / "raw/interaction_result.json"
    if not interaction_path.is_file() or not (attempt_dir / "raw/rosbag/metadata.yaml").is_file():
        reason = "interaction result or rosbag absent"
        for name in ("settling_time", "control_effort", "acceleration_peak", "acceleration_rms",
                     "acceleration_rise_time", "tracking_RMSE"):
            metrics[name] = metric_na(reason)
        return result_envelope(attempt_dir, "E4A", Path(__file__), manifest, dependencies,
            scored_interval=None, terminal_classification=terminal_classification(manifest),
            analysis_status="INCOMPLETE_EVIDENCE", metrics=metrics, source_coverage=coverage,
            raw_inventory=raw_inventory if raw_inventory is not None else file_inventory(attempt_dir))
    interaction = json.loads(interaction_path.read_text())
    mission_id = int(interaction["mission_id"])
    records = read_bag(attempt_dir / "raw/rosbag", lambda topic: topic.endswith(RELEVANT))
    t0 = command_time(records, mission_id)
    explicit_t = float(spec["duration_s"])
    if abs(explicit_t - float(manifest["execution_spec"]["requested_T"]["value_s"])) > 1.0e-12:
        raise EvidenceError("E4A exact explicit T mismatch")
    end = t0 + explicit_t
    interval = {"start": t0, "end": end, "duration_s": explicit_t,
                "basis": "interaction execution-command header timestamp plus exact-spec explicit T"}
    uav_ids = [int(value) for value in spec["uav_ids"]]
    per_effort = {}; per_peak = {}; per_rms = {}; per_rise = {}; accel_coverage = {}
    commands = records_for(records, "/execution_command", mission_id=mission_id)
    for uav_id in uav_ids:
        own_commands = [r.message for r in commands if int(r.message.uav_id) == uav_id]
        if len(own_commands) != 1:
            raise EvidenceError(f"E4A UAV {uav_id} requires exactly one interaction command")
        command = own_commands[0]
        expected_target = spec["assigned_targets_m"][uav_id - 1]
        actual_target = [command.target_pos.x, command.target_pos.y, command.target_pos.z]
        if command.profile.style != spec["style"] or abs(command.profile.duration - explicit_t) > 1.0e-6:
            raise EvidenceError(f"E4A UAV {uav_id} deployed profile identity mismatch")
        if not np.allclose(actual_target, expected_target, rtol=0.0, atol=1.0e-9):
            raise EvidenceError(f"E4A UAV {uav_id} command target mismatch")
        # The immediately preceding controller sample brackets command-publication t0.
        subset = records_for(records, "/control_tracking_debug", uav_id=uav_id)
        acceleration = normalize_series([r.timestamp for r in subset], [vector(r.message.ladrc_output) for r in subset])
        clipped, cov = clip_series(acceleration, t0, end)
        magnitude = vector_norm(clipped.value)
        per_effort[str(uav_id)] = trapezoidal_integral(clipped.t, magnitude)
        per_peak[str(uav_id)] = float(np.max(magnitude))
        per_rms[str(uav_id)] = time_weighted_rms(clipped.t, magnitude)
        per_rise[str(uav_id)] = acceleration_rise_time(clipped.t, magnitude)
        accel_coverage[str(uav_id)] = cov
    metrics["control_effort"] = metric_value(float(np.mean(list(per_effort.values()))),
        unit="m/s", per_uav=per_effort, aggregation="mean per-UAV integral")
    metrics["acceleration_peak"] = metric_value(float(np.mean(list(per_peak.values()))),
        unit="m/s^2", per_uav=per_peak, max_per_uav_diagnostic=max(per_peak.values()),
        aggregation="mean per-UAV peak")
    metrics["acceleration_rms"] = metric_value(math.sqrt(float(np.mean(np.square(list(per_rms.values()))))),
        unit="m/s^2", per_uav=per_rms, aggregation="equal-UAV pooled RMS")
    rise_valid = all(item["valid"] for item in per_rise.values())
    if rise_valid:
        metrics["acceleration_rise_time"] = metric_value(
            float(np.mean([item["value_s"] for item in per_rise.values()])), unit="s",
            per_uav=per_rise, aggregation="mean only when every UAV is valid")
    else:
        metrics["acceleration_rise_time"] = metric_na(
            "one or more required UAV rise-time measurements are invalid", per_uav=per_rise,
            aggregation="all-UAV completeness required")
    coverage["commanded_ladrc_acceleration"] = accel_coverage
    tracking, tracking_cov = tracking_rmse(records, uav_ids, mission_id, t0, end)
    metrics["tracking_RMSE"] = metric_value(tracking["swarm_equal_uav_pooled_rmse_m"],
        unit="m", per_uav=tracking["per_uav_m"], aggregation="equal-UAV pooled RMS")
    coverage["tracking_error"] = tracking_cov
    settling = {}; missing_settling = []
    for uav_id in uav_ids:
        stable = [r.timestamp for r in records_for(records, "/status", mission_id=mission_id, uav_id=uav_id)
                  if bool(r.message.is_hover_stable) and r.timestamp >= t0]
        if stable:
            settling[str(uav_id)] = min(stable) - t0
        else:
            missing_settling.append(uav_id)
    if missing_settling:
        metrics["settling_time"] = metric_na("registered stable-hover entry absent for required UAVs",
            per_uav=settling, missing_uav_ids=missing_settling)
    else:
        metrics["settling_time"] = metric_value(max(settling.values()), unit="s", per_uav=settling,
            aggregation="maximum per-UAV", truncated_at_explicit_T=False)
    coverage["settling_event"] = {"per_uav_present": {str(i): str(i) in settling for i in uav_ids}}
    return result_envelope(attempt_dir, "E4A", Path(__file__), manifest, dependencies,
        scored_interval=interval, terminal_classification=terminal_classification(manifest),
        analysis_status="COMPLETE", metrics=metrics, source_coverage=coverage,
        raw_inventory=raw_inventory if raw_inventory is not None else file_inventory(attempt_dir))


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("attempt_dir", type=Path); parser.add_argument("--output", type=Path)
    args = parser.parse_args(); result = extract(args.attempt_dir)
    text = json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
    if args.output: args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(text)
    else: print(text, end="")
    return 0


if __name__ == "__main__": raise SystemExit(main())
