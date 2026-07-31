#!/usr/bin/env python3
"""Analyze raw experiment 10 trials and build fixed-schema summary CSV files."""

from __future__ import annotations

import argparse
import json
import math
from bisect import bisect_left
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from system_common import (
    CONFIG_PATH,
    REPO_ROOT,
    TASK_NAMES,
    bool_value,
    finite,
    load_yaml,
    mean,
    quantile,
    read_csv,
    stddev,
    write_csv,
    write_json,
)


TRIAL_FIELDS = [
    "experiment_id", "batch_id", "task_type", "trial_id",
    "overall_success", "semantic_success", "execution_success",
    "safety_success", "parsing_latency_ms", "lfs_compilation_latency_ms",
    "assignment_compute_time_ms", "command_dispatch_skew_ms",
    "planned_xy_crossings", "planned_proximity_crossings",
    "planned_min_distance", "local_swap_iterations", "total_latency",
    "completion_time", "total_end_to_end_time", "mission_completion_overhead",
    "controller_tracking_rmse", "tracking_rmse", "avoidance_deviation",
    "arrival_spread", "min_distance", "iapf_activation_count",
    "iapf_active_duration", "violation_count", "violation_duration",
    "near_miss_duration", "mean_rtf", "min_rtf", "p5_rtf",
    "mean_cpu", "p95_cpu", "max_cpu", "mean_memory_bytes",
    "max_memory_bytes", "control_loop_effective_frequency",
    "failure_reason",
]
STAGE_FIELDS = [
    "experiment_id", "batch_id", "task_type", "trial_id", "stage_id",
    "start_time", "end_time", "completion_time", "success",
    "failure_reason", "mission_ids", "uav_ids",
]
ARRIVAL_FIELDS = [
    "experiment_id", "batch_id", "task_type", "trial_id", "stage_id",
    "mission_id", "uav_id", "dispatch_time", "arrival_time",
    "completion_time", "arrival_time_error", "final_position_error",
]
TRACKING_FIELDS = [
    "experiment_id", "batch_id", "task_type", "trial_id", "mission_id",
    "uav_id", "controller_tracking_rmse", "avoidance_deviation",
    "peak_velocity", "peak_acceleration", "semantic_gain_multiplier",
    "sample_count",
]
SAFETY_FIELDS = [
    "experiment_id", "batch_id", "task_type", "trial_id",
    "minimum_inter_agent_distance", "collision_count", "violation_count",
    "violation_duration", "near_miss_duration", "iapf_activation_count",
    "iapf_active_duration", "hysteresis_switching_count",
    "mean_closing_speed_at_activation", "maximum_active_neighbor_count",
    "position_saturation_ratio", "acceleration_saturation_ratio",
    "stale_neighbor_ratio", "safety_success",
]
RESOURCE_FIELDS = [
    "experiment_id", "batch_id", "task_type", "trial_id",
    "mean_rtf", "min_rtf", "p5_rtf", "mean_cpu", "p95_cpu", "max_cpu",
    "mean_memory_bytes", "max_memory_bytes",
    "control_loop_effective_frequency", "realtime_success",
]
TABLE_FIELDS = [
    "task_type", "trials", "success_count", "success_fraction",
    "completion_time_mean_std", "tracking_rmse_mean_std",
    "minimum_distance_mean_std", "arrival_spread_mean_std",
    "iapf_active_duration_mean_std", "mean_rtf_mean_std",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--config", default=str(CONFIG_PATH))
    parser.add_argument("--results-root")
    parser.add_argument("--include-pilot", action="store_true")
    return parser.parse_args()


def safe_csv(path: Path) -> List[Dict[str, str]]:
    return read_csv(path) if path.is_file() else []


def number(row: Dict[str, Any], key: str, default: float = math.nan) -> float:
    try:
        value = float(row.get(key, default))
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) else default


def event_count(mask: Sequence[bool]) -> int:
    return sum(value and (index == 0 or not mask[index - 1])
               for index, value in enumerate(mask))


def mask_duration(times: Sequence[float], mask: Sequence[bool]) -> float:
    return sum(
        max(0.0, following - current)
        for current, following, active in zip(times, times[1:], mask)
        if active
    )


def synchronized_positions(
    odom: Sequence[Dict[str, str]], bin_width: float = 0.1,
) -> List[tuple[float, Dict[int, tuple[float, float, float]]]]:
    grouped: Dict[float, Dict[int, tuple[float, float, float]]] = {}
    for row in odom:
        timestamp = number(row, "timestamp")
        uid = int(number(row, "uav_id", -1))
        if not math.isfinite(timestamp) or uid < 0:
            continue
        key = round(timestamp / bin_width) * bin_width
        grouped.setdefault(key, {})[uid] = (
            number(row, "x"), number(row, "y"), number(row, "z"))
    return sorted(grouped.items())


def distance_series(
    odom: Sequence[Dict[str, str]],
) -> List[tuple[float, float]]:
    series: List[tuple[float, float]] = []
    for timestamp, positions in synchronized_positions(odom):
        if len(positions) < 2:
            continue
        ids = sorted(positions)
        minimum = min(
            math.dist(positions[ids[i]], positions[ids[j]])
            for i in range(len(ids)) for j in range(i + 1, len(ids)))
        series.append((timestamp, minimum))
    return series


def activation_metrics(rows: Sequence[Dict[str, str]]) -> Dict[str, Any]:
    by_uav: Dict[int, List[Dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_uav[int(number(row, "uav_id", -1))].append(row)
    activations = 0
    active_duration = 0.0
    switches = 0
    closing_speeds: List[float] = []
    for samples in by_uav.values():
        samples.sort(key=lambda row: number(row, "timestamp"))
        times = [number(row, "timestamp") for row in samples]
        active = [bool_value(row.get("iapf_active")) for row in samples]
        hysteresis = [bool_value(row.get("hysteresis_active")) for row in samples]
        activations += event_count(active)
        active_duration += mask_duration(times, active)
        switches += sum(
            current != previous
            for previous, current in zip(hysteresis, hysteresis[1:]))
        for index, value in enumerate(active):
            if value and (index == 0 or not active[index - 1]):
                speed = number(samples[index], "nearest_neighbor_closing_speed")
                if math.isfinite(speed):
                    closing_speeds.append(speed)
    total = len(rows)
    stale = sum(number(row, "stale_neighbor_count", 0.0) for row in rows)
    neighbors = sum(
        number(row, "stale_neighbor_count", 0.0)
        + number(row, "valid_neighbor_count", 0.0) for row in rows)
    return {
        "iapf_activation_count": activations,
        "iapf_active_duration": active_duration,
        "hysteresis_switching_count": switches,
        "mean_closing_speed_at_activation": mean(closing_speeds),
        "maximum_active_neighbor_count": max(
            [number(row, "active_neighbor_count", 0.0) for row in rows] or [0]),
        "position_saturation_ratio": (
            sum(bool_value(row.get("position_saturated")) for row in rows) / total
            if total else math.nan),
        "acceleration_saturation_ratio": (
            sum(bool_value(row.get("acceleration_saturated")) for row in rows) / total
            if total else math.nan),
        "stale_neighbor_ratio": stale / neighbors if neighbors else 0.0,
    }


def nearest_row(
    sorted_rows: Sequence[Dict[str, str]], timestamp: float,
    tolerance: float = 0.2,
) -> Dict[str, str] | None:
    if not sorted_rows:
        return None
    times = [number(row, "timestamp") for row in sorted_rows]
    index = bisect_left(times, timestamp)
    candidates = [
        sorted_rows[value] for value in (index - 1, index)
        if 0 <= value < len(sorted_rows)
    ]
    closest = min(candidates, key=lambda row: abs(number(row, "timestamp") - timestamp))
    return closest if abs(number(closest, "timestamp") - timestamp) <= tolerance else None


def tracking_metrics(
    odom: Sequence[Dict[str, str]], iapf: Sequence[Dict[str, str]],
    control: Sequence[Dict[str, str]],
) -> List[Dict[str, Any]]:
    odom_by_uav: Dict[int, List[Dict[str, str]]] = defaultdict(list)
    for row in odom:
        odom_by_uav[int(number(row, "uav_id", -1))].append(row)
    for rows in odom_by_uav.values():
        rows.sort(key=lambda row: number(row, "timestamp"))
    grouped: Dict[tuple[int, int], Dict[str, Any]] = defaultdict(
        lambda: {"tracking_sq": [], "deviation_sq": []})
    for row in iapf:
        uid = int(number(row, "uav_id", -1))
        mission = int(number(row, "mission_id", 0))
        actual = nearest_row(
            odom_by_uav.get(uid, []), number(row, "timestamp"))
        if actual is None:
            continue
        actual_position = [number(actual, key) for key in ("x", "y", "z")]
        modulated = [number(row, key) for key in (
            "modulated_ref_x", "modulated_ref_y", "modulated_ref_z")]
        nominal = [number(row, key) for key in (
            "nominal_ref_x", "nominal_ref_y", "nominal_ref_z")]
        if all(math.isfinite(value) for value in actual_position + modulated + nominal):
            grouped[(mission, uid)]["tracking_sq"].append(
                math.dist(actual_position, modulated) ** 2)
            grouped[(mission, uid)]["deviation_sq"].append(
                math.dist(modulated, nominal) ** 2)
    control_latest: Dict[tuple[int, int], Dict[str, str]] = {}
    for row in control:
        control_latest[(
            int(number(row, "mission_id", 0)),
            int(number(row, "uav_id", -1)),
        )] = row
    results = []
    for key, values in grouped.items():
        mission, uid = key
        control_row = control_latest.get(key, {})
        tracking_sq = values["tracking_sq"]
        deviation_sq = values["deviation_sq"]
        results.append({
            "mission_id": mission, "uav_id": uid,
            "controller_tracking_rmse": math.sqrt(mean(tracking_sq)),
            "avoidance_deviation": math.sqrt(mean(deviation_sq)),
            "peak_velocity": number(control_row, "peak_velocity"),
            "peak_acceleration": number(control_row, "peak_acceleration"),
            "semantic_gain_multiplier": number(control_row, "gain_multiplier"),
            "sample_count": len(tracking_sq),
        })
    return results


def effective_frequency(iapf: Sequence[Dict[str, str]]) -> float:
    by_uav: Dict[int, List[float]] = defaultdict(list)
    for row in iapf:
        by_uav[int(number(row, "uav_id", -1))].append(number(row, "timestamp"))
    frequencies = []
    for timestamps in by_uav.values():
        values = sorted(value for value in timestamps if math.isfinite(value))
        intervals = [
            following - current for current, following in zip(values, values[1:])
            if 0.001 < following - current < 0.5
        ]
        if intervals:
            frequencies.append(1.0 / quantile(intervals, 0.5))
    return mean(frequencies)


def stage_rows(events: Sequence[Dict[str, str]]) -> List[Dict[str, Any]]:
    starts = {
        int(number(row, "stage_id", 0)): row
        for row in events if row.get("event") == "stage_start"
    }
    ends = [
        row for row in events if row.get("event") == "stage_end"
    ]
    results = []
    for end in ends:
        stage_id = int(number(end, "stage_id", 0))
        start = starts.get(stage_id, {})
        results.append({
            "stage_id": stage_id,
            "start_time": number(start, "timestamp"),
            "end_time": number(end, "timestamp"),
            "completion_time": number(end, "duration_s"),
            "success": bool_value(end.get("success")),
            "failure_reason": end.get("failure_reason", ""),
            "mission_ids": end.get("mission_ids", ""),
            "uav_ids": end.get("uav_ids", ""),
        })
    return results


def arrival_rows(
    commands: Sequence[Dict[str, str]], status: Sequence[Dict[str, str]],
    trajectory: Sequence[Dict[str, str]], events: Sequence[Dict[str, str]],
) -> List[Dict[str, Any]]:
    dispatch: Dict[tuple[int, int], float] = {}
    stage_for_mission: Dict[int, int] = {}
    for row in commands:
        key = (int(number(row, "mission_id", 0)), int(number(row, "uav_id", -1)))
        dispatch.setdefault(key, number(row, "timestamp"))
    for event in events:
        if event.get("event") not in {"stage_start", "stage_end"}:
            continue
        stage_id = int(number(event, "stage_id", 0))
        try:
            missions = json.loads(event.get("mission_ids") or "[]")
        except json.JSONDecodeError:
            missions = []
        for mission in missions:
            stage_for_mission[int(mission)] = stage_id
    arrival: Dict[tuple[int, int], float] = {}
    for row in status:
        if bool_value(row.get("is_hover_stable")):
            key = (
                int(number(row, "mission_id", 0)),
                int(number(row, "uav_id", -1)))
            arrival.setdefault(key, number(row, "timestamp"))
    final_metrics: Dict[tuple[int, int], Dict[str, str]] = {}
    for row in trajectory:
        final_metrics[(
            int(number(row, "mission_id", 0)),
            int(number(row, "uav_id", -1)),
        )] = row
    results = []
    for key, dispatch_time in dispatch.items():
        mission, uid = key
        arrived = arrival.get(key, math.nan)
        metrics = final_metrics.get(key, {})
        results.append({
            "stage_id": stage_for_mission.get(mission, 0),
            "mission_id": mission, "uav_id": uid,
            "dispatch_time": dispatch_time, "arrival_time": arrived,
            "completion_time": arrived - dispatch_time
            if math.isfinite(arrived) else math.nan,
            "arrival_time_error": number(metrics, "arrival_time_error"),
            "final_position_error": number(metrics, "final_position_error"),
        })
    return results


def common(manifest: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "experiment_id": manifest["experiment_id"],
        "batch_id": manifest["batch_id"],
        "task_type": manifest["task_type"],
        "trial_id": manifest["trial_id"],
    }


def analyze_trial(trial_dir: Path, config: Dict[str, Any]) -> Dict[str, Any]:
    manifest_path = trial_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    odom = safe_csv(trial_dir / "odom.csv")
    status = safe_csv(trial_dir / "status.csv")
    trajectory = safe_csv(trial_dir / "trajectory_metrics.csv")
    control = safe_csv(trial_dir / "control_adaptation.csv")
    iapf = safe_csv(trial_dir / "iapf_debug.csv")
    commands = safe_csv(trial_dir / "swarm_commands.csv")
    resources = safe_csv(trial_dir / "system_resources.csv")
    events = safe_csv(trial_dir / "mission_events.csv")
    identity = common(manifest)

    distances = distance_series(odom)
    distance_times = [row[0] for row in distances]
    distance_values = [row[1] for row in distances]
    safety_cfg = config["safety"]
    collision_mask = [
        value < float(safety_cfg["collision_distance"]) for value in distance_values]
    violation_mask = [
        value < float(safety_cfg["violation_distance"]) for value in distance_values]
    near_mask = [
        float(safety_cfg["violation_distance"]) <= value
        < float(safety_cfg["iapf_enter_distance"]) for value in distance_values]
    active = activation_metrics(iapf)
    safety = {
        **identity,
        "minimum_inter_agent_distance": min(distance_values)
        if distance_values else math.nan,
        "collision_count": event_count(collision_mask),
        "violation_count": event_count(violation_mask),
        "violation_duration": mask_duration(distance_times, violation_mask),
        "near_miss_duration": mask_duration(distance_times, near_mask),
        **active,
    }
    safety["safety_success"] = bool(
        distance_values
        and safety["collision_count"] == 0
        and safety["minimum_inter_agent_distance"]
        >= float(safety_cfg["violation_distance"]))

    rtf = finite(row.get("real_time_factor") for row in resources)
    cpu = finite(row.get("cpu_percent") for row in resources)
    memory = finite(row.get("memory_used_bytes") for row in resources)
    frequency = effective_frequency(iapf)
    resource = {
        **identity,
        "mean_rtf": mean(rtf), "min_rtf": min(rtf) if rtf else math.nan,
        "p5_rtf": quantile(rtf, 0.05), "mean_cpu": mean(cpu),
        "p95_cpu": quantile(cpu, 0.95), "max_cpu": max(cpu) if cpu else math.nan,
        "mean_memory_bytes": mean(memory),
        "max_memory_bytes": max(memory) if memory else math.nan,
        "control_loop_effective_frequency": frequency,
    }
    resource["realtime_success"] = bool(
        rtf and resource["mean_rtf"]
        >= float(config["realtime"]["minimum_mean_rtf"])
        and math.isfinite(frequency)
        and frequency >= float(
            config["realtime"]["minimum_effective_control_frequency"]))

    stages = [{**identity, **row} for row in stage_rows(events)]
    arrivals = [{**identity, **row} for row in arrival_rows(
        commands, status, trajectory, events)]
    tracking = [{**identity, **row} for row in tracking_metrics(
        odom, iapf, control)]
    parse_metrics = {}
    if (trial_dir / "llm_metrics.json").is_file():
        parse_metrics = json.loads(
            (trial_dir / "llm_metrics.json").read_text(encoding="utf-8"))
    assignments = [
        row for row in events if row.get("event") == "assignment_complete"]
    dispatches = [
        row for row in events if row.get("event") == "commands_dispatched"]
    completion_time = sum(
        number(row, "completion_time", 0.0) for row in stages)
    requested = sum(
        max([
            number(command, "duration", 0.0)
            for command in commands
            if int(number(command, "mission_id", 0)) in json.loads(
                stage.get("mission_ids") or "[]")
        ] or [0.0])
        for stage in stages)
    arrival_spreads = []
    for stage_id in sorted({int(row["stage_id"]) for row in arrivals}):
        values = finite(
            row["arrival_time"] for row in arrivals
            if int(row["stage_id"]) == stage_id)
        if values:
            arrival_spreads.append(max(values) - min(values))
    tracking_rmse = math.sqrt(mean(
        number(row, "controller_tracking_rmse") ** 2
        for row in tracking
        if math.isfinite(number(row, "controller_tracking_rmse"))))
    avoidance_deviation = math.sqrt(mean(
        number(row, "avoidance_deviation") ** 2
        for row in tracking
        if math.isfinite(number(row, "avoidance_deviation"))))

    semantic_success = bool(manifest.get("semantic_success"))
    stage_execution = bool(
        manifest.get("execution_success")
        and stages and all(row["success"] for row in stages))
    execution_success = bool(stage_execution and resource["realtime_success"])
    safety_success = bool(safety["safety_success"])
    failure_reason = str(manifest.get("failure_reason") or "")
    if semantic_success and stage_execution and not resource["realtime_success"]:
        failure_reason = "gazebo_realtime_failure"
    elif semantic_success and execution_success and not safety_success:
        failure_reason = "safety_violation"
    elif semantic_success and execution_success and safety_success:
        failure_reason = ""
    overall = semantic_success and execution_success and safety_success
    summary = {
        **identity,
        "overall_success": overall,
        "semantic_success": semantic_success,
        "execution_success": execution_success,
        "safety_success": safety_success,
        "parsing_latency_ms": parse_metrics.get("parsing_latency_ms", math.nan),
        "lfs_compilation_latency_ms": parse_metrics.get(
            "lfs_compilation_latency_ms", math.nan),
        "assignment_compute_time_ms": sum(
            number(row, "assignment_compute_time_ms", 0.0)
            for row in assignments),
        "command_dispatch_skew_ms": max(
            [number(row, "dispatch_skew_ms") for row in dispatches]
            or [math.nan]),
        "planned_xy_crossings": sum(
            int(number(row, "planned_xy_crossings", 0)) for row in assignments),
        "planned_proximity_crossings": sum(
            int(number(row, "planned_proximity_crossings", 0))
            for row in assignments),
        "planned_min_distance": min(
            [number(row, "planned_min_distance") for row in assignments]
            or [math.nan]),
        "local_swap_iterations": sum(
            int(number(row, "local_swap_iterations", 0)) for row in assignments),
        "total_latency": parse_metrics.get(
            "end_to_end_parse_elapsed_ms", math.nan),
        "completion_time": completion_time,
        "total_end_to_end_time": max(
            finite(row.get("timestamp") for row in resources) or [math.nan]),
        "mission_completion_overhead": completion_time - requested,
        "controller_tracking_rmse": tracking_rmse,
        "tracking_rmse": tracking_rmse,
        "avoidance_deviation": avoidance_deviation,
        "arrival_spread": max(arrival_spreads) if arrival_spreads else math.nan,
        "min_distance": safety["minimum_inter_agent_distance"],
        "iapf_activation_count": safety["iapf_activation_count"],
        "iapf_active_duration": safety["iapf_active_duration"],
        "violation_count": safety["violation_count"],
        "violation_duration": safety["violation_duration"],
        "near_miss_duration": safety["near_miss_duration"],
        **{key: resource[key] for key in (
            "mean_rtf", "min_rtf", "p5_rtf", "mean_cpu", "p95_cpu",
            "max_cpu", "mean_memory_bytes", "max_memory_bytes",
            "control_loop_effective_frequency")},
        "failure_reason": failure_reason,
    }
    manifest.update({
        "execution_success": execution_success,
        "safety_success": safety_success,
        "overall_success": overall,
        "failure_reason": failure_reason,
        "analysis_complete": True,
    })
    write_json(manifest_path, manifest)
    write_json(trial_dir / "trial_summary.json", summary)
    return {
        "trial": summary, "stages": stages, "arrivals": arrivals,
        "tracking": tracking, "safety": safety, "resource": resource,
        "manifest": manifest,
    }


def format_mean_std(values: Iterable[Any]) -> str:
    return f"{mean(values):.3f} ± {stddev(values):.3f}"


def main() -> int:
    args = parse_args()
    config = load_yaml(Path(args.config).resolve())
    results_root = Path(args.results_root).resolve() if args.results_root else (
        REPO_ROOT / config["paths"]["results_root"]).resolve()
    batch_root = results_root / args.batch_id
    raw_roots = [batch_root / "raw"]
    if args.include_pilot:
        raw_roots.append(batch_root / "pilot" / "raw")
    trial_dirs = sorted(
        path for root in raw_roots if root.is_dir()
        for path in root.glob("task_*/trial_*")
        if (path / "manifest.json").is_file())
    if not trial_dirs:
        raise FileNotFoundError(f"no completed trial manifests in {batch_root}")
    analyzed = [analyze_trial(path, config) for path in trial_dirs]
    summaries = batch_root / "summaries"
    write_csv(
        summaries / "system_trial_summary.csv",
        [row["trial"] for row in analyzed], TRIAL_FIELDS)
    write_csv(
        summaries / "stage_timeline.csv",
        [item for row in analyzed for item in row["stages"]], STAGE_FIELDS)
    write_csv(
        summaries / "uav_arrival_summary.csv",
        [item for row in analyzed for item in row["arrivals"]], ARRIVAL_FIELDS)
    write_csv(
        summaries / "tracking_summary.csv",
        [item for row in analyzed for item in row["tracking"]], TRACKING_FIELDS)
    write_csv(
        summaries / "safety_summary.csv",
        [row["safety"] for row in analyzed], SAFETY_FIELDS)
    write_csv(
        summaries / "resource_summary.csv",
        [row["resource"] for row in analyzed], RESOURCE_FIELDS)
    table = []
    trial_rows = [row["trial"] for row in analyzed]
    for task_type in TASK_NAMES:
        rows = [row for row in trial_rows if row["task_type"] == task_type]
        if not rows:
            continue
        success = sum(bool_value(row["overall_success"]) for row in rows)
        table.append({
            "task_type": task_type, "trials": len(rows),
            "success_count": success,
            "success_fraction": f"{success}/{len(rows)}",
            "completion_time_mean_std": format_mean_std(
                row["completion_time"] for row in rows),
            "tracking_rmse_mean_std": format_mean_std(
                row["tracking_rmse"] for row in rows),
            "minimum_distance_mean_std": format_mean_std(
                row["min_distance"] for row in rows),
            "arrival_spread_mean_std": format_mean_std(
                row["arrival_spread"] for row in rows),
            "iapf_active_duration_mean_std": format_mean_std(
                row["iapf_active_duration"] for row in rows),
            "mean_rtf_mean_std": format_mean_std(
                row["mean_rtf"] for row in rows),
        })
    write_csv(summaries / "paper_task_table.csv", table, TABLE_FIELDS)
    manifest_root = batch_root / "manifests"
    manifest_root.mkdir(parents=True, exist_ok=True)
    for row in analyzed:
        manifest = row["manifest"]
        destination = manifest_root / (
            f"{manifest['task_type']}_trial_{int(manifest['trial_id']):02d}.json")
        write_json(destination, manifest)
    print(f"analyzed {len(analyzed)} trials into {summaries}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
