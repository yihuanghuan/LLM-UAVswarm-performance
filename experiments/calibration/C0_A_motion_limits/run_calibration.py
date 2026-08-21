#!/usr/bin/env python3
"""Create and optionally execute the bounded C0-A feasibility trial plan."""
from __future__ import annotations

import argparse, csv, hashlib, json, math, random, subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]

def load(path):
    with path.open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except subprocess.SubprocessError:
        return "unavailable"

def scenarios():
    return [case for name in ("single_axis.yaml", "diagonal.yaml") for case in load(ROOT / "scenarios" / name)["cases"]]

def duration(displacement, limits, margin):
    distance = math.sqrt(sum(float(v) ** 2 for v in displacement))
    return margin * max(1.875 * distance / limits["velocity"],
                        math.sqrt((10.0 / math.sqrt(3.0)) * distance / limits["acceleration"]),
                        (60.0 * distance / limits["jerk"]) ** (1.0 / 3.0), 0.5)

def candidates(base, sweep):
    yield "baseline", "A", dict(base)
    for phase, factor, values in (("B1", "velocity", sweep["velocity"]), ("B2", "acceleration", sweep["acceleration"]), ("B3", "jerk", sweep["jerk"])):
        for value in values:
            limits = dict(base); limits[factor] = float(value)
            yield f"{phase}_{factor}_{value:g}", "B", limits

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=ROOT / "configs" / "baseline.yaml")
    parser.add_argument("--sweep", type=Path, default=ROOT / "configs" / "sweep.yaml")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--execute", action="store_true", help="run the configured site-specific trial command")
    parser.add_argument("--execute-all", action="store_true", help="execute every planned trial (never implied by --execute)")
    parser.add_argument("--execute-stage", choices=("A", "B", "C"), help="execute only one existing calibration stage")
    parser.add_argument("--candidate-prefix", help="execute only candidates with this prefix")
    parser.add_argument("--max-repetitions", type=int, help="execute repetitions up to this number")
    parser.add_argument("--validation", action="store_true", help="create/run Stage C using selected_parameters.yaml")
    args = parser.parse_args()
    base = load(args.baseline); sweep = load(args.sweep)
    output = (args.output_dir or REPO / base["output_dir"]).resolve(); output.mkdir(parents=True, exist_ok=True)
    if args.validation:
        selected_path = output / "selected_parameters.yaml"
        if not selected_path.exists(): raise SystemExit("Stage C requires selected_parameters.yaml from summarize_results.py")
        selected = load(selected_path); pool = [("selected_validation", "C", selected["motion_limits"])]
    else:
        pool = list(candidates(base["motion_limits"], sweep))
    records = []
    for candidate, stage, limits in pool:
        stage_cases = scenarios()
        if stage == "B":
            stage_cases = [case for case in stage_cases if case["id"] in base["stage_b_scenarios"]]
        for case in stage_cases:
            for repetition in range(1, int(base["repetitions"]) + 1):
                seed = int(base["seed"]) + len(records)
                record = {"trial_id": f"{stage}_{candidate}_{case['id']}_r{repetition}", "stage": stage, "candidate_id": candidate, "scenario_id": case["id"], "repetition": repetition, "seed": seed, **limits}
                record["duration_s"] = duration(case["displacement"], limits, float(base["duration_margin"]))
                record["displacement"] = case["displacement"]; records.append(record)
    random.Random(int(base["seed"]) + (1 if args.validation else 0)).shuffle(records)
    plan = output / ("stage_c_plan.csv" if args.validation else "calibration_plan.csv")
    with plan.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0])); writer.writeheader(); writer.writerows(records)
    manifest = {"calibration_id": base["calibration_id"], "git_commit": git_commit(), "baseline_config_sha256": digest(args.baseline), "sweep_config_sha256": digest(args.sweep), "configuration_hash": hashlib.sha256(json.dumps({"baseline": base, "sweep": sweep}, sort_keys=True).encode()).hexdigest(), "seed": base["seed"], "stage": "C" if args.validation else "A+B", "plan": plan.name}
    (output / "calibration_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    template = base["execution"].get("command_template", "")
    if args.execute and not template: raise SystemExit("--execute requires execution.command_template in baseline.yaml")
    execution_records = []
    if args.execute:
        if args.execute_all:
            execution_records = records
        elif args.execute_stage:
            execution_records = [record for record in records if record["stage"] == args.execute_stage]
            if args.candidate_prefix:
                execution_records = [record for record in execution_records if record["candidate_id"].startswith(args.candidate_prefix)]
            if args.max_repetitions is not None:
                execution_records = [record for record in execution_records if record["repetition"] <= args.max_repetitions]
        else:
            execution = base["execution"]
            execution_records = [record for record in records if (
                record["candidate_id"] == execution["smoke_candidate_id"]
                and record["scenario_id"] == execution["smoke_scenario_id"]
                and record["repetition"] == int(execution["smoke_repetition"]))]
            if len(execution_records) != 1:
                raise SystemExit("configured smoke trial is absent from the plan")
    for record in execution_records:
        trial_dir = output / "trials" / record["trial_id"]; trial_dir.mkdir(parents=True, exist_ok=True)
        metrics_path = trial_dir / "metrics.json"
        if metrics_path.exists():
            try:
                if json.loads(metrics_path.read_text(encoding="utf-8")).get("success"):
                    continue
            except json.JSONDecodeError:
                pass
        spec = {"trial": record, "ladrc": base["ladrc"], "motion_limits": {key: record[key] for key in ("velocity", "acceleration", "jerk")}, "git_commit": manifest["git_commit"], "configuration_hash": manifest["configuration_hash"]}
        spec_path = trial_dir / "trial_spec.json"; spec_path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
        command = template.format(trial_dir=trial_dir, trial_spec=spec_path, seed=record["seed"], stage=record["stage"])
        result = subprocess.run(command, shell=True, cwd=REPO, text=True, capture_output=True)
        (trial_dir / "runner.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode: raise SystemExit(f"trial failed: {record['trial_id']}")
    print(json.dumps({"plan": str(plan), "trials": len(records), "executed_trials": len(execution_records)}, indent=2))

if __name__ == "__main__": main()
