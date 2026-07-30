#!/usr/bin/env python3
"""Validate the frozen 16-arm experiment 09 pilot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


VARIANTS = ["B0", "P", "E", "Full"]
SCENARIOS = [
    "s1_crossing_4", "s1_crossing_8", "s2_dense_local_bias",
    "s3_staggered_dynamic_crossing",
]


def validate(batch_dir: Path) -> None:
    summaries = sorted(batch_dir.glob("raw/**/trial_summary.csv"))
    if len(summaries) != 16:
        raise ValueError(f"expected 16 pilot summaries, found {len(summaries)}")
    data = pd.concat([pd.read_csv(path) for path in summaries], ignore_index=True)
    expected = {(scenario, variant) for scenario in SCENARIOS for variant in VARIANTS}
    actual = set(zip(data["scenario"], data["variant"]))
    if actual != expected:
        raise ValueError(f"pilot matrix mismatch: missing={expected-actual}, extra={actual-expected}")
    for scenario, group in data.groupby("scenario"):
        if group["paired_input_digest"].nunique() != 1:
            raise ValueError(f"{scenario}: variants did not share paired inputs")
        by_variant = group.set_index("variant")
        for variant in ("B0", "E"):
            if by_variant.loc[variant, "assignment_mode"] != "distance_hungarian":
                raise ValueError(f"{scenario}/{variant}: wrong assignment mode")
        for variant in ("P", "Full"):
            if by_variant.loc[variant, "assignment_mode"] != "safety_aware":
                raise ValueError(f"{scenario}/{variant}: wrong assignment mode")
        for variant in ("B0", "P"):
            row = by_variant.loc[variant]
            if (
                float(row["iapf_activation_count"]) != 0.0
                or float(row["max_position_offset"]) != 0.0
                or float(row["max_acceleration_offset"]) != 0.0
            ):
                raise ValueError(f"{scenario}/{variant}: off mode intervened")
        for variant in ("E", "Full"):
            trial = next(
                path.parent for path in summaries
                if path.parent.parent.name == variant
                and path.parent.parent.parent.name == scenario)
            debug = pd.read_csv(trial / "iapf_debug.csv")
            if debug.empty or set(debug["avoidance_mode"]) != {"iapf_dual"}:
                raise ValueError(f"{scenario}/{variant}: invalid IAPF debug stream")
    for path in batch_dir.glob("raw/**/run_metadata.json"):
        if "_failed_attempt_" in str(path):
            continue
        metadata = json.loads(path.read_text(encoding="utf-8"))
        if metadata.get("outcome", {}).get("node_crash"):
            raise ValueError(f"{path.parent}: node crash")
        rtf = metadata.get("rtf_summary", {}).get("rtf")
        if rtf is not None and float(rtf) <= 0.0:
            raise ValueError(f"{path.parent}: invalid RTF")
    s3 = data[data["scenario"] == "s3_staggered_dynamic_crossing"].set_index("variant")
    if not (
        s3.loc["P", "nominal_proximity_crossings"]
        < s3.loc["B0", "nominal_proximity_crossings"]
        and s3.loc["P", "predicted_min_distance"]
        >= s3.loc["B0", "predicted_min_distance"] + 0.3
    ):
        raise ValueError("S3 planning-layer pilot acceptance criterion failed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("batch_dir", type=Path)
    args = parser.parse_args()
    validate(args.batch_dir)
    marker = args.batch_dir / "PILOT_ACCEPTED"
    marker.write_text("experiment 09 pilot accepted\n", encoding="utf-8")
    print(marker)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
