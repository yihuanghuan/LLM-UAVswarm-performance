#!/usr/bin/env python3
"""Generate experiment-10 v2 attempt, timing, reliability, and paper summaries."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List

from system_common import (
    CONFIG_PATH, REPO_ROOT, TASK_NAMES, bool_value, finite, load_yaml, mean,
    quantile, read_csv, stddev, write_csv,
)
from summarize_system_trials import (
    RESOURCE_FIELDS, SAFETY_FIELDS, TRACKING_FIELDS, analyze_trial,
)


ATTEMPT_FIELDS = [
    "batch_id", "task_type", "attempt_id", "run_order",
    "target_execution_index", "trial_id", "replacement_for",
    "entered_execution", "semantic_success", "execution_success",
    "safety_success", "overall_success", "failure_reason", "path",
]
READINESS_FIELDS = [
    "batch_id", "task_type", "attempt_id", "uav_id", "condition",
    "has_odom", "odom_fresh", "has_vehicle_status", "armed", "offboard",
    "failsafe", "speed", "readiness_success",
]
SEMANTIC_FIELDS = [
    "batch_id", "task_type", "attempt_id", "attempt_index",
    "llm_model", "latency_ms", "valid_json", "schema_valid",
    "semantic_valid", "repair_applied", "error_type", "raw_response_path",
]
STAGE_FIELDS = [
    "batch_id", "task_type", "attempt_id", "trial_id", "stage_id",
    "stage_start_time", "assignment_complete_time",
    "first_command_dispatch_time", "last_command_dispatch_time",
    "reference_start_time", "all_references_finished_time",
    "all_uavs_stable_time", "stage_end_time", "planning_time",
    "dispatch_time", "reference_execution_time", "trajectory_finish_spread",
    "stabilization_delay", "stable_hold_time", "stable_arrival_spread",
    "stage_wall_time", "slowest_uav_id", "valid", "invalid_reason",
]
MISSION_FIELDS = [
    "batch_id", "task_type", "attempt_id", "trial_id", "stage_count",
    "mission_wall_time", "planning_time", "dispatch_time",
    "stage_wall_time",
    "reference_execution_time", "stabilization_delay", "stable_hold_time",
    "trajectory_finish_spread", "stable_arrival_spread",
]
ARRIVAL_FIELDS = [
    "batch_id", "task_type", "attempt_id", "trial_id", "stage_id",
    "mission_id", "uav_id", "dispatch_time", "reference_start_time",
    "reference_finish_time", "stable_candidate_time",
    "stable_confirmed_time", "stable_hold_time", "final_position_error",
    "settling_time", "valid", "invalid_reason",
]
OUTLIER_FIELDS = [
    "task_type", "attempt_id", "metric", "value", "q1", "q3",
    "lower_bound", "upper_bound", "is_outlier", "reason",
]
STAT_FIELDS = [
    "task_type", "metric", "count", "mean", "std", "median", "iqr", "min",
    "max", "p90", "p95", "coefficient_of_variation",
]


def number(value, default=math.nan):
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def first(rows, event):
    values = [number(row["timestamp"]) for row in rows if row["event"] == event]
    return min(finite(values)) if values else math.nan


def event_rows(rows, event, stage_id):
    return [
        row for row in rows
        if row.get("event") == event
        and int(number(row.get("stage_id"), stage_id)) == stage_id
    ]


def timing_rows(trial_dir: Path, manifest: dict):
    if not (trial_dir / "mission_events.csv").is_file():
        return [], []
    events = read_csv(trial_dir / "mission_events.csv")
    commands = read_csv(trial_dir / "swarm_commands.csv")
    trajectories = read_csv(trial_dir / "trajectory_metrics.csv")
    stages, arrivals = [], []
    stage_ids = sorted({
        int(number(row.get("stage_id"), 0)) for row in events
        if number(row.get("stage_id"), 0) > 0
    })
    identity = {
        "batch_id": manifest["batch_id"], "task_type": manifest["task_type"],
        "attempt_id": manifest["attempt_id"],
        "trial_id": manifest.get("target_execution_index", ""),
    }
    for stage_id in stage_ids:
        stage_events = [
            row for row in events if int(number(row.get("stage_id"), 0)) == stage_id]
        starts = event_rows(events, "stage_start", stage_id)
        ends = event_rows(events, "stage_end", stage_id)
        assignments = event_rows(events, "assignment_complete", stage_id)
        stage_start = first(starts, "stage_start")
        assignment = first(assignments, "assignment_complete")
        stage_end = first(ends, "stage_end")
        mission_ids = set()
        uav_ids = set()
        for row in starts:
            mission_ids.update(json.loads(row.get("mission_ids") or "[]"))
            uav_ids.update(json.loads(row.get("uav_ids") or "[]"))
        dispatch = {
            (int(number(row["mission_id"])), int(number(row["uav_id"]))):
            number(row["timestamp"])
            for row in stage_events if row["event"] == "command_dispatch"
        }
        reference_start = defaultdict(list)
        reference_finish = defaultdict(list)
        candidates = defaultdict(list)
        confirmed = defaultdict(list)
        for row in stage_events:
            key = (int(number(row.get("mission_id"), 0)),
                   int(number(row.get("uav_id"), -1)))
            if row["event"] == "reference_start":
                reference_start[key].append(number(row["timestamp"]))
            elif row["event"] == "reference_finish":
                reference_finish[key].append(number(row["timestamp"]))
            elif row["event"] == "stable_candidate_enter":
                candidates[key].append(number(row["timestamp"]))
            elif row["event"] == "stable_confirmed":
                confirmed[key].append(number(row["timestamp"]))
        invalid = []
        expected = set(dispatch)
        if not expected or {uid for _, uid in expected} != set(map(int, uav_ids)):
            invalid.append("missing_dispatch")
        arrival_stage = []
        for key in sorted(expected):
            mission, uid = key
            reasons = []
            if mission not in set(map(int, mission_ids)):
                reasons.append("mission_id_mismatch")
            if len(confirmed[key]) > 1:
                reasons.append("conflicting_stable_confirmed")
            d = dispatch[key]
            rs = min(finite(reference_start[key]) or [math.nan])
            rf = min(finite(reference_finish[key]) or [math.nan])
            sc = min(finite(candidates[key]) or [math.nan])
            sf = min(finite(confirmed[key]) or [math.nan])
            for label, value in (
                ("reference_start_before_dispatch", rs),
                ("reference_finish_before_dispatch", rf),
                ("candidate_before_dispatch", sc),
                ("arrival_before_dispatch", sf),
            ):
                if math.isfinite(value) and value < d:
                    reasons.append(label)
            if not all(math.isfinite(v) for v in (d, rs, rf, sc, sf)):
                reasons.append("missing_required_timestamp")
            final_rows = [
                row for row in trajectories
                if int(number(row.get("mission_id"), 0)) == mission
                and int(number(row.get("uav_id"), -1)) == uid
            ]
            final_error = (
                number(final_rows[-1].get("final_position_error"))
                if final_rows else math.nan)
            settling = (
                number(final_rows[-1].get("elapsed_time"))
                if final_rows else math.nan)
            arrival = {
                **identity, "stage_id": stage_id, "mission_id": mission,
                "uav_id": uid, "dispatch_time": d,
                "reference_start_time": rs, "reference_finish_time": rf,
                "stable_candidate_time": sc, "stable_confirmed_time": sf,
                "stable_hold_time": sf - sc if all(
                    math.isfinite(v) for v in (sf, sc)) else math.nan,
                "final_position_error": final_error, "settling_time": settling,
                "valid": not reasons, "invalid_reason": ";".join(reasons),
            }
            arrival_stage.append(arrival)
            arrivals.append(arrival)
            invalid.extend(reasons)
        dispatch_values = finite(row["dispatch_time"] for row in arrival_stage)
        start_values = finite(row["reference_start_time"] for row in arrival_stage)
        finish_values = finite(row["reference_finish_time"] for row in arrival_stage)
        candidate_values = finite(
            row["stable_candidate_time"] for row in arrival_stage)
        stable_values = finite(
            row["stable_confirmed_time"] for row in arrival_stage)
        hold_values = finite(row["stable_hold_time"] for row in arrival_stage)
        all_finished = len(finish_values) == len(expected)
        all_stable = len(stable_values) == len(expected)
        slowest = (
            max(
                (row for row in arrival_stage
                 if math.isfinite(row["stable_confirmed_time"])),
                key=lambda row: row["stable_confirmed_time"])["uav_id"]
            if stable_values else "")
        row = {
            **identity, "stage_id": stage_id,
            "stage_start_time": stage_start,
            "assignment_complete_time": assignment,
            "first_command_dispatch_time": min(dispatch_values or [math.nan]),
            "last_command_dispatch_time": max(dispatch_values or [math.nan]),
            "reference_start_time": min(start_values or [math.nan]),
            "all_references_finished_time": (
                max(finish_values) if all_finished else math.nan),
            "all_uavs_stable_time": (
                max(stable_values) if all_stable else math.nan),
            "stage_end_time": stage_end,
            "planning_time": assignment - stage_start,
            "dispatch_time": (
                max(dispatch_values) - assignment if dispatch_values else math.nan),
            "reference_execution_time": (
                max(finish_values) - min(dispatch_values)
                if all_finished and dispatch_values else math.nan),
            "trajectory_finish_spread": (
                max(finish_values) - min(finish_values)
                if all_finished else math.nan),
            "stabilization_delay": (
                max(stable_values) - max(finish_values)
                if all_stable and all_finished else math.nan),
            "stable_hold_time": (
                mean(hold_values) if len(hold_values) == len(expected)
                else math.nan),
            "stable_arrival_spread": (
                max(stable_values) - min(stable_values)
                if all_stable else math.nan),
            "stage_wall_time": stage_end - stage_start,
            "slowest_uav_id": slowest, "valid": not invalid,
            "invalid_reason": ";".join(sorted(set(invalid))),
        }
        numeric = [
            row[key] for key in (
                "planning_time", "dispatch_time", "reference_execution_time",
                "trajectory_finish_spread", "stabilization_delay",
                "stable_hold_time", "stable_arrival_spread", "stage_wall_time")
        ]
        if any(math.isfinite(v) and v < 0 for v in numeric):
            row["valid"] = False
            row["invalid_reason"] += ";negative_completion_time"
        stages.append(row)
    return stages, arrivals


def stats(rows, metrics):
    output = []
    for task in TASK_NAMES:
        selected = [row for row in rows if row["task_type"] == task]
        for metric in metrics:
            values = finite(row.get(metric) for row in selected)
            q1, q3 = quantile(values, .25), quantile(values, .75)
            avg = mean(values)
            output.append({
                "task_type": task, "metric": metric, "count": len(values),
                "mean": avg, "std": stddev(values),
                "median": quantile(values, .5), "iqr": q3 - q1,
                "min": min(values) if values else math.nan,
                "max": max(values) if values else math.nan,
                "p90": quantile(values, .9), "p95": quantile(values, .95),
                "coefficient_of_variation": (
                    stddev(values) / avg if values and avg != 0 else math.nan),
            })
    return output


def outliers(rows, metrics):
    output = []
    reason_map = {
        "planning_time": "planning", "tracking_rmse": "tracking",
        "stabilization_delay": "stabilization",
        "iapf_active_duration": "IAPF", "mean_rtf": "RTF",
    }
    for task in TASK_NAMES:
        selected = [row for row in rows if row["task_type"] == task]
        for metric in metrics:
            values = finite(row.get(metric) for row in selected)
            q1, q3 = quantile(values, .25), quantile(values, .75)
            iqr = q3 - q1
            lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            for row in selected:
                value = number(row.get(metric))
                if not math.isfinite(value):
                    continue
                flagged = value < lower or value > upper
                output.append({
                    "task_type": task, "attempt_id": row["attempt_id"],
                    "metric": metric, "value": value, "q1": q1, "q3": q3,
                    "lower_bound": lower, "upper_bound": upper,
                    "is_outlier": flagged,
                    "reason": reason_map.get(metric, "other") if flagged else "",
                })
    return output


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--config", default=str(CONFIG_PATH))
    parser.add_argument("--results-root")
    parser.add_argument(
        "--execution-commit", default="unknown",
        help="Git commit used to execute the frozen formal batch")
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_yaml(Path(args.config).resolve())
    root = Path(args.results_root).resolve() if args.results_root else (
        REPO_ROOT / config["paths"]["results_root"]).resolve()
    batch = root / args.batch_id
    outcomes_path = batch / "formal_batch_outcomes.json"
    if not outcomes_path.exists():
        outcomes_path = batch / "pilot_batch_outcomes.json"
    outcomes = json.loads(outcomes_path.read_text(encoding="utf-8"))
    attempt_rows, readiness_rows, semantic_rows = [], [], []
    stage_rows, arrival_rows, analyzed = [], [], []
    for outcome in outcomes:
        trial_dir = Path(outcome["path"])
        manifest = json.loads(
            (trial_dir / "manifest.json").read_text(encoding="utf-8"))
        entered = bool(manifest.get("entered_execution"))
        attempt_rows.append({
            **{key: manifest.get(key, outcome.get(key, "")) for key in ATTEMPT_FIELDS},
            "run_order": outcome["run_order"],
            "trial_id": manifest.get("target_execution_index") if entered else "",
            "path": str(trial_dir),
        })
        readiness = trial_dir / "readiness_failure.json"
        if readiness.exists():
            payload = json.loads(readiness.read_text(encoding="utf-8"))
            for row in payload.get("uavs", []):
                readiness_rows.append({
                    "batch_id": args.batch_id, "task_type": manifest["task_type"],
                    "attempt_id": manifest["attempt_id"],
                    "condition": payload.get("condition", ""),
                    "readiness_success": False, **row,
                })
        elif manifest.get("failure_reason") != "simulator_startup_failure":
            readiness_rows.append({
                "batch_id": args.batch_id, "task_type": manifest["task_type"],
                "attempt_id": manifest["attempt_id"], "uav_id": "all",
                "condition": "all_checks", "readiness_success": True,
            })
        llm_path = trial_dir / "llm_metrics.json"
        if llm_path.exists():
            llm = json.loads(llm_path.read_text(encoding="utf-8"))
            for call in llm.get("attempts", []):
                semantic_rows.append({
                    "batch_id": args.batch_id, "task_type": manifest["task_type"],
                    "attempt_id": manifest["attempt_id"],
                    "llm_model": llm.get("llm_model", ""),
                    "raw_response_path": str(llm_path), **call,
                })
        if entered:
            stages, arrivals = timing_rows(trial_dir, manifest)
            stage_rows.extend(stages)
            arrival_rows.extend(arrivals)
            result = analyze_trial(trial_dir, config)
            analyzed.append(result)
            attempt_rows[-1].update({
                key: result["manifest"].get(key, attempt_rows[-1].get(key, ""))
                for key in (
                    "semantic_success", "execution_success", "safety_success",
                    "overall_success", "failure_reason")
            })
    summaries = batch / "summaries"
    write_csv(summaries / "attempt_summary.csv", attempt_rows, ATTEMPT_FIELDS)
    write_csv(summaries / "readiness_summary.csv", readiness_rows, READINESS_FIELDS)
    write_csv(summaries / "semantic_summary.csv", semantic_rows, SEMANTIC_FIELDS)
    write_csv(summaries / "stage_phase_timing.csv", stage_rows, STAGE_FIELDS)
    write_csv(summaries / "uav_arrival_summary.csv", arrival_rows, ARRIVAL_FIELDS)
    trial_metrics = []
    for result in analyzed:
        trial = result["trial"]
        matching = next(
            row for row in attempt_rows
            if row["task_type"] == trial["task_type"]
            and row["trial_id"] == trial["trial_id"])
        trial["attempt_id"] = matching["attempt_id"]
        trial_metrics.append(trial)
    mission_rows = []
    for attempt in [row for row in attempt_rows if row["entered_execution"]]:
        stages = [
            row for row in stage_rows if row["attempt_id"] == attempt["attempt_id"]]
        valid = [row for row in stages if row["valid"]]
        wall_times = finite(row["stage_wall_time"] for row in stages)
        mission_rows.append({
            "batch_id": args.batch_id, "task_type": attempt["task_type"],
            "attempt_id": attempt["attempt_id"], "trial_id": attempt["trial_id"],
            "stage_count": len(stages),
            "mission_wall_time": sum(wall_times),
            "stage_wall_time": sum(wall_times),
            **{
                metric: sum(number(row[metric], 0) for row in valid)
                for metric in (
                    "planning_time", "dispatch_time", "reference_execution_time",
                    "stabilization_delay", "stable_hold_time")
            },
            "trajectory_finish_spread": max(finite(
                row["trajectory_finish_spread"] for row in valid) or [math.nan]),
            "stable_arrival_spread": max(finite(
                row["stable_arrival_spread"] for row in valid) or [math.nan]),
        })
    by_attempt = {row["attempt_id"]: row for row in mission_rows}
    combined = []
    for trial in trial_metrics:
        row = {**trial, **by_attempt.get(trial["attempt_id"], {})}
        row["minimum_inter_agent_distance"] = row.get("min_distance")
        combined.append(row)
    metrics = [
        "planning_time", "reference_execution_time", "stabilization_delay",
        "stage_wall_time", "mission_wall_time", "trajectory_finish_spread",
        "stable_arrival_spread", "tracking_rmse",
        "minimum_inter_agent_distance", "mean_rtf",
    ]
    statistics = stats(combined, metrics)
    outlier_rows = outliers(
        combined, metrics + ["iapf_active_duration"])
    write_csv(summaries / "mission_timing_summary.csv", mission_rows, MISSION_FIELDS)
    write_csv(summaries / "tracking_summary.csv",
              [item for row in analyzed for item in row["tracking"]],
              TRACKING_FIELDS)
    write_csv(summaries / "safety_summary.csv",
              [row["safety"] for row in analyzed],
              SAFETY_FIELDS)
    write_csv(summaries / "resource_summary.csv",
              [row["resource"] for row in analyzed],
              RESOURCE_FIELDS)
    write_csv(summaries / "outlier_summary.csv", outlier_rows, OUTLIER_FIELDS)
    write_csv(summaries / "paper_task_table.csv", statistics, STAT_FIELDS)
    report = [
        f"# Experiment 10 v2 completion report: {args.batch_id}", "",
        "## Reproduction record", "",
        "- branch: `exp/10-system-8uav`",
        f"- execution code commit: `{args.execution_commit}`",
        f"- frozen configuration: `{batch / 'configuration' / 'full_system.yaml'}`",
        f"- data location: `{batch}`",
        "- run command: `source /opt/ros/humble/setup.bash && "
        "source /home/yihuang/learning/LLM_swarm_ws/install/setup.bash && "
        "/home/yihuang/learning/LLM_swarm_ws/llm_env/bin/python -u "
        "experiments/system_8uav/scripts/run_batch.py "
        f"--batch-id {args.batch_id} --phase formal --manage-sim`",
        "- completed successfully: yes", "",
        "## Attempt accounting", "",
        f"- attempts: {len(attempt_rows)}",
        f"- execution-entry trials: {len(mission_rows)}", "",
    ]
    for task in TASK_NAMES:
        attempts = [row for row in attempt_rows if row["task_type"] == task]
        entered = sum(bool_value(row["entered_execution"]) for row in attempts)
        succeeded = sum(bool_value(row["overall_success"]) for row in attempts)
        timeouts = sum(row["failure_reason"] == "stage_timeout" for row in attempts)
        report.append(
            f"- {task}: {entered} execution trials / {len(attempts)} attempts; "
            f"{succeeded} successful, {timeouts} stage timeouts")
    readiness_failures = sum(
        not bool_value(row["readiness_success"]) for row in readiness_rows)
    invalid_stages = [row for row in stage_rows if not bool_value(row["valid"])]
    invalid_arrivals = [row for row in arrival_rows if not bool_value(row["valid"])]
    negative_times = sum(
        number(row.get(metric), 0) < 0
        for row in stage_rows
        for metric in (
            "planning_time", "dispatch_time", "reference_execution_time",
            "trajectory_finish_spread", "stabilization_delay",
            "stable_hold_time", "stable_arrival_spread", "stage_wall_time")
    ) + sum(
        number(row.get(metric), 0) < 0
        for row in arrival_rows
        for metric in ("stable_hold_time", "settling_time")
    )
    config_checksums = {
        json.loads((Path(row["path"]) / "manifest.json").read_text(
            encoding="utf-8")).get("config_checksum", "")
        for row in attempt_rows
    }
    prompts_per_task = {
        task: len({
            json.loads((Path(row["path"]) / "manifest.json").read_text(
                encoding="utf-8")).get("command_text", "")
            for row in attempt_rows if row["task_type"] == task
        })
        for task in TASK_NAMES
    }
    report.extend([
        "", "## Validation", "",
        f"- readiness failures: {readiness_failures}",
        f"- valid stage rows: {len(stage_rows) - len(invalid_stages)} / {len(stage_rows)}",
        f"- valid UAV arrival rows: {len(arrival_rows) - len(invalid_arrivals)} / {len(arrival_rows)}",
        f"- negative completion or arrival times: {negative_times}",
        f"- distinct configuration checksums: {len(config_checksums)}",
        "- distinct prompts per task: " + ", ".join(
            f"{task}={count}" for task, count in prompts_per_task.items()),
        "- the configured model does not support a fixed seed; model output may remain stochastic.",
        "- invalid rows remain in the CSV files with explicit reasons; they are not imputed.",
        "", "Outliers are flagged with the frozen 1.5×IQR rule and are not removed.",
        "The legacy and v2 batches are not pooled because parser and stability semantics differ.",
    ])
    summaries.mkdir(parents=True, exist_ok=True)
    (summaries / "completion_report.md").write_text(
        "\n".join(report) + "\n", encoding="utf-8")
    manifest_root = batch / "manifests"
    manifest_root.mkdir(parents=True, exist_ok=True)
    for attempt in attempt_rows:
        source = Path(attempt["path"]) / "manifest.json"
        destination = manifest_root / f"{attempt['attempt_id']}.json"
        destination.write_bytes(source.read_bytes())
    print(f"generated v2 summaries for {len(attempt_rows)} attempts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
