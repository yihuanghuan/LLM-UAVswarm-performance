#!/usr/bin/env python3
"""批量评估自然语言指令到 LFS/调度任务的解析结果。"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List


REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_SRC = REPO_ROOT / "location_allocate"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from location_allocate.lfs_validator import estimate_field_accuracy  # noqa: E402
from location_allocate.no_location import parse_uav_command  # noqa: E402


RESULT_FIELDS = [
    "command_id",
    "command_type",
    "valid_json",
    "schema_valid",
    "compiled_success",
    "field_accuracy",
    "prompt_tokens",
    "completion_tokens",
    "latency_ms",
    "retry_count",
    "error_type",
]

LOG_PATH = REPO_ROOT / "logs" / "llm_parse_log.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="评估 LLM 指令解析效果。")
    parser.add_argument(
        "--input",
        default=str(REPO_ROOT / "experiments" / "commands"),
        help="输入 JSON 文件或目录，默认 experiments/commands。",
    )
    parser.add_argument(
        "--output",
        default=str(REPO_ROOT / "experiments" / "results" / "llm_parser_results.csv"),
        help="输出 CSV 路径。",
    )
    parser.add_argument("--limit", type=int, default=None, help="最多评估多少条指令。")
    return parser.parse_args()


def command_files(input_path: Path) -> List[Path]:
    if input_path.is_dir():
        files = sorted(input_path.glob("*.json"))
    elif input_path.is_file():
        files = [input_path]
    else:
        raise FileNotFoundError(f"输入路径不存在: {input_path}")
    if not files:
        raise FileNotFoundError(f"未找到 JSON 指令文件: {input_path}")
    return files


def load_commands(input_path: Path) -> List[Dict[str, Any]]:
    commands: List[Dict[str, Any]] = []
    for path in command_files(input_path):
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            payload = payload.get("commands", [payload])
        if not isinstance(payload, list):
            raise ValueError(f"{path} 必须是 JSON 数组或包含 commands 数组的对象")
        for item in payload:
            if not isinstance(item, dict):
                raise ValueError(f"{path} 中存在非对象命令条目")
            for field in ("id", "type", "command", "ros_aux_info"):
                if field not in item:
                    raise ValueError(f"{path} 的命令缺少字段: {field}")
            commands.append(item)
    return commands


def read_log_rows() -> List[Dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    with LOG_PATH.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def bool_text(value: Any) -> str:
    if isinstance(value, str):
        return "true" if value.strip().lower() in {"true", "1", "yes"} else "false"
    return "true" if bool(value) else "false"


def int_value(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return default


def float_value(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default


def summarize_log_rows(rows: Iterable[Dict[str, str]], command_text: str) -> Dict[str, Any]:
    matched = [row for row in rows if row.get("raw_command") == command_text]
    if not matched:
        return {}

    prompt_tokens = sum(int_value(row.get("prompt_tokens")) for row in matched)
    completion_tokens = sum(int_value(row.get("completion_tokens")) for row in matched)
    latency_ms = sum(int_value(row.get("latency_ms")) for row in matched)
    retry_count = max(int_value(row.get("retry_count")) for row in matched)
    last = matched[-1]
    error_type = ""
    for row in reversed(matched):
        if row.get("error_type"):
            error_type = row["error_type"]
            break
    return {
        "valid_json": bool_text(last.get("valid_json")),
        "schema_valid": bool_text(last.get("schema_valid")),
        "field_accuracy": float_value(last.get("field_accuracy")),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "latency_ms": latency_ms,
        "retry_count": retry_count,
        "error_type": error_type,
    }


def evaluate_command(item: Dict[str, Any]) -> Dict[str, Any]:
    before_count = len(read_log_rows())
    start = time.time()
    error_type = ""
    result: Dict[str, Any] = {}

    try:
        parsed = parse_uav_command(str(item["command"]), str(item.get("ros_aux_info", "")))
        result = parsed if isinstance(parsed, dict) else {}
    except Exception as exc:  # 评估脚本不能因单条指令失败而中断
        error_type = type(exc).__name__
        result = {"task_sequences": [], "error_msg": str(exc)}

    elapsed_ms = int((time.time() - start) * 1000)
    after_rows = read_log_rows()
    new_rows = after_rows[before_count:]
    log_summary = summarize_log_rows(new_rows, str(item["command"]))

    compiled_success = bool(result.get("task_sequences"))
    inferred_accuracy = estimate_field_accuracy(result) if compiled_success else 0.0
    if result.get("error_msg") and not error_type:
        error_type = str(result.get("error_code", "parse_error"))

    return {
        "command_id": item["id"],
        "command_type": item["type"],
        "valid_json": log_summary.get("valid_json", bool_text(compiled_success)),
        "schema_valid": log_summary.get("schema_valid", bool_text(compiled_success)),
        "compiled_success": bool_text(compiled_success),
        "field_accuracy": f"{float(log_summary.get('field_accuracy', inferred_accuracy)):.4f}",
        "prompt_tokens": log_summary.get("prompt_tokens", 0),
        "completion_tokens": log_summary.get("completion_tokens", 0),
        "latency_ms": log_summary.get("latency_ms", elapsed_ms),
        "retry_count": log_summary.get("retry_count", 0),
        "error_type": log_summary.get("error_type") or error_type,
    }


def write_results(rows: List[Dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    commands = load_commands(Path(args.input))
    if args.limit is not None:
        if args.limit < 0:
            raise ValueError("--limit 不能为负数")
        commands = commands[: args.limit]

    rows = [evaluate_command(item) for item in commands]
    write_results(rows, Path(args.output))
    print(f"已评估 {len(rows)} 条命令，结果写入 {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
