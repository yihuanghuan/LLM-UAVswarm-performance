#!/usr/bin/env python3
"""Materialize the prospectively frozen parking layout audit."""

from __future__ import annotations

import json
from pathlib import Path

from large_swarm_common import ROOT, layout_audit


def main() -> int:
    output = ROOT / "scenarios/large_swarm_parking_layout_audit.json"
    audit = layout_audit()
    output.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": audit["status"], "output": str(output)}, sort_keys=True))
    return 0 if audit["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
