#!/usr/bin/env python3
"""离线比较 step、linear、trapezoidal、minimum_jerk 轨迹。"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, Iterable, List

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]

SUMMARY_FIELDS = [
    "profile",
    "duration",
    "distance",
    "max_velocity",
    "max_acceleration",
    "max_jerk",
    "integrated_squared_jerk",
    "final_error",
]

TIMESERIES_FIELDS = [
    "profile",
    "time_s",
    "position",
    "velocity",
    "acceleration",
    "jerk",
]

PROFILES = ["step", "linear", "trapezoidal", "minimum_jerk"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成并评估轨迹 profile。")
    parser.add_argument(
        "--output-summary",
        default=str(REPO_ROOT / "experiments" / "results" / "trajectory_profile_results.csv"),
        help="轨迹指标 CSV 输出路径。",
    )
    parser.add_argument(
        "--output-timeseries",
        default=str(REPO_ROOT / "experiments" / "results" / "trajectory_profile_timeseries.csv"),
        help="轨迹时序 CSV 输出路径。",
    )
    parser.add_argument("--duration", type=float, default=8.0, help="轨迹持续时间。")
    parser.add_argument("--distance", type=float, default=10.0, help="一维目标位移。")
    parser.add_argument("--dt", type=float, default=0.02, help="采样间隔。")
    return parser.parse_args()


def time_axis(duration: float, dt: float) -> np.ndarray:
    sample_count = int(np.floor(duration / dt)) + 1
    axis = np.linspace(0.0, duration, sample_count)
    if axis[-1] < duration:
        axis = np.append(axis, duration)
    return axis


def step_position(t: np.ndarray, distance: float) -> np.ndarray:
    position = np.full_like(t, distance, dtype=float)
    position[0] = 0.0
    return position


def linear_position(t: np.ndarray, duration: float, distance: float) -> np.ndarray:
    return distance * np.clip(t / duration, 0.0, 1.0)


def trapezoidal_position(t: np.ndarray, duration: float, distance: float) -> np.ndarray:
    accel_time = duration * 0.25
    cruise_time = duration - 2.0 * accel_time
    accel = distance / (accel_time * (accel_time + cruise_time))
    velocity_peak = accel * accel_time
    position = np.zeros_like(t, dtype=float)

    for idx, current in enumerate(t):
        if current <= accel_time:
            position[idx] = 0.5 * accel * current * current
        elif current <= accel_time + cruise_time:
            position[idx] = 0.5 * accel * accel_time**2 + velocity_peak * (current - accel_time)
        else:
            decel_t = current - accel_time - cruise_time
            position[idx] = (
                0.5 * accel * accel_time**2
                + velocity_peak * cruise_time
                + velocity_peak * decel_t
                - 0.5 * accel * decel_t * decel_t
            )
    return np.clip(position, 0.0, distance)


def minimum_jerk_position(t: np.ndarray, duration: float, distance: float) -> np.ndarray:
    tau = np.clip(t / duration, 0.0, 1.0)
    progress = 10.0 * tau**3 - 15.0 * tau**4 + 6.0 * tau**5
    return distance * progress


def derivatives(position: np.ndarray, t: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    velocity = np.gradient(position, t, edge_order=2)
    acceleration = np.gradient(velocity, t, edge_order=2)
    jerk = np.gradient(acceleration, t, edge_order=2)
    return velocity, acceleration, jerk


def build_profile(profile: str, t: np.ndarray, duration: float, distance: float) -> Dict[str, np.ndarray]:
    if profile == "step":
        position = step_position(t, distance)
    elif profile == "linear":
        position = linear_position(t, duration, distance)
    elif profile == "trapezoidal":
        position = trapezoidal_position(t, duration, distance)
    elif profile == "minimum_jerk":
        position = minimum_jerk_position(t, duration, distance)
    else:
        raise ValueError(f"未知轨迹类型: {profile}")

    velocity, acceleration, jerk = derivatives(position, t)
    return {
        "position": position,
        "velocity": velocity,
        "acceleration": acceleration,
        "jerk": jerk,
    }


def format_float(value: float) -> str:
    return f"{float(value):.6f}"


def summary_row(profile: str, data: Dict[str, np.ndarray], duration: float, distance: float) -> Dict[str, str]:
    jerk = data["jerk"]
    return {
        "profile": profile,
        "duration": format_float(duration),
        "distance": format_float(distance),
        "max_velocity": format_float(np.max(np.abs(data["velocity"]))),
        "max_acceleration": format_float(np.max(np.abs(data["acceleration"]))),
        "max_jerk": format_float(np.max(np.abs(jerk))),
        "integrated_squared_jerk": format_float(np.trapezoid(jerk * jerk, dx=duration / (len(jerk) - 1))),
        "final_error": format_float(abs(data["position"][-1] - distance)),
    }


def timeseries_rows(profile: str, t: np.ndarray, data: Dict[str, np.ndarray]) -> Iterable[Dict[str, str]]:
    for idx, current in enumerate(t):
        yield {
            "profile": profile,
            "time_s": format_float(current),
            "position": format_float(data["position"][idx]),
            "velocity": format_float(data["velocity"][idx]),
            "acceleration": format_float(data["acceleration"][idx]),
            "jerk": format_float(data["jerk"][idx]),
        }


def write_csv(path: Path, fields: List[str], rows: Iterable[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    if args.duration <= 0.0:
        raise ValueError("--duration 必须大于 0")
    if args.distance <= 0.0:
        raise ValueError("--distance 必须大于 0")
    if args.dt <= 0.0 or args.dt >= args.duration:
        raise ValueError("--dt 必须大于 0 且小于 --duration")

    t = time_axis(args.duration, args.dt)
    summary: List[Dict[str, str]] = []
    timeseries: List[Dict[str, str]] = []
    for profile in PROFILES:
        data = build_profile(profile, t, args.duration, args.distance)
        summary.append(summary_row(profile, data, args.duration, args.distance))
        timeseries.extend(timeseries_rows(profile, t, data))

    write_csv(Path(args.output_summary), SUMMARY_FIELDS, summary)
    write_csv(Path(args.output_timeseries), TIMESERIES_FIELDS, timeseries)
    print(f"已写入轨迹指标: {args.output_summary}")
    print(f"已写入轨迹时序: {args.output_timeseries}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
