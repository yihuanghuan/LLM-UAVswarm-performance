"""Fixed, preregistered configuration for Gazebo tracking experiment 06."""

from __future__ import annotations


SEED = 20260727
REPEATS = 5
METHODS = {
    "px4_step": {
        "trajectory_profile": "step",
        "enable_ladrc_accel_feedforward": False,
    },
    "linear_ladrc": {
        "trajectory_profile": "linear",
        "enable_ladrc_accel_feedforward": True,
    },
    "minimum_jerk_ladrc": {
        "trajectory_profile": "minimum_jerk",
        "enable_ladrc_accel_feedforward": True,
    },
}
SCENARIOS = {
    "single_uav": {
        "uav_ids": [0],
        "duration_s": 8.0,
        "targets": {0: (6.0, 0.0, 5.0)},
    },
    "five_uav_circle": {
        "uav_ids": [1, 2, 3, 4, 5],
        "duration_s": 8.0,
        "targets": {
            1: (11.23606798, 5.19577393, 5.0),
            2: (6.76393202, 6.64885899, 5.0),
            3: (14.0, 9.0, 5.0),
            4: (6.76393202, 11.35114101, 5.0),
            5: (11.23606798, 12.80422607, 5.0),
        },
    },
    "eight_uav_line_to_circle": {
        "uav_ids": [1, 2, 3, 4, 5, 6, 7, 8],
        "duration_s": 12.0,
        "targets": {
            1: (10.0, 7.5, 5.0),
            2: (14.24264069, 9.25735931, 5.0),
            3: (5.75735931, 9.25735931, 5.0),
            4: (4.0, 13.5, 5.0),
            5: (16.0, 13.5, 5.0),
            6: (5.75735931, 17.74264069, 5.0),
            7: (14.24264069, 17.74264069, 5.0),
            8: (10.0, 19.5, 5.0),
        },
    },
}


def validate() -> None:
    for scenario, config in SCENARIOS.items():
        ids = config["uav_ids"]
        targets = config["targets"]
        if set(ids) != set(targets):
            raise ValueError(f"{scenario}: targets do not match UAV IDs")
        if config["duration_s"] <= 0:
            raise ValueError(f"{scenario}: duration must be positive")
    if set(METHODS) != {"px4_step", "linear_ladrc", "minimum_jerk_ladrc"}:
        raise ValueError("experiment 06 requires exactly three preregistered methods")
