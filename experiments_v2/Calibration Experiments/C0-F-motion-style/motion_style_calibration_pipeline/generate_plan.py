#!/usr/bin/env python3
"""Materialize the fixed, non-Cartesian C0-F calibration plan."""
from __future__ import annotations

import csv

from common import RESULTS, SCENES_FILE, STYLES, load_yaml


def main() -> None:
    definitions = load_yaml(SCENES_FILE)
    rows = []
    for scene_id, scene in definitions["scenes"].items():
        for style in STYLES:
            rows.append({
                "trial_key": f"screening_{scene_id}_{style}_cold1",
                "stage": "screening", "scene": scene_id, "style": style,
                "cold_start": 1, "seed": definitions["seed_policy"]["screening"],
                "uav_count": len(scene["participants"]),
                "time_mode": scene["time_request"]["mode"],
                "control_mode": definitions["common"]["control_mode"],
            })
    rows.append({"trial_key": "style_switch_screening", "stage": "style_switch_screening",
                 "scene": "SWITCH", "style": "style_switch", "cold_start": 1,
                 "seed": definitions["seed_policy"]["screening"],
                 "uav_count": len(definitions["style_switch"]["participants"]),
                 "time_mode": "explicit", "control_mode": definitions["common"]["control_mode"]})
    for scene_id, scene in definitions["scenes"].items():
        for style in STYLES:
            for cold in (1, 2):
                rows.append({
                    "trial_key": f"confirmation_{scene_id}_{style}_cold{cold}",
                    "stage": "confirmation", "scene": scene_id, "style": style,
                    "cold_start": cold,
                    "seed": definitions["seed_policy"][f"confirmation_cold_{cold}"],
                    "uav_count": len(scene["participants"]),
                    "time_mode": scene["time_request"]["mode"],
                    "control_mode": definitions["common"]["control_mode"],
                })
    rows.append({"trial_key": "style_switch_confirmation", "stage": "style_switch_confirmation",
                 "scene": "SWITCH", "style": "style_switch", "cold_start": 1,
                 "seed": definitions["seed_policy"]["confirmation_cold_1"],
                 "uav_count": len(definitions["style_switch"]["participants"]),
                 "time_mode": "explicit", "control_mode": definitions["common"]["control_mode"]})
    RESULTS.mkdir(parents=True, exist_ok=True)
    path = RESULTS / "calibration_plan.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys(), lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


if __name__ == "__main__":
    main()
