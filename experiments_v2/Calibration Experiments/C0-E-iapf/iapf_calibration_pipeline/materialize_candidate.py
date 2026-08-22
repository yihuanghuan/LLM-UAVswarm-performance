#!/usr/bin/env python3
"""Materialize a bounded C0-E candidate from the frozen C0-D envelope."""
from __future__ import annotations

import argparse
from pathlib import Path
import yaml


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--enter", type=float, required=True)
    parser.add_argument("--exit", dest="exit_", type=float, required=True)
    parser.add_argument("--repulsion-base", type=float, default=1.0)
    parser.add_argument("--repulsion-margin", type=float, default=0.25)
    args = parser.parse_args()
    policy = yaml.safe_load(args.base.read_text())
    safety = policy["safety"]
    safety.update(mapping_type="hard_anchored_linear", d_hard=1.50,
                  d_plan_base=1.80, s_min=1.0, s_max=2.0,
                  iapf_enter_base=args.enter, iapf_exit_base=args.exit_,
                  iapf_repulsion_base=args.repulsion_base,
                  iapf_repulsion_margin=args.repulsion_margin)
    # Deterministic coverage bounds, derived from monotone s in [1, 2].
    hard = safety["d_hard"]
    enter_max = hard + 2.0 * (args.enter - hard)
    exit_max = hard + 2.0 * (args.exit_ - hard)
    repulsion_max = args.repulsion_base + args.repulsion_margin
    policy["controller_hard_clamps"].update(
        iapf_enter_min=args.enter, iapf_enter_max=enter_max,
        iapf_exit_max=exit_max, iapf_repulsion_max=repulsion_max)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(yaml.safe_dump(policy, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
