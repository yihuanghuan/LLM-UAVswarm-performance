#!/usr/bin/env python3
"""Build and execute the complete paired experiment 08 protocol."""

from __future__ import annotations

import argparse
import csv
import json
import os
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from experiment_common import CONFIG_ROOT, RESULTS_ROOT, load_yaml


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
WORKSPACE_ROOT = REPO_ROOT.parents[1]


@dataclass(frozen=True)
class Trial:
    phase: str
    family: str
    scenario: str
    method: str
    trial: int
    seed: int
    condition_label: str | None = None
    overrides: Dict[str, float] = field(default_factory=dict)
    escape_mode: str | None = None


def protocol_arms() -> List[tuple[str, str, str]]:
    arms: List[tuple[str, str, str]] = []
    arms.extend(
        ("nonintrusive", scenario, method)
        for scenario in ["safe_wide_line_to_circle", "safe_parallel_groups"]
        for method in ["IAPF_OFF", "IAPF_ON"])
    arms.extend(
        ("fallback", scenario, method)
        for scenario in [
            "staggered_crossing_delay", "group_crossing_hold",
            "dense_local_bias"]
        for method in ["IAPF_OFF", "IAPF_ON"])
    arms.extend(
        ("complement", scenario, method)
        for scenario in ["assignment_crossing_4", "assignment_dense_8"]
        for method in ["DIST_OFF", "DIST_ON", "SAFE_OFF", "SAFE_ON"])
    arms.extend(
        ("stress", scenario, method)
        for scenario in [
            "head_on", "vertical", "grouped_reconfiguration",
            "dense_infeasible"]
        for method in ["STRESS_OFF", "STRESS_ON"])
    arms.append(("ablation", "staggered_crossing_delay", "ABL_POSITION"))
    if len(arms) != 27:
        raise AssertionError(f"expected 27 protocol arms, got {len(arms)}")
    return arms


def protocol_trials(include_pilot: bool = True) -> List[Trial]:
    defaults = load_yaml(CONFIG_ROOT / "experiment_defaults.yaml")
    formal_seeds = [int(value) for value in defaults["experiment"]["seeds"]]
    pilot_seeds = [int(value) for value in defaults["experiment"]["pilot_seeds"]]
    trials: List[Trial] = []
    arms = protocol_arms()
    if include_pilot:
        for family, scenario, method in arms:
            for index, seed in enumerate(pilot_seeds, start=1):
                trials.append(Trial(
                    "pilot", family, scenario, method, index, seed))
    for family, scenario, method in arms:
        seeds = formal_seeds[:5] if family == "stress" else formal_seeds
        for index, seed in enumerate(seeds, start=1):
            trials.append(Trial(
                family, family, scenario, method, index, seed))
    formal_count = sum(trial.phase != "pilot" for trial in trials)
    if formal_count != int(defaults["protocol"]["formal_trial_count"]):
        raise AssertionError(
            f"expected 230 formal trials, got {formal_count}")
    return trials


class SimulatorSupervisor:
    def __init__(self, batch_dir: Path, uav_count: int = 8):
        self.batch_dir = batch_dir
        self.uav_count = uav_count
        self.processes: List[tuple[subprocess.Popen, object]] = []

    def start_process(
        self, name: str, command: str, cwd: Path | None = None
    ) -> subprocess.Popen:
        log_path = self.batch_dir / "runtime_logs" / f"{name}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handle = log_path.open("a", encoding="utf-8")
        process = subprocess.Popen(
            ["bash", "-lc", command], cwd=cwd, stdout=handle,
            stderr=subprocess.STDOUT, start_new_session=True)
        self.processes.append((process, handle))
        return process

    def start(self) -> None:
        self.stop()
        px4_root = Path(os.environ.get(
            "PX4_AUTOPILOT_DIR", "/home/yihuang/PX4-Autopilot"))
        self.start_process("micro_xrce_agent", "MicroXRCEAgent udp4 -p 8888")
        self.start_process(
            "px4_gazebo",
            "source Tools/simulation/gazebo-classic/setup_gazebo.bash "
            "$(pwd) $(pwd)/build/px4_sitl_default && "
            f"./Tools/simulation/gazebo-classic/sitl_multiple_run.sh "
            f"-m iris -n {self.uav_count}",
            px4_root)
        time.sleep(18)
        self.start_process(
            "controllers",
            f"source /opt/ros/humble/setup.bash && "
            f"source {WORKSPACE_ROOT}/install/setup.bash && "
            f"ros2 launch ladrc_controller swarm_launch.py "
            f"uav_ids:=[{','.join(map(str, range(1, self.uav_count + 1)))}]")
        time.sleep(18)
        failed = [
            process.pid for process, _ in self.processes
            if process.poll() is not None]
        if failed:
            raise RuntimeError(f"simulator startup process exited: {failed}")

    def stop(self) -> None:
        for process, _ in reversed(self.processes):
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGINT)
                except ProcessLookupError:
                    pass
        deadline = time.monotonic() + 12
        for process, handle in reversed(self.processes):
            remaining = max(0.0, deadline - time.monotonic())
            try:
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)
            handle.close()
        self.processes.clear()


def trial_command(
    trial: Trial, batch_id: str, dry_run: bool,
    results_root: Path,
    calibrated_overrides: Dict[str, float] | None = None,
) -> List[str]:
    command = [
        "python3", str(SCRIPT_DIR / "run_experiment.py"),
        "--scenario", trial.scenario, "--method", trial.method,
        "--trial", str(trial.trial), "--seed", str(trial.seed),
        "--batch-id", batch_id, "--phase", trial.phase,
        "--family", trial.family,
        "--results-root", str(results_root),
    ]
    if trial.condition_label:
        command.extend(["--condition-label", trial.condition_label])
    if trial.escape_mode:
        command.extend(["--escape-mode", trial.escape_mode])
    effective_overrides = dict(calibrated_overrides or {})
    effective_overrides.update(trial.overrides)
    for name, value in effective_overrides.items():
        command.extend(["--parameter-override", f"{name}={value}"])
    if dry_run:
        command.append("--dry-run")
    return command


def read_trial_collision(batch_dir: Path, trial: Trial) -> bool:
    label = trial.condition_label or trial.method
    summary = (
        batch_dir / "raw" / trial.scenario / label
        / f"trial_{trial.trial:02d}_seed_{trial.seed}" / "trial_summary.csv")
    if not summary.is_file():
        return False
    with summary.open(newline="", encoding="utf-8") as handle:
        row = next(csv.DictReader(handle))
    return int(float(row["collision_event_count"])) > 0


def scenario_uav_count(scenario: str) -> int:
    configuration = load_yaml(
        CONFIG_ROOT / "scenarios" / f"{scenario}.yaml")
    return len(configuration["uav_ids"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-id", required=True)
    parser.add_argument(
        "--phase", action="append",
        choices=["pilot", "formal", "nonintrusive", "fallback", "complement",
                 "stress", "ablation", "all"],
        default=[])
    parser.add_argument("--manage-sim", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-retries", type=int, default=2)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    phases = set(args.phase or ["all"])
    selected = protocol_trials()
    if "all" not in phases:
        selected = [
            trial for trial in selected
            if trial.phase in phases
            or ("formal" in phases and trial.phase != "pilot")]
    has_pilot = any(trial.phase == "pilot" for trial in selected)
    has_formal = any(trial.phase != "pilot" for trial in selected)
    result_partition = (
        "combined" if has_pilot and has_formal
        else ("pilot" if has_pilot else "formal"))
    results_root = RESULTS_ROOT / result_partition
    batch_dir = results_root / args.batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    manifest = [
        {
            "index": index, "phase": trial.phase, "family": trial.family,
            "scenario": trial.scenario,
            "method": trial.method, "condition": trial.condition_label or trial.method,
            "trial": trial.trial, "seed": trial.seed,
            "overrides": trial.overrides, "escape_mode": trial.escape_mode,
        }
        for index, trial in enumerate(selected, start=1)
    ]
    (batch_dir / "batch_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"planned trials: {len(selected)}")
    if args.dry_run:
        for trial in selected:
            subprocess.run(
                trial_command(
                    trial, args.batch_id, True, results_root), check=True)
        return 0

    supervisor = SimulatorSupervisor(batch_dir) if args.manage_sim else None
    active_uav_count = None
    try:
        for index, trial in enumerate(selected, start=1):
            label = trial.condition_label or trial.method
            trial_dir = (
                batch_dir / "raw" / trial.scenario / label
                / f"trial_{trial.trial:02d}_seed_{trial.seed}")
            if args.resume and (trial_dir / "trial_summary.csv").is_file():
                print(f"[{index}/{len(selected)}] skip completed {trial_dir}")
                continue
            if supervisor:
                required_uav_count = scenario_uav_count(trial.scenario)
                if required_uav_count != active_uav_count:
                    supervisor.stop()
                    supervisor.uav_count = required_uav_count
                    supervisor.start()
                    active_uav_count = required_uav_count
            for attempt in range(args.max_retries + 1):
                print(
                    f"[{index}/{len(selected)}] {trial.phase} {trial.scenario} "
                    f"{label} trial={trial.trial} attempt={attempt}")
                result = subprocess.run(
                    trial_command(
                        trial, args.batch_id, False, results_root),
                    check=False)
                if result.returncode == 0:
                    break
                if trial_dir.exists():
                    failed_dir = trial_dir.with_name(
                        f"{trial_dir.name}_failed_attempt_{attempt}")
                    if failed_dir.exists():
                        raise FileExistsError(failed_dir)
                    trial_dir.rename(failed_dir)
                if attempt >= args.max_retries:
                    raise RuntimeError(f"trial failed after retries: {trial}")
                if supervisor:
                    supervisor.start()
                time.sleep(2)
            if supervisor and read_trial_collision(batch_dir, trial):
                supervisor.start()
    finally:
        if supervisor:
            supervisor.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
