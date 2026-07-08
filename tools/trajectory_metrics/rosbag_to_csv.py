#!/usr/bin/env python3
"""Export selected ROS 2 bag topics to flat CSV files."""

from __future__ import annotations

import argparse
import csv
import fnmatch
import math
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List


DEFAULT_TOPIC_PATTERNS = [
    "/uav*/trajectory_metrics",
    "/uav*/control_adaptation",
    "/uav*/odom",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert selected ROS 2 bag topics into CSV files."
    )
    parser.add_argument("bag", help="Path to a ROS 2 bag directory.")
    parser.add_argument(
        "--out-dir",
        default="bag_csv",
        help="Directory for exported CSV files.",
    )
    parser.add_argument(
        "--topics",
        nargs="*",
        default=DEFAULT_TOPIC_PATTERNS,
        help="Topic names or shell-style patterns. Defaults to UAV metrics topics.",
    )
    return parser.parse_args()


def sanitize_topic(topic: str) -> str:
    text = topic.strip("/") or "root"
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", text)
    return text.replace("/", "_")


def should_export(topic: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(topic, pattern) for pattern in patterns)


def flatten_value(prefix: str, value: Any, out: Dict[str, Any]) -> None:
    if hasattr(value, "get_fields_and_field_types"):
        for field in value.get_fields_and_field_types().keys():
            flatten_value(f"{prefix}.{field}" if prefix else field, getattr(value, field), out)
        return

    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            flatten_value(f"{prefix}.{index}", item, out)
        return

    if isinstance(value, float) and not math.isfinite(value):
        out[prefix] = "nan"
    else:
        out[prefix] = value


def flatten_message(message: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    flatten_value("", message, out)
    return {key.replace(".", "_"): value for key, value in out.items()}


class TopicCsvWriter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.rows: List[Dict[str, Any]] = []
        self.fieldnames = {"bag_time_ns"}

    def append(self, timestamp: int, row: Dict[str, Any]) -> None:
        data = {"bag_time_ns": timestamp, **row}
        self.rows.append(data)
        self.fieldnames.update(data.keys())

    def close(self) -> None:
        ordered = ["bag_time_ns"] + sorted(name for name in self.fieldnames if name != "bag_time_ns")
        with self.path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=ordered)
            writer.writeheader()
            for row in self.rows:
                writer.writerow(row)


def convert_bag(bag_path: Path, out_dir: Path, patterns: List[str]) -> Dict[str, int]:
    try:
        import rosbag2_py
        from rclpy.serialization import deserialize_message
        from rosidl_runtime_py.utilities import get_message
    except ImportError as exc:
        raise RuntimeError(
            "ROS 2 Python bag utilities are unavailable. Source ROS 2 and the workspace first."
        ) from exc

    if not bag_path.exists():
        raise FileNotFoundError(f"Bag path does not exist: {bag_path}")

    out_dir.mkdir(parents=True, exist_ok=True)

    reader = rosbag2_py.SequentialReader()
    storage_options = rosbag2_py.StorageOptions(uri=str(bag_path), storage_id="")
    converter_options = rosbag2_py.ConverterOptions(
        input_serialization_format="cdr",
        output_serialization_format="cdr",
    )
    reader.open(storage_options, converter_options)

    topic_types = {
        topic.name: topic.type
        for topic in reader.get_all_topics_and_types()
        if should_export(topic.name, patterns)
    }
    if not topic_types:
        available = ", ".join(topic.name for topic in reader.get_all_topics_and_types())
        raise RuntimeError(f"No selected topics found. Available topics: {available}")

    message_types = {
        topic: get_message(type_name)
        for topic, type_name in topic_types.items()
    }
    writers = {
        topic: TopicCsvWriter(out_dir / f"{sanitize_topic(topic)}.csv")
        for topic in topic_types
    }
    counts = {topic: 0 for topic in topic_types}

    while reader.has_next():
        topic, data, timestamp = reader.read_next()
        if topic not in writers:
            continue
        message = deserialize_message(data, message_types[topic])
        writers[topic].append(timestamp, flatten_message(message))
        counts[topic] += 1

    for writer in writers.values():
        writer.close()
    return counts


def main() -> int:
    args = parse_args()
    counts = convert_bag(Path(args.bag), Path(args.out_dir), args.topics)
    for topic, count in sorted(counts.items()):
        print(f"{topic}: {count} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
