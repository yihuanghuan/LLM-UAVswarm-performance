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
from typing import Dict, Iterable, List

from experiment_common import CONFIG_ROOT, RESULTS_ROOT, load_yaml


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
WORKSPACE_ROOT = REPO_ROOT.parents[1]


@dataclass(frozen=True)
class Trial:
    phase: str
    scenario: str
    method: str
    trial: int
    seed: int
    condition_label: str | None = None
    overrides: Dict[str, float] = field(default_factory=dict)
    escape_mode: str | None = None


def base_trials(
    phase: str, scenarios: Iterable[str], seeds: List[int]
) -> List[Trial]:
    return [
        Trial(phase, scenario, method, index, seed)
        for scenario in scenarios
        for method in [f"M{value}" for value in range(6)]
        for index, seed in enumerate(seeds, start=1)
    ]


def protocol_trials() -> List[Trial]:
    defaults = load_yaml(CONFIG_ROOT / "experiment_defaults.yaml")
    formal_seeds = [int(value) for value in defaults["experiment"]["seeds"]]
    pilot_seeds = [int(value) for value in defaults["experiment"]["pilot_seeds"]]
    calibration_seeds = [int(value) for value in defaults["calibration"]["seeds"]]
    trials: List[Trial] = []

    nominal = {
        "iapf_repulsion_gain": 25.0,
        "iapf_position_gain": 0.05,
        "iapf_accel_gain": 0.30,
    }
    calibration_conditions = [("cal_nominal", {})]
    for parameter, values in defaults["calibration"]["factors"].items():
        for value in values:
            if float(value) == nominal[parameter]:
                continue
            suffix = "low" if float(value) < nominal[parameter] else "high"
            calibration_conditions.append(
                (f"cal_{parameter}_{suffix}", {parameter: float(value)}))
    for scenario in ["head_on_calibration", "dense_calibration"]:
        for label, overrides in calibration_conditions:
            for index, seed in enumerate(calibration_seeds, start=1):
                trials.append(Trial(
                    "calibration", scenario, "M3", index, seed,
                    label, overrides))

    trials.extend(base_trials(
        "pilot",
        ["head_on", "dense_feasible", "dense_infeasible", "vertical",
         "grouped_reconfiguration"],
        pilot_seeds))
    trials.extend(base_trials(
        "main",
        ["head_on", "dense_feasible", "vertical", "grouped_reconfiguration"],
        formal_seeds))
    trials.extend(base_trials("stress", ["dense_infeasible"], formal_seeds))

    for index, seed in enumerate(formal_seeds, start=1):
        trials.append(Trial(
            "ablation", "vertical", "M3", index, seed,
            "M3_escape_fixed_positive_z", {},
            "fixed_positive_z"))

    sensitivity = [
        ("M3_krep_low", {"iapf_repulsion_gain": 12.5}),
        ("M3_krep_high", {"iapf_repulsion_gain": 50.0}),
        ("M3_accel_zero", {"iapf_accel_gain": 0.0}),
        ("M3_accel_high", {"iapf_accel_gain": 0.60}),
    ]
    for scenario in ["head_on", "dense_feasible"]:
        for label, overrides in sensitivity:
            for index, seed in enumerate(formal_seeds, start=1):
                trials.append(Trial(
                    "sensitivity", scenario, "M3", index, seed,
                    label, overrides))
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
    calibrated_overrides: Dict[str, float] | None = None,
) -> List[str]:
    command = [
        "python3", str(SCRIPT_DIR / "run_experiment.py"),
        "--scenario", trial.scenario, "--method", trial.method,
        "--trial", str(trial.trial), "--seed", str(trial.seed),
        "--batch-id", batch_id, "--phase", trial.phase,
    ]
    if trial.condition_label:
        command.extend(["--condition-label", trial.condition_label])
    if trial.escape_mode:
        command.extend(["--escape-mode", trial.escape_mode])
    effective_overrides = dict(calibrated_overrides or {})
    effective_overrides.update(trial.overrides)
    if trial.phase == "calibration":
        effective_overrides = dict(trial.overrides)
    for name, value in effective_overrides.items():
        command.extend(["--parameter-override", f"{name}={value}"])
    if dry_run:
        command.append("--dry-run")
    return command


def select_calibration(batch_dir: Path, manifest: List[dict]) -> Dict[str, float]:
    candidates: Dict[str, List[dict]] = {}
    override_map: Dict[str, Dict[str, float]] = {}
    for entry in manifest:
        if entry["phase"] != "calibration":
            continue
        label = entry["condition"]
        override_map[label] = {
            name: float(value) for name, value in entry["overrides"].items()}
        summary = (
            batch_dir / "raw" / entry["scenario"] / label
            / f"trial_{entry['trial']:02d}_seed_{entry['seed']}"
            / "trial_summary.csv")
        if not summary.is_file():
            continue
        with summary.open(newline="", encoding="utf-8") as handle:
            candidates.setdefault(label, []).append(next(csv.DictReader(handle)))
    if not candidates:
        return {}

    def score(item: tuple[str, List[dict]]) -> tuple:
        _, rows = item
        success = sum(row["mission_success"].lower() == "true" for row in rows)
        collisions = sum(int(float(row["collision_event_count"])) for row in rows)
        violations = sum(int(float(row["violation_event_count"])) for row in rows)
        risk = sum(float(row["risk_integral"]) for row in rows)
        deviation = sum(float(row["mean_trajectory_deviation"]) for row in rows)
        control = sum(float(row["integrated_squared_acceleration"]) for row in rows)
        return (-success, collisions, violations, risk, deviation, control, item[0])

    selected_label, rows = min(candidates.items(), key=score)
    selected = override_map[selected_label]
    result = {
        "selected_condition": selected_label,
        "selected_overrides": selected,
        "candidate_count": len(candidates),
        "trial_count": sum(len(value) for value in candidates.values()),
        "selection_rule": (
            "mission success, collision events, violation events, risk integral, "
            "trajectory deviation, control burden"),
    }
    (batch_dir / "calibrated_parameters.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8")
    return selected


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-id", required=True)
    parser.add_argument(
        "--phase", action="append",
        choices=["calibration", "pilot", "main", "stress", "ablation",
                 "sensitivity", "all"],
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
        selected = [trial for trial in selected if trial.phase in phases]
    batch_dir = RESULTS_ROOT / args.batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    manifest = [
        {
            "index": index, "phase": trial.phase, "scenario": trial.scenario,
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
                trial_command(trial, args.batch_id, True), check=True)
        return 0

    supervisor = SimulatorSupervisor(batch_dir) if args.manage_sim else None
    if supervisor:
        supervisor.start()
    calibrated_path = batch_dir / "calibrated_parameters.json"
    calibrated_overrides = {}
    if calibrated_path.is_file():
        calibrated_overrides = json.loads(
            calibrated_path.read_text(encoding="utf-8")).get(
                "selected_overrides", {})
    calibration_selected = bool(calibrated_overrides)
    try:
        for index, trial in enumerate(selected, start=1):
            if trial.phase != "calibration" and not calibration_selected:
                calibrated_overrides = select_calibration(batch_dir, manifest)
                calibration_selected = True
            label = trial.condition_label or trial.method
            trial_dir = (
                batch_dir / "raw" / trial.scenario / label
                / f"trial_{trial.trial:02d}_seed_{trial.seed}")
            if args.resume and (trial_dir / "trial_summary.csv").is_file():
                print(f"[{index}/{len(selected)}] skip completed {trial_dir}")
                continue
            for attempt in range(args.max_retries + 1):
                print(
                    f"[{index}/{len(selected)}] {trial.phase} {trial.scenario} "
                    f"{label} trial={trial.trial} attempt={attempt}")
                result = subprocess.run(
                    trial_command(
                        trial, args.batch_id, False, calibrated_overrides),
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
        if any(trial.phase == "calibration" for trial in selected):
            select_calibration(batch_dir, manifest)
    finally:
        if supervisor:
            supervisor.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
