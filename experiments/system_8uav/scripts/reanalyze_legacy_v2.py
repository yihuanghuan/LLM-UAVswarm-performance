#!/usr/bin/env python3
"""Read-only reanalysis of recoverable timing fields in the legacy formal batch."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from system_common import read_csv, write_csv

FIELDS = [
    "task_type", "trial_id", "stage_id", "first_command_dispatch_time",
    "all_references_finished_time", "trajectory_finish_spread",
    "stage_end_time", "stabilization_delay",
    "stable_arrival_spread", "stable_arrival_spread_status",
]


def number(value, default=math.nan):
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (TypeError, ValueError):
        return default


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch_root", type=Path)
    args = parser.parse_args()
    batch = args.batch_root.resolve()
    output = batch / "reanalysis_v2"
    rows = []
    for trial in sorted((batch / "raw").glob("task_*/trial_*")):
        manifest = json.loads((trial / "manifest.json").read_text(encoding="utf-8"))
        events = read_csv(trial / "mission_events.csv")
        commands = read_csv(trial / "swarm_commands.csv")
        trajectory = read_csv(trial / "trajectory_metrics.csv")
        for start in [row for row in events if row["event"] == "stage_start"]:
            stage_id = int(number(start["stage_id"], 0))
            missions = set(map(int, json.loads(start.get("mission_ids") or "[]")))
            dispatched = [
                number(row["timestamp"]) for row in commands
                if int(number(row["mission_id"], 0)) in missions]
            finishes = {}
            for row in trajectory:
                mission = int(number(row["mission_id"], 0))
                uid = int(number(row["uav_id"], -1))
                if mission in missions and str(row.get("is_finished", "")).lower() == "true":
                    finishes.setdefault((mission, uid), number(row["timestamp"]))
            end = next((
                row for row in events
                if row["event"] == "stage_end"
                and int(number(row["stage_id"], 0)) == stage_id), None)
            end_time = number(end["timestamp"]) if end else math.nan
            finish_values = list(finishes.values())
            all_finish = max(finish_values) if finish_values else math.nan
            rows.append({
                "task_type": manifest["task_type"],
                "trial_id": manifest["trial_id"], "stage_id": stage_id,
                "first_command_dispatch_time": min(dispatched or [math.nan]),
                "all_references_finished_time": all_finish,
                "trajectory_finish_spread": (
                    max(finish_values) - min(finish_values)
                    if finish_values else math.nan),
                "stage_end_time": end_time,
                "stabilization_delay": (
                    end_time - all_finish
                    if math.isfinite(end_time) and math.isfinite(all_finish)
                    else math.nan),
                "stable_arrival_spread": math.nan,
                "stable_arrival_spread_status":
                    "not_recoverable_from_existing_logs",
            })
    write_csv(output / "legacy_stage_timing.csv", rows, FIELDS)
    output.mkdir(parents=True, exist_ok=True)
    (output / "README.md").write_text(
        "# Legacy batch v2 reanalysis\n\n"
        "Existing command and trajectory streams recover dispatch, reference "
        "finish, trajectory spread, and stage-level stabilization delay. "
        "Per-UAV stable-confirmed timestamps were not logged and the recorder "
        "could associate a pre-dispatch status with the next mission, so "
        "`stable_arrival_spread` is `not_recoverable_from_existing_logs`.\n",
        encoding="utf-8")
    print(f"wrote {len(rows)} legacy stage rows to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
