#!/usr/bin/env python3
"""Side-effect-free constants and parking layout for the supplementary study."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[3]
PROTOCOL = ROOT / "infrastructure/large_swarm_infrastructure_sweep_protocol.yaml"
RESULTS = ROOT / "results/infrastructure_sweep"
POLICY = REPO / "lfs_policy/config/lfs_policy.paper_current.yaml"
SIZES = (20, 24, 28, 32)
SHOWCASE_SIZES = (24, 28, 32)
BASELINE = "6cf402debf23851b1eff3edc6f3ab49eae7127c4"
POLICY_SHA = "6b47d27f4253d7311e79ea51f6dd1cf0d0182e6df24374a94abae0aa6a135858"
E5_SOURCE = "558def6238826460cb3f9323af445e8c299fb610"
E5_ANALYSIS = "bc760d5795ff87c62df6e86875d9a906cc449e2d"
WORKSPACE_LOWER = (-15.0, -10.0, 0.5)
WORKSPACE_UPPER = (15.0, 35.0, 15.0)
D_HARD = 1.5
D_PLAN = 1.8


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def parking_layout(n: int, altitude: float = 0.83) -> list[dict[str, Any]]:
    if n not in SIZES and n not in SHOWCASE_SIZES:
        raise ValueError("supplementary N must be one of 20, 24, 28, 32")
    rows = math.ceil(n / 8)
    output = []
    uid = 1
    for row in range(rows):
        count = min(8, n - len(output))
        y = 12.5 + 3.0 * (row - (rows - 1) / 2.0)
        for column in range(count):
            x = 3.0 * (column - (count - 1) / 2.0)
            output.append({"uav_id": uid, "x": x, "y": y, "z": altitude})
            uid += 1
    assert len(output) == n
    return output


def minimum_distance(layout: list[dict[str, Any]]) -> float:
    return min(
        math.dist((a["x"], a["y"], a["z"]), (b["x"], b["y"], b["z"]))
        for index, a in enumerate(layout) for b in layout[index + 1:]
    )


def layout_audit() -> dict[str, Any]:
    rows = []
    for n in SIZES:
        layout = parking_layout(n)
        spacing = minimum_distance(layout)
        inside = all(
            WORKSPACE_LOWER[0] <= p["x"] <= WORKSPACE_UPPER[0]
            and WORKSPACE_LOWER[1] <= p["y"] <= WORKSPACE_UPPER[1]
            and WORKSPACE_LOWER[2] <= p["z"] <= WORKSPACE_UPPER[2]
            for p in layout
        )
        rows.append({
            "N": n, "positions": layout, "workspace_fit": inside,
            "minimum_pairwise_spacing_m": spacing,
            "spacing_strictly_above_d_plan": spacing > D_PLAN,
            "spawn_overlap": spacing <= 0.0,
            "bounds": {
                "x": [min(p["x"] for p in layout), max(p["x"] for p in layout)],
                "y": [min(p["y"] for p in layout), max(p["y"] for p in layout)],
                "z": [min(p["z"] for p in layout), max(p["z"] for p in layout)],
            },
            "layout_sha256": canonical_sha256(layout),
        })
    return {
        "schema": "large_swarm_parking_layout_audit_v1",
        "status": "PASS" if all(r["workspace_fit"] and r["spacing_strictly_above_d_plan"] and not r["spawn_overlap"] for r in rows) else "FAIL",
        "frozen_before_first_smoke": True, "workspace_lower": WORKSPACE_LOWER,
        "workspace_upper": WORKSPACE_UPPER, "d_plan_m": D_PLAN,
        "layout_rule": "row-major; max 8 per centered row; centered rows; 3.0 m spacing",
        "rows": rows,
    }
