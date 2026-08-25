#!/usr/bin/env python3
"""Run only the preregistered C0-F screening, confirmation, or smoke trials."""
from __future__ import annotations

import argparse
import subprocess
import sys

from common import CANONICAL_POLICY, PIPELINE, PYTHON, RAW, SCENES_FILE, STYLES, load_yaml


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("screening", "confirmation", "style_switch_screening", "style_switch_confirmation"), required=True)
    parser.add_argument("--policy", default=str(CANONICAL_POLICY))
    parser.add_argument("--root", default=str(RAW))
    args = parser.parse_args()
    definitions = load_yaml(SCENES_FILE)
    if args.stage == "screening":
        trials = [(scene, style, 1, definitions["seed_policy"]["screening"])
                  for scene in ("S1", "S2", "S3", "S4") for style in STYLES]
    elif args.stage == "confirmation":
        trials = [
            (scene, style, cold, definitions["seed_policy"][f"confirmation_cold_{cold}"])
            for scene in ("S1", "S2", "S3", "S4") for style in STYLES for cold in (1, 2)
        ]
    else:
        trials = [("SWITCH", "style_switch", 1,
                   definitions["seed_policy"]["screening" if args.stage.endswith("screening") else "confirmation_cold_1"])]
    failures = []
    for index, (scene, style, cold, seed) in enumerate(trials, start=1):
        command = [
            str(PYTHON), str(PIPELINE / "run_trial.py"), "--stage", args.stage,
            "--scene", scene, "--style", style, "--cold-start", str(cold),
            "--seed", seed, "--policy", args.policy, "--root", args.root,
        ]
        print(f"[{index}/{len(trials)}] {scene} {style} cold={cold}", flush=True)
        result = subprocess.run(command, text=True)
        if result.returncode:
            failures.append((scene, style, cold, result.returncode))
            # A failed screening condition is evidence; continue the fixed screen.
    if failures:
        print(f"C0-F {args.stage} failures: {failures}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
