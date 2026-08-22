#!/usr/bin/env python3
"""Check C0-E candidate mappings without changing the production loader."""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "lfs_policy"))
from lfs_policy import load_paper_policy  # noqa: E402

S_VALUES = (1.00, 1.25, 1.50, 1.75, 2.00)


def mapping(safety: dict, s: float) -> tuple[float, float, float, float]:
    hard = safety["d_hard"]
    plan = hard + s * (safety["d_plan_base"] - hard)
    enter = hard + s * (safety["iapf_enter_base"] - hard)
    exit_ = hard + s * (safety["iapf_exit_base"] - hard)
    repulsion = safety["iapf_repulsion_base"] + safety["iapf_repulsion_margin"] * (s - 1.0)
    return plan, enter, exit_, repulsion


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("policy", type=Path)
    parser.add_argument("--csv", type=Path, required=True)
    args = parser.parse_args()
    raw = yaml.safe_load(args.policy.read_text())
    # This intentionally invokes the unmodified production parser/guards.
    load_paper_policy(args.policy)
    safety, clamps = raw["safety"], raw["controller_hard_clamps"]
    rows = []
    for s in S_VALUES:
        plan, enter, exit_, repulsion = mapping(safety, s)
        passed = (
            safety["d_hard"] < enter < exit_ <= plan
            and clamps["iapf_enter_min"] > safety["d_hard"]
            and clamps["iapf_enter_min"] <= enter <= clamps["iapf_enter_max"]
            and exit_ <= clamps["iapf_exit_max"]
            and 0.0 <= repulsion <= clamps["iapf_repulsion_max"]
        )
        rows.append({"s": f"{s:.2f}", "d_plan_m": f"{plan:.6f}",
                     "d_enter_m": f"{enter:.6f}", "d_exit_m": f"{exit_:.6f}",
                     "k_rep": f"{repulsion:.6f}", "pass": str(passed).upper()})
    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with args.csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader(); writer.writerows(rows)
    if not all(row["pass"] == "TRUE" for row in rows):
        raise SystemExit("C0-E static mapping check failed")
    print("PASS")


if __name__ == "__main__":
    raise SystemExit(main())
