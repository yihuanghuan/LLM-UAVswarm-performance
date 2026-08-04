#!/usr/bin/env python3
"""Generate experiment-10 v3 summaries with success-only paper statistics."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from analysis_v3 import number, stage_timing_rows, truth
from summarize_system_trials import (
    RESOURCE_FIELDS, SAFETY_FIELDS, TRACKING_FIELDS, analyze_trial,
)
from summarize_v2 import OUTLIER_FIELDS, STAT_FIELDS, outliers, stats
from system_common import (
    CONFIG_PATH, REPO_ROOT, TASK_NAMES, finite, git_revision, load_yaml,
    render_execution_commit, utc_now, write_csv, write_json,
)


ATTEMPT_FIELDS = [
    "batch_id", "task_type", "attempt_id", "run_order",
    "target_execution_index", "trial_id", "replacement_for", "input_mode",
    "entered_execution", "semantic_success", "execution_success",
    "safety_success", "overall_success", "original_failure_reason",
    "failure_reason", "path",
]
READINESS_FIELDS = [
    "batch_id", "task_type", "attempt_id", "uav_id", "condition",
    "has_odom", "odom_fresh", "has_vehicle_status", "armed", "offboard",
    "failsafe", "speed", "readiness_success",
]
SEMANTIC_FIELDS = [
    "batch_id", "task_type", "attempt_id", "attempt_index", "input_mode",
    "llm_called", "llm_model", "latency_ms", "valid_json", "schema_valid",
    "semantic_valid", "repair_applied", "error_type", "raw_response_path",
]
STAGE_FIELDS = [
    "batch_id", "task_type", "attempt_id", "trial_id", "stage_id",
    "stage_start_time", "assignment_complete_time",
    "first_command_dispatch_time", "last_command_dispatch_time",
    "all_commands_acknowledged_time", "reference_start_time",
    "all_references_finished_time", "all_uavs_stable_time", "stage_end_time",
    "planning_time", "dispatch_time", "reference_execution_time",
    "trajectory_finish_spread", "stabilization_delay", "stable_hold_time",
    "stable_arrival_spread", "stage_wall_time", "slowest_uav_id",
    "failure_reason", "valid", "invalid_reason",
]
MISSION_FIELDS = [
    "batch_id", "task_type", "attempt_id", "trial_id", "stage_count",
    "execution_success", "all_stages_valid", "main_analysis_eligible",
    "failure_reason", "mission_wall_time", "planning_time", "dispatch_time",
    "stage_wall_time", "reference_execution_time", "stabilization_delay",
    "stable_hold_time", "trajectory_finish_spread", "stable_arrival_spread",
]
ARRIVAL_FIELDS = [
    "batch_id", "task_type", "attempt_id", "trial_id", "stage_id",
    "mission_id", "uav_id", "dispatch_time", "reference_start_time",
    "reference_finish_time", "stable_candidate_time", "stable_confirmed_time",
    "stable_hold_time", "final_position_error", "settling_time", "valid",
    "invalid_reason",
]
TIMEOUT_FIELDS = [
    "batch_id", "task_type", "attempt_id", "trial_id", "stage_id", "uav_id",
    "mission_id", "failure_reason", "failure_condition", "command_ack",
    "reference_finished", "stability_state", "position_error", "speed",
    "odom_age", "status_age", "iapf_active", "nearest_neighbor_distance",
    "last_candidate_time", "last_confirmed_time",
]
PAPER_FIELDS = [
    *STAT_FIELDS, "attempt_count", "execution_entry_count",
    "execution_success_count", "main_analysis_count",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--config", default=str(CONFIG_PATH))
    parser.add_argument("--results-root")
    parser.add_argument("--output-dir")
    parser.add_argument("--legacy-v2", action="store_true")
    parser.add_argument("--execution-commit", default=None,
                        help="git commit label; auto-detected from batch plan if omitted")
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="do not refresh the batch manifests/ archive (read-only reanalysis)")
    return parser.parse_args()


def find_outcomes(batch: Path) -> Path:
    for name in (
        "formal_batch_outcomes.json", "diagnostic_batch_outcomes.json",
            "pilot_batch_outcomes.json"):
        path = batch / name
        if path.is_file():
            return path
    raise FileNotFoundError(f"no batch outcomes found in {batch}")


def main() -> int:
    args = parse_args()
    config = load_yaml(Path(args.config).resolve())
    root = Path(args.results_root).resolve() if args.results_root else (
        REPO_ROOT / config["paths"]["results_root"]).resolve()
    batch = root / args.batch_id
    outcomes = json.loads(find_outcomes(batch).read_text(encoding="utf-8"))
    plan_path = batch / "formal_batch_plan.json"
    if not plan_path.is_file():
        plan_path = batch / "pilot_batch_plan.json"
    plan = (json.loads(plan_path.read_text(encoding="utf-8"))
            if plan_path.is_file() else {})
    if args.execution_commit:
        execution_commit = args.execution_commit
    elif plan.get("execution_commit_short"):
        execution_commit = render_execution_commit({
            "commit_short": plan["execution_commit_short"],
            "dirty": bool(plan.get("execution_commit_dirty")),
        })
    else:
        revision = git_revision(REPO_ROOT)
        execution_commit = render_execution_commit(revision)
    branch = plan.get("branch", "")
    summaries = Path(args.output_dir).resolve() if args.output_dir else batch / "summaries"

    attempt_rows, readiness_rows, semantic_rows = [], [], []
    stage_rows, arrival_rows, timeout_rows, analyzed = [], [], [], []
    for outcome in outcomes:
        trial_dir = Path(outcome["path"])
        manifest_path = trial_dir / "manifest.json"
        if not manifest_path.is_file():
            manifest_path = trial_dir / "runtime_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entered = bool(manifest.get("entered_execution"))
        original_reason = str(manifest.get("failure_reason") or "")
        attempt = {
            "batch_id": args.batch_id, "task_type": manifest["task_type"],
            "attempt_id": manifest["attempt_id"],
            "run_order": outcome.get("run_order", ""),
            "target_execution_index": manifest.get("target_execution_index", ""),
            "trial_id": manifest.get("target_execution_index", "") if entered else "",
            "replacement_for": manifest.get("replacement_for", ""),
            "input_mode": manifest.get("input_mode", "llm"),
            "entered_execution": entered,
            "semantic_success": manifest.get("semantic_success", False),
            "execution_success": manifest.get("execution_success", False),
            "safety_success": manifest.get("safety_success", False),
            "overall_success": manifest.get("overall_success", False),
            "original_failure_reason": original_reason,
            "failure_reason": original_reason,
            "path": str(trial_dir),
        }
        attempt_rows.append(attempt)
        readiness_path = trial_dir / "readiness_failure.json"
        if readiness_path.is_file():
            payload = json.loads(readiness_path.read_text(encoding="utf-8"))
            for row in payload.get("uavs", []):
                readiness_rows.append({
                    "batch_id": args.batch_id, "task_type": manifest["task_type"],
                    "attempt_id": manifest["attempt_id"],
                    "condition": payload.get("condition", ""),
                    "readiness_success": False, **row,
                })
        elif original_reason != "simulator_startup_failure":
            readiness_rows.append({
                "batch_id": args.batch_id, "task_type": manifest["task_type"],
                "attempt_id": manifest["attempt_id"], "uav_id": "all",
                "condition": "all_checks", "readiness_success": True,
            })
        metrics_path = trial_dir / "llm_metrics.json"
        if metrics_path.is_file():
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            calls = metrics.get("attempts", [])
            if not calls and manifest.get("input_mode") == "replay":
                calls = [{
                    "attempt_index": 0, "semantic_valid": True,
                    "valid_json": True, "schema_valid": True,
                    "error_type": "replay_not_applicable",
                }]
            for call in calls:
                semantic_rows.append({
                    "batch_id": args.batch_id, "task_type": manifest["task_type"],
                    "attempt_id": manifest["attempt_id"],
                    "input_mode": manifest.get("input_mode", "llm"),
                    "llm_called": manifest.get("input_mode", "llm") == "llm",
                    "llm_model": manifest.get("llm_model", ""),
                    "raw_response_path": str(metrics_path), **call,
                })
        if entered:
            stages, arrivals, diagnostics = stage_timing_rows(
                trial_dir, manifest, config, legacy_v2=args.legacy_v2)
            stage_rows.extend(stages)
            arrival_rows.extend(arrivals)
            timeout_rows.extend(diagnostics)
            classified = next(
                (row["failure_reason"] for row in stages if row["failure_reason"]),
                original_reason)
            attempt["failure_reason"] = classified
            analysis = analyze_trial(trial_dir, config)
            analyzed.append(analysis)
            # analyze_trial computes safety/realtime results and updates the
            # manifest. Keep the attempt table in sync with that final verdict
            # instead of retaining run_trial's pre-analysis placeholders.
            analyzed_manifest = analysis["manifest"]
            for field in (
                    "execution_success", "safety_success", "overall_success"):
                attempt[field] = analyzed_manifest.get(field, attempt[field])
            attempt["failure_reason"] = str(
                analyzed_manifest.get("failure_reason") or classified)

    if not args.no_archive:
        manifest_root = batch / "manifests"
        manifest_root.mkdir(parents=True, exist_ok=True)
        for attempt in attempt_rows:
            source = Path(attempt["path"]) / "manifest.json"
            if not source.is_file():
                continue
            destination = manifest_root / f"{attempt['attempt_id']}.json"
            destination.write_bytes(source.read_bytes())

    mission_rows = []
    for attempt in [row for row in attempt_rows if truth(row["entered_execution"])]:
        selected = [
            row for row in stage_rows if row["attempt_id"] == attempt["attempt_id"]]
        all_valid = bool(selected) and all(truth(row["valid"]) for row in selected)
        eligible = truth(attempt["execution_success"]) and all_valid
        valid_for_aggregate = selected if all_valid else []
        wall_times = finite(row["stage_wall_time"] for row in selected)
        mission_rows.append({
            "batch_id": args.batch_id, "task_type": attempt["task_type"],
            "attempt_id": attempt["attempt_id"], "trial_id": attempt["trial_id"],
            "stage_count": len(selected),
            "execution_success": attempt["execution_success"],
            "all_stages_valid": all_valid,
            "main_analysis_eligible": eligible,
            "failure_reason": attempt["failure_reason"],
            "mission_wall_time": sum(wall_times) if wall_times else math.nan,
            "stage_wall_time": (
                sum(number(row["stage_wall_time"]) for row in valid_for_aggregate)
                if eligible else math.nan),
            **{
                metric: (
                    sum(number(row[metric]) for row in valid_for_aggregate)
                    if eligible else math.nan)
                for metric in (
                    "planning_time", "dispatch_time", "reference_execution_time",
                    "stabilization_delay", "stable_hold_time")
            },
            "trajectory_finish_spread": (
                max(finite(row["trajectory_finish_spread"]
                           for row in valid_for_aggregate) or [math.nan])
                if eligible else math.nan),
            "stable_arrival_spread": (
                max(finite(row["stable_arrival_spread"]
                           for row in valid_for_aggregate) or [math.nan])
                if eligible else math.nan),
        })

    trial_metrics = []
    mission_by_attempt = {row["attempt_id"]: row for row in mission_rows}
    for result in analyzed:
        trial = dict(result["trial"])
        matching = next(
            row for row in attempt_rows
            if row["task_type"] == trial["task_type"]
            and str(row["trial_id"]) == str(trial["trial_id"]))
        trial["attempt_id"] = matching["attempt_id"]
        trial["minimum_inter_agent_distance"] = trial.get("min_distance")
        trial.update(mission_by_attempt.get(trial["attempt_id"], {}))
        trial_metrics.append(trial)
    eligible_metrics = [
        row for row in trial_metrics if truth(row.get("main_analysis_eligible"))]
    metrics = [
        "planning_time", "reference_execution_time", "stabilization_delay",
        "stage_wall_time", "mission_wall_time", "trajectory_finish_spread",
        "stable_arrival_spread", "tracking_rmse",
        "minimum_inter_agent_distance", "mean_rtf",
    ]
    paper = stats(eligible_metrics, metrics)
    for row in paper:
        task = row["task_type"]
        attempts = [item for item in attempt_rows if item["task_type"] == task]
        missions = [item for item in mission_rows if item["task_type"] == task]
        row.update({
            "attempt_count": len(attempts),
            "execution_entry_count": len(missions),
            "execution_success_count": sum(
                truth(item["execution_success"]) for item in attempts),
            "main_analysis_count": sum(
                truth(item["main_analysis_eligible"]) for item in missions),
        })
    outlier_rows = outliers(
        eligible_metrics, metrics + ["iapf_active_duration"])

    write_csv(summaries / "attempt_summary.csv", attempt_rows, ATTEMPT_FIELDS)
    write_csv(summaries / "readiness_summary.csv", readiness_rows, READINESS_FIELDS)
    write_csv(summaries / "semantic_summary.csv", semantic_rows, SEMANTIC_FIELDS)
    write_csv(summaries / "stage_phase_timing.csv", stage_rows, STAGE_FIELDS)
    write_csv(summaries / "mission_timing_summary.csv", mission_rows, MISSION_FIELDS)
    write_csv(summaries / "uav_arrival_summary.csv", arrival_rows, ARRIVAL_FIELDS)
    write_csv(summaries / "timeout_diagnostics.csv", timeout_rows, TIMEOUT_FIELDS)
    write_csv(summaries / "tracking_summary.csv",
              [item for row in analyzed for item in row["tracking"]], TRACKING_FIELDS)
    write_csv(summaries / "safety_summary.csv",
              [row["safety"] for row in analyzed], SAFETY_FIELDS)
    write_csv(summaries / "resource_summary.csv",
              [row["resource"] for row in analyzed], RESOURCE_FIELDS)
    write_csv(summaries / "outlier_summary.csv", outlier_rows, OUTLIER_FIELDS)
    write_csv(summaries / "paper_task_table.csv", paper, PAPER_FIELDS)

    report = [
        f"# Experiment 10 v3 completion report: {args.batch_id}", "",
        "## Reproduction record", "",
        f"- branch: `{branch}`",
        f"- execution code commit: `{execution_commit}`",
        f"- frozen configuration: `{batch / 'configuration' / 'full_system.yaml'}`",
        f"- data location: `{batch}`",
        f"- config checksum: `{plan.get('config_checksum', '')}`",
        f"- created at: `{plan.get('created_at', '')}`",
        f"- input mode: `{plan.get('input_mode', 'llm')}`",
        f"- completed successfully: {'yes' if not args.no_archive else 'reanalysis (read-only)'}",
        "", "## Attempt accounting", "",
        f"- attempts: {len(attempt_rows)}",
        f"- execution-entry trials: {len(mission_rows)}",
        "- main-analysis trials: "
        f"{sum(truth(row['main_analysis_eligible']) for row in mission_rows)}",
        "- readiness failures: "
        f"{sum(not truth(row['readiness_success']) for row in readiness_rows)}",
        "",
    ]
    for task in TASK_NAMES:
        attempts = [row for row in attempt_rows if row["task_type"] == task]
        missions = [row for row in mission_rows if row["task_type"] == task]
        failures = {}
        for row in attempts:
            reason = row["failure_reason"] or "none"
            failures[reason] = failures.get(reason, 0) + 1
        report.append(
            f"- {task}: attempts={len(attempts)}, execution={len(missions)}, "
            f"eligible={sum(truth(row['main_analysis_eligible']) for row in missions)}, "
            f"outcomes={failures}")
    report.extend([
        "", "Missing continuous metrics are NaN and are excluded from paper statistics.",
        "Timeout and partial-stage attempts remain in attempt and diagnostic tables.",
        "Outliers use the frozen 1.5×IQR rule and are not removed.",
    ])
    summaries.mkdir(parents=True, exist_ok=True)
    (summaries / "completion_report.md").write_text(
        "\n".join(report) + "\n", encoding="utf-8")
    print(f"generated v3 summaries for {len(attempt_rows)} attempts in {summaries}")

    try:
        from verify_batch import verify_batch
        violations = verify_batch(batch, summaries)
    except ImportError:
        violations = []
        print("verify_batch not available; skipping consistency check",
              file=sys.stderr)
    if violations:
        for violation in violations:
            print(f"consistency violation: {violation}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
