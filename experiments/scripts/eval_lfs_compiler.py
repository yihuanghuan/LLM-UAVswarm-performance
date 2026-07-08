#!/usr/bin/env python3
"""离线评估 LFS schema/语义校验和编译链路。"""

from __future__ import annotations

import argparse
import csv
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_SRC = REPO_ROOT / "location_allocate"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from location_allocate.lfs_validator import (  # noqa: E402
    LFSValidationError,
    validate_and_compile_lfs,
    validate_schema,
)


RESULT_FIELDS = [
    "case_id",
    "case_type",
    "schema_valid",
    "semantic_valid",
    "compile_success",
    "expected_success",
    "pass",
    "error_type",
]

AVAILABLE_UAV_IDS = [1, 2, 3, 4, 5, 6, 7, 8]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="评估 LFS 编译器。")
    parser.add_argument(
        "--output",
        default=str(REPO_ROOT / "experiments" / "results" / "lfs_compiler_results.csv"),
        help="输出 CSV 路径。",
    )
    return parser.parse_args()


def formal_task(**overrides: Any) -> Dict[str, Any]:
    task = {
        "task_id": 1,
        "U": [1, 2, 3],
        "F": "Circle",
        "c": [0.0, 0.0, 3.0],
        "r": 2.0,
        "T": 5.0,
        "m": "normal",
        "s": 1.0,
        "q": "direct",
    }
    task.update(overrides)
    return task


def legacy_task(**overrides: Any) -> Dict[str, Any]:
    task = {
        "task_sequence_id": 1,
        "duration_seconds": 5.0,
        "uav_id": [1, 2, 3],
        "uav_count": 3,
        "trigger_condition": "direct_execution",
        "wait_time": None,
        "iapf_safety_margin_factor": 1.0,
        "motion_profile": "normal",
        "constraints": ["minimal_topology_change", "no_trajectory_cross", "keep_safety_distance"],
        "global_center": [0.0, 0.0, 3.0],
        "generation_mode": "parametric",
        "parametric_data": {
            "formation_type": "Circle",
            "formation_radius": 2.0,
        },
    }
    task.update(overrides)
    return task


def build_cases() -> List[Dict[str, Any]]:
    missing_field = formal_task()
    del missing_field["F"]

    return [
        {
            "case_id": "formal_valid_circle",
            "case_type": "formal_lfs",
            "payload": {"lfs_version": "1.0", "tasks": [formal_task()]},
            "expected_success": True,
        },
        {
            "case_id": "formal_valid_parallel",
            "case_type": "formal_lfs",
            "payload": {
                "lfs_version": "1.0",
                "tasks": [
                    formal_task(task_id=1, U=[1, 2, 3], parallel_group="g1"),
                    formal_task(task_id=2, U=[4, 5], F="Line", parallel_group="g1"),
                ],
            },
            "expected_success": True,
        },
        {
            "case_id": "formal_alias_M",
            "case_type": "formal_lfs",
            "payload": {"lfs_version": "1.0", "M": [formal_task()]},
            "expected_success": True,
        },
        {
            "case_id": "invalid_missing_field",
            "case_type": "invalid_lfs",
            "payload": {"lfs_version": "1.0", "tasks": [missing_field]},
            "expected_success": False,
        },
        {
            "case_id": "invalid_motion_enum",
            "case_type": "invalid_lfs",
            "payload": {"lfs_version": "1.0", "tasks": [formal_task(m="fast")]},
            "expected_success": False,
        },
        {
            "case_id": "invalid_unknown_uav",
            "case_type": "invalid_lfs",
            "payload": {"lfs_version": "1.0", "tasks": [formal_task(U=[1, 9])]},
            "expected_success": False,
        },
        {
            "case_id": "invalid_parallel_overlap",
            "case_type": "invalid_lfs",
            "payload": {
                "lfs_version": "1.0",
                "tasks": [
                    formal_task(task_id=1, U=[1, 2], parallel_group="g1"),
                    formal_task(task_id=2, U=[2, 3], parallel_group="g1"),
                ],
            },
            "expected_success": False,
        },
        {
            "case_id": "legacy_valid",
            "case_type": "legacy_task_sequences",
            "payload": {"task_sequences": [legacy_task()]},
            "expected_success": True,
        },
        {
            "case_id": "legacy_uav_count_mismatch",
            "case_type": "legacy_task_sequences",
            "payload": {"task_sequences": [legacy_task(uav_count=4)]},
            "expected_success": False,
        },
    ]


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def evaluate_case(case: Dict[str, Any]) -> Dict[str, Any]:
    payload = deepcopy(case["payload"])
    schema_valid = False
    semantic_valid = False
    compile_success = False
    error_type = ""

    try:
        validate_schema(payload)
        schema_valid = True
    except Exception as exc:
        error_type = type(exc).__name__

    if schema_valid:
        try:
            validate_and_compile_lfs(payload, AVAILABLE_UAV_IDS)
            semantic_valid = True
            compile_success = True
        except LFSValidationError as exc:
            semantic_valid = False
            error_type = type(exc).__name__
        except Exception as exc:
            semantic_valid = False
            error_type = type(exc).__name__

    expected_success = bool(case["expected_success"])
    passed = compile_success == expected_success
    return {
        "case_id": case["case_id"],
        "case_type": case["case_type"],
        "schema_valid": bool_text(schema_valid),
        "semantic_valid": bool_text(semantic_valid),
        "compile_success": bool_text(compile_success),
        "expected_success": bool_text(expected_success),
        "pass": bool_text(passed),
        "error_type": error_type,
    }


def write_results(rows: List[Dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    rows = [evaluate_case(case) for case in build_cases()]
    write_results(rows, Path(args.output))
    failures = [row["case_id"] for row in rows if row["pass"] != "true"]
    print(f"已评估 {len(rows)} 个 LFS 编译用例，结果写入 {args.output}")
    if failures:
        print(f"失败用例: {', '.join(failures)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
