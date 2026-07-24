#!/usr/bin/env python3
"""Run experiment 01 across all LLM parsing methods."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from openai import OpenAI
import httpx


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from llm_parser_experiment import (  # noqa: E402
    METHODS,
    RunConfig,
    call_method,
    evaluate_prediction,
    prompt_manifest,
)


DEFAULT_INPUT = REPO_ROOT / "experiments" / "commands" / "experiment_01_commands.json"
DEFAULT_RESULTS = REPO_ROOT / "experiments" / "results" / "experiments_01"
DEFAULT_BASE_URL = "https://api.minimax.chat/v1"
DEFAULT_MODEL = "MiniMax-M2.7-highspeed"

RESULT_FIELDS = [
    "run_id", "command_id", "command_type", "complexity", "method",
    "valid_json", "schema_valid", "compiled_success", "prompt_tokens",
    "completion_tokens", "latency_ms", "retry_count", "error_type",
    "matched_task_coverage", "uav_set_accuracy", "formation_accuracy",
    "center_error", "radius_error", "duration_error", "motion_style_accuracy",
    "safety_factor_error", "trigger_accuracy", "field_accuracy",
    "exact_task_accuracy", "rejection_accuracy", "normalized_response",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行实验 01：四种 LLM 解析方法对比。")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output-dir", default=str(DEFAULT_RESULTS))
    parser.add_argument("--run-id", default=datetime.now().strftime("run_%Y%m%d_%H%M%S"))
    parser.add_argument("--method", choices=["all", *METHODS], default="all")
    parser.add_argument("--model", default=os.getenv("LLM_MODEL", DEFAULT_MODEL))
    parser.add_argument("--base-url", default=os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--workers", type=int, default=1, help="并发 API 请求数，默认 1。")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--sample-id", action="append", default=[], help="只运行指定样本 ID，可重复传入。")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--retry-api-errors", action="store_true", help="续跑时重试 api_error/quota_exhausted 行。")
    return parser.parse_args()


def load_dataset(path: Path) -> List[Dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        rows = json.load(handle)
    if not isinstance(rows, list) or not rows:
        raise ValueError("输入必须是非空 JSON 数组")
    ids = set()
    for row in rows:
        required = {"id", "type", "complexity", "command", "ros_aux_info"}
        missing = required - set(row)
        if missing:
            raise ValueError(f"样本缺少字段 {sorted(missing)}")
        if ("expected_lfs" in row) == ("expected_error" in row):
            raise ValueError(f"样本 {row['id']} 必须且只能包含 expected_lfs/expected_error 之一")
        if row["id"] in ids:
            raise ValueError(f"样本 ID 重复: {row['id']}")
        ids.add(row["id"])
    return rows


def read_existing(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_rows(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=RESULT_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def prepare_run(
    args: argparse.Namespace,
    dataset: List[Dict[str, Any]],
    selected_methods: Sequence[str],
) -> Tuple[Path, List[Dict[str, str]]]:
    run_dir = Path(args.output_dir) / args.run_id
    result_path = run_dir / "sample_results.csv"
    if run_dir.exists() and not args.resume:
        raise FileExistsError(f"运行目录已存在；拒绝覆盖: {run_dir}。续跑请添加 --resume")
    run_dir.mkdir(parents=True, exist_ok=True)
    existing = read_existing(result_path) if args.resume else []
    if args.resume and args.retry_api_errors:
        existing = [row for row in existing if row.get("error_type") not in {"api_error", "quota_exhausted"}]
    if not (run_dir / "dataset.json").exists():
        (run_dir / "dataset.json").write_text(
            json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    config_path = run_dir / "run_config.json"
    if not config_path.exists():
        config_path.write_text(json.dumps({
            "experiment": "experiments_01",
            "run_id": args.run_id,
            "base_tag": "gazebo-experiment-v1",
            "base_commit": "6c3496e7a42d7987751dc414396b3d9b11841721",
            "model": args.model,
            "base_url": args.base_url,
            "temperature": 0.0,
            "top_p": 0.01,
            "max_tokens": 4000,
            "max_retries": args.max_retries,
            "timeout": args.timeout,
            "workers": args.workers,
            "methods": list(selected_methods),
            "numeric_tolerance": 1e-6,
            "prompts": prompt_manifest(),
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return run_dir, existing


def semantic_error(item: Dict[str, Any], execution: Dict[str, Any], metrics: Dict[str, Any]) -> str:
    if execution["error_type"]:
        return str(execution["error_type"])
    normalized = execution.get("normalized") or {}
    if "expected_error" in item:
        if metrics["rejection_accuracy"] == 1.0:
            return ""
        return "wrong_rejection" if normalized.get("error") else "unexpected_task"
    if normalized.get("error"):
        return "unexpected_rejection"
    if metrics["exact_task_accuracy"] != 1.0:
        return "semantic_mismatch"
    return ""


def main() -> int:
    args = parse_args()
    if args.max_retries < 1:
        raise ValueError("--max-retries 必须至少为 1")
    if args.workers < 1:
        raise ValueError("--workers 必须至少为 1")
    if args.limit is not None and args.limit < 0:
        raise ValueError("--limit 不能为负数")
    api_key = os.getenv("LLM_API_KEY") or os.getenv("MINIMAX_API_KEY")
    if not api_key:
        raise RuntimeError("缺少 LLM_API_KEY 或 MINIMAX_API_KEY")

    dataset = load_dataset(Path(args.input))
    if args.sample_id:
        requested = set(args.sample_id)
        dataset = [item for item in dataset if item["id"] in requested]
        missing = sorted(requested - {item["id"] for item in dataset})
        if missing:
            raise ValueError(f"未找到样本 ID: {missing}")
    if args.limit is not None:
        dataset = dataset[:args.limit]
    methods = list(METHODS) if args.method == "all" else [args.method]
    run_dir, existing_rows = prepare_run(args, dataset, methods)
    result_path = run_dir / "sample_results.csv"
    raw_path = run_dir / "raw_attempts.jsonl"
    completed = {(row["command_id"], row["method"]) for row in existing_rows}
    rows: List[Dict[str, Any]] = list(existing_rows)

    client = OpenAI(
        api_key=api_key,
        base_url=args.base_url,
        http_client=httpx.Client(trust_env=False),
    )
    config = RunConfig(model=args.model, max_retries=args.max_retries, timeout=args.timeout)
    total = len(dataset) * len(methods)
    done = sum((item["id"], method) in completed for item in dataset for method in methods)
    print(f"实验开始：{len(dataset)} 条样本 × {len(methods)} 种方法；已完成 {done}/{total}")

    pending = [
        (item, method)
        for item in dataset
        for method in methods
        if (item["id"], method) not in completed
    ]
    quota_stopped = False
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        for batch_start in range(0, len(pending), args.workers):
            batch = pending[batch_start:batch_start + args.workers]
            futures: Dict[Future[Any], Tuple[Dict[str, Any], str]] = {
                executor.submit(call_method, client, method, item, config): (item, method)
                for item, method in batch
            }
            for future in as_completed(futures):
                item, method = futures[future]
                execution, attempts = future.result()
                metrics = evaluate_prediction(item, execution.get("normalized"))
                error_type = semantic_error(item, execution, metrics)
                row: Dict[str, Any] = {
                    "run_id": args.run_id,
                    "command_id": item["id"],
                    "command_type": item["type"],
                    "complexity": item["complexity"],
                    "method": method,
                    "valid_json": execution["valid_json"],
                    "schema_valid": execution["schema_valid"],
                    "compiled_success": execution["compiled_success"],
                    "prompt_tokens": execution["prompt_tokens"],
                    "completion_tokens": execution["completion_tokens"],
                    "latency_ms": execution["latency_ms"],
                    "retry_count": execution["retry_count"],
                    "error_type": error_type,
                    **metrics,
                    "normalized_response": json.dumps(execution.get("normalized"), ensure_ascii=False, separators=(",", ":")),
                }
                rows.append(row)
                with raw_path.open("a", encoding="utf-8") as handle:
                    for attempt in attempts:
                        handle.write(json.dumps({
                            "run_id": args.run_id,
                            "command_id": item["id"],
                            "method": method,
                            **attempt,
                        }, ensure_ascii=False) + "\n")
                write_rows(result_path, rows)
                done += 1
                print(
                    f"[{done}/{total}] {item['id']} / {method}: "
                    f"schema={execution['schema_valid']} error={error_type or 'none'}"
                )
                quota_stopped = quota_stopped or error_type == "quota_exhausted"
            if quota_stopped:
                print("检测到 Token Plan 用量上限，停止提交后续请求；补充额度后使用 --resume --retry-api-errors。")
                break

    if quota_stopped:
        print(f"实验未完成：当前保存 {len(rows)}/{total} 条结果到 {result_path}")
        return 2
    print(f"实验完成：{len(rows)} 条结果写入 {result_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
