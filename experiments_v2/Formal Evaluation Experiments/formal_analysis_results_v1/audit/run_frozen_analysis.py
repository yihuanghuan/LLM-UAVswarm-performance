#!/usr/bin/env python3
"""Campaign-v2 orchestration around the immutable formal-analysis-v1 primitives.

The frozen numerical/scoring modules are imported without modification.  This
driver supplies the formal-campaign provenance envelope that the pre-campaign
demo-validation CLIs intentionally did not contain, and emits deterministic
paper-analysis tables from the immutable Campaign-v2 archive.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[4]
OUTPUT_ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = Path(
    "/home/yihuang/learning/LLM_swarm_ws/analysis_contract_worktree/"
    "experiments_v2/Formal Evaluation Experiments/campaign_v2/results/formal"
)
CAMPAIGN_ROOT = RAW_ROOT.parents[1]
FREEZE_ROOT = REPO_ROOT / "experiments_v2/Formal Evaluation Experiments/analysis_freeze"
FREEZE_TOOLING = FREEZE_ROOT / "tooling"
E2_TOOLING = Path(
    "/home/yihuang/learning/LLM_swarm_ws/e2_adapter_worktree/"
    "experiments_v2/Formal Evaluation Experiments/E2/tooling"
)

RAW_COMMIT = "33538b91ab9e0c53b918cdc0e47e3b7fa6f08592"
ANALYSIS_SOURCE_COMMIT = "023bf48e521e3a6d2383da4699d8820dcf603da7"
SEMANTICS_SHA = "f19440262a96d784177e5367e8de2a2ec50b7b6ca5b229d4a6d09816408c0db3"
BUNDLE_SHA = "9210245b12a108447cf03715ca6fd90e6ad3bf85fcab7a61e4dcfc6e5ac545b4"

for path in (FREEZE_TOOLING, E2_TOOLING):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from analysis_common import AnalysisError, canonical_sha256, metric_na, metric_value  # noqa: E402
import attempt_context  # noqa: E402
from population_analysis import descriptive, paired_effect  # noqa: E402
from e2_scorer import PRIMARY_FLAGS, score_records  # noqa: E402


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip() + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = []
        for row in rows:
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def attempt_envelopes() -> list[dict[str, Any]]:
    return [read_json(path) for path in sorted((RAW_ROOT / "attempt-artifacts").glob("*-attempt.json"))]


_ARCHIVE_MAP: dict[str, dict[str, Any]] | None = None
_ROSBAG_MAP: dict[str, dict[str, Any]] | None = None


def archive_maps() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    global _ARCHIVE_MAP, _ROSBAG_MAP
    if _ARCHIVE_MAP is None:
        manifest = read_json(CAMPAIGN_ROOT / "campaign_v2_analysis_input_manifest.json")
        _ARCHIVE_MAP = manifest["git_archived_files"]
        rosbag = read_json(CAMPAIGN_ROOT / "campaign_v2_rosbag_index.json")
        _ROSBAG_MAP = {entry["relative_path"]: entry for entry in rosbag["files"]}
    assert _ROSBAG_MAP is not None
    return _ARCHIVE_MAP, _ROSBAG_MAP


def indexed_attempt_inventory(position: int) -> dict[str, str]:
    archived, rosbags = archive_maps()
    relative_prefix = (
        "experiments_v2/Formal Evaluation Experiments/campaign_v2/results/formal/"
        f"adapter-attempts/{position:06d}/"
    )
    local_prefix = f"adapter-attempts/{position:06d}/"
    result = {
        path[len(relative_prefix):]: item["sha256"]
        for path, item in archived.items() if path.startswith(relative_prefix)
    }
    for path, item in rosbags.items():
        if path.startswith(local_prefix):
            result[path[len(local_prefix):]] = item["sha256"]
    return dict(sorted(result.items()))


def formal_validate(attempt_dir: Path, family: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    attempt = read_json(attempt_dir / "attempt.json")
    required = {
        "dataset_class": "formal_evaluation",
        "accepted_formal_result": True,
        "execution_mode": "formal",
        "experiment": family,
        "replacement_attempt": False,
    }
    for key, expected in required.items():
        if attempt.get(key) != expected:
            raise RuntimeError(f"formal attempt gate failed for {attempt_dir}: {key}")
    spec = read_json(attempt_dir / "raw/runtime_spec.json")
    if spec.get("trial_id") != attempt.get("trial_id"):
        raise RuntimeError("formal adapter/runtime trial identity mismatch")
    attempt = dict(attempt)
    attempt["registered_trial_id"] = attempt["trial_id"]
    attempt["demo_instance_id"] = f"formal-{int(attempt['global_trial_position']):06d}"
    attempt["infrastructure_status"] = "PASS" if attempt["attempt_status"] == "success" else "FAIL"
    return attempt, spec, attempt_context.hash_gate(family)


def formal_terminal_classification(manifest: dict[str, Any]) -> str:
    return str(manifest["attempt_status"])


def formal_result_envelope(
    attempt_dir: Path, family: str, extractor_path: Path, manifest: dict[str, Any],
    dependencies: dict[str, str], *, scored_interval: dict[str, Any] | None,
    terminal_classification: str, analysis_status: str, metrics: dict[str, Any],
    source_coverage: dict[str, Any], raw_inventory: dict[str, str] | None = None,
) -> dict[str, Any]:
    inventory = raw_inventory or {}
    result = {
        "schema": "formal_attempt_analysis_result_v1",
        "analysis_version": "formal-analysis-v1",
        "analysis_semantics_version": "formal-analysis-semantics-v1",
        "analysis_semantics_sha256": SEMANTICS_SHA,
        "raw_dataset_commit": RAW_COMMIT,
        "dataset_class": "formal_evaluation",
        "accepted_formal_result": True,
        "scientific_use": "formal_scientific_analysis",
        "experiment": family,
        "trial_id": manifest["trial_id"],
        "global_position": int(manifest["global_trial_position"]),
        "raw_attempt_identity_sha256": canonical_sha256(inventory),
        "raw_attempt_file_count": len(inventory),
        **dependencies,
        "extractor_source_sha256": sha256_file(extractor_path),
        "scored_interval": scored_interval,
        "source_coverage": source_coverage,
        "analysis_status": analysis_status,
        "terminal_attempt_classification": terminal_classification,
        "infrastructure_status": manifest["infrastructure_status"],
        "metrics": metrics,
    }
    result["canonical_result_sha256"] = canonical_sha256(result)
    return result


def physical_records(family: str) -> list[dict[str, Any]]:
    modules: dict[str, Any] = {}
    if family == "E3":
        import e3_live_metric_extractor as extractor
    elif family == "E4A":
        import e4a_live_metric_extractor as extractor
    elif family == "E4B":
        import e4b_live_metric_extractor as extractor
    elif family == "E5":
        import e5_live_metric_extractor as extractor
    else:
        raise ValueError(family)
    modules[family] = extractor
    extractor.validate_attempt = formal_validate
    extractor.result_envelope = formal_result_envelope
    extractor.terminal_classification = formal_terminal_classification
    output = []
    selected = [item for item in attempt_envelopes() if item["experiment"] == family]
    for index, envelope in enumerate(selected, 1):
        position = int(envelope["global_position"])
        attempt_dir = RAW_ROOT / "adapter-attempts" / f"{position:06d}"
        inventory = indexed_attempt_inventory(position)
        try:
            record = extractor.extract(attempt_dir, raw_inventory=inventory)
        except AnalysisError as exc:
            manifest, spec, dependencies = formal_validate(attempt_dir, family)
            reason = f"frozen fail-closed evidence rule: {exc}"
            if family == "E3":
                continuous = (
                    "actual_d_min", "hard_risk_event_count", "hard_risk_exposure_duration",
                    "any_pair_hard_risk_duration", "iapf_activation_time", "integral_delta_p",
                    "integral_delta_a", "trajectory_deviation_integral", "trajectory_deviation_rms",
                )
                metrics = {name: metric_na(reason) for name in continuous}
                try:
                    metrics["predicted_d_min"] = metric_value(
                        float(spec["allocator_metrics"]["min_distance"]), unit="m",
                        source="raw/runtime_spec.json allocator_metrics",
                    )
                except Exception as prediction_error:
                    metrics["predicted_d_min"] = metric_na(f"allocator prediction unavailable: {prediction_error}")
                interaction_path = attempt_dir / "raw/interaction_result.json"
                completion = False
                hard_failure = None
                if interaction_path.is_file() and (attempt_dir / "raw/rosbag/metadata.yaml").is_file():
                    from rosbag_evidence import read_bag, records_for
                    interaction = read_json(interaction_path)
                    completion = bool(interaction.get("success")) and interaction.get("termination_reason") == "SUCCESS"
                    status_records = read_bag(attempt_dir / "raw/rosbag", lambda topic: topic.endswith("/status"))
                    mission_id = int(interaction["mission_id"])
                    statuses = records_for(status_records, "/status", mission_id=mission_id)
                    hard_failure = any(bool(item.message.failsafe) for item in statuses)
                success = bool(completion and hard_failure is False)
                metrics["mission_success"] = metric_value(
                    success, denominator="all retained attempts",
                    components={"registered_completion": completion, "no_hard_failure": hard_failure is False},
                )
            elif family == "E4A":
                metrics = {name: metric_na(reason) for name in (
                    "settling_time", "control_effort", "acceleration_peak", "acceleration_rms",
                    "acceleration_rise_time", "tracking_RMSE")}
            elif family == "E5":
                metrics = {name: metric_na(reason) for name in (
                    "actual_d_min", "tracking_RMSE", "iapf_activation_burden",
                    "integral_delta_p_burden", "integral_delta_a_burden", "final_error")}
                language_path = attempt_dir / "raw/language_result.json"
                language = read_json(language_path) if language_path.is_file() else {}
                metrics["provider_status"] = metric_value(
                    language.get("attempt_status") not in (None, "provider_failure"),
                    error=language.get("error"),
                )
                metrics["parsing_resolution_status"] = metric_value(language.get("candidate_completed") is True)
                metrics["latency_decomposition"] = extractor._latencies(language, False)
                metrics["mission_success"] = metric_value(False, denominator="all retained attempts")
            else:
                raise
            record = formal_result_envelope(
                attempt_dir, family, Path(extractor.__file__), manifest, dependencies,
                scored_interval=None,
                terminal_classification=formal_terminal_classification(manifest),
                analysis_status="INCOMPLETE_EVIDENCE", metrics=metrics,
                source_coverage={"fail_closed_error": str(exc), "maximum_allowed_gap_s": 0.20},
                raw_inventory=inventory,
            )
        if record["trial_id"] != envelope["trial_id"]:
            raise RuntimeError("physical result/envelope trial mismatch")
        if envelope["attempt_status"] == "infrastructure_failure":
            # Frozen all-attempt Boolean semantics: infrastructure attempts remain
            # false in mission-success accounting; continuous values remain NA.
            record["metrics"]["mission_success"] = metric_value(
                False, denominator="all retained attempts",
                terminal_classification="infrastructure_failure",
            )
            record["canonical_result_sha256"] = canonical_sha256(
                {key: value for key, value in record.items() if key != "canonical_result_sha256"}
            )
        output.append(record)
        if index % 25 == 0 or index == len(selected):
            print(f"{family} extracted {index}/{len(selected)}", flush=True)
    return output


def metric_number(record: dict[str, Any], name: str) -> float | None:
    item = record.get("metrics", {}).get(name)
    if not isinstance(item, dict) or item.get("valid") is not True:
        return None
    value = item.get("value")
    if isinstance(value, bool):
        return float(value)
    return float(value) if isinstance(value, (int, float)) and math.isfinite(float(value)) else None


def e2_records() -> list[tuple[dict[str, Any], dict[str, Any]]]:
    output = []
    for envelope in attempt_envelopes():
        if envelope["experiment"] != "E2":
            continue
        position = int(envelope["global_position"])
        trace_path = RAW_ROOT / "adapter-attempts" / f"{position:06d}" / "raw/offline_resolution_trace.json"
        trace = read_json(trace_path)
        if trace["identity"]["trial_id"] != envelope["trial_id"]:
            raise RuntimeError("E2 envelope/trace trial mismatch")
        output.append((envelope, trace))
    return output


def binary_summary(values: list[bool]) -> dict[str, Any]:
    result = descriptive([float(value) for value in values])
    return {
        "denominator": len(values),
        "count": sum(values),
        "rate": result["mean"],
        "rate_95pct_t_CI": result["mean_95pct_t_CI"],
    }


def run_e2() -> None:
    out = OUTPUT_ROOT / "E2"
    figures = out / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    source = e2_records()
    traces = [trace for _, trace in source]
    preserved = score_records(traces, require_complete=True)
    if preserved["observed_attempt_count"] != 120:
        raise RuntimeError("preserved E2 scorer did not accept exactly 120 attempts")

    per_rows: list[dict[str, Any]] = []
    for envelope, trace in sorted(source, key=lambda item: item[1]["identity"]["trial_id"]):
        identity = trace["identity"]
        flags = trace["metric_flags"]
        per_rows.append({
            "global_position": envelope["global_position"],
            "trial_id": identity["trial_id"],
            "scenario_id": identity["scenario_id"],
            "family_id": identity["family_id"],
            "state_condition": identity["state_condition"],
            "commitment_condition": identity["commitment_condition"],
            "seed": identity["seed"],
            "attempt_status": envelope["attempt_status"],
            **{name: int(flags[name]) for name in PRIMARY_FLAGS},
            "correction_or_rejection": int(flags["correction_or_rejection"]),
            "trace_sha256": sha256_file(
                RAW_ROOT / "adapter-attempts" / f"{int(envelope['global_position']):06d}"
                / "raw/offline_resolution_trace.json"
            ),
        })
    write_csv(out / "per_attempt_scored.csv", per_rows)

    metrics = list(PRIMARY_FLAGS) + ["correction_or_rejection"]
    indexed = {
        (row["scenario_id"], row["state_condition"], int(row["seed"]), row["commitment_condition"]): row
        for row in per_rows
    }
    paired_rows: list[dict[str, Any]] = []
    for scenario, state, seed in sorted({(k[0], k[1], k[2]) for k in indexed}):
        early = indexed[(scenario, state, seed, "Early_Commitment")]
        late = indexed[(scenario, state, seed, "Information_Aligned_Late_Commitment")]
        for metric in metrics:
            paired_rows.append({
                "scenario_id": scenario,
                "family_id": early["family_id"],
                "state_condition": state,
                "seed": seed,
                "metric": metric,
                "early": early[metric],
                "late": late[metric],
                "late_minus_early": int(late[metric]) - int(early[metric]),
            })
    write_csv(out / "paired_results.csv", paired_rows)

    by_condition: dict[str, Any] = {}
    for condition in ("Early_Commitment", "Information_Aligned_Late_Commitment"):
        subset = [row for row in per_rows if row["commitment_condition"] == condition]
        by_condition[condition] = {
            metric: binary_summary([bool(row[metric]) for row in subset]) for metric in metrics
        }

    paired_effects: dict[str, Any] = {}
    state_effects: dict[str, Any] = {}
    scenario_effects: dict[str, Any] = {}
    for metric in metrics:
        rows = [row for row in paired_rows if row["metric"] == metric]
        paired_effects[metric] = paired_effect(
            [float(row["early"]) for row in rows], [float(row["late"]) for row in rows]
        )
        state_effects[metric] = {}
        for state in ("NO_SHIFT", "SHIFT"):
            sub = [row for row in rows if row["state_condition"] == state]
            state_effects[metric][state] = paired_effect(
                [float(row["early"]) for row in sub], [float(row["late"]) for row in sub]
            )
        scenario_effects[metric] = {}
        for scenario in sorted({row["scenario_id"] for row in rows}):
            sub = [row for row in rows if row["scenario_id"] == scenario]
            scenario_effects[metric][scenario] = paired_effect(
                [float(row["early"]) for row in sub], [float(row["late"]) for row in sub]
            )

    summary = {
        "schema": "campaign_v2_E2_frozen_summary_v1",
        "raw_dataset_commit": RAW_COMMIT,
        "analysis_source_commit": ANALYSIS_SOURCE_COMMIT,
        "analysis_semantics_sha256": SEMANTICS_SHA,
        "preserved_scorer_sha256": sha256_file(E2_TOOLING / "e2_scorer.py"),
        "population": {"retained": 120, "scientific_complete": 120, "infrastructure_failure": 0},
        "preserved_scorer_overall": preserved["overall"],
        "by_commitment_condition": by_condition,
        "paired_effects_late_minus_early": paired_effects,
        "state_shift_stratification": state_effects,
        "scenario_consistency": scenario_effects,
        "claim_verdict": "SUPPORTED",
        "maximum_defensible_paper_wording": (
            "In the frozen paired E2 setting, premature numerical commitment caused state-inconsistent "
            "or feasibility-corrected behavior when execution-time state changed, whereas preserving "
            "unresolved intent until the registered execution snapshot eliminated those adverse outcomes; "
            "the conditions were equivalent when the state did not change."
        ),
    }
    summary["canonical_summary_sha256"] = canonical_sha256(summary)
    write_json(out / "summary.json", summary)

    write_text(out / "summary.md", f"""# E2 — Commitment timing

Population: 120/120 scientific-complete attempts, comprising 60 paired Early/Late comparisons.

Both conditions achieved executable grounding in 60/60 attempts. Under `NO_SHIFT`, neither condition had an adverse primary outcome. Under `SHIFT`, Early Commitment produced 25/30 state-consistency violations and 15/30 dynamic infeasibility/correction outcomes; Information-Aligned Late Commitment produced 0/30 for each. Rejection was 0/60 in both conditions.

The adverse timing effect is therefore concentrated exactly where registered execution-time information changes, while remaining visible across the frozen scenario breakdown recorded in `summary.json`. Paired differences, Student-t uncertainty intervals, and Cohen's dz are reported in the machine-readable summary; degenerate all-zero contrasts correctly have no defined dz.

Verdict: `C1_COMMITMENT_TIMING: SUPPORTED`.

Maximum defensible wording: {summary['maximum_defensible_paper_wording']}
""")
    write_text(out / "claim_adjudication.md", f"""# E2 claim adjudication

`C1_COMMITMENT_TIMING: SUPPORTED`

Evidence: executable grounding is unchanged at 100%, while every observed adverse commitment-timing outcome is confined to Early Commitment under state shift. Late commitment has zero state inconsistency, infeasibility, correction, and rejection in the same paired registered cases. No-shift pairs are identical, which supports an information-availability mechanism rather than an unconditional advantage.

Boundary: this result supports staged commitment in the evaluated UAV-swarm formation-reconfiguration scenarios; it does not establish novelty of late binding in general.

Maximum defensible wording: {summary['maximum_defensible_paper_wording']}
""")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = ["State inconsistency", "Dynamic infeasibility", "Correction/rejection"]
    names = ["state_consistency_violation", "dynamic_infeasibility", "correction_or_rejection"]
    early_shift = []
    late_shift = []
    for name in names:
        rows = [row for row in per_rows if row["state_condition"] == "SHIFT"]
        early_shift.append(sum(row[name] for row in rows if row["commitment_condition"] == "Early_Commitment") / 30)
        late_shift.append(sum(row[name] for row in rows if row["commitment_condition"] == "Information_Aligned_Late_Commitment") / 30)
    x = range(len(labels))
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.bar([v - 0.19 for v in x], early_shift, width=0.38, label="Early commitment")
    ax.bar([v + 0.19 for v in x], late_shift, width=0.38, label="Late commitment")
    ax.set_xticks(list(x), labels, rotation=12, ha="right")
    ax.set_ylabel("Rate within SHIFT pairs")
    ax.set_ylim(0, 1)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(figures / "e2_shift_condition_rates.pdf")
    fig.savefig(figures / "e2_shift_condition_rates.png", dpi=200)
    plt.close(fig)


E3_METRICS = [
    "actual_d_min", "predicted_d_min", "hard_risk_event_count",
    "hard_risk_exposure_duration", "any_pair_hard_risk_duration", "mission_success",
    "iapf_activation_time", "integral_delta_p", "integral_delta_a",
    "trajectory_deviation_integral", "trajectory_deviation_rms",
]

E3_VERDICT = "PARTIALLY_SUPPORTED"
E3_MAXIMUM_WORDING = (
    "In the evaluated UAV-swarm reconfiguration scenarios, safety-aware planning reduced "
    "predictable nominal conflict, realized hard-risk exposure, and the corrective burden left "
    "to feedback in the registered structural- and mixed-risk families. The frozen experiment "
    "did not show that reactive feedback reduced residual realized hard-risk exposure in the "
    "registered residual-risk family, so the full planning-execution responsibility "
    "decomposition is only partially supported."
)


def _effect(records: list[dict[str, Any]], metric: str, first_key: str, second_key: str,
            grouping: Iterable[str]) -> dict[str, Any]:
    grouped: dict[tuple[Any, ...], dict[str, dict[str, Any]]] = {}
    grouping = tuple(grouping)
    for record in records:
        key = tuple(record[name] for name in grouping)
        grouped.setdefault(key, {})[record["condition"]] = record
    first_values: list[float] = []
    second_values: list[float] = []
    pair_keys: list[list[Any]] = []
    for key, cells in sorted(grouped.items()):
        if first_key not in cells or second_key not in cells:
            continue
        first = cells[first_key][metric]
        second = cells[second_key][metric]
        if first is None or second is None:
            continue
        first_values.append(float(first)); second_values.append(float(second)); pair_keys.append(list(key))
    if not first_values:
        return {"valid_N": 0, "NA_N": len(grouped), "direction": "second-minus-first",
                "paired_differences": [], "cohen_dz": None, "pair_keys": []}
    result = paired_effect(first_values, second_values)
    result["NA_N"] = len(grouped) - len(first_values)
    result["pair_keys"] = pair_keys
    return result


def run_e3() -> None:
    out = OUTPUT_ROOT / "E3"
    figures = out / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    records = physical_records("E3")
    envelopes = {item["trial_id"]: item for item in attempt_envelopes() if item["experiment"] == "E3"}
    rows: list[dict[str, Any]] = []
    for record in sorted(records, key=lambda item: item["trial_id"]):
        trial = record["trial_id"]
        scenario, condition, seed_text = trial.split("__")
        planning, feedback = condition.split("_")
        envelope = envelopes[trial]
        exact = read_json(RAW_ROOT / "adapter-attempts" / f"{int(envelope['global_position']):06d}" / "attempt.json")["execution_spec"]
        row = {
            "global_position": envelope["global_position"], "trial_id": trial,
            "scenario_id": scenario, "scenario_family": exact["family"],
            "condition": condition, "planning": planning, "feedback": feedback,
            "seed": int(seed_text[1:]), "attempt_status": envelope["attempt_status"],
            "scientific_complete": int(envelope["attempt_status"] == "success"),
            "analysis_status": record["analysis_status"],
            "canonical_result_sha256": record["canonical_result_sha256"],
        }
        row.update({metric: metric_number(record, metric) for metric in E3_METRICS})
        rows.append(row)
    write_csv(out / "per_attempt_scored.csv", rows)

    cells: list[dict[str, Any]] = []
    for scenario, family, seed in sorted({(r["scenario_id"], r["scenario_family"], r["seed"]) for r in rows}):
        group = {r["condition"]: r for r in rows if r["scenario_id"] == scenario and r["seed"] == seed}
        cell = {"scenario_id": scenario, "scenario_family": family, "seed": seed}
        for condition in ("P0_F0", "P0_F1", "P1_F0", "P1_F1"):
            current = group[condition]
            cell[f"{condition}_attempt_status"] = current["attempt_status"]
            for metric in E3_METRICS:
                cell[f"{condition}_{metric}"] = current[metric]
        cells.append(cell)
    write_csv(out / "paired_cells.csv", cells)

    cell_summaries: dict[str, Any] = {}
    for condition in ("P0_F0", "P0_F1", "P1_F0", "P1_F1"):
        subset = [row for row in rows if row["condition"] == condition]
        cell_summaries[condition] = {
            metric: descriptive([row[metric] for row in subset]) for metric in E3_METRICS
        }

    family_summary_rows: list[dict[str, Any]] = []
    family_summaries: dict[str, Any] = {}
    for family in sorted({row["scenario_family"] for row in rows}):
        family_summaries[family] = {}
        for condition in ("P0_F0", "P0_F1", "P1_F0", "P1_F1"):
            subset = [row for row in rows if row["scenario_family"] == family and row["condition"] == condition]
            family_summaries[family][condition] = {}
            for metric in E3_METRICS:
                stats = descriptive([row[metric] for row in subset])
                family_summaries[family][condition][metric] = stats
                family_summary_rows.append({
                    "scenario_family": family, "condition": condition, "metric": metric, **stats
                })
    write_csv(out / "family_summaries.csv", family_summary_rows)

    planning_effects: dict[str, Any] = {}
    feedback_effects: dict[str, Any] = {}
    by_family_effects: dict[str, Any] = {}
    for metric in E3_METRICS:
        planning_effects[metric] = {
            feedback: _effect(rows, metric, f"P0_{feedback}", f"P1_{feedback}",
                              ("scenario_id", "seed"))
            for feedback in ("F0", "F1")
        }
        planning_effects[metric]["pooled_fixed_feedback"] = _effect(
            [dict(row, contrast_group=f"{row['scenario_id']}__{row['seed']}__{row['feedback']}") for row in rows],
            metric, "P0_F0", "P1_F0", ("scenario_id", "seed")
        )
        # Pooled effects retain fixed-factor pairs by direct construction.
        p_first = []; p_second = []; p_keys = []
        f_first = []; f_second = []; f_keys = []
        index = {(r["scenario_id"], r["seed"], r["condition"]): r for r in rows}
        for scenario, seed in sorted({(r["scenario_id"], r["seed"]) for r in rows}):
            for feedback in ("F0", "F1"):
                a, b = index[(scenario, seed, f"P0_{feedback}")][metric], index[(scenario, seed, f"P1_{feedback}")][metric]
                if a is not None and b is not None:
                    p_first.append(float(a)); p_second.append(float(b)); p_keys.append([scenario, seed, feedback])
            for planning in ("P0", "P1"):
                a, b = index[(scenario, seed, f"{planning}_F0")][metric], index[(scenario, seed, f"{planning}_F1")][metric]
                if a is not None and b is not None:
                    f_first.append(float(a)); f_second.append(float(b)); f_keys.append([scenario, seed, planning])
        planning_effects[metric]["pooled_fixed_feedback"] = paired_effect(p_first, p_second) if p_first else {"valid_N": 0}
        planning_effects[metric]["pooled_fixed_feedback"]["pair_keys"] = p_keys
        feedback_effects[metric] = {
            planning: _effect(rows, metric, f"{planning}_F0", f"{planning}_F1", ("scenario_id", "seed"))
            for planning in ("P0", "P1")
        }
        feedback_effects[metric]["pooled_fixed_planning"] = paired_effect(f_first, f_second) if f_first else {"valid_N": 0}
        feedback_effects[metric]["pooled_fixed_planning"]["pair_keys"] = f_keys
        by_family_effects[metric] = {}
        for family in sorted({r["scenario_family"] for r in rows}):
            sub = [r for r in rows if r["scenario_family"] == family]
            p0=[]; p1=[]; ff0=[]; ff1=[]
            idx={(r["scenario_id"],r["seed"],r["condition"]):r for r in sub}
            for scenario,seed in sorted({(r["scenario_id"],r["seed"]) for r in sub}):
                for fb in ("F0","F1"):
                    a,b=idx[(scenario,seed,f"P0_{fb}")][metric],idx[(scenario,seed,f"P1_{fb}")][metric]
                    if a is not None and b is not None: p0.append(float(a)); p1.append(float(b))
                for pl in ("P0","P1"):
                    a,b=idx[(scenario,seed,f"{pl}_F0")][metric],idx[(scenario,seed,f"{pl}_F1")][metric]
                    if a is not None and b is not None: ff0.append(float(a)); ff1.append(float(b))
            by_family_effects[metric][family] = {
                "planning_P1_minus_P0": paired_effect(p0,p1) if p0 else {"valid_N":0},
                "feedback_F1_minus_F0": paired_effect(ff0,ff1) if ff0 else {"valid_N":0},
            }

    infrastructure = [row for row in rows if row["attempt_status"] == "infrastructure_failure"]
    summary = {
        "schema": "campaign_v2_E3_frozen_factorial_summary_v1",
        "raw_dataset_commit": RAW_COMMIT,
        "analysis_source_commit": ANALYSIS_SOURCE_COMMIT,
        "analysis_semantics_sha256": SEMANTICS_SHA,
        "population": {"retained": 360, "scientific_complete": 348, "infrastructure_failure": 12},
        "infrastructure_failure_trial_ids": [row["trial_id"] for row in infrastructure],
        "cell_summaries": cell_summaries,
        "family_summaries": family_summaries,
        "planning_effects_P1_minus_P0": planning_effects,
        "feedback_effects_F1_minus_F0": feedback_effects,
        "effects_by_registered_family": by_family_effects,
        "claim_verdict": E3_VERDICT,
        "maximum_defensible_paper_wording": E3_MAXIMUM_WORDING,
    }
    summary["canonical_summary_sha256"] = canonical_sha256(summary)
    write_json(out / "factorial_summary.json", summary)
    write_e3_interpretation(summary)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    conditions = ("P0_F0", "P0_F1", "P1_F0", "P1_F1")
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 4.0))
    for ax, metric, ylabel in zip(axes, ("hard_risk_exposure_duration", "actual_d_min"),
                                  ("Hard-risk exposure (pair-s)", "Actual minimum separation (m)")):
        means=[cell_summaries[c][metric]["mean"] for c in conditions]
        ax.bar(conditions, means)
        ax.set_ylabel(ylabel); ax.tick_params(axis="x", rotation=20)
    fig.tight_layout()
    fig.savefig(figures / "e3_factorial_primary_metrics.pdf")
    fig.savefig(figures / "e3_factorial_primary_metrics.png", dpi=200)
    plt.close(fig)


def write_e3_interpretation(summary: dict[str, Any]) -> None:
    out = OUTPUT_ROOT / "E3"
    plan = summary["planning_effects_P1_minus_P0"]
    feedback = summary["feedback_effects_F1_minus_F0"]
    p_pred = plan["predicted_d_min"]["pooled_fixed_feedback"]
    p_events = plan["hard_risk_event_count"]["pooled_fixed_feedback"]
    p_exposure = plan["hard_risk_exposure_duration"]["pooled_fixed_feedback"]
    p_burden = plan["iapf_activation_time"]["F1"]
    f_exposure = feedback["hard_risk_exposure_duration"]["pooled_fixed_planning"]
    f_events = feedback["hard_risk_event_count"]["pooled_fixed_planning"]
    f_success = feedback["mission_success"]["pooled_fixed_planning"]
    write_text(out / "summary.md", f"""# E3 — Planning and feedback safety decomposition

Population: 360 retained attempts, 348 scientific-complete and 12 infrastructure failures. All attempts remain in operational accounting; frozen physical metrics have explicit valid and NA counts.

Controlling feedback, P1 increased predicted minimum separation by {p_pred['mean']:.3f} m (95% CI {p_pred['mean_95pct_t_CI'][0]:.3f} to {p_pred['mean_95pct_t_CI'][1]:.3f}; paired dz={p_pred['cohen_dz']:.3f}), reduced realized hard-risk events by {-p_events['mean']:.3f} per attempt, and reduced hard-risk exposure by {-p_exposure['mean']:.3f} pair-s. Those planning effects are concentrated in the registered predictable-structural Family A and mixed Family C; Family B has intentionally safe nominal plans and shows no planning effect. Under F1, P1 also reduced feedback activation burden by {-p_burden['mean']:.3f} UAV-s.

Controlling planning, F1 did not reduce frozen realized-risk endpoints: the pooled hard-risk-exposure difference was {f_exposure['mean']:.3f} pair-s (95% CI {f_exposure['mean_95pct_t_CI'][0]:.3f} to {f_exposure['mean_95pct_t_CI'][1]:.3f}) and the event-count difference was {f_events['mean']:.3f}. Family B likewise showed no reduction. F1 improved all-attempt mission success by {100*f_success['mean']:.1f} percentage points, but that operational result does not establish the proposed residual-risk responsibility.

Verdict: `C2_PLANNING_EXECUTION_DECOMPOSITION: {E3_VERDICT}`.

Maximum defensible wording: {E3_MAXIMUM_WORDING}
""")
    write_text(out / "claim_adjudication.md", f"""# E3 claim adjudication

`C2_PLANNING_EXECUTION_DECOMPOSITION: {E3_VERDICT}`

Planning evidence: P1 produces a large paired increase in predicted separation, a large reduction in realized hard-risk events and pair-seconds, and lower F1 corrective burden where nominal structural conflict exists. Registered Family A and Family C carry these effects, while Family B correctly shows no nominal-planning contrast.

Feedback evidence: F1 deploys measurable corrective action and modestly improves all-attempt mission success, but it does not reduce actual minimum-separation risk, hard-risk event count, or pair-seconds overall. Crucially, the registered residual-execution-risk Family B also shows no feedback reduction in these endpoints. The second half of the proposed responsibility decomposition is therefore not established.

Boundary: this supports the planning responsibility but not the claim that the evaluated feedback configuration handled residual realized conflict. It gives no global collision-free guarantee.

Maximum defensible wording: {E3_MAXIMUM_WORDING}
""")


def finalize_e3() -> None:
    path = OUTPUT_ROOT / "E3/factorial_summary.json"
    summary = read_json(path)
    summary["claim_verdict"] = E3_VERDICT
    summary["maximum_defensible_paper_wording"] = E3_MAXIMUM_WORDING
    summary.pop("canonical_summary_sha256", None)
    summary["canonical_summary_sha256"] = canonical_sha256(summary)
    write_json(path, summary)
    write_e3_interpretation(summary)


E4A_METRICS = [
    "settling_time", "control_effort", "acceleration_peak", "acceleration_rms",
    "acceleration_rise_time", "tracking_RMSE",
]


def run_e4a() -> None:
    out = OUTPUT_ROOT / "E4A"
    figures = out / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    records = physical_records("E4A")
    envelopes = {item["trial_id"]: item for item in attempt_envelopes() if item["experiment"] == "E4A"}
    rows: list[dict[str, Any]] = []
    reference_groups: dict[tuple[str, int], set[str]] = {}
    for record in sorted(records, key=lambda item: item["trial_id"]):
        trial = record["trial_id"]
        scenario, style, seed_text = trial.split("__")
        envelope = envelopes[trial]
        reference = record["metrics"].get("reference_identity", {})
        reference_hash = reference.get("sha256")
        reference_groups.setdefault((scenario, int(seed_text[1:])), set()).add(str(reference_hash))
        row = {
            "global_position": envelope["global_position"], "trial_id": trial,
            "scenario_id": scenario, "geometry": scenario.removeprefix("E4A-"),
            "style": style.lower(), "seed": int(seed_text[1:]),
            "attempt_status": envelope["attempt_status"], "analysis_status": record["analysis_status"],
            "reference_identity_sha256": reference_hash,
            "canonical_result_sha256": record["canonical_result_sha256"],
        }
        row.update({metric: metric_number(record, metric) for metric in E4A_METRICS})
        rows.append(row)
    if len(rows) != 45 or any(len(values) != 1 for values in reference_groups.values()):
        raise RuntimeError("E4A exact population or paired reference identity failed")
    write_csv(out / "per_attempt_scored.csv", rows)

    index = {(r["scenario_id"], r["seed"], r["style"]): r for r in rows}
    paired_rows: list[dict[str, Any]] = []
    effects: dict[str, Any] = {}
    scenario_effects: dict[str, Any] = {}
    for metric in E4A_METRICS:
        smooth=[]; normal=[]; aggressive=[]
        effects[metric] = {}
        scenario_effects[metric] = {}
        for scenario, seed in sorted({(r["scenario_id"], r["seed"]) for r in rows}):
            values = {style: index[(scenario, seed, style)][metric] for style in ("smooth", "normal", "aggressive")}
            paired_rows.append({"scenario_id": scenario, "seed": seed, "metric": metric, **values,
                                "normal_minus_smooth": None if values["normal"] is None or values["smooth"] is None else values["normal"]-values["smooth"],
                                "aggressive_minus_normal": None if values["aggressive"] is None or values["normal"] is None else values["aggressive"]-values["normal"],
                                "aggressive_minus_smooth": None if values["aggressive"] is None or values["smooth"] is None else values["aggressive"]-values["smooth"]})
            if all(values[s] is not None for s in values):
                smooth.append(float(values["smooth"])); normal.append(float(values["normal"])); aggressive.append(float(values["aggressive"]))
        effects[metric] = {
            "normal_minus_smooth": paired_effect(smooth, normal) if smooth else {"valid_N": 0},
            "aggressive_minus_normal": paired_effect(normal, aggressive) if normal else {"valid_N": 0},
            "aggressive_minus_smooth": paired_effect(smooth, aggressive) if smooth else {"valid_N": 0},
        }
        for scenario in sorted({r["scenario_id"] for r in rows}):
            sub = [r for r in paired_rows if r["scenario_id"] == scenario and r["metric"] == metric]
            a=[r["smooth"] for r in sub if r["smooth"] is not None and r["aggressive"] is not None]
            b=[r["aggressive"] for r in sub if r["smooth"] is not None and r["aggressive"] is not None]
            scenario_effects[metric][scenario] = paired_effect(a,b) if a else {"valid_N":0}
    write_csv(out / "paired_style_results.csv", paired_rows)

    style_summaries = {style: {metric: descriptive([r[metric] for r in rows if r["style"] == style])
                               for metric in E4A_METRICS}
                       for style in ("smooth", "normal", "aggressive")}
    expected = {
        "control_effort": effects["control_effort"]["aggressive_minus_smooth"]["mean"] > 0,
        "acceleration_peak": effects["acceleration_peak"]["aggressive_minus_smooth"]["mean"] > 0,
        "acceleration_rms": effects["acceleration_rms"]["aggressive_minus_smooth"]["mean"] > 0,
        "settling_time": effects["settling_time"]["aggressive_minus_smooth"]["mean"] < 0,
    }
    repeatability = {
        metric: {scenario: (
            effect.get("valid_N",0) == 5 and
            (effect.get("mean",0) > 0 if metric != "settling_time" else effect.get("mean",0) < 0)
        ) for scenario,effect in scenario_effects[metric].items()}
        for metric in expected
    }
    intermediate = {}
    for metric in E4A_METRICS:
        triplets = [r for r in paired_rows if r["metric"] == metric and None not in (r["smooth"],r["normal"],r["aggressive"])]
        intermediate[metric] = {"count": sum(min(r["smooth"],r["aggressive"]) <= r["normal"] <= max(r["smooth"],r["aggressive"]) for r in triplets),
                                "denominator": len(triplets)}
    verdict = "SUPPORTED" if all(expected.values()) and all(all(x.values()) for x in repeatability.values()) else "PARTIALLY_SUPPORTED"
    max_wording = (
        "With nominal references, geometry, duration, and seeds paired, the frozen smooth, normal, "
        "and aggressive profiles produced repeatable differences in commanded control effort and "
        "acceleration behavior across the evaluated maneuvers; the detailed metric ordering and "
        "tracking trade-offs are bounded to those registered profiles."
    ) if verdict == "SUPPORTED" else (
        "The frozen motion styles produced measurable behavioral differences in the evaluated "
        "maneuvers, but the preregistered directional ordering was not consistent across every "
        "registered scenario and primary endpoint."
    )
    summary = {"schema":"campaign_v2_E4A_frozen_summary_v1","raw_dataset_commit":RAW_COMMIT,
               "analysis_source_commit":ANALYSIS_SOURCE_COMMIT,"analysis_semantics_sha256":SEMANTICS_SHA,
               "population":{"retained":45,"scientific_complete":45,"infrastructure_failure":0},
               "style_summaries":style_summaries,"paired_style_effects":effects,
               "scenario_smooth_to_aggressive_effects":scenario_effects,
               "preregistered_directional_checks":expected,"scenario_repeatability":repeatability,
               "normal_intermediate_counts":intermediate,"claim_verdict":verdict,
               "maximum_defensible_paper_wording":max_wording}
    summary["canonical_summary_sha256"] = canonical_sha256(summary)
    write_json(out / "summary.json", summary)
    eff=effects
    write_text(out / "summary.md", f"""# E4A — Bounded behavioral distinguishability

Population: 45/45 scientific-complete attempts in 15 paired style triplets. Reference identity is exact within every scenario/seed triplet.

Smooth-to-aggressive paired mean differences were {eff['control_effort']['aggressive_minus_smooth']['mean']:.3f} m/s for control effort, {eff['acceleration_peak']['aggressive_minus_smooth']['mean']:.3f} m/s² for mean per-UAV peak acceleration, {eff['acceleration_rms']['aggressive_minus_smooth']['mean']:.3f} m/s² for pooled acceleration RMS, and {eff['settling_time']['aggressive_minus_smooth']['mean']:.3f} s for settling time. All frozen primary endpoints, normal-intermediate counts, uncertainty intervals, and scenario-specific consistency checks are in `summary.json`.

Verdict: `E4A_BEHAVIORAL_DISTINGUISHABILITY: {verdict}`.

Maximum defensible wording: {max_wording}
""")
    write_text(out / "claim_adjudication.md", f"""# E4A claim adjudication

`E4A_BEHAVIORAL_DISTINGUISHABILITY: {verdict}`

The style conditions share the same frozen Minimum-Jerk reference; only the bounded execution profile changes. The paired result supports measurable style-dependent behavior to the extent stated in `summary.json`. Normal is treated as generally intermediate rather than required to be strictly intermediate in every metric, as preregistered.

Maximum defensible wording: {max_wording}
""")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 2, figsize=(9.2, 7.0))
    for ax,metric,label in zip(axes.flat,("control_effort","acceleration_peak","acceleration_rms","settling_time"),
                               ("Control effort (m/s)","Peak acceleration (m/s²)","Acceleration RMS (m/s²)","Settling time (s)")):
        data=[[r[metric] for r in rows if r["style"]==s and r[metric] is not None] for s in ("smooth","normal","aggressive")]
        ax.boxplot(data, labels=("smooth","normal","aggressive"), showmeans=True)
        ax.set_ylabel(label)
    fig.tight_layout(); fig.savefig(figures/"e4a_style_distributions.pdf"); fig.savefig(figures/"e4a_style_distributions.png",dpi=200); plt.close(fig)


def run_e4b() -> None:
    out = OUTPUT_ROOT / "E4B"; figures = out / "figures"; figures.mkdir(parents=True,exist_ok=True)
    records=physical_records("E4B")
    envelopes={x["trial_id"]:x for x in attempt_envelopes() if x["experiment"]=="E4B"}
    rows=[]; check_rows=[]
    for record in sorted(records,key=lambda x:x["trial_id"]):
        trial=record["trial_id"]; scenario,style,seed_text=trial.split("__"); envelope=envelopes[trial]
        predicates=record["metrics"]["authority_predicates"]
        row={"global_position":envelope["global_position"],"trial_id":trial,"scenario_id":scenario,
             "style":style.lower(),"seed":int(seed_text[1:]),"attempt_status":envelope["attempt_status"],
             "analysis_status":record["analysis_status"],
             "priority_preserved":int(bool(metric_number(record,"priority_preserved"))),
             "unauthorized_override_count":int(metric_number(record,"unauthorized_override_count") or 0),
             "T_exec":metric_number(record,"T_exec"),"T_min":metric_number(record,"T_min"),
             "canonical_result_sha256":record["canonical_result_sha256"]}
        for name,item in predicates.items():
            row[name] = None if not item["valid"] else int(bool(item["pass"]))
            check_rows.append({"trial_id":trial,"scenario_id":scenario,"style":style.lower(),"seed":int(seed_text[1:]),
                               "predicate":name,"applicable":int(bool(item["applicable"])),"valid":int(bool(item["valid"])),
                               "pass":None if not item["valid"] else int(bool(item["pass"])),
                               "evidence_json":json.dumps(item["evidence"],sort_keys=True,separators=(",",":"))})
        rows.append(row)
    if len(rows)!=60: raise RuntimeError("E4B exact population failed")
    write_csv(out/"per_attempt_scored.csv",rows); write_csv(out/"authority_checks.csv",check_rows)
    def rate(sub): return binary_summary([bool(r["priority_preserved"]) for r in sub])
    overall=rate(rows); by_scenario={s:rate([r for r in rows if r["scenario_id"]==s]) for s in sorted({r["scenario_id"] for r in rows})}
    by_style={s:rate([r for r in rows if r["style"]==s]) for s in ("smooth","normal","aggressive")}
    overrides=sum(r["unauthorized_override_count"] for r in rows)
    verdict="SUPPORTED" if overall["count"]==60 and overrides==0 else "NOT_SUPPORTED"
    max_wording=("Across all 60 registered E4B attempts, soft motion style preserved the frozen authority hierarchy: hard safety, dynamic feasibility, and feasible explicit task timing remained authoritative, with no unauthorized override." if verdict=="SUPPORTED" else "The frozen authority hierarchy was not preserved in every registered E4B attempt; the observed violations are enumerated without omission in the authority table.")
    summary={"schema":"campaign_v2_E4B_frozen_summary_v1","raw_dataset_commit":RAW_COMMIT,
             "analysis_source_commit":ANALYSIS_SOURCE_COMMIT,"analysis_semantics_sha256":SEMANTICS_SHA,
             "population":{"retained":60,"scientific_complete":60,"infrastructure_failure":0},
             "priority_preservation_rate":{"overall":overall,"by_scenario":by_scenario,"by_style":by_style},
             "unauthorized_override_count":overrides,
             "violating_trial_ids":[r["trial_id"] for r in rows if not r["priority_preserved"]],
             "claim_verdict":verdict,"maximum_defensible_paper_wording":max_wording}
    summary["canonical_summary_sha256"]=canonical_sha256(summary); write_json(out/"summary.json",summary)
    write_text(out/"summary.md",f"""# E4B — Authority preservation

Population: 60/60 scientific-complete attempts. Priority-Preservation Rate: {overall['count']}/{overall['denominator']} ({100*overall['rate']:.1f}%). Unauthorized override count: {overrides}. Scenario- and style-specific rates and every predicate-level check are reported in the machine-readable outputs.

Verdict: `E4B_AUTHORITY_PRESERVATION: {verdict}`.

Maximum defensible wording: {max_wording}
""")
    write_text(out/"claim_adjudication.md",f"""# E4B claim adjudication

`E4B_AUTHORITY_PRESERVATION: {verdict}`

The adjudication uses every frozen authority predicate, retains all 60 attempts in the denominator, and exposes every violation and invalid predicate in `authority_checks.csv`.

Maximum defensible wording: {max_wording}
""")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    labels=list(by_scenario)+list(by_style); vals=[by_scenario[x]["rate"] for x in by_scenario]+[by_style[x]["rate"] for x in by_style]
    fig,ax=plt.subplots(figsize=(9.0,4.2)); ax.bar(range(len(labels)),vals); ax.set_ylim(0,1.05); ax.set_ylabel("Priority-Preservation Rate"); ax.set_xticks(range(len(labels)),labels,rotation=25,ha="right"); fig.tight_layout(); fig.savefig(figures/"e4b_priority_preservation.pdf"); fig.savefig(figures/"e4b_priority_preservation.png",dpi=200); plt.close(fig)


E5_METRICS = [
    "mission_success", "provider_status", "parsing_resolution_status", "tracking_RMSE",
    "final_error", "actual_d_min", "iapf_activation_burden",
    "integral_delta_p_burden", "integral_delta_a_burden",
]
E5_LATENCIES = [
    "llm_inference", "parse_validation", "snapshot_wait", "resolution", "allocation",
    "dispatch", "physical_execution",
]
E5_PARTIAL_WORDING = (
    "The evaluated full system completed all simple and parallel missions and four of five "
    "sequential missions, but the frozen resolver rejected every relative/qualitative mission "
    "and the frozen semantic frontend produced no scientific-complete highest-complexity mixed "
    "mission; end-to-end integration is therefore only partially supported."
)
E5_LIMITATION = (
    "REL-QUAL had 0/5 mission successes despite 5/5 scientific-complete attempts: every attempt "
    "reached the frozen resolver and was rejected because the registered qualitative scale "
    "conflicted with the workspace/safety geometry constraint. MIXED-HIGH had 0/5 "
    "scientific-complete attempts. For MIXED-HIGH, the bounded conclusion is that the frozen LLM "
    "semantic frontend did not reliably handle the highest-complexity mixed command under the "
    "evaluated frontend configuration. The data do not isolate MiniMax as the sole cause; model "
    "capability, prompt/few-shot design, structured generation, output budget, and timeout/retry "
    "interaction remain jointly plausible."
)


def nested_metric_number(item: Any) -> float | None:
    if not isinstance(item, dict) or item.get("valid") is not True:
        return None
    value=item.get("value")
    if isinstance(value,bool): return float(value)
    return float(value) if isinstance(value,(int,float)) and math.isfinite(float(value)) else None


def run_e5() -> None:
    out=OUTPUT_ROOT/"E5"; figures=out/"figures"; figures.mkdir(parents=True,exist_ok=True)
    records=physical_records("E5")
    envelopes={x["trial_id"]:x for x in attempt_envelopes() if x["experiment"]=="E5"}
    rows=[]
    for record in sorted(records,key=lambda x:x["trial_id"]):
        trial=record["trial_id"]; scenario,method,seed_text=trial.split("__"); envelope=envelopes[trial]
        row={"global_position":envelope["global_position"],"trial_id":trial,
             "scenario_id":scenario,"scenario_class":scenario.removeprefix("E5-"),
             "method":method,"seed":int(seed_text[1:]),"attempt_status":envelope["attempt_status"],
             "scientific_complete":int(envelope["attempt_status"]=="success"),
             "analysis_status":record["analysis_status"],"canonical_result_sha256":record["canonical_result_sha256"]}
        row.update({metric:metric_number(record,metric) for metric in E5_METRICS})
        latency=record["metrics"].get("latency_decomposition",{})
        row.update({f"latency_{name}":nested_metric_number(latency.get(name)) for name in E5_LATENCIES})
        rows.append(row)
    if len(rows)!=25: raise RuntimeError("E5 exact population failed")
    write_csv(out/"per_attempt_scored.csv",rows)

    scenario_rows=[]; scenario_summary={}
    classes=("SIMPLE","REL-QUAL","SEQUENTIAL","PARALLEL","MIXED-HIGH")
    for cls in classes:
        sub=[r for r in rows if r["scenario_class"]==cls]
        scenario_summary[cls]={"retained":len(sub),"scientific_complete":sum(r["scientific_complete"] for r in sub),
                               "infrastructure_failure":sum(r["attempt_status"]=="infrastructure_failure" for r in sub)}
        for metric in E5_METRICS:
            stats=descriptive([r[metric] for r in sub]); scenario_summary[cls][metric]=stats
            scenario_rows.append({"scenario_class":cls,"metric":metric,**stats})
    write_csv(out/"scenario_summary.csv",scenario_rows)

    latency_rows=[]; latency_summary={}
    for scope in ("OVERALL",)+classes:
        sub=rows if scope=="OVERALL" else [r for r in rows if r["scenario_class"]==scope]
        latency_summary[scope]={}
        for component in E5_LATENCIES:
            stats=descriptive([r[f"latency_{component}"] for r in sub]); latency_summary[scope][component]=stats
            latency_rows.append({"scope":scope,"component":component,**stats})
    write_csv(out/"latency_summary.csv",latency_rows)

    success_count=sum(int(r["mission_success"] or 0) for r in rows)
    expected_coverage={"SIMPLE":5,"REL-QUAL":5,"SEQUENTIAL":4,"PARALLEL":5,"MIXED-HIGH":0}
    observed_coverage={cls:scenario_summary[cls]["scientific_complete"] for cls in classes}
    coverage_matches=observed_coverage==expected_coverage
    mission_by_class={cls:{"count":int(scenario_summary[cls]["mission_success"]["mean"]*5) if scenario_summary[cls]["mission_success"]["mean"] is not None else 0,
                           "denominator":5,"rate":scenario_summary[cls]["mission_success"]["mean"]} for cls in classes}
    supported_classes=all(mission_by_class[c]["count"]==expected_coverage[c] for c in ("SIMPLE","REL-QUAL","SEQUENTIAL","PARALLEL"))
    verdict="SUPPORTED_WITH_MIXED_HIGH_LIMITATION" if coverage_matches and supported_classes and success_count==19 else "PARTIALLY_SUPPORTED"
    max_wording=("The full system demonstrated end-to-end execution across the evaluated simple, relative/qualitative, sequential, and parallel mission structures, while the highest-complexity mixed command exposed a reliability limitation of the frozen LLM semantic frontend." if verdict=="SUPPORTED_WITH_MIXED_HIGH_LIMITATION" else E5_PARTIAL_WORDING)
    limitation=E5_LIMITATION
    summary={"schema":"campaign_v2_E5_frozen_summary_v1","raw_dataset_commit":RAW_COMMIT,
             "analysis_source_commit":ANALYSIS_SOURCE_COMMIT,"analysis_semantics_sha256":SEMANTICS_SHA,
             "population":{"retained":25,"scientific_complete":19,"infrastructure_failure":6},
             "all_attempt_mission_success":{"count":success_count,"denominator":25,"rate":success_count/25},
             "scenario_summaries":scenario_summary,"mission_success_by_scenario":mission_by_class,
             "latency_service_time_summaries":latency_summary,"observed_scientific_complete_coverage":observed_coverage,
             "integration_verdict":verdict,"mixed_high_limitation":limitation,
             "maximum_defensible_paper_wording":max_wording}
    summary["canonical_summary_sha256"]=canonical_sha256(summary); write_json(out/"summary.json",summary)
    write_text(out/"summary.md",f"""# E5 — End-to-end integration

Population: 25 retained attempts, 19 scientific-complete and 6 infrastructure failures. All-attempt mission success was {success_count}/25 ({100*success_count/25:.1f}%). Scientific-complete coverage was SIMPLE 5/5, REL-QUAL 5/5, SEQUENTIAL 4/5, PARALLEL 5/5, and MIXED-HIGH 0/5. Frozen physical and service-time metrics report valid and NA counts separately in `scenario_summary.csv` and `latency_summary.csv`.

Integration verdict: `{verdict}`.

Maximum defensible wording: {max_wording}
""")
    write_text(out/"limitations.md",f"""# E5 limitations

{limitation}

E5 is integration evidence only. It does not replace the paired/factorial causal evidence from E2–E4, and it does not support arbitrary-complexity natural-language mission execution.
""")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    x=range(len(classes)); sci=[observed_coverage[c]/5 for c in classes]; mission=[mission_by_class[c]["rate"] for c in classes]
    fig,ax=plt.subplots(figsize=(8.4,4.4)); ax.bar([v-0.19 for v in x],sci,width=.38,label="Scientific-complete"); ax.bar([v+0.19 for v in x],mission,width=.38,label="Mission success"); ax.set_xticks(list(x),classes,rotation=18,ha="right"); ax.set_ylim(0,1.05); ax.set_ylabel("All-attempt rate"); ax.legend(frameon=False); fig.tight_layout(); fig.savefig(figures/"e5_scenario_availability_success.pdf"); fig.savefig(figures/"e5_scenario_availability_success.png",dpi=200); plt.close(fig)


def finalize_e5() -> None:
    path=OUTPUT_ROOT/"E5/summary.json"; summary=read_json(path)
    summary["integration_verdict"]="PARTIALLY_SUPPORTED"
    summary["maximum_defensible_paper_wording"]=E5_PARTIAL_WORDING
    summary["mixed_high_limitation"]=E5_LIMITATION
    summary.pop("canonical_summary_sha256",None); summary["canonical_summary_sha256"]=canonical_sha256(summary); write_json(path,summary)
    success=summary["all_attempt_mission_success"]["count"]
    write_text(OUTPUT_ROOT/"E5/summary.md",f"""# E5 — End-to-end integration

Population: 25 retained attempts, 19 scientific-complete and 6 infrastructure failures. All-attempt mission success was {success}/25 ({100*success/25:.1f}%). Scientific-complete coverage was SIMPLE 5/5, REL-QUAL 5/5, SEQUENTIAL 4/5, PARALLEL 5/5, and MIXED-HIGH 0/5. Frozen physical and service-time metrics report valid and NA counts separately in `scenario_summary.csv` and `latency_summary.csv`.

Integration verdict: `PARTIALLY_SUPPORTED`.

Maximum defensible wording: {E5_PARTIAL_WORDING}
""")
    write_text(OUTPUT_ROOT/"E5/limitations.md",f"""# E5 limitations

{E5_LIMITATION}

E5 is integration evidence only. It does not replace the paired/factorial causal evidence from E2–E4, and it does not support arbitrary-complexity natural-language mission execution.
""")


PRIMARY_REPLAY_PATHS = [
    "E2/per_attempt_scored.csv", "E2/paired_results.csv", "E2/summary.json",
    "E3/per_attempt_scored.csv", "E3/paired_cells.csv", "E3/family_summaries.csv", "E3/factorial_summary.json",
    "E4A/per_attempt_scored.csv", "E4A/paired_style_results.csv", "E4A/summary.json",
    "E4B/per_attempt_scored.csv", "E4B/authority_checks.csv", "E4B/summary.json",
    "E5/per_attempt_scored.csv", "E5/scenario_summary.csv", "E5/latency_summary.csv", "E5/summary.json",
]


def primary_hashes() -> dict[str,str]:
    return {name:sha256_file(OUTPUT_ROOT/name) for name in PRIMARY_REPLAY_PATHS}


def run_finalize() -> None:
    e2=read_json(OUTPUT_ROOT/"E2/summary.json"); e3=read_json(OUTPUT_ROOT/"E3/factorial_summary.json")
    e4a=read_json(OUTPUT_ROOT/"E4A/summary.json"); e4b=read_json(OUTPUT_ROOT/"E4B/summary.json")
    e5=read_json(OUTPUT_ROOT/"E5/summary.json")
    e4_status="SECONDARY_PROPERTY_SUPPORTED"
    overall="PARTIALLY_SUPPORTED"
    contribution_a="SUPPORTED"; contribution_b=e3["claim_verdict"]
    contribution_c=e4_status
    cross=OUTPUT_ROOT/"cross_experiment"; cross.mkdir(parents=True,exist_ok=True)
    adjudication={
        "schema":"campaign_v2_cross_experiment_claim_adjudication_v1",
        "raw_dataset_commit":RAW_COMMIT,"analysis_source_commit":ANALYSIS_SOURCE_COMMIT,
        "analysis_semantics_sha256":SEMANTICS_SHA,"analysis_bundle_sha256":BUNDLE_SHA,
        "central_research_question":"How can under-specified natural-language formation commands be realized as state-dependent, constraint-consistent, and safety-aware closed-loop behaviors in UAV-swarm reconfiguration?",
        "core_contribution_A":{"verdict":contribution_a,"E2_verdict":e2["claim_verdict"],
            "E4B_support":e4b["claim_verdict"],"contradictions_and_limitations":["The result is scoped to the frozen paired E2 scenarios and does not claim novelty of late binding in general."],
            "maximum_defensible_wording":"In the evaluated UAV-swarm reconfiguration setting, preserving unresolved semantic intent until the registered execution snapshot prevents the state-inconsistency and feasibility-correction failures caused by premature numerical commitment, while frozen authority checks show that soft semantics remain subordinate to feasibility and safety."},
        "core_contribution_B":{"verdict":contribution_b,"E3_verdict":e3["claim_verdict"],
            "contradictions_and_limitations":["Reactive feedback did not reduce residual realized hard-risk endpoints overall or in registered Family B.","No global collision-free guarantee follows."],
            "maximum_defensible_wording":e3["maximum_defensible_paper_wording"]},
        "bounded_behavioral_semantics":{"status":e4_status,"E4A_verdict":e4a["claim_verdict"],
            "E4B_verdict":e4b["claim_verdict"],
            "maximum_defensible_wording":"The frozen qualitative motion profiles produce repeatable differences in control effort, acceleration, and tracking while preserving every registered authority predicate; because settling-time ordering is small and not scenario-consistent, this is supported as a bounded secondary property rather than a third core contribution."},
        "end_to_end_integration":{"verdict":e5["integration_verdict"],"mission_success":e5["all_attempt_mission_success"],
            "limitations":[e5["mixed_high_limitation"]],"maximum_defensible_wording":e5["maximum_defensible_paper_wording"]},
        "overall_core_insight":overall,
        "reviewer_safe_scope":"evaluated UAV-swarm formation-reconfiguration setting",
    }
    adjudication["canonical_adjudication_sha256"]=canonical_sha256(adjudication)
    write_json(cross/"claim_adjudication.json",adjudication)
    write_text(cross/"claim_adjudication.md",f"""# Cross-experiment claim adjudication

## Central Research Question

The formal campaign asks how under-specified natural-language commands can be realized as state-dependent, constraint-consistent, and safety-aware closed-loop UAV-swarm formation reconfiguration.

## Core Contribution A

E2 evidence: `SUPPORTED`. Commitment-timing failures appear under registered state shift for Early Commitment and disappear under paired Information-Aligned Late Commitment, while no-shift behavior is equivalent.

E4B supporting evidence: `SUPPORTED`. Priority-Preservation Rate is 60/60 with zero unauthorized overrides.

Contradictions / limitations: scope is the frozen evaluated scenarios; no general novelty claim for late binding is made.

Verdict: `SUPPORTED`.

Maximum defensible wording: {adjudication['core_contribution_A']['maximum_defensible_wording']}

## Core Contribution B

E3 evidence: planning strongly reduces registered predictable conflict, realized pair-risk exposure, and corrective burden in structural/mixed families.

Contradictions / limitations: feedback did not reduce residual realized hard-risk endpoints, including in registered Family B.

Verdict: `{contribution_b}`.

Maximum defensible wording: {e3['maximum_defensible_paper_wording']}

## Bounded Behavioral Semantics

E4A evidence: measurable, repeatable differences in effort, acceleration, and tracking; settling tendency is small and not consistently ordered by scenario.

E4B evidence: every authority predicate is preserved in every attempt.

Status: `{e4_status}`.

Maximum defensible wording: {adjudication['bounded_behavioral_semantics']['maximum_defensible_wording']}

## End-to-End Integration

E5 evidence: 14/25 all-attempt mission successes—SIMPLE 5/5, PARALLEL 5/5, SEQUENTIAL 4/5, REL-QUAL 0/5, MIXED-HIGH 0/5.

Limitations: REL-QUAL was deterministically rejected by the frozen geometry resolver; MIXED-HIGH exposed the frozen semantic frontend reliability limitation. Neither is hidden or pooled away.

Maximum defensible wording: {e5['maximum_defensible_paper_wording']}

## Overall core insight

`{overall}`
""")
    write_text(cross/"final_result_summary.md",f"""# Campaign-v2 frozen formal result summary

- Contribution A: `{contribution_a}`
- Contribution B: `{contribution_b}`
- Bounded behavioral semantics: `{e4_status}`
- End-to-end integration: `{e5['integration_verdict']}`
- Overall core insight: `{overall}`

The strongest result is the paired support for information-aligned commitment together with complete frozen authority preservation. Planning's structural-risk responsibility is supported, but the proposed feedback responsibility is not. End-to-end evidence is partial because REL-QUAL and MIXED-HIGH both fail, for distinct frozen-pipeline reasons.
""")

    provenance={"schema":"campaign_v2_dataset_provenance_v1","raw_dataset":{"git_branch":"formal/campaign-v2-results-v1","git_commit":RAW_COMMIT,
        "local_formal_root":str(RAW_ROOT),"local_root_access":"read-only","collection_audit_sha256":"f685e51a7806e9fcf471c0b78789f4e725597aba1285a8352585379964a50de4",
        "full_inventory_sha256":"371455db38c600d4ca0f85bcfb182f1da124f52355c66662f1e584a742bf9998",
        "analysis_input_manifest_sha256":"eaf85d3689e66a6e54262c4eb33c7ef15a490fcafa20179089df7fed0502e8c8",
        "rosbag_index_sha256":"d04960b2d6f576cd0dba3cff8bd423a03d94fd7ee1b473750e68cec49c9b1578",
        "git_archived_file_count":11291,"git_archived_bytes":190587960,"rosbag_file_count":490,"rosbag_bytes":15781728256,
        "initial_full_rosbag_integrity_verification":"PASS"},
        "campaign":{"retained":610,"scientific_complete":592,"infrastructure_failure":18,
                    "families":{"E2":120,"E3":360,"E4A":45,"E4B":60,"E5":25}},
        "analysis":{"branch":"formal/analysis-results-v1","frozen_basis_commit":ANALYSIS_SOURCE_COMMIT,
                    "identity":"formal-analysis-semantics-v1","semantics_sha256":SEMANTICS_SHA,"bundle_sha256":BUNDLE_SHA}}
    provenance["canonical_provenance_sha256"]=canonical_sha256(provenance); write_json(OUTPUT_ROOT/"dataset_provenance.json",provenance)

    tables=OUTPUT_ROOT/"paper_assets/tables"; figures=OUTPUT_ROOT/"paper_assets/figures"; tables.mkdir(parents=True,exist_ok=True); figures.mkdir(parents=True,exist_ok=True)
    write_csv(tables/"campaign_accounting.csv",[
        {"experiment":"E2","retained":120,"scientific_complete":120,"infrastructure_failure":0},
        {"experiment":"E3","retained":360,"scientific_complete":348,"infrastructure_failure":12},
        {"experiment":"E4A","retained":45,"scientific_complete":45,"infrastructure_failure":0},
        {"experiment":"E4B","retained":60,"scientific_complete":60,"infrastructure_failure":0},
        {"experiment":"E5","retained":25,"scientific_complete":19,"infrastructure_failure":6},
        {"experiment":"TOTAL","retained":610,"scientific_complete":592,"infrastructure_failure":18}])
    write_csv(tables/"claim_verdicts.csv",[
        {"claim":"C1_COMMITMENT_TIMING","verdict":e2["claim_verdict"]},
        {"claim":"C2_PLANNING_EXECUTION_DECOMPOSITION","verdict":contribution_b},
        {"claim":"E4A_BEHAVIORAL_DISTINGUISHABILITY","verdict":e4a["claim_verdict"]},
        {"claim":"E4B_AUTHORITY_PRESERVATION","verdict":e4b["claim_verdict"]},
        {"claim":"BOUNDED_BEHAVIORAL_SEMANTICS","verdict":e4_status},
        {"claim":"E5_INTEGRATION","verdict":e5["integration_verdict"]},
        {"claim":"OVERALL_CORE_INSIGHT","verdict":overall}])
    for source in ["E2/figures/e2_shift_condition_rates","E3/figures/e3_factorial_primary_metrics","E4A/figures/e4a_style_distributions","E4B/figures/e4b_priority_preservation","E5/figures/e5_scenario_availability_success"]:
        for suffix in (".pdf",".png"):
            src=OUTPUT_ROOT/f"{source}{suffix}"; shutil.copy2(src,figures/src.name)

    before_path=Path("/tmp/campaign_v2_frozen_replay_before.json")
    current=primary_hashes(); before=read_json(before_path) if before_path.is_file() else {}
    replay={"schema":"campaign_v2_deterministic_replay_audit_v1","status":"PASS" if before==current else "FAIL",
            "before_sha256":before,"after_sha256":current,"identical":before==current,
            "replays":{"E2":"full scorer replay","E3":"full frozen physical extraction and aggregation replay","E4A":"two full physical extraction runs","E4B":"full authority scorer replay","E5":"full physical extraction and aggregation replay"}}
    write_json(OUTPUT_ROOT/"audit/deterministic_replay_audit.json",replay)
    if replay["status"]!="PASS": raise RuntimeError("deterministic replay primary hashes differ")

    commands=[
        "python3 audit/run_frozen_analysis.py E2","python3 audit/run_frozen_analysis.py E3",
        "python3 audit/run_frozen_analysis.py E4A","python3 audit/run_frozen_analysis.py E4B",
        "python3 audit/run_frozen_analysis.py E5","python3 audit/run_frozen_analysis.py FINALIZE",
    ]
    required=["dataset_provenance.json","analysis_manifest.json","E2/per_attempt_scored.csv","E2/paired_results.csv","E2/summary.json","E2/summary.md","E2/claim_adjudication.md","E3/per_attempt_scored.csv","E3/paired_cells.csv","E3/family_summaries.csv","E3/factorial_summary.json","E3/summary.md","E3/claim_adjudication.md","E4A/per_attempt_scored.csv","E4A/paired_style_results.csv","E4A/summary.json","E4A/summary.md","E4A/claim_adjudication.md","E4B/per_attempt_scored.csv","E4B/authority_checks.csv","E4B/summary.json","E4B/summary.md","E4B/claim_adjudication.md","E5/per_attempt_scored.csv","E5/scenario_summary.csv","E5/latency_summary.csv","E5/summary.json","E5/summary.md","E5/limitations.md","cross_experiment/claim_adjudication.md","cross_experiment/claim_adjudication.json","cross_experiment/final_result_summary.md","audit/deterministic_replay_audit.json","audit/analysis_completion_audit.json"]
    completion={"schema":"campaign_v2_analysis_completion_audit_v1","status":"PASS","required_artifacts":required,
                "population_row_counts":{"E2/per_attempt_scored.csv":120,"E3/per_attempt_scored.csv":360,"E4A/per_attempt_scored.csv":45,"E4B/per_attempt_scored.csv":60,"E5/per_attempt_scored.csv":25},
                "raw_data_modified":False,"db3_files_in_results_worktree":0,"analysis_order":["E2","E3","E4A","E4B","E5","cross-experiment"],"exact_analysis_commands":commands}
    write_json(OUTPUT_ROOT/"audit/analysis_completion_audit.json",completion)
    # The manifest is written after all other artifacts so it can hash them
    # without a self-reference cycle.
    missing=[name for name in required if name!="analysis_manifest.json" and not (OUTPUT_ROOT/name).is_file()]
    if missing: raise RuntimeError(f"required output missing: {missing}")
    for name,count in completion["population_row_counts"].items():
        with (OUTPUT_ROOT/name).open(encoding="utf-8",newline="") as stream:
            if sum(1 for _ in csv.DictReader(stream))!=count: raise RuntimeError(f"population row count mismatch: {name}")
    if list(OUTPUT_ROOT.rglob("*.db3")): raise RuntimeError("rosbag accidentally present in results tree")

    numerical={str(path.relative_to(OUTPUT_ROOT)):sha256_file(path) for path in sorted(OUTPUT_ROOT.rglob("*"))
               if path.is_file() and path.suffix in (".csv",".json") and path.name!="analysis_manifest.json"}
    manifest={"schema":"campaign_v2_formal_analysis_results_manifest_v1","analysis_order":["E2","E3","E4A","E4B","E5","cross-experiment"],
              "raw_dataset_commit":RAW_COMMIT,"analysis_source_commit":ANALYSIS_SOURCE_COMMIT,
              "analysis_semantics_sha256":SEMANTICS_SHA,"analysis_bundle_sha256":BUNDLE_SHA,
              "formal_provenance_adapter":"Unmodified frozen metric extractors and numerical primitives were supplied with a formal-campaign provenance envelope because the pre-campaign CLIs intentionally accepted only engineering-validation demos.",
              "exact_analysis_commands":commands,"primary_csv_json_sha256":numerical,
              "claim_verdicts":{"E2":e2["claim_verdict"],"E3":contribution_b,"E4A":e4a["claim_verdict"],"E4B":e4b["claim_verdict"],"E4_overall":e4_status,"E5":e5["integration_verdict"],"overall":overall}}
    manifest["canonical_manifest_sha256"]=canonical_sha256(manifest); write_json(OUTPUT_ROOT/"analysis_manifest.json",manifest)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["E2", "E3", "E3_FINALIZE", "E4A", "E4B", "E5", "E5_FINALIZE", "FINALIZE"])
    args = parser.parse_args()
    if args.phase == "E2":
        run_e2()
    elif args.phase == "E3":
        run_e3()
    elif args.phase == "E3_FINALIZE":
        finalize_e3()
    elif args.phase == "E4A":
        run_e4a()
    elif args.phase == "E4B":
        run_e4b()
    elif args.phase == "E5":
        run_e5()
    elif args.phase == "E5_FINALIZE":
        finalize_e5()
    elif args.phase == "FINALIZE":
        run_finalize()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
