#!/usr/bin/env python3
"""Analytic trajectory profiles used by experiment 05."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np


PROFILES = ("step", "linear", "trapezoidal", "minimum_jerk")


@dataclass(frozen=True)
class AnalyticMetrics:
    max_velocity: float
    max_acceleration: float
    max_jerk: float
    integrated_squared_jerk: float
    max_velocity_valid: bool
    max_acceleration_valid: bool
    max_jerk_valid: bool
    integrated_squared_jerk_valid: bool
    continuity_order: int
    note: str


def validate(profile: str, duration: float) -> None:
    if profile not in PROFILES:
        raise ValueError(f"unknown profile: {profile}")
    if duration <= 0.0:
        raise ValueError("duration must be positive")


def sample_progress(profile: str, time_s: np.ndarray, duration: float) -> Dict[str, np.ndarray]:
    """Return scalar progress and its first three piecewise derivatives."""
    validate(profile, duration)
    t = np.asarray(time_s, dtype=float)
    tc = np.clip(t, 0.0, duration)
    position = np.zeros_like(tc)
    velocity = np.zeros_like(tc)
    acceleration = np.zeros_like(tc)
    jerk = np.zeros_like(tc)

    if profile == "step":
        position[t > 0.0] = 1.0
        jerk[np.isclose(t, 0.0)] = np.nan
        return {
            "position": position,
            "velocity": velocity,
            "acceleration": acceleration,
            "jerk": jerk,
        }

    if profile == "linear":
        position = tc / duration
        moving = (t >= 0.0) & (t < duration)
        velocity[moving] = 1.0 / duration
        discontinuity = np.isclose(t, 0.0) | np.isclose(t, duration)
        acceleration[discontinuity] = np.nan
        jerk[discontinuity] = np.nan
        return {
            "position": position,
            "velocity": velocity,
            "acceleration": acceleration,
            "jerk": jerk,
        }

    if profile == "trapezoidal":
        accel_time = duration / 4.0
        cruise_end = 3.0 * duration / 4.0
        accel = 1.0 / (accel_time * (duration - accel_time))
        peak_velocity = accel * accel_time
        first = tc <= accel_time
        middle = (tc > accel_time) & (tc <= cruise_end)
        last = (tc > cruise_end) & (tc < duration)
        position[first] = 0.5 * accel * tc[first] ** 2
        velocity[first] = accel * tc[first]
        acceleration[first] = accel
        position[middle] = (
            0.5 * accel * accel_time**2
            + peak_velocity * (tc[middle] - accel_time)
        )
        velocity[middle] = peak_velocity
        decel_t = tc[last] - cruise_end
        position[last] = (
            0.5 * accel * accel_time**2
            + peak_velocity * duration / 2.0
            + peak_velocity * decel_t
            - 0.5 * accel * decel_t**2
        )
        velocity[last] = peak_velocity - accel * decel_t
        acceleration[last] = -accel
        position[t >= duration] = 1.0
        acceleration[t >= duration] = 0.0
        switches = (
            np.isclose(t, 0.0)
            | np.isclose(t, accel_time)
            | np.isclose(t, cruise_end)
            | np.isclose(t, duration)
        )
        jerk[switches] = np.nan
        return {
            "position": position,
            "velocity": velocity,
            "acceleration": acceleration,
            "jerk": jerk,
        }

    tau = tc / duration
    position = 10.0 * tau**3 - 15.0 * tau**4 + 6.0 * tau**5
    velocity = (30.0 * tau**2 - 60.0 * tau**3 + 30.0 * tau**4) / duration
    acceleration = (60.0 * tau - 180.0 * tau**2 + 120.0 * tau**3) / duration**2
    jerk = (60.0 - 360.0 * tau + 360.0 * tau**2) / duration**3
    after = t > duration
    velocity[after] = 0.0
    acceleration[after] = 0.0
    jerk[after] = 0.0
    return {
        "position": position,
        "velocity": velocity,
        "acceleration": acceleration,
        "jerk": jerk,
    }


def analytic_metrics(profile: str, distance: float, duration: float) -> AnalyticMetrics:
    validate(profile, duration)
    if distance < 0.0:
        raise ValueError("distance must be non-negative")
    nan = float("nan")
    if profile == "step":
        return AnalyticMetrics(
            nan, nan, nan, nan, False, False, False, False, -1,
            "position discontinuity; qualitative baseline only",
        )
    if profile == "linear":
        return AnalyticMetrics(
            distance / duration, nan, nan, nan, True, False, False, False, 0,
            "endpoint velocity discontinuities; acceleration/jerk/ISJ undefined",
        )
    if profile == "trapezoidal":
        return AnalyticMetrics(
            (4.0 / 3.0) * distance / duration,
            (16.0 / 3.0) * distance / duration**2,
            nan,
            nan,
            True,
            True,
            False,
            False,
            1,
            "acceleration jumps at segment boundaries; jerk/ISJ undefined",
        )
    return AnalyticMetrics(
        15.0 * distance / (8.0 * duration),
        10.0 * np.sqrt(3.0) * distance / (3.0 * duration**2),
        60.0 * distance / duration**3,
        720.0 * distance**2 / duration**5,
        True,
        True,
        True,
        True,
        2,
        "C2 continuous minimum-jerk trajectory",
    )
