#!/usr/bin/env python3
"""Reanalyze the frozen experiment-10 v2 batch under v3 timing semantics."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from system_common import CONFIG_PATH, REPO_ROOT, load_yaml


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--batch-id", default="exp10-formal-v2-gated-20260803")
    parser.add_argument("--config", default=str(CONFIG_PATH))
    parser.add_argument("--execution-commit", default="unknown")
    args = parser.parse_args()
    config = load_yaml(Path(args.config).resolve())
    batch = (REPO_ROOT / config["paths"]["results_root"] / args.batch_id).resolve()
    output = batch / "reanalysis_v3"
    script_root = Path(__file__).resolve().parent
    subprocess.run([
        sys.executable, str(script_root / "summarize_v3.py"),
        "--batch-id", args.batch_id, "--config", str(Path(args.config).resolve()),
        "--output-dir", str(output), "--legacy-v2",
        "--execution-commit", args.execution_commit,
    ], check=True)
    subprocess.run([
        sys.executable, str(script_root / "plot_v3.py"), str(batch),
        "--summaries-dir", str(output),
        "--figures-dir", str(output / "figures"),
    ], check=True)
    print(f"generated read-only v3 reanalysis in {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
