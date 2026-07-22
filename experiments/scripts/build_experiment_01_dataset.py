#!/usr/bin/env python3
"""Build the fixed, human-reviewable dataset for experiment 01."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = REPO_ROOT / "experiments" / "commands" / "experiment_01_commands.json"
ALL_UAVS = list(range(1, 11))
ROS_10 = "当前可用无人机编号: [1,2,3,4,5,6,7,8,9,10]，总数: 10"


def task(
    uavs: Sequence[int], formation: str, center: Sequence[float], radius: float,
    duration: float, style: str = "normal", safety: float = 1.0,
    trigger: str = "direct", **extra: Any,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "U": list(uavs), "F": formation, "c": list(center), "r": radius,
        "T": duration, "m": style, "s": safety, "q": trigger,
    }
    result.update(extra)
    return result


def sample(
    sample_id: str, command_type: str, command: str, expected_tasks: List[Dict[str, Any]],
    complexity: int, ros_aux_info: str = ROS_10,
) -> Dict[str, Any]:
    return {
        "id": sample_id,
        "type": command_type,
        "complexity": complexity,
        "command": command,
        "ros_aux_info": ros_aux_info,
        "expected_lfs": {"lfs_version": "1.0", "tasks": expected_tasks},
    }


def build_simple() -> List[Dict[str, Any]]:
    specs = [
        ("Circle", "圆形", [1, 2, 3, 4, 5], [2, 9, 3], 3, 12),
        ("Line", "直线", [1, 2, 3, 4], [0, 0, 4], 2, 8),
        ("Sphere", "球形", [1, 2, 3, 4, 5, 6], [1, 1, 5], 2.5, 10),
        ("Triangle", "正三角形", [1, 2, 3], [-2, 3, 4], 2, 6),
        ("Polygon", "正多边形", [1, 2, 3, 4, 5, 6], [4, -2, 5], 3, 9),
        ("Line", "一字长蛇阵", [2, 3, 4, 5, 6], [0, 5, 3], 1.5, 7),
    ]
    rows: List[Dict[str, Any]] = []
    for index in range(18):
        formation, zh_name, uavs, base_center, radius, duration = specs[index % len(specs)]
        shift = index // len(specs)
        center = [base_center[0] + shift, base_center[1] - shift, base_center[2]]
        command = (
            f"{uavs[0]}到{uavs[-1]}号无人机以[{center[0]},{center[1]},{center[2]}]为中心，"
            f"组成{zh_name}编队，半径或间距为{radius}米，在{duration}秒内完成"
        )
        rows.append(sample(
            f"simple_{index + 1:02d}", "simple", command,
            [task(uavs, formation, center, radius, duration)], 1 + (index % 2),
        ))
    return rows


def build_sequential() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    uav_sets = [list(range(1, 6)), list(range(2, 8)), list(range(1, 9))]
    for index in range(18):
        uavs = uav_sets[index % len(uav_sets)]
        x = 4 + index % 4
        z = 3 + index % 3
        first_radius = 2 + (index % 3) * 0.5
        second_radius = 2.5 + (index % 2) * 0.5
        first_duration = 5 + index % 4
        second_duration = 7 + index % 4
        first_style = "smooth" if index % 3 == 0 else "normal"
        second_style = "aggressive" if index % 3 == 1 else "normal"
        command = (
            f"首先{uavs[0]}到{uavs[-1]}号机用{first_duration}秒在[{x},0,{z}]组成间距"
            f"{first_radius}米的直线编队；随后用{second_duration}秒转移到[0,{x},{z}]并组成半径"
            f"{second_radius}米的圆形编队，第一阶段{first_style}模式，第二阶段{second_style}模式"
        )
        rows.append(sample(
            f"sequential_{index + 1:02d}", "sequential", command,
            [
                task(uavs, "Line", [x, 0, z], first_radius, first_duration, first_style, trigger="continuous"),
                task(uavs, "Circle", [0, x, z], second_radius, second_duration, second_style),
            ],
            3 + (index % 3 == 2),
        ))
    return rows


def build_grouped() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for index in range(18):
        split = 3 + index % 3
        left = list(range(1, split + 1))
        right = list(range(split + 1, 9))
        y = 3 + index % 4
        z = 4 + index % 2
        circle_radius = 2 + (index % 3) * 0.5
        line_spacing = 1.5 + (index % 2) * 0.5
        duration = 7 + index % 4
        command = (
            f"{left[0]}到{left[-1]}号机同时在[-3,{y},{z}]组成半径{circle_radius}米的圆形编队；"
            f"{right[0]}到{right[-1]}号机在[3,-{y},{z}]组成间距{line_spacing}米的直线编队，"
            f"两组都在{duration}秒内完成"
        )
        rows.append(sample(
            f"grouped_{index + 1:02d}", "grouped", command,
            [
                task(left, "Circle", [-3, y, z], circle_radius, duration, parallel_group="group-1"),
                task(right, "Line", [3, -y, z], line_spacing, duration, parallel_group="group-1"),
            ],
            3 + (index % 3 == 0),
        ))
    return rows


def build_style() -> List[Dict[str, Any]]:
    style_words = [
        ("smooth", "柔和平滑地"),
        ("normal", "以标准模式"),
        ("aggressive", "快速激进地"),
    ]
    formations = [("Circle", "圆形"), ("Line", "直线"), ("Polygon", "正多边形")]
    rows: List[Dict[str, Any]] = []
    for index in range(18):
        style, style_word = style_words[index % 3]
        formation, formation_word = formations[(index // 3) % 3]
        center = [index % 5 - 2, (index * 2) % 7 - 3, 4 + index % 2]
        radius = 2 + (index % 4) * 0.5
        duration = 6 + index % 6
        command = (
            f"1到6号机{style_word}以[{center[0]},{center[1]},{center[2]}]为中心组成"
            f"{formation_word}编队，半径或间距{radius}米，限时{duration}秒"
        )
        rows.append(sample(
            f"style_{index + 1:02d}", "style-conditioned", command,
            [task(range(1, 7), formation, center, radius, duration, style)], 2 + (index % 2),
        ))
    return rows


def build_safety() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for index in range(10):
        safety = 0.5 + index * 0.25
        center = [index % 3 - 1, 4 - index % 4, 5]
        radius = 2 + (index % 3) * 0.5
        command = (
            f"1到5号机以[{center[0]},{center[1]},{center[2]}]为中心组成半径{radius}米的圆形编队，"
            f"8秒完成，避障安全系数设为{safety}"
        )
        rows.append(sample(
            f"safety_{index + 1:02d}", "safety-conditioned", command,
            [task(range(1, 6), "Circle", center, radius, 8, safety=safety)], 2,
        ))
    return rows


def build_invalid() -> List[Dict[str, Any]]:
    commands = [
        ("unrelated", "帮我写一首关于无人机的诗"),
        ("unrelated", "今天重庆的天气怎么样"),
        ("unrelated", "解释一下量子纠缠"),
        ("unrelated", "把这段文字翻译成英文"),
        ("unknown_uav", "99号机以[0,0,3]为中心组成半径2米的圆形编队，限时5秒"),
        ("unknown_uav", "1到12号机以[0,0,4]为中心组成直线编队，间距2米"),
        ("unknown_uav", "让15号无人机加入1到5号机的圆形编队"),
        ("unknown_uav", "0号机和1号机在[1,1,3]组成直线编队"),
        ("missing_formation", "1到5号机移动到[0,0,3]附近，限时5秒"),
        ("missing_formation", "全体无人机在8秒内完成变换"),
        ("missing_formation", "2到6号机以[2,2,4]为中心重新排列"),
        ("missing_formation", "请让1到4号机快速改变队形"),
        ("ambiguous", "1到5号机同时组成圆形和直线编队"),
        ("ambiguous", "全体无人机到左边那个点组成圆形"),
        ("ambiguous", "1到5号机组成半径2米和4米的圆形编队"),
        ("ambiguous", "部分无人机以适当距离组成一个合适的阵型"),
        ("ambiguous", "1到5号机先后同时完成圆形编队"),
        ("ambiguous", "1到5号机以[0,0,3]和[5,5,3]为中心组成一个圆形编队"),
    ]
    return [
        {
            "id": f"invalid_{index + 1:02d}",
            "type": "invalid/ambiguous",
            "complexity": 2 + index % 4,
            "command": command,
            "ros_aux_info": ROS_10,
            "expected_error": category,
        }
        for index, (category, command) in enumerate(commands)
    ]


def build_dataset() -> List[Dict[str, Any]]:
    rows = build_simple() + build_sequential() + build_grouped() + build_style() + build_safety() + build_invalid()
    assert len(rows) == 100
    assert len({row["id"] for row in rows}) == 100
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="生成实验 01 固定标注数据集。")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()
    content = json.dumps(build_dataset(), ensure_ascii=False, indent=2) + "\n"
    if args.stdout:
        print(content, end="")
    else:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
        print(f"已生成 {len(build_dataset())} 条样本: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
