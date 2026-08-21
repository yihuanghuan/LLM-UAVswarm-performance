#!/usr/bin/env python3
"""Classify C0-A results and freeze only a repeatable feasibility policy."""
from __future__ import annotations

import argparse, csv, json, math, subprocess
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[2]

REQUIRED = ("tracking_rmse_m", "final_position_error_m", "max_position_error_m", "settling_time_s", "velocity_peak_mps", "acceleration_peak_mps2", "jerk_peak_mps3", "saturation_ratio", "failure_reason")
LEGACY_DIAGNOSTIC_FAILURES = {"COMMAND_JERK_P99_5"}

def load(path):
    with path.open(encoding="utf-8") as stream: return yaml.safe_load(stream)

def git_commit():
    try: return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    except subprocess.SubprocessError: return "unavailable"

def numeric(value):
    try: return float(value)
    except (TypeError, ValueError): return math.nan

def analytic_reference_jerk(row):
    """Return the profile jerk, which is C0-A's jerk-feasibility source."""
    values = []
    for uav in row.get("runtime_metrics", {}).get("per_uav", []):
        value = uav.get("analytic_reference_peaks", {}).get("jerk")
        if value is not None:
            values.append(numeric(value))
    return max(values, default=math.nan)

def classify(rows, criteria):
    reasons = []
    if len(rows) == 0: return False, ["NO_RESULTS"]
    for row in rows:
        if not bool(row.get("success")):
            reasons.append(f"{row['trial_id']}:unsuccessful")
        failures = {item.strip() for item in str(row.get("failure_reason", "")).split(";") if item.strip()}
        failures -= LEGACY_DIAGNOSTIC_FAILURES
        if failures and {item.lower() for item in failures}.isdisjoint({"none", "null", "nan", "ok", "success"}):
            reasons.append(f"{row['trial_id']}:{';'.join(sorted(failures))}")
        checks = (("tracking_rmse_m", "max_tracking_rmse_m"), ("final_position_error_m", "max_final_position_error_m"), ("max_position_error_m", "max_position_error_m"), ("saturation_ratio", "max_saturation_ratio"))
        for metric, limit in checks:
            value = numeric(row.get(metric))
            if not math.isfinite(value) or value > float(criteria[limit]): reasons.append(f"{row['trial_id']}:{metric}")
        if criteria.get("require_settling", True) and (not math.isfinite(numeric(row.get("settling_time_s"))) or numeric(row["settling_time_s"]) < 0): reasons.append(f"{row['trial_id']}:no_settling")
        reference_jerk = analytic_reference_jerk(row)
        if not math.isfinite(reference_jerk) or reference_jerk > float(row["jerk"]) + 1e-9:
            reasons.append(f"{row['trial_id']}:analytic_reference_jerk")
    for scenario in {row["scenario_id"] for row in rows}:
        values = [numeric(row.get("final_position_error_m")) for row in rows if row["scenario_id"] == scenario]
        if (len(values) > 1 and all(math.isfinite(value) for value in values)
                and max(values) - min(values) > float(criteria["max_repeatability_spread_m"])):
            reasons.append(f"{scenario}:repeatability_spread")
    return not reasons, sorted(set(reasons))

def read_results(plan, output):
    rows = list(csv.DictReader(plan.open(encoding="utf-8")))
    results = []
    for row in rows:
        metric_file = output / "trials" / row["trial_id"] / "metrics.json"
        if not metric_file.exists():
            results.append({**row, "failure_reason": "MISSING_METRICS"}); continue
        data = json.loads(metric_file.read_text(encoding="utf-8"))
        # A runner may retain extra fields, but these C0-A names are mandatory.
        missing = [field for field in REQUIRED if field not in data]
        results.append({**row, **data, "failure_reason": "MISSING_FIELDS:" + ",".join(missing) if missing else data.get("failure_reason", "")})
    return results

def select_factor(groups, factor, sweep_values):
    stable = []
    for candidate, outcome in groups.items():
        # Stage-B candidates carry their phase prefix (for example,
        # ``B1_velocity_5``).  Match the factor token rather than assuming it
        # is the first token so the policy-selection artifact can be generated
        # from the recorded B1/B2/B3 trials.
        if f"_{factor}_" in candidate and outcome["acceptable"]:
            stable.append((float(outcome["limits"][factor]), candidate))
    stable.sort()
    if not stable: return None, "no stable candidate"
    # Never freeze an unexplored/aggressive endpoint: step back one stable level.
    endpoint = max(float(v) for v in sweep_values)
    choices = [item for item in stable if item[0] < endpoint]
    return (choices[-1] if choices else stable[0]), None

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=ROOT / "configs" / "baseline.yaml")
    parser.add_argument("--sweep", type=Path, default=ROOT / "configs" / "sweep.yaml")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--validation", action="store_true", help="evaluate Stage C and write the frozen policy")
    args = parser.parse_args(); baseline, sweep = load(args.baseline), load(args.sweep)
    output = (args.output_dir or REPO / baseline["output_dir"]).resolve()
    plan = output / ("stage_c_plan.csv" if args.validation else "calibration_plan.csv")
    if not plan.exists(): raise SystemExit(f"missing plan: {plan}")
    rows = read_results(plan, output)
    with (output / "calibration_results.csv").open("w", newline="", encoding="utf-8") as stream:
        fields = sorted({key for row in rows for key in row}); writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    grouped = defaultdict(list)
    for row in rows: grouped[row["candidate_id"]].append(row)
    groups = {}
    for candidate, candidate_rows in grouped.items():
        accepted, reasons = classify(candidate_rows, baseline["criteria"])
        groups[candidate] = {"acceptable": accepted, "reasons": reasons, "limits": {name: float(candidate_rows[0][name]) for name in ("velocity", "acceleration", "jerk")}, "trial_count": len(candidate_rows)}
    report = ["# C0-A Dynamic Feasibility Calibration", "", f"Git commit: `{git_commit()}`", "", "## Tested range", "", f"- velocity: {sweep['velocity']}", f"- acceleration: {sweep['acceleration']}", f"- jerk: {sweep['jerk']}", "", "## Candidate classification", ""]
    for candidate, item in sorted(groups.items()): report.append(f"- {candidate}: {'ACCEPT' if item['acceptable'] else 'REJECT'}" + ("" if item['acceptable'] else " — " + "; ".join(item['reasons'])))
    if not args.validation:
        baseline_ok = groups.get("baseline", {}).get("acceptable", False)
        selections, errors = {}, []
        for factor in ("velocity", "acceleration", "jerk"):
            choice, error = select_factor(groups, factor, sweep[factor]);
            if error: errors.append(f"{factor}: {error}")
            else: selections[factor] = choice[0]
        if not baseline_ok: errors.append("Stage A baseline validation failed")
        if errors:
            report += ["", "## Freeze status", "", "No candidate is eligible for Stage C: " + "; ".join(errors)]
        else:
            selected = {"calibration_id": baseline["calibration_id"], "motion_limits": selections, "ladrc": baseline["ladrc"], "selection_rule": "highest stable non-endpoint OAT value", "source_git_commit": git_commit()}
            (output / "selected_parameters.yaml").write_text(yaml.safe_dump(selected, sort_keys=False), encoding="utf-8")
            report += ["", "## Stage C required", "", "Selected provisional limits were written to `selected_parameters.yaml`. Run Stage C before treating them as frozen."]
    else:
        accepted = groups.get("selected_validation", {}).get("acceptable", False)
        if accepted:
            selected = load(output / "selected_parameters.yaml"); selected["freeze_status"] = "frozen"; selected["validation_git_commit"] = git_commit()
            (output / "frozen_execution_policy.yaml").write_text(yaml.safe_dump(selected, sort_keys=False), encoding="utf-8")
            validation_rows = grouped["selected_validation"]
            report += ["", "## Validation metrics", "", f"- trials: {len(validation_rows)}", f"- worst tracking RMSE: {max(numeric(row.get('tracking_rmse_m')) for row in validation_rows):.4f} m", f"- worst final position error: {max(numeric(row.get('final_position_error_m')) for row in validation_rows):.4f} m", f"- worst saturation ratio: {max(numeric(row.get('saturation_ratio')) for row in validation_rows):.4f}", "", "## Freeze status", "", "FROZEN: Stage C passed all scenarios and repetitions."]
        else: report += ["", "## Freeze status", "", "NOT FROZEN: Stage C did not satisfy all feasibility criteria."]
    (output / "summary_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(json.dumps(groups, indent=2, sort_keys=True))

if __name__ == "__main__": main()
