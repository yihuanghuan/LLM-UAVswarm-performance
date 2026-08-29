#!/usr/bin/env python3
"""Read retained ROS 2 bags without mutating runtime or formal artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from analysis_common import EvidenceError


@dataclass(frozen=True)
class BagRecord:
    topic: str
    message_type: str
    bag_timestamp: float
    timestamp: float
    message: Any


def message_timestamp(message: Any, bag_timestamp_ns: int) -> float:
    if hasattr(message, "header") and hasattr(message.header, "stamp"):
        stamp = message.header.stamp
        value = float(stamp.sec) + float(stamp.nanosec) * 1.0e-9
        if value > 0.0:
            return value
    return float(bag_timestamp_ns) * 1.0e-9


def read_bag(bag_dir: Path, topic_predicate: Callable[[str], bool] | None = None) -> list[BagRecord]:
    try:
        import rosbag2_py
        from rclpy.serialization import deserialize_message
        from rosidl_runtime_py.utilities import get_message
    except ImportError as exc:
        raise EvidenceError(f"ROS 2 analysis environment unavailable: {exc}") from exc
    bag_dir = Path(bag_dir)
    if not (bag_dir / "metadata.yaml").is_file():
        raise EvidenceError(f"rosbag metadata missing: {bag_dir}")
    reader = rosbag2_py.SequentialReader()
    try:
        reader.open(
            rosbag2_py.StorageOptions(uri=str(bag_dir), storage_id="sqlite3"),
            rosbag2_py.ConverterOptions("cdr", "cdr"),
        )
    except Exception as exc:
        raise EvidenceError(f"cannot open rosbag {bag_dir}: {exc}") from exc
    types = {entry.name: entry.type for entry in reader.get_all_topics_and_types()}
    records: list[BagRecord] = []
    while reader.has_next():
        topic, data, bag_ns = reader.read_next()
        if topic_predicate is not None and not topic_predicate(topic):
            continue
        try:
            message = deserialize_message(data, get_message(types[topic]))
        except Exception as exc:
            raise EvidenceError(f"cannot deserialize {topic} ({types[topic]}): {exc}") from exc
        records.append(BagRecord(topic, types[topic], bag_ns * 1.0e-9,
                                 message_timestamp(message, bag_ns), message))
    return records


def records_for(records: Iterable[BagRecord], suffix: str, *, mission_id: int | None = None,
                uav_id: int | None = None) -> list[BagRecord]:
    output = []
    for record in records:
        if not record.topic.endswith(suffix):
            continue
        if mission_id is not None and getattr(record.message, "mission_id", None) != mission_id:
            continue
        if uav_id is not None and getattr(record.message, "uav_id", None) != uav_id:
            continue
        output.append(record)
    return output


def point(value: Any) -> list[float]:
    return [float(value.x), float(value.y), float(value.z)]


def vector(value: Any) -> list[float]:
    return [float(value.x), float(value.y), float(value.z)]
