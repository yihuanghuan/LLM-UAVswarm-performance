#!/usr/bin/env python3
"""Read-only reconstruction of the immutable v1 large-swarm sweep evidence."""

from __future__ import annotations

import csv
import json
import math
import re
from collections import defaultdict
from pathlib import Path


HERE = Path(__file__).resolve()
V2 = HERE.parents[1]
STUDY = HERE.parents[2]
V1_RESULTS = STUDY / "results/infrastructure_sweep"
RUNS = {20: "N20_recovery1", 24: "N24", 28: "N28", 32: "N32"}
FRESHNESS_S = 0.5


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def finite(values: list[float]) -> bool:
    return bool(values) and all(math.isfinite(float(value)) for value in values)


def agent_clients(text: str) -> dict[int, dict]:
    clients: dict[int, dict] = defaultdict(
        lambda: {"participant_count": 0, "reader_count": 0, "writer_count": 0,
                 "first_timestamp": None, "last_timestamp": None}
    )
    for line in text.splitlines():
        match = re.search(r"\[(\d+\.\d+)\].*client_key: 0x([0-9A-Fa-f]+)", line)
        if not match:
            continue
        timestamp = float(match.group(1))
        client = clients[int(match.group(2), 16)]
        client["first_timestamp"] = timestamp if client["first_timestamp"] is None else min(client["first_timestamp"], timestamp)
        client["last_timestamp"] = timestamp if client["last_timestamp"] is None else max(client["last_timestamp"], timestamp)
        client["participant_count"] += int("participant created" in line)
        client["reader_count"] += int("datareader created" in line)
        client["writer_count"] += int("datawriter created" in line)
    return dict(clients)


def per_uav(n: int) -> list[dict]:
    run_dir = V1_RESULTS / RUNS[n]
    result = load_json(run_dir / "result.json")
    readiness = load_json(run_dir / "readiness.stdout.json")
    controller_text = (run_dir / "controllers.log").read_text(encoding="utf-8", errors="replace")
    clients = agent_clients((run_dir / "agent.log").read_text(encoding="utf-8", errors="replace"))
    rows = []
    for uid in range(1, n + 1):
        px4 = (run_dir / f"px4_{uid}.log").read_text(encoding="utf-8", errors="replace")
        controller_lines = [line for line in controller_text.splitlines() if f"[uav{uid}." in line]
        controller = "\n".join(controller_lines)
        status = readiness.get("diagnostics", {}).get(str(uid), {})
        state = readiness.get("state_diagnostics", {}).get(str(uid), {})
        values = list(state.get("position", [])) + list(state.get("velocity", []))
        rtts = [int(value) for value in re.findall(r"RTT too high for timesync: (\d+) ms", px4)]
        client = clients.get(uid + 1, {})
        warnings = []
        if "height estimate not stable" in px4:
            warnings.append("PX4 height estimate not stable")
        if "Failsafe activated" in px4:
            warnings.append("PX4 transient failsafe logged")
        if "create entities failed" in px4:
            warnings.append("XRCE entity creation failure")
        if not ("vehicle_odometry data writer" in px4):
            warnings.append("no PX4 odometry writer")
        if "启动流程失败" in controller or "startup=FAILED" in controller:
            warnings.append("controller startup failed")
        if state.get("present") and not finite(values):
            warnings.append("non-finite final state")
        if not state.get("present"):
            warnings.append("no final swarm_state")
        if rtts:
            warnings.append(f"max timesync RTT {max(rtts)} ms")
        rows.append({
            "uav_id": uid,
            "px4_alive": result.get("process_counts_at_readiness", {}).get("px4") == n,
            "sim_connected": "Simulator connected" in px4,
            "dds_initialized": "uxrce_dds_client] init UDP" in px4 and client.get("participant_count", 0) == 1,
            "px4_output_writers": client.get("writer_count", 0),
            "vehicle_status_observed": bool(status.get("present")),
            "vehicle_odometry_observed": "已接收到 vehicle_odometry 消息" in controller,
            "controller_alive": result.get("process_counts_at_readiness", {}).get("controllers") == n and bool(controller_lines),
            "armed": bool(status.get("armed")),
            "offboard": bool(status.get("offboard")),
            "swarm_state_observed": bool(state.get("present")),
            "final_state_finite": finite(values),
            "final_state_fresh": bool(state.get("present")) and float(state.get("age_s", math.inf)) <= FRESHNESS_S,
            "altitude_m": status.get("altitude"),
            "speed_mps": status.get("speed"),
            "max_timesync_rtt_ms": max(rtts, default=None),
            "relevant_error_warning": "; ".join(warnings) or "none",
        })
    return rows


def write_csv(n: int, rows: list[dict]) -> None:
    path = V2 / f"per_uav_N{n}_diagnostics.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    all_rows = {n: per_uav(n) for n in RUNS}
    for n in (24, 28, 32):
        write_csv(n, all_rows[n])
    summary = {}
    for n, rows in all_rows.items():
        summary[str(n)] = {
            "px4_alive": sum(row["px4_alive"] for row in rows),
            "sim_connected": sum(row["sim_connected"] for row in rows),
            "dds_initialized": sum(row["dds_initialized"] for row in rows),
            "px4_with_all_15_output_writers": sum(row["px4_output_writers"] == 15 for row in rows),
            "vehicle_status_observed": sum(row["vehicle_status_observed"] for row in rows),
            "vehicle_odometry_observed": sum(row["vehicle_odometry_observed"] for row in rows),
            "controller_alive": sum(row["controller_alive"] for row in rows),
            "armed_offboard": sum(row["armed"] and row["offboard"] for row in rows),
            "swarm_state_observed_at_timeout": sum(row["swarm_state_observed"] for row in rows),
            "final_finite": sum(row["final_state_finite"] for row in rows),
            "final_fresh": sum(row["final_state_fresh"] for row in rows),
            "max_timesync_rtt_ms": max((row["max_timesync_rtt_ms"] or 0) for row in rows),
        }
    (V2 / "v1_evidence_machine_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
