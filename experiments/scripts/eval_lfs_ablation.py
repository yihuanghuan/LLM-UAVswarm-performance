#!/usr/bin/env python3
"""Run the four-method LFS representation ablation against a fixed dataset."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import httpx
from openai import OpenAI


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lfs_ablation_experiment import (  # noqa: E402
    METHODS,
    RunConfig,
    call_method,
    prompt_manifest,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行实验2 LFS中间表示消融。")
    parser.add_argument(
        "--dataset",
        default=str(REPO_ROOT / "experiments" / "commands" / "experiment_02_commands.json"),
    )
    parser.add_argument("--run-id", default="minimax_m27_100x4")
    parser.add_argument("--method", choices=("all",) + METHODS, default="all")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--model", default="MiniMax-M2.7-highspeed")
    parser.add_argument("--base-url", default="https://api.minimax.chat/v1")
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--max-tokens", type=int, default=4000)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--retry-api-errors",
        action="store_true",
        help="配合 --resume，仅重跑最终 error_type=api_error 的现有行。",
    )
    return parser.parse_args()


def _git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_existing(path: Path) -> Dict[Tuple[str, str], Dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        return {(row["command_id"], row["method"]): row for row in csv.DictReader(handle)}


def _rewrite_without_keys(path: Path, keys: Iterable[Tuple[str, str]]) -> None:
    if not path.exists():
        return
    remove = set(keys)
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        rows = [row for row in reader if (row["command_id"], row["method"]) not in remove]
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _append_csv(path: Path, row: Dict[str, Any]) -> None:
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row), lineterminator="\n")
        if not exists:
            writer.writeheader()
        writer.writerow(row)
        handle.flush()


def _append_jsonl(path: Path, records: Iterable[Dict[str, Any]]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()


def _bool_text(value: Any) -> Any:
    return str(value).lower() if isinstance(value, bool) else value


def _run_one(
    client: OpenAI,
    method: str,
    item: Dict[str, Any],
    config: RunConfig,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    result, attempts = call_method(client, method, item, config)
    return {key: _bool_text(value) for key, value in result.items()}, attempts


def main() -> int:
    args = parse_args()
    api_key = os.getenv("LLM_API_KEY") or os.getenv("MINIMAX_API_KEY")
    if not api_key:
        print("缺少 LLM_API_KEY 或 MINIMAX_API_KEY", file=sys.stderr)
        return 2
    if args.workers < 1 or args.max_retries < 1:
        print("workers 和 max-retries 必须大于0", file=sys.stderr)
        return 2

    dataset_path = Path(args.dataset).resolve()
    with dataset_path.open(encoding="utf-8") as handle:
        dataset = json.load(handle)
    if not isinstance(dataset, list) or len(dataset) != 100:
        print(f"固定数据集必须包含100条，实际为 {len(dataset) if isinstance(dataset, list) else '非数组'}", file=sys.stderr)
        return 2
    if len({item["id"] for item in dataset}) != len(dataset):
        print("数据集 command id 不唯一", file=sys.stderr)
        return 2

    methods = METHODS if args.method == "all" else (args.method,)
    run_dir = REPO_ROOT / "experiments" / "results" / "experiments_02" / args.run_id
    sample_path = run_dir / "sample_results.csv"
    attempts_path = run_dir / "raw_attempts.jsonl"
    if run_dir.exists() and not args.resume and (sample_path.exists() or attempts_path.exists()):
        print(f"结果目录已存在：{run_dir}；使用 --resume 继续，避免覆盖已有数据。", file=sys.stderr)
        return 2
    run_dir.mkdir(parents=True, exist_ok=True)

    config = RunConfig(
        model=args.model,
        max_retries=args.max_retries,
        timeout=args.timeout,
        max_tokens=args.max_tokens,
    )
    manifest = {
        "experiment": "experiments_02",
        "run_id": args.run_id,
        "base_tag": "gazebo-experiment-v1",
        "base_commit": _git_output("rev-parse", "gazebo-experiment-v1"),
        "starting_commit": _git_output("rev-parse", "HEAD"),
        "branch": _git_output("branch", "--show-current"),
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_path": str(dataset_path.relative_to(REPO_ROOT)),
        "dataset_sha256": _sha256(dataset_path),
        "dataset_size": len(dataset),
        "valid_commands": sum(bool(item.get("expected_lfs")) for item in dataset),
        "invalid_commands": sum(not bool(item.get("expected_lfs")) for item in dataset),
        "model": args.model,
        "base_url": args.base_url,
        "temperature": config.temperature,
        "top_p": config.top_p,
        "max_tokens": config.max_tokens,
        "max_retries": config.max_retries,
        "timeout": config.timeout,
        "workers": args.workers,
        "methods": list(methods),
        "prompts": prompt_manifest(),
    }
    with (run_dir / "run_config.json").open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    with (run_dir / "dataset.json").open("w", encoding="utf-8") as handle:
        json.dump(dataset, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    existing = _read_existing(sample_path)
    targets: List[Tuple[str, Dict[str, Any]]] = []
    retry_keys = set()
    for item in dataset:
        for method in methods:
            key = (str(item["id"]), method)
            row = existing.get(key)
            if row is None:
                targets.append((method, item))
            elif args.resume and args.retry_api_errors and row.get("error_type") == "api_error":
                targets.append((method, item))
                retry_keys.add(key)
    if retry_keys:
        _rewrite_without_keys(sample_path, retry_keys)

    print(f"run_dir={run_dir}")
    print(f"待运行 {len(targets)} 个样本；已保留 {len(existing) - len(retry_keys)} 个样本")
    if not targets:
        return 0

    http_client = httpx.Client(trust_env=False, limits=httpx.Limits(max_connections=max(8, args.workers * 2)))
    client = OpenAI(api_key=api_key, base_url=args.base_url, http_client=http_client)
    failures = 0
    completed = 0
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            future_map = {
                executor.submit(_run_one, client, method, item, config): (method, item["id"])
                for method, item in targets
            }
            for future in as_completed(future_map):
                method, command_id = future_map[future]
                try:
                    row, attempts = future.result()
                except Exception as exc:
                    print(f"[{command_id}/{method}] runner异常: {type(exc).__name__}: {exc}", file=sys.stderr)
                    failures += 1
                    continue
                _append_jsonl(attempts_path, attempts)
                _append_csv(sample_path, row)
                completed += 1
                if row["error_type"] == "api_error":
                    failures += 1
                print(
                    f"[{completed}/{len(targets)}] {command_id}/{method} "
                    f"exec={row['executable']} compile={row['compilation_success']} "
                    f"retry={row['retry_count']} error={row['error_type'] or '-'}"
                )
    finally:
        http_client.close()

    final_rows = _read_existing(sample_path)
    expected_keys = {(str(item["id"]), method) for item in dataset for method in methods}
    missing = sorted(expected_keys - set(final_rows))
    print(f"最终结果 {len(final_rows)} 行；本轮 runner/API 异常 {failures}；缺失 {len(missing)}")
    if missing:
        print("缺失键: " + ", ".join(f"{key[0]}/{key[1]}" for key in missing[:20]), file=sys.stderr)
        return 1
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
