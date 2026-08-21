#!/usr/bin/env python3
"""Audit the terminal C0-A prereg-v2 campaign without changing trial outcomes."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
V1_HASHES = {
    "C0-A-prereg-v1_PROTOCOL.md": "9b71550f76e2bb536cf0451ca0ea65f4665d7419b84377867868d72c972670bd",
    "C0-A-prereg-v1_RESULT.md": "c5564de0ac893787527079c165d55fbe1a8f4b53755f26beb7aabac29cb778e9",
    "C0-A-prereg-v1_manifest.json": "2969a9e4f71ac42edc9a488a08ae6bc1c4e55221e1c00a503b1da228a3091a5d",
    "C0-A-prereg-v1_preflight_checks.txt": "5e350482f1d7681bd91d1d4c68ab3ebe402f805cc41dc6c23c11b8abff3b8280",
    "C0-A-prereg-v1_trial_order.json": "1ae3a73c16a41b1c0fa4fd89eb18d2c00fdf3a6554e3fbf3d59f08be05e09981",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    artifact = args.artifact_root.resolve()
    schedule = json.loads((ROOT / "trial_order_v2.json").read_text(encoding="utf-8"))
    state = json.loads((artifact / "campaign_state.json").read_text(encoding="utf-8"))
    ranking = json.loads(
        (artifact / "metrics" / "a1_screening_ranking.json").read_text(encoding="utf-8")
    )
    aggregate_path = artifact / "metrics" / "aggregate_v2.json"
    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
    checks: list[dict] = []

    def check(name: str, condition: bool, evidence) -> None:
        checks.append({"name": name, "pass": bool(condition), "evidence": evidence})

    screening_entries = [entry for entry in schedule["entries"] if entry["stage"] == "A1_SCREENING"]
    expected_ids = {entry["trial_id"] for entry in screening_entries}
    metric_paths = sorted((artifact / "raw").glob("*/metrics.json"))
    manifest_paths = sorted((artifact / "raw").glob("*/manifest.json"))
    metrics = [json.loads(path.read_text(encoding="utf-8")) for path in metric_paths]
    manifests = [json.loads(path.read_text(encoding="utf-8")) for path in manifest_paths]
    metric_ids = [item["trial_id"] for item in metrics]
    manifest_ids = [item["trial_id"] for item in manifests]
    by_candidate = defaultdict(list)
    for item in metrics:
        by_candidate[item["candidate_id"]].append(item)
    failure_counts = Counter(
        failure for item in metrics for failure in item.get("hard_failures", [])
    )
    termination_counts = Counter(item["termination_reason"] for item in manifests)

    check("protocol_version", schedule["protocol_version"] == "C0-A-prereg-v2", schedule["protocol_version"])
    check("schedule_complete", schedule["schedule_complete"] is True, schedule["schedule_complete"])
    check("unresolved_protocol_ambiguity", schedule["unresolved_protocol_ambiguity"] == 0, schedule["unresolved_protocol_ambiguity"])
    check("ordering_seed", schedule["ordering_seed"] == 41999, schedule["ordering_seed"])
    check("a1_schedule_count", len(screening_entries) == 300, len(screening_entries))
    check("metrics_count", len(metrics) == 300, len(metrics))
    check("manifests_count", len(manifests) == 300, len(manifests))
    check("unique_metric_ids", len(set(metric_ids)) == len(metric_ids), len(set(metric_ids)))
    check("unique_manifest_ids", len(set(manifest_ids)) == len(manifest_ids), len(set(manifest_ids)))
    check("executed_ids_equal_a1_schedule", set(metric_ids) == expected_ids == set(manifest_ids), {
        "missing": sorted(expected_ids - set(metric_ids)),
        "unexpected": sorted(set(metric_ids) - expected_ids),
    })
    check("candidate_count", len(by_candidate) == 25, len(by_candidate))
    check("twelve_trials_per_candidate", all(len(items) == 12 for items in by_candidate.values()), {
        candidate: len(items) for candidate, items in sorted(by_candidate.items())
    })
    check("all_candidates_eliminated", all(any(not item["hard_pass"] for item in items) for items in by_candidate.values()), {
        "eliminated": sum(any(not item["hard_pass"] for item in items) for items in by_candidate.values())
    })
    check("ranking_complete", len(ranking["candidates"]) == 25 and all(item["complete"] for item in ranking["candidates"]), len(ranking["candidates"]))
    check("ranking_survivors_zero", ranking["survivor_count"] == 0, ranking["survivor_count"])
    check("terminal_status", state["campaign_status"] == "NO_ACCEPTABLE_CONFIGURATION", state["campaign_status"])
    check("formal_trial_count", state["formal_trials_executed"] == 300, state["formal_trials_executed"])
    check("only_a1_completed", state["completed_stages"] == ["A1_SCREENING"], state["completed_stages"])
    check("no_winners", all(state.get(key) is None for key in ("a1_winner", "a2_winner", "a3_winner")), {
        key: state.get(key) for key in ("a1_winner", "a2_winner", "a3_winner")
    })
    check("later_stages_not_executed", all(item["stage"] == "A1_SCREENING" for item in metrics), sorted({item["stage"] for item in metrics}))
    check("aggregate_count", aggregate["formal_trials_executed"] == 300, aggregate["formal_trials_executed"])
    check("aggregate_status", aggregate["campaign_status"] == state["campaign_status"], aggregate["campaign_status"])
    check("aggregate_failure_counts", aggregate["failure_counts"] == dict(sorted(failure_counts.items())), aggregate["failure_counts"])
    check("aggregate_termination_counts", aggregate["termination_counts"] == dict(sorted(termination_counts.items())), aggregate["termination_counts"])
    deviations = sorted(path.name for path in (ROOT / "deviations").glob("C0-A-prereg-v2_DEV-*.md"))
    check("recorded_deviations", deviations == ["C0-A-prereg-v2_DEV-001.md", "C0-A-prereg-v2_DEV-002.md"], deviations)
    v1_observed = {
        name: digest(ROOT / "history" / name) if (ROOT / "history" / name).is_file() else None
        for name in V1_HASHES
    }
    check("v1_history_byte_preserved", v1_observed == V1_HASHES, v1_observed)
    terminal_manifest_path = ROOT / "manifest_v2.json"
    if terminal_manifest_path.is_file():
        terminal_manifest = json.loads(terminal_manifest_path.read_text(encoding="utf-8"))
        evidence_dir = ROOT / "evidence_v2"
        evidence_hashes = terminal_manifest["artifact_storage"]["repository_evidence"]
        observed_evidence_hashes = {
            name: digest(evidence_dir / name) if (evidence_dir / name).is_file() else None
            for name in evidence_hashes
        }
        check("terminal_manifest_status", terminal_manifest["status"] == "NO_ACCEPTABLE_CONFIGURATION", terminal_manifest["status"])
        check("terminal_manifest_no_freeze", terminal_manifest["frozen_parameter_commit"] is None and terminal_manifest["checkpoint_tag"] is None and terminal_manifest["ready_for_c0_b"] is False, {
            key: terminal_manifest[key] for key in ("frozen_parameter_commit", "checkpoint_tag", "ready_for_c0_b")
        })
        check("result_hash", digest(ROOT / "CALIBRATION_RESULT_v2.md") == terminal_manifest["result_sha256"], terminal_manifest["result_sha256"])
        check("repository_evidence_hashes", observed_evidence_hashes == evidence_hashes, observed_evidence_hashes)
        trial_records = (evidence_dir / "trial_records_v2.jsonl").read_text(encoding="utf-8").splitlines()
        record_ids = []
        records_consistent = True
        for line in trial_records:
            record = json.loads(line)
            ids = (
                record["manifest"]["trial_id"],
                record["metrics"]["trial_id"],
                record["trial_spec"]["entry"]["trial_id"],
            )
            record_ids.append(ids[0])
            records_consistent = records_consistent and len(set(ids)) == 1
        check("repository_trial_records", len(record_ids) == 300 and len(set(record_ids)) == 300 and records_consistent and set(record_ids) == expected_ids, {
            "count": len(record_ids), "unique": len(set(record_ids)), "records_consistent": records_consistent
        })

    report = {
        "audit": "C0-A-prereg-v2 terminal campaign audit",
        "artifact_root": str(artifact),
        "checks": checks,
        "failure_counts": dict(sorted(failure_counts.items())),
        "hard_pass_trials": sum(bool(item["hard_pass"]) for item in metrics),
        "hard_fail_trials": sum(not bool(item["hard_pass"]) for item in metrics),
        "overall": "PASS" if all(item["pass"] for item in checks) else "FAIL",
        "termination_counts": dict(sorted(termination_counts.items())),
    }
    if not args.check_only:
        output = artifact / "logs" / "final_audit_v2.json"
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
