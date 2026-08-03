"""Experiment-10 v3 stage timing and stability-interval reconstruction."""

from __future__ import annotations

import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from system_common import finite, mean, read_csv


def number(value: Any, default: float = math.nan) -> float:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def truth(value: Any) -> bool:
    return str(value).lower() == "true" if isinstance(value, str) else bool(value)


def first_event(rows: Iterable[dict], name: str) -> float:
    values = finite(number(row.get("timestamp")) for row in rows if row.get("event") == name)
    return min(values) if values else math.nan


def final_interval_from_events(
    events: List[dict], key: Tuple[int, int], stage_id: int,
    dispatch: float, stage_end: float,
) -> Dict[str, Any]:
    candidate = None
    confirmed = None
    last_candidate = None
    last_confirmed = None
    mission, uid = key
    selected = sorted(
        (row for row in events
         if int(number(row.get("stage_id"), 0)) == stage_id
         and int(number(row.get("mission_id"), 0)) == mission
         and int(number(row.get("uav_id"), -1)) == uid
         and dispatch <= number(row.get("timestamp")) <= stage_end),
        key=lambda row: number(row.get("timestamp")),
    )
    for row in selected:
        name = row.get("event")
        timestamp = number(row.get("timestamp"))
        if name == "stable_candidate_enter":
            candidate = timestamp
            last_candidate = timestamp
        elif name == "stable_confirmed":
            confirmed = timestamp
            last_confirmed = timestamp
        elif name in (
            "stable_candidate_exit", "stable_confirmed_exit", "stable_unstable"
        ):
            candidate = None
            confirmed = None
    return {
        "candidate": candidate, "confirmed": confirmed,
        "last_candidate": last_candidate, "last_confirmed": last_confirmed,
        "state": 2 if confirmed is not None else (1 if candidate is not None else 0),
    }


def final_interval_from_status(
    status: List[dict], key: Tuple[int, int], start: float, stage_end: float,
    thresholds: dict,
) -> Dict[str, Any]:
    state = 0
    candidate = None
    confirmed = None
    last_candidate = None
    last_confirmed = None
    mission, uid = key
    selected = sorted(
        (row for row in status
         if int(number(row.get("mission_id"), 0)) == mission
         and int(number(row.get("uav_id"), -1)) == uid
         and start <= number(row.get("timestamp")) <= stage_end),
        key=lambda row: number(row.get("timestamp")),
    )
    for row in selected:
        timestamp = number(row.get("timestamp"))
        position = number(row.get("position_error"))
        speed = number(row.get("speed"))
        should_exit = (
            position > thresholds["position_exit"]
            or speed > thresholds["speed_exit"])
        should_enter = (
            position <= thresholds["position_enter"]
            and speed <= thresholds["speed_enter"])
        if should_exit:
            state, candidate, confirmed = 0, None, None
        elif state == 0 and should_enter:
            state, candidate = 1, timestamp
            last_candidate = timestamp
        elif (
            state == 1 and candidate is not None
            and timestamp - candidate >= thresholds["hold_time"]
        ):
            state, confirmed = 2, timestamp
            last_confirmed = timestamp
    return {
        "candidate": candidate, "confirmed": confirmed,
        "last_candidate": last_candidate, "last_confirmed": last_confirmed,
        "state": state,
    }


def load_optional_csv(path: Path) -> List[dict]:
    return read_csv(path) if path.is_file() else []


def stage_timing_rows(
    trial_dir: Path, manifest: dict, config: dict, legacy_v2: bool = False,
) -> tuple[List[dict], List[dict], List[dict]]:
    events = load_optional_csv(trial_dir / "mission_events.csv")
    if not events:
        return [], [], []
    status = load_optional_csv(trial_dir / "status.csv")
    odom = load_optional_csv(trial_dir / "odom.csv")
    trajectories = load_optional_csv(trial_dir / "trajectory_metrics.csv")
    controls = load_optional_csv(trial_dir / "control_adaptation.csv")
    iapf = load_optional_csv(trial_dir / "iapf_debug.csv")
    thresholds = {
        "position_enter": float(config["experiment"]["stable_position_enter"]),
        "speed_enter": float(config["experiment"]["stable_speed_enter"]),
        "position_exit": float(config["experiment"]["stable_position_exit"]),
        "speed_exit": float(config["experiment"]["stable_speed_exit"]),
        "hold_time": float(config["experiment"]["stable_hold_time"]),
    }
    stage_ids = sorted({
        int(number(row.get("stage_id"), 0)) for row in events
        if row.get("event") == "stage_start"
    })
    identity = {
        "batch_id": manifest.get("batch_id", ""),
        "task_type": manifest.get("task_type", ""),
        "attempt_id": manifest.get("attempt_id", ""),
        "trial_id": manifest.get("target_execution_index", ""),
    }
    stages: List[dict] = []
    arrivals: List[dict] = []
    diagnostics: List[dict] = []
    for stage_id in stage_ids:
        stage_events = [
            row for row in events
            if int(number(row.get("stage_id"), 0)) == stage_id]
        stage_start = first_event(stage_events, "stage_start")
        assignment = first_event(stage_events, "assignment_complete")
        stage_end = first_event(stage_events, "stage_end")
        end_event = next(
            (row for row in reversed(stage_events) if row.get("event") == "stage_end"),
            {})
        dispatch = {
            (int(number(row.get("mission_id"), 0)),
             int(number(row.get("uav_id"), -1))): number(row.get("timestamp"))
            for row in stage_events if row.get("event") == "command_dispatch"
        }
        reference_start = defaultdict(list)
        reference_finish = defaultdict(list)
        ack = defaultdict(list)
        for row in stage_events:
            key = (int(number(row.get("mission_id"), 0)),
                   int(number(row.get("uav_id"), -1)))
            if row.get("event") == "reference_start":
                reference_start[key].append(number(row.get("timestamp")))
            elif row.get("event") == "reference_finish":
                reference_finish[key].append(number(row.get("timestamp")))
            elif row.get("event") == "command_acknowledged":
                ack[key].append(number(row.get("timestamp")))
        if legacy_v2:
            for row in controls:
                key = (int(number(row.get("mission_id"), 0)),
                       int(number(row.get("uav_id"), -1)))
                if key in dispatch:
                    ack[key].append(number(row.get("timestamp")))
        expected = set(dispatch)
        invalid_stage: List[str] = []
        if not expected:
            invalid_stage.append("missing_dispatch")
        arrival_stage = []
        interval_by_key = {}
        for key in sorted(expected):
            mission, uid = key
            d = dispatch[key]
            rs = min(finite(reference_start[key]) or [math.nan])
            rf = min(finite(reference_finish[key]) or [math.nan])
            interval = (
                final_interval_from_status(
                    status, key, max(d, rf) if math.isfinite(rf) else d,
                    stage_end, thresholds)
                if legacy_v2 else
                final_interval_from_events(events, key, stage_id, d, stage_end)
            )
            interval_by_key[key] = interval
            candidate = number(interval["candidate"])
            confirmed = number(interval["confirmed"])
            reasons = []
            for label, timestamp in (
                ("reference_start_before_dispatch", rs),
                ("reference_finish_before_dispatch", rf),
                ("candidate_before_dispatch", candidate),
                ("arrival_before_dispatch", confirmed),
                ("arrival_before_reference_start", confirmed),
            ):
                lower = rs if label == "arrival_before_reference_start" else d
                if math.isfinite(timestamp) and math.isfinite(lower) and timestamp < lower:
                    reasons.append(label)
            if not math.isfinite(rs):
                reasons.append("missing_reference_start")
            if not math.isfinite(rf):
                reasons.append("missing_reference_finish")
            if not math.isfinite(confirmed):
                reasons.append("missing_final_confirmed")
            final_rows = [
                row for row in trajectories
                if int(number(row.get("mission_id"), 0)) == mission
                and int(number(row.get("uav_id"), -1)) == uid]
            final = final_rows[-1] if final_rows else {}
            arrival = {
                **identity, "stage_id": stage_id, "mission_id": mission,
                "uav_id": uid, "dispatch_time": d,
                "reference_start_time": rs, "reference_finish_time": rf,
                "stable_candidate_time": candidate,
                "stable_confirmed_time": confirmed,
                "stable_hold_time": (
                    confirmed - candidate
                    if math.isfinite(confirmed) and math.isfinite(candidate)
                    else math.nan),
                "final_position_error": number(final.get("final_position_error")),
                "settling_time": number(final.get("elapsed_time")),
                "valid": not reasons, "invalid_reason": ";".join(reasons),
            }
            arrival_stage.append(arrival)
            arrivals.append(arrival)
            invalid_stage.extend(reasons)
        dispatch_values = finite(row["dispatch_time"] for row in arrival_stage)
        start_values = finite(row["reference_start_time"] for row in arrival_stage)
        finish_values = finite(row["reference_finish_time"] for row in arrival_stage)
        confirmed_values = finite(row["stable_confirmed_time"] for row in arrival_stage)
        hold_values = finite(row["stable_hold_time"] for row in arrival_stage)
        all_finished = len(finish_values) == len(expected) and bool(expected)
        all_confirmed = len(confirmed_values) == len(expected) and bool(expected)
        failure_reason = str(end_event.get("failure_reason") or "")
        if legacy_v2 and failure_reason == "stage_timeout":
            max_age = float(config["experiment"]["stage_data_max_age"])
            stale = any(
                stage_end - max(finite(
                    number(row.get("timestamp")) for row in status
                    if int(number(row.get("uav_id"), -1)) == uid
                    and number(row.get("timestamp")) <= stage_end) or [-math.inf])
                > max_age
                or stage_end - max(finite(
                    number(row.get("timestamp")) for row in odom
                    if int(number(row.get("uav_id"), -1)) == uid
                    and number(row.get("timestamp")) <= stage_end) or [-math.inf])
                > max_age
                for _, uid in expected)
            if stale:
                failure_reason = "stage_data_stale"
            elif len(ack) < len(expected):
                failure_reason = "dispatch_timeout"
            elif not all_finished:
                failure_reason = "reference_finish_timeout"
            else:
                failure_reason = "stabilization_timeout"
        slowest = ""
        if confirmed_values:
            slowest = max(
                (row for row in arrival_stage
                 if math.isfinite(number(row["stable_confirmed_time"]))),
                key=lambda row: number(row["stable_confirmed_time"]))["uav_id"]
        stage = {
            **identity, "stage_id": stage_id,
            "stage_start_time": stage_start,
            "assignment_complete_time": assignment,
            "first_command_dispatch_time": min(dispatch_values or [math.nan]),
            "last_command_dispatch_time": max(dispatch_values or [math.nan]),
            "all_commands_acknowledged_time": max(
                finite(v for values in ack.values() for v in values) or [math.nan]),
            "reference_start_time": min(start_values or [math.nan]),
            "all_references_finished_time": max(finish_values) if all_finished else math.nan,
            "all_uavs_stable_time": max(confirmed_values) if all_confirmed else math.nan,
            "stage_end_time": stage_end,
            "planning_time": assignment - stage_start,
            "dispatch_time": (
                max(dispatch_values) - assignment if dispatch_values else math.nan),
            "reference_execution_time": (
                max(finish_values) - min(dispatch_values)
                if all_finished and dispatch_values else math.nan),
            "trajectory_finish_spread": (
                max(finish_values) - min(finish_values) if all_finished else math.nan),
            "stabilization_delay": (
                max(confirmed_values) - max(finish_values)
                if all_confirmed and all_finished else math.nan),
            "stable_hold_time": (
                mean(hold_values) if len(hold_values) == len(expected) else math.nan),
            "stable_arrival_spread": (
                max(confirmed_values) - min(confirmed_values)
                if all_confirmed else math.nan),
            "stage_wall_time": stage_end - stage_start,
            "slowest_uav_id": slowest,
            "failure_reason": failure_reason,
            "valid": not invalid_stage,
            "invalid_reason": ";".join(sorted(set(invalid_stage))),
        }
        numeric_metrics = (
            "planning_time", "dispatch_time", "reference_execution_time",
            "trajectory_finish_spread", "stabilization_delay",
            "stable_hold_time", "stable_arrival_spread", "stage_wall_time")
        if any(number(stage[name], 0) < 0 for name in numeric_metrics):
            stage["valid"] = False
            stage["invalid_reason"] = ";".join(filter(None, [
                stage["invalid_reason"], "negative_completion_time"]))
        stages.append(stage)
        if failure_reason:
            for key in sorted(expected):
                mission, uid = key
                latest_status = next((
                    row for row in reversed(status)
                    if int(number(row.get("mission_id"), 0)) == mission
                    and int(number(row.get("uav_id"), -1)) == uid
                    and number(row.get("timestamp")) <= stage_end), {})
                latest_odom = next((
                    row for row in reversed(odom)
                    if int(number(row.get("uav_id"), -1)) == uid
                    and number(row.get("timestamp")) <= stage_end), {})
                latest_iapf = next((
                    row for row in reversed(iapf)
                    if int(number(row.get("mission_id"), 0)) == mission
                    and int(number(row.get("uav_id"), -1)) == uid
                    and number(row.get("timestamp")) <= stage_end), {})
                interval = interval_by_key[key]
                if not ack[key]:
                    condition = "missing_command_ack"
                elif not reference_finish[key]:
                    condition = "reference_not_finished"
                elif interval["state"] != 2:
                    condition = "not_confirmed"
                else:
                    condition = "stage_peer_failure"
                diagnostics.append({
                    **identity, "stage_id": stage_id, "uav_id": uid,
                    "mission_id": mission, "failure_reason": failure_reason,
                    "failure_condition": condition,
                    "command_ack": bool(ack[key]),
                    "reference_finished": bool(reference_finish[key]),
                    "stability_state": interval["state"],
                    "position_error": number(latest_status.get("position_error")),
                    "speed": number(latest_status.get("speed")),
                    "odom_age": stage_end - number(latest_odom.get("timestamp")),
                    "status_age": stage_end - number(latest_status.get("timestamp")),
                    "iapf_active": truth(latest_iapf.get("iapf_active")),
                    "nearest_neighbor_distance": number(
                        latest_iapf.get("nearest_neighbor_distance")),
                    "last_candidate_time": number(interval["last_candidate"]),
                    "last_confirmed_time": number(interval["last_confirmed"]),
                })
    return stages, arrivals, diagnostics
