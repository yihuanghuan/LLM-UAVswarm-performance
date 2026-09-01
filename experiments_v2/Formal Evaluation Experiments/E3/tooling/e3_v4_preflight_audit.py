#!/usr/bin/env python3
"""Static, non-executing E3-v4 campaign and formal-adapter preflight."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

import yaml

from e3_v4_formal_adapter import AdapterError, adapter_identity, validate_context
from e3_v4_trial_registry import (
    E3, OLD_V3_SHA256, ORDER, ORDER_META, ORDER_META_SHA256, ORDER_SHA256,
    POLICY, POLICY_SHA256, REGISTRY, REGISTRY_SHA256, SEEDS, SEEDS_SHA256,
    build_exact_runtime_spec, registered_trial_ids, sha256_file,
)

REPO = E3.parents[2]
START_HEAD = "cda52d13c14cb05b3d92ee57dcae8fdfba0b157f"
PRODUCTION_BASELINE = "6cf402debf23851b1eff3edc6f3ab49eae7127c4"
V3 = E3 / "e3_factorial_registry_v3.yaml"
ANALYSIS = E3 / "E3_v4_analysis_contract.md"
JOURNAL_CONTRACT = E3 / "E3_v4_campaign_journal_contract.yaml"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    ids = registered_trial_ids()
    registry = yaml.safe_load(REGISTRY.read_text())
    seed_registry = yaml.safe_load(SEEDS.read_text())
    identity = adapter_identity()
    counts = Counter()
    blocks: dict[tuple[str, int], set[str]] = defaultdict(set)
    runtime_hashes = {}
    planning = defaultdict(dict)
    mechanisms = defaultdict(set)
    for index, trial in enumerate(ids, start=1):
        runtime = build_exact_runtime_spec(trial)
        scene = runtime["scenario_id"]
        condition = runtime["condition"]
        seed = int(runtime["seed"])
        counts[(scene, condition)] += 1
        blocks[(scene, seed)].add(condition)
        runtime_hashes[trial] = runtime["runtime_spec_sha256"]
        planning[scene][condition] = {
            "assignment": runtime["allocator_diagnostics"]["final_assignment"],
            "hard_violations": int(runtime["allocator_diagnostics"]["hard_violations"]),
            "d_min_m": float(runtime["allocator_diagnostics"]["min_distance"]),
        }
        mechanisms[scene].add(runtime["manipulation"]["type"])
    expected_conditions = {"P0_F0", "P0_F1", "P1_F0", "P1_F1"}
    blocks_complete = len(blocks) == 90 and all(value == expected_conditions for value in blocks.values())
    cardinality = len(ids) == len(set(ids)) == 360 and all(value == 15 for value in counts.values())
    planning_pass = True
    for scene, values in planning.items():
        p0 = values["P0_F0"]
        p1 = values["P1_F0"]
        feedback_invariant = (
            values["P0_F0"] == values["P0_F1"]
            and values["P1_F0"] == values["P1_F1"]
        )
        if "-A-" in scene:
            family_pass = p0["hard_violations"] > 0 and p1["hard_violations"] == 0
        elif "-B-" in scene:
            family_pass = p0["hard_violations"] == p1["hard_violations"] == 0
        else:
            family_pass = p0["hard_violations"] > 0 and p1["hard_violations"] == 0
        planning_pass &= family_pass and feedback_invariant
    mechanisms_pass = (
        mechanisms["E3-A-01"] == mechanisms["E3-A-02"] == {"none"}
        and mechanisms["E3-B-01"] == mechanisms["E3-C-01"] == {"command_delay"}
        and mechanisms["E3-B-02"] == mechanisms["E3-C-02"] == {"reference_deviation"}
    )
    sample = ids[0]
    formal_context = {
        "trial_id": sample,
        "campaign_position": 1,
        "execution_mode": "formal",
        "dataset_class": "formal_evaluation",
        "formal_launch_authorized": True,
        "runner_commit": identity["commit"],
        "runner_source_sha256": identity["source_sha256"],
        "runner_tooling_bundle_sha256": identity["execution_tooling"]["bundle_sha256"],
        "registry_sha256": REGISTRY_SHA256,
        "formal_seed_registry_sha256": SEEDS_SHA256,
        "order_sha256": ORDER_SHA256,
        "policy_sha256": POLICY_SHA256,
        "attempt_output_dir": "/nonexistent/not-used",
    }
    formal_gate_refused = False
    formal_gate_error = None
    try:
        validate_context(sample, formal_context)
    except AdapterError as exc:
        formal_gate_refused = "pending human registry activation" in str(exc)
        formal_gate_error = str(exc)
    changed = subprocess_output = __import__("subprocess").check_output(
        ["git", "diff", "--name-only", START_HEAD], cwd=REPO, text=True
    ).splitlines()
    e3_prefix = "experiments_v2/Formal Evaluation Experiments/E3/"
    production_invariant = all(value.startswith(e3_prefix) for value in changed)
    hashes_pass = (
        sha256_file(REGISTRY) == REGISTRY_SHA256
        and sha256_file(SEEDS) == SEEDS_SHA256
        and sha256_file(ORDER) == ORDER_SHA256
        and sha256_file(ORDER_META) == ORDER_META_SHA256
        and sha256_file(POLICY) == POLICY_SHA256
        and sha256_file(V3) == OLD_V3_SHA256
    )
    evidence = {
        "schema": "E3_v4_preflight_audit_v1",
        "status": "PASS" if all((
            cardinality, blocks_complete, planning_pass, mechanisms_pass,
            formal_gate_refused, production_invariant, hashes_pass,
            ANALYSIS.is_file(), registry["qualification_provenance"]["F1_attempt_count"] == 0,
            JOURNAL_CONTRACT.is_file(),
            registry["qualification_provenance"]["formal_attempt_count"] == 0,
        )) else "FAIL",
        "registry_status": registry["status"],
        "scenario_preflight_ready": True,
        "formal_execution_started": False,
        "formal_launch_gate_refused_pending_human_review": formal_gate_refused,
        "formal_launch_gate_error": formal_gate_error,
        "attempt_count": len(ids),
        "unique_attempt_count": len(set(ids)),
        "complete_four_cell_block_count": len(blocks),
        "blocks_complete": blocks_complete,
        "scenario_condition_counts": {
            f"{scene}__{condition}": count
            for (scene, condition), count in sorted(counts.items())
        },
        "paired_seeds": seed_registry["paired_seeds"],
        "planning_validation": planning,
        "mechanisms": {key: sorted(value) for key, value in mechanisms.items()},
        "runtime_spec_hashes": runtime_hashes,
        "runtime_spec_hash_inventory_sha256": hashlib.sha256(json.dumps(
            runtime_hashes, sort_keys=True, separators=(",", ":")
        ).encode()).hexdigest(),
        "adapter_identity": identity,
        "production_invariance": {
            "start_head": START_HEAD,
            "production_baseline": PRODUCTION_BASELINE,
            "changed_paths_since_start": changed,
            "only_E3_experiment_subtree_changed": production_invariant,
        },
        "hashes": {
            "registry_sha256": sha256_file(REGISTRY),
            "formal_seed_registry_sha256": sha256_file(SEEDS),
            "order_sha256": sha256_file(ORDER),
            "order_metadata_sha256": sha256_file(ORDER_META),
            "policy_sha256_before": POLICY_SHA256,
            "policy_sha256_after": sha256_file(POLICY),
            "E3_v3_registry_sha256_before": OLD_V3_SHA256,
            "E3_v3_registry_sha256_after": sha256_file(V3),
            "analysis_contract_sha256": sha256_file(ANALYSIS),
            "journal_contract_sha256": sha256_file(JOURNAL_CONTRACT),
        },
        "F1_qualification_attempt_count": 0,
        "formal_attempt_count": 0,
    }
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(evidence["status"])
    return 0 if evidence["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
