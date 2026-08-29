#!/usr/bin/env python3
"""Isolated worker that invokes one pinned adapter in non-formal spec mode."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--entrypoint", required=True)
    parser.add_argument("--trial-id", required=True)
    parser.add_argument("--context", type=Path, required=True)
    args = parser.parse_args()
    source = args.checkout / args.entrypoint
    sys.path.insert(0, str(source.parent))
    sys.path.insert(0, str(args.checkout))
    spec = importlib.util.spec_from_file_location("campaign_v2_pinned_adapter", source)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load pinned adapter")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    context = json.loads(args.context.read_text(encoding="utf-8"))
    descriptor = module.run_exact_trial(args.trial_id, context)
    print(json.dumps(descriptor, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
