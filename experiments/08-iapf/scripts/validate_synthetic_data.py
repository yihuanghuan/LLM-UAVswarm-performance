#!/usr/bin/env python3
"""Run deterministic synthetic checks without ROS or Gazebo."""

import numpy as np

from analysis_core import event_count, pair_metrics, resample_odometry


def main() -> int:
    assert event_count([False, True, True, False]) == 1
    assert event_count([True, False, True]) == 2
    rows = []
    for uav_id, offset in ((1, 0.0), (2, 1.2)):
        for index in range(21):
            rows.append({
                "timestamp": index * 0.05 + (0.01 if uav_id == 2 else 0.0),
                "uav_id": uav_id, "x": offset, "y": 0.0, "z": 2.0,
            })
    timeline, positions = resample_odometry(rows, 20.0, 0.10)
    pairs, _ = pair_metrics(timeline, positions, 0.7, 1.0)
    assert pairs[0].violation_event_count == 0
    assert np.isclose(pairs[0].minimum_distance, 1.2)
    print("synthetic validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
