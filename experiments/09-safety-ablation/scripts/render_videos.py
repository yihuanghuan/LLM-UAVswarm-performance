#!/usr/bin/env python3
"""Render paired representative-seed trajectory videos for experiment 09."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.animation as animation  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402


VARIANTS = ["B0", "P", "E", "Full"]


def representative(batch_dir: Path, scenario: str, variant: str) -> Path:
    matches = list(
        (batch_dir / "raw" / scenario / variant).glob("trial_*_seed_4201"))
    if len(matches) != 1:
        raise FileNotFoundError(f"{scenario}/{variant}: representative trial missing")
    return matches[0]


def render(batch_dir: Path, scenario: str, output: Path) -> None:
    frames = {
        variant: pd.read_csv(
            representative(batch_dir, scenario, variant) / "odom.csv")
        for variant in VARIANTS
    }
    all_x = pd.concat([frame["x"] for frame in frames.values()])
    all_y = pd.concat([frame["y"] for frame in frames.values()])
    x_limits = (all_x.min() - 0.5, all_x.max() + 0.5)
    y_limits = (all_y.min() - 0.5, all_y.max() + 0.5)
    fig, axes = plt.subplots(2, 2, figsize=(10, 9))
    artists = {}
    frame_count = 0
    for axis, variant in zip(axes.flat, VARIANTS):
        data = frames[variant]
        by_uav = {
            int(uid): group.sort_values("timestamp").iloc[::2].reset_index(drop=True)
            for uid, group in data.groupby("uav_id")
        }
        frame_count = max(frame_count, max(len(group) for group in by_uav.values()))
        lines, points = {}, {}
        for uid in sorted(by_uav):
            line, = axis.plot([], [], linewidth=1.2, label=f"UAV{uid}")
            point, = axis.plot([], [], marker="o", color=line.get_color())
            lines[uid], points[uid] = line, point
        axis.set(xlim=x_limits, ylim=y_limits, xlabel="x (m)", ylabel="y (m)")
        axis.set_title(variant)
        axis.set_aspect("equal", adjustable="box")
        axis.grid(alpha=0.25)
        artists[variant] = (by_uav, lines, points)
    fig.suptitle(f"Experiment 09 representative seed 4201: {scenario}")

    def update(index: int):
        changed = []
        for variant in VARIANTS:
            by_uav, lines, points = artists[variant]
            for uid, group in by_uav.items():
                end = min(index + 1, len(group))
                lines[uid].set_data(group["x"].iloc[:end], group["y"].iloc[:end])
                points[uid].set_data(
                    [group["x"].iloc[end - 1]], [group["y"].iloc[end - 1]])
                changed.extend([lines[uid], points[uid]])
        return changed

    output.parent.mkdir(parents=True, exist_ok=True)
    if animation.writers.is_available("ffmpeg"):
        movie = animation.FuncAnimation(
            fig, update, frames=frame_count, interval=50, blit=True)
        movie.save(output, writer="ffmpeg", fps=20, dpi=120)
    else:
        # OpenCV provides a deterministic MP4 fallback on minimal experiment
        # hosts where the ffmpeg executable is not installed.
        import cv2

        fig.set_dpi(120)
        fig.canvas.draw()
        width, height = fig.canvas.get_width_height()
        writer = cv2.VideoWriter(
            str(output), cv2.VideoWriter_fourcc(*"mp4v"), 20, (width, height))
        if not writer.isOpened():
            raise RuntimeError(f"unable to open MP4 writer for {output}")
        try:
            for index in range(frame_count):
                update(index)
                fig.canvas.draw()
                rgb = np.asarray(fig.canvas.buffer_rgba())[:, :, :3]
                writer.write(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        finally:
            writer.release()
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("batch_dir", type=Path)
    args = parser.parse_args()
    video_dir = args.batch_dir / "videos"
    scenarios = sorted(path.name for path in (args.batch_dir / "raw").iterdir())
    for scenario in scenarios:
        render(args.batch_dir, scenario, video_dir / f"{scenario}.mp4")
    print(video_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
