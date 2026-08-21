#!/usr/bin/env python3
"""Replay C0-B planner-equivalent wait from recorded snapshot timing rows."""
from __future__ import annotations

import argparse
import csv
import hashlib
import math
from collections import defaultdict
from pathlib import Path

import yaml


def percentile(values, value):
    ordered = sorted(values)
    position = (len(ordered) - 1) * value / 100.0
    lower, upper = math.floor(position), math.ceil(position)
    return ordered[lower] if lower == upper else ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--measurements", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    policy = yaml.safe_load(args.policy.read_text(encoding="utf-8"))["state_freshness"]
    timeout, skew = float(policy["state_timeout_ms"]), float(policy["snapshot_skew_threshold_ms"])
    with args.measurements.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    groups = defaultdict(list)
    for row in rows:
        groups[(row["scenario"], row["timestamp"])].append(row)
    starts, output = {}, []
    for (scenario, timestamp), group in sorted(groups.items(), key=lambda item: (item[0][0], float(item[0][1]))):
        if len(group) != int(group[0]["uav_count"]):
            continue
        timestamp = float(timestamp)
        fresh = (max(float(row["state_age_ms"]) for row in group) <= timeout and float(group[0]["snapshot_skew_ms"]) <= skew)
        if fresh:
            wait_ms = 0.0 if scenario not in starts else (timestamp - starts.pop(scenario)) * 1000.0
        else:
            wait_ms = 0.0 if scenario not in starts else (timestamp - starts[scenario]) * 1000.0
            starts.setdefault(scenario, timestamp)
        output.append({"timestamp": f"{timestamp:.9f}", "scenario": scenario, "fresh": str(fresh).lower(), "planner_wait_ms": f"{wait_ms:.6f}"})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=("timestamp", "scenario", "fresh", "planner_wait_ms"), lineterminator="\n")
        writer.writeheader(); writer.writerows(output)
    values = [float(row["planner_wait_ms"]) for row in output]
    summary = {"measurement_sha256": hashlib.sha256(args.measurements.read_bytes()).hexdigest(), "frozen_predicates_ms": {"state_timeout_ms": timeout, "snapshot_skew_threshold_ms": skew}, "samples": len(values), "p99_wait_ms": percentile(values, 99), "fixed_margin_ms": 10.0, "planner_wait_timeout_ms": percentile(values, 99) + 10.0}
    args.summary.write_text(yaml.safe_dump(summary, sort_keys=False), encoding="utf-8")
    print(yaml.safe_dump(summary, sort_keys=False), end="")


if __name__ == "__main__":
    main()
