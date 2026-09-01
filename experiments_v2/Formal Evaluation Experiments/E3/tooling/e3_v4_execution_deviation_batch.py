#!/usr/bin/env python3
"""Resume the frozen 60-attempt F0-only Family-B qualification order."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

import yaml

TOOLING = Path(__file__).resolve().parent
E3_DIR = TOOLING.parent
GRID = E3_DIR / "E3_v4_family_B_execution_deviation_grid.yaml"
RUNNER = TOOLING / "e3_v4_execution_deviation_qualification.py"
DEFAULT_OUTPUT = E3_DIR / "results/qualification/execution_deviation_raw"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def expanded_order(grid: dict) -> list[tuple[str, str, int]]:
    return [
        (candidate, condition, int(seed))
        for candidate in grid["execution_order"]["candidate_order"]
        for condition in grid["qualification_population"]["conditions"]
        for seed in grid["qualification_population"]["seeds"]
    ]


def manifests(output: Path, trial_id: str) -> list[dict]:
    values = []
    for path in sorted(output.glob(trial_id + "*/attempt.json")):
        try:
            value = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if value.get("trial_id") == trial_id:
            values.append(value)
    return values


def next_retry(values: list[dict]) -> str | None:
    if not values:
        return None
    maximum = 0
    for value in values:
        suffix = value.get("retry_suffix")
        if isinstance(suffix, str) and suffix.startswith("r"):
            maximum = max(maximum, int(suffix[1:]))
    return f"r{maximum + 1}"


def append_journal(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
        stream.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-new-attempts", type=int)
    args = parser.parse_args()
    grid = yaml.safe_load(GRID.read_text())
    if grid["F1_permitted"] is not False or grid["formal_execution_permitted"] is not False:
        raise RuntimeError("grid is not sealed to non-formal F0 qualification")
    output = args.output_root.resolve()
    output.mkdir(parents=True, exist_ok=True)
    journal = output / "batch_journal.jsonl"
    launched = 0
    order = expanded_order(grid)
    for index, (candidate, condition, seed) in enumerate(order, start=1):
        trial_id = f"E3V4B-{candidate}__{condition}__S{seed}"
        existing = manifests(output, trial_id)
        if any(value.get("attempt_status") == "success" for value in existing):
            continue
        if args.max_new_attempts is not None and launched >= args.max_new_attempts:
            break
        retry = next_retry(existing)
        command = [
            sys.executable, str(RUNNER), "--candidate", candidate,
            "--condition", condition, "--seed", str(seed),
            "--output-root", str(output),
        ]
        if retry:
            command.extend(["--retry-suffix", retry])
        started = utc_now()
        print(
            f"[{index:02d}/{len(order)}] {trial_id}"
            + (f" retry={retry}" if retry else ""),
            flush=True,
        )
        run = subprocess.run(command, text=True, stdout=subprocess.DEVNULL)
        launched += 1
        updated = manifests(output, trial_id)
        latest = updated[-1] if updated else {}
        append_journal(journal, {
            "schema": "E3_v4_execution_deviation_batch_journal_v1",
            "order_index": index,
            "registered_trial_id": trial_id,
            "candidate_id": candidate,
            "condition": condition,
            "feedback": "F0",
            "seed": seed,
            "retry_suffix": retry,
            "started_utc": started,
            "finished_utc": utc_now(),
            "runner_returncode": run.returncode,
            "attempt_instance_id": latest.get("attempt_instance_id"),
            "attempt_status": latest.get("attempt_status"),
            "accepted_formal_result": False,
            "formal_cursor_consumed": False,
        })
        print(
            f"  -> {latest.get('attempt_status', 'MISSING')} "
            f"({latest.get('attempt_instance_id', 'no manifest')})",
            flush=True,
        )
        if run.returncode != 0 or latest.get("attempt_status") != "success":
            print("STOP_ON_RETAINED_FAILURE", flush=True)
            return 2
    completed = sum(
        any(value.get("attempt_status") == "success" for value in manifests(
            output, f"E3V4B-{candidate}__{condition}__S{seed}"
        )) for candidate, condition, seed in order
    )
    print(f"QUALIFICATION_ORDER_PROGRESS={completed}/{len(order)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
