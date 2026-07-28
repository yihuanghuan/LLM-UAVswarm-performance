"""Preregistered configuration for experiment 07."""

from __future__ import annotations


SEED = 20260728
REPEATS = 5
UAV_ID = 1
TARGET = (6.0, 3.0, 5.0)
DURATION_S = 3.0
OBSERVATION_S = 15.0
FORMATION = "Line"
FORMATION_RADIUS = 1.0
METHODS = {
    "fixed_gain": {
        "semantic_gain_mode": "fixed",
        "fixed_gain_multiplier": 1.0,
    },
    "task_conditioned": {
        "semantic_gain_mode": "task_conditioned",
        "fixed_gain_multiplier": 1.0,
    },
}
COMMANDS = {
    "smooth": "1号机以柔和平滑模式，变换成以[6,3,5]为中心、间距1米的一字长蛇阵。",
    "normal": "1号机以标准模式，变换成以[6,3,5]为中心、间距1米的一字长蛇阵。",
    "aggressive": "1号机以快速激进模式，尽快变换成以[6,3,5]为中心、间距1米的一字长蛇阵。",
}
ROS_AUX_INFO = "当前可用无人机编号: [1]，总数: 1"


def validate() -> None:
    if set(METHODS) != {"fixed_gain", "task_conditioned"}:
        raise ValueError("experiment 07 requires fixed_gain and task_conditioned")
    if set(COMMANDS) != {"smooth", "normal", "aggressive"}:
        raise ValueError("experiment 07 requires three motion styles")
    if REPEATS < 5:
        raise ValueError("experiment 07 requires at least five repeats")
    if DURATION_S <= 0.0 or OBSERVATION_S <= DURATION_S or FORMATION_RADIUS <= 0.0:
        raise ValueError("duration and formation radius must be positive")
