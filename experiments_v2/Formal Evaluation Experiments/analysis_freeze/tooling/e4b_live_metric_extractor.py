#!/usr/bin/env python3
"""Authoritative E4B authority-preservation attempt scorer."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from analysis_common import EvidenceError, file_inventory, metric_value
from attempt_context import result_envelope, terminal_classification, validate_attempt
from rosbag_evidence import read_bag, records_for


TOLERANCE = 1.0e-9
PREDICATE_IDS = (
    "feasible_explicit_T_preserved",
    "dynamic_feasibility_and_T_min_preserved",
    "auto_T_min_preserved",
    "hard_safety_ownership_preserved",
    "motion_limits_and_controller_clamps_preserved",
    "no_priority_above_style_changed",
)


def predicate(value: bool | None, evidence: Any, *, applicable: bool = True) -> dict[str, Any]:
    if not applicable:
        return {"applicable": False, "valid": True, "pass": True, "evidence": evidence}
    if value is None:
        return {"applicable": True, "valid": False, "pass": None, "evidence": evidence}
    return {"applicable": True, "valid": True, "pass": bool(value), "evidence": evidence}


def evaluate_authority_case(*, scenario: str, style: str, t_exec: float,
                            requested: dict[str, Any], t_min: float | None,
                            feasibility_terms: dict[str, float], safety_ok: bool,
                            profiles_ok: bool, physical_commands_ok: bool | None) -> dict[str, Any]:
    """Pure frozen predicate core, intentionally usable by independent fixtures."""
    feasible = scenario == "E4B-FEASIBLE-EXPLICIT-T"
    infeasible = scenario == "E4B-INFEASIBLE-EXPLICIT-T"
    auto = scenario == "E4B-AUTO-T"
    dynamic_ok = True
    if infeasible:
        dynamic_ok = (t_min is not None and t_exec + TOLERANCE >= t_min
                      and all(t_exec + TOLERANCE >= float(feasibility_terms[key])
                              for key in ("velocity", "acceleration", "jerk")))
    return {
        "feasible_explicit_T_preserved": predicate(
            abs(t_exec - float(requested["value_s"])) <= TOLERANCE if feasible else True,
            {"T_exec_s": t_exec, "T_request_s": requested.get("value_s"), "tolerance": TOLERANCE},
            applicable=feasible),
        "dynamic_feasibility_and_T_min_preserved": predicate(
            dynamic_ok, {"T_exec_s": t_exec, "T_min_s": t_min,
                         "feasibility_terms_s": feasibility_terms}, applicable=infeasible),
        "auto_T_min_preserved": predicate(
            t_min is not None and t_exec + TOLERANCE >= t_min if auto else True,
            {"T_exec_s": t_exec, "T_min_s": t_min, "style": style}, applicable=auto),
        "hard_safety_ownership_preserved": predicate(safety_ok, {"frozen_contract_pass": safety_ok}),
        "motion_limits_and_controller_clamps_preserved": predicate(
            profiles_ok and physical_commands_ok if physical_commands_ok is not None else None,
            {"compiled_profiles_pass": profiles_ok, "physical_commands_pass": physical_commands_ok}),
    }


def extract(attempt_dir: Path, *, raw_inventory: dict[str, str] | None = None) -> dict[str, Any]:
    attempt_dir = Path(attempt_dir).resolve()
    manifest, spec, dependencies = validate_attempt(attempt_dir, "E4B")
    scenario = spec["scenario_id"]
    t_exec = float(spec["duration_s"])
    t_min = spec.get("T_min_s")
    requested = spec["requested_T"]
    limits = spec["authority_evidence"]["frozen_motion_limits"]
    safety = spec["authority_evidence"]["safety_contract"]
    checks: dict[str, Any]
    infeasible = scenario == "E4B-INFEASIBLE-EXPLICIT-T"
    timing_terms = spec.get("timing_feasibility_evidence", {})
    safety_ok = (float(safety["d_hard"]) == 1.5 and safety["style_may_change"] is False
                 and safety["d_plan_ownership"] == "frozen safety mapping/allocator"
                 and spec["assignment_mode"] == "safety_aware"
                 and spec["avoidance_mode"] == "iapf_dual")
    profile_ok = True
    profile_evidence = []
    for profile in spec["profiles"]:
        current = {
            "velocity_mps": float(profile["velocity_limit"]),
            "acceleration_mps2": float(profile["acceleration_limit"]),
            "jerk_mps3": float(profile["jerk_limit"]),
        }
        ok = (current["velocity_mps"] <= float(limits["velocity_mps"]) + TOLERANCE
              and current["acceleration_mps2"] <= float(limits["acceleration_mps2"]) + TOLERANCE
              and current["jerk_mps3"] <= float(limits["jerk_mps3"]) + TOLERANCE)
        profile_ok = profile_ok and ok
        profile_evidence.append({"profile": current, "within_frozen_limits": ok})
    physical_command_evidence = None
    interaction_path = attempt_dir / "raw/interaction_result.json"
    bag_path = attempt_dir / "raw/rosbag/metadata.yaml"
    physical_valid = True
    if interaction_path.is_file() and bag_path.is_file():
        interaction = json.loads(interaction_path.read_text())
        mission_id = int(interaction["mission_id"])
        records = read_bag(attempt_dir / "raw/rosbag", lambda topic: topic.endswith("/execution_command"))
        commands = records_for(records, "/execution_command", mission_id=mission_id)
        physical_valid = len(commands) == len(spec["uav_ids"])
        command_checks = []
        for record in commands:
            profile = record.message.profile
            ok = (abs(float(profile.duration) - t_exec) <= 1.0e-6
                  and float(profile.velocity_limit) <= float(limits["velocity_mps"]) + 1.0e-6
                  and float(profile.acceleration_limit) <= float(limits["acceleration_mps2"]) + 1.0e-6
                  and float(profile.jerk_limit) <= float(limits["jerk_mps3"]) + 1.0e-6)
            physical_valid = physical_valid and ok
            command_checks.append({"uav_id": int(record.message.uav_id), "pass": ok,
                                   "duration_s": float(profile.duration), "style": profile.style})
        physical_command_evidence = {"mission_id": mission_id, "command_count": len(commands),
                                     "commands": command_checks}
    else:
        physical_valid = None
        physical_command_evidence = {"status": "missing interaction command evidence"}
    checks = evaluate_authority_case(
        scenario=scenario, style=spec["style"], t_exec=t_exec, requested=requested,
        t_min=float(t_min) if t_min is not None else None, feasibility_terms=timing_terms,
        safety_ok=safety_ok, profiles_ok=profile_ok, physical_commands_ok=physical_valid)
    checks["hard_safety_ownership_preserved"]["evidence"].update({
        "d_hard": safety["d_hard"], "d_plan_ownership": safety["d_plan_ownership"],
        "style_may_change": safety["style_may_change"], "assignment_mode": spec["assignment_mode"],
        "avoidance_mode": spec["avoidance_mode"]})
    checks["motion_limits_and_controller_clamps_preserved"]["evidence"].update({
        "frozen_limits": limits, "compiled_profiles": profile_evidence,
        "physical_commands": physical_command_evidence})
    hierarchy = spec["authority_evidence"]["hierarchy"]
    expected_hierarchy = "hard_safety > dynamic_feasibility > feasible_explicit_task_requirement > soft_motion_style_preference"
    checks["no_priority_above_style_changed"] = predicate(
        hierarchy == expected_hierarchy and all(item["pass"] is not False for item in checks.values()),
        {"hierarchy": hierarchy})
    if set(checks) != set(PREDICATE_IDS):
        raise EvidenceError("E4B predicate set is incomplete")
    violations = [name for name, item in checks.items() if item["valid"] and item["pass"] is False]
    invalid = [name for name, item in checks.items() if not item["valid"]]
    priority_preserved = not violations and not invalid
    metrics = {
        "authority_predicates": checks,
        "unauthorized_override_count": metric_value(len(violations), violated_predicates=violations),
        "priority_preserved": metric_value(priority_preserved, invalid_predicates=invalid,
            denominator_membership=True),
        "T_exec": metric_value(t_exec, unit="s"),
        "T_min": metric_value(float(t_min), unit="s") if t_min is not None else
                 {"valid": False, "value": None, "reason": "not applicable to safety-active exact spec"},
    }
    return result_envelope(attempt_dir, "E4B", Path(__file__), manifest, dependencies,
        scored_interval=None, terminal_classification=terminal_classification(manifest),
        analysis_status="COMPLETE" if not invalid else "PARTIAL_VALID_METRICS",
        metrics=metrics, source_coverage={"authority_evidence_complete": not invalid,
                                         "invalid_predicates": invalid},
        raw_inventory=raw_inventory if raw_inventory is not None else file_inventory(attempt_dir))


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("attempt_dir", type=Path); parser.add_argument("--output", type=Path)
    args = parser.parse_args(); result = extract(args.attempt_dir)
    text = json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
    if args.output: args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(text)
    else: print(text, end="")
    return 0


if __name__ == "__main__": raise SystemExit(main())
