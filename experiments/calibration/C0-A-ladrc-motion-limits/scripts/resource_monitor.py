#!/usr/bin/env python3
"""Read-only per-second host and in-scope process resource logger."""

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()
    with args.output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=(
            "timestamp_utc", "load_1m", "memory_used_bytes", "memory_total_bytes",
            "px4_processes", "gzserver_processes", "controller_processes",
        ))
        writer.writeheader()
        while True:
            load_1m = Path("/proc/loadavg").read_text().split()[0]
            memory = {}
            for line in Path("/proc/meminfo").read_text().splitlines():
                key, value = line.split(":", 1)
                memory[key] = int(value.strip().split()[0]) * 1024
            counts = {}
            for name in ("px4", "gzserver", "ladrc_position_controller_node"):
                result = subprocess.run(
                    ["pgrep", "-xc", name], text=True, capture_output=True, check=False
                )
                counts[name] = int(result.stdout.strip() or 0)
            writer.writerow({
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "load_1m": load_1m,
                "memory_used_bytes": memory["MemTotal"] - memory["MemAvailable"],
                "memory_total_bytes": memory["MemTotal"],
                "px4_processes": counts["px4"],
                "gzserver_processes": counts["gzserver"],
                "controller_processes": counts["ladrc_position_controller_node"],
            })
            stream.flush()
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
