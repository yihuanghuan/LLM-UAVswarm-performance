#!/usr/bin/env python3
"""Freeze C0-B freshness thresholds from a recorded baseline campaign only."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
EXPERIMENT = ROOT.parent
REPO = ROOT.parents[3]
FIELDS = ("timestamp", "scenario", "uav_count", "uav_id", "state_age_ms",
          "snapshot_skew_ms", "planner_wait_ms")


def load_yaml(path: Path):
    with path.open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
        ).strip()
    except subprocess.SubprocessError:
        return "unavailable"


def percentile(values, value):
    """Linear percentile, explicitly defined to make the freeze reproducible."""
    ordered = sorted(float(item) for item in values)
    if not ordered:
        raise ValueError("cannot calculate a percentile of no measurements")
    position = (len(ordered) - 1) * float(value) / 100.0
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def read_measurements(paths, campaign):
    rows = []
    for path in paths:
        with path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            if set(FIELDS) - set(reader.fieldnames or ()):
                raise ValueError(f"measurement CSV lacks fields: {sorted(set(FIELDS) - set(reader.fieldnames or ()))}")
            rows.extend(reader)
    if not rows:
        raise ValueError("measurement CSV is empty")
    required = set(campaign["required_scenarios"])
    found = {row["scenario"] for row in rows}
    missing = required - found
    unexpected = found - required
    if missing or unexpected:
        raise ValueError(f"required scenarios missing={sorted(missing)} unexpected={sorted(unexpected)}")
    expected_counts = campaign["scenario_uav_counts"]
    for row in rows:
        if int(row["uav_count"]) != expected_counts[row["scenario"]]:
            raise ValueError(f"wrong uav_count for {row['scenario']}")
        for key in ("timestamp", "state_age_ms", "snapshot_skew_ms", "planner_wait_ms"):
            number = float(row[key])
            if not math.isfinite(number) or number < 0.0:
                raise ValueError(f"invalid {key} in measurement row")
    return rows


def validate(policy):
    """Exercise the existing state-snapshot gate; no production code is changed."""
    sys.path.insert(0, str(REPO / "location_allocate"))
    from location_allocate.state_snapshot import FreshStateSnapshotManager, SnapshotError

    timeout = policy["state_freshness"]["state_timeout_ms"] / 1000.0
    skew = policy["state_freshness"]["snapshot_skew_threshold_ms"] / 1000.0
    normal = FreshStateSnapshotManager(timeout, skew, require_velocity=True,
                                       allow_receive_time_fallback=False)
    normal.update(1, [0, 0, 1], 100.0, [0, 0, 0], 99.995)
    normal.update(2, [1, 0, 1], 100.0, [0, 0, 0], 99.997)
    normal.snapshot([1, 2], 100.0)

    stale = FreshStateSnapshotManager(timeout, skew, require_velocity=True,
                                      allow_receive_time_fallback=False)
    stale.update(1, [0, 0, 1], 100.0, [0, 0, 0], 100.0 - timeout - 0.001)
    stale_rejected = False
    try:
        stale.snapshot([1], 100.0)
    except SnapshotError as error:
        stale_rejected = "stale UAV states" in str(error)
    if not stale_rejected:
        raise RuntimeError("stale-state validation did not reject the state")
    return [
        {"case": "normal_operation", "status": "pass", "evidence": "fresh snapshot accepted"},
        {"case": "stale_state_rejection", "status": "pass", "evidence": "SnapshotError prevented snapshot/command resolution"},
    ]


def write_csv(path: Path, rows, fields):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def freeze(args):
    campaign_path = args.campaign.resolve()
    campaign = load_yaml(campaign_path)
    measurement_paths = [path.resolve() for path in args.measurements]
    measurements = read_measurements(measurement_paths, campaign)
    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()) and not args.overwrite:
        raise SystemExit(f"refusing to overwrite non-empty output: {output}")
    output.mkdir(parents=True, exist_ok=True)
    margin = float(campaign["selection_rule"]["safety_margin_ms"])
    pct = float(campaign["selection_rule"]["percentile"])
    selected = {
        "state_timeout_ms": percentile([row["state_age_ms"] for row in measurements], pct) + margin,
        "snapshot_skew_threshold_ms": percentile([row["snapshot_skew_ms"] for row in measurements], pct) + margin,
        "planner_wait_timeout_ms": percentile([row["planner_wait_ms"] for row in measurements], pct) + margin,
    }
    selected = {key: round(value, 3) for key, value in selected.items()}
    policy = {
        "state_freshness": selected,
        "selection_rule": {"percentile": f"P{pct:g}", "safety_margin_ms": margin,
                           "method": "linear percentile plus fixed safety margin"},
        "source_dataset": {"file": "freshness_measurements.csv", "rows": len(measurements),
                           "scenarios": campaign["required_scenarios"]},
        "freeze_status": "frozen",
    }
    validation = validate(policy)
    write_csv(output / "freshness_measurements.csv", measurements, FIELDS)
    plan_rows = [{"stage": "A", "scenario": name,
                  "purpose": "baseline freshness measurement", "parameter_changes": "none"}
                 for name in campaign["required_scenarios"]]
    plan_rows.extend([
        {"stage": "B", "scenario": "all", "purpose": "P99 + fixed margin selection", "parameter_changes": "none"},
        {"stage": "C", "scenario": "normal_operation", "purpose": "fresh acceptance", "parameter_changes": "frozen freshness policy only"},
        {"stage": "C", "scenario": "stale_state_rejection", "purpose": "reject stale state", "parameter_changes": "controlled timestamp delay only"},
    ])
    write_csv(output / "calibration_plan.csv", plan_rows, ("stage", "scenario", "purpose", "parameter_changes"))
    summary = []
    for metric, field in (("state_age_ms", "state_timeout_ms"), ("snapshot_skew_ms", "snapshot_skew_threshold_ms"), ("planner_wait_ms", "planner_wait_timeout_ms")):
        values = [float(row[metric]) for row in measurements]
        summary.append({"metric": metric, "samples": len(values), "p99_ms": round(percentile(values, pct), 3),
                        "safety_margin_ms": margin, "frozen_threshold_ms": selected[field]})
    write_csv(output / "trial_metrics.csv", summary, ("metric", "samples", "p99_ms", "safety_margin_ms", "frozen_threshold_ms"))
    write_csv(output / "validation_metrics.csv", validation, ("case", "status", "evidence"))
    (output / "frozen_state_freshness_policy.yaml").write_text(yaml.safe_dump(policy, sort_keys=False), encoding="utf-8")
    c0a = (REPO / campaign["c0a_frozen_policy"]).resolve()
    baseline = (REPO / campaign["baseline_policy"]).resolve()
    manifest = {"calibration_id": campaign["calibration_id"], "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "git_commit": git_commit(), "configuration_hashes": {"campaign": sha256(campaign_path), "baseline_policy": sha256(baseline), "c0a_frozen_policy": sha256(c0a)},
                "input_measurements_sha256": {str(path): sha256(path) for path in measurement_paths}, "validation": validation,
                "c0a_policy_modified": False, "algorithm_or_controller_modified": False}
    (output / "manifest.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    report = "# C0-B state freshness calibration report\n\n"
    report += "This freeze uses a single pre-declared P99-plus-margin rule; no task-performance metric or threshold search was used.\n\n"
    report += "## Frozen policy\n\n```yaml\n" + yaml.safe_dump(policy, sort_keys=False) + "```\n"
    report += "## Validation\n\n- Normal operation: pass — fresh states accepted.\n- Stale-state rejection: pass — a controlled stale timestamp raised `SnapshotError` before a snapshot could reach command resolution.\n"
    (output / "calibration_report.md").write_text(report, encoding="utf-8")
    print(json.dumps({"output": str(output), "policy": selected, "validation": "pass"}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("freeze", help="select and validate one frozen policy from baseline measurements")
    command.add_argument("--measurements", type=Path, required=True, nargs="+",
                         help="one raw baseline CSV per required scenario")
    command.add_argument("--campaign", type=Path, default=ROOT / "configs" / "campaign.yaml")
    command.add_argument("--output-dir", type=Path, default=EXPERIMENT / "results" / "C0-B_state_freshness_freeze")
    command.add_argument("--overwrite", action="store_true")
    command.set_defaults(func=freeze)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
