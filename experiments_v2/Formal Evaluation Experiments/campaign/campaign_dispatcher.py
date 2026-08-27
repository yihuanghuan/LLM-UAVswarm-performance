#!/usr/bin/env python3
"""Dispatch exactly the next sealed global trial (synthetic validation only)."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
from typing import Any, Dict, Mapping

from campaign_common import (
    ATTEMPT_STATUSES, BASELINE_COMMIT, BASELINE_TAG, CAMPAIGN_DIR,
    CANONICAL_POLICY_SHA256, DATASET_CLASS, FORMAL_RESULTS_DIR,
    GLOBAL_REGISTRY_SHA256, NOT_FORMAL_RESULT, ORDER_TXT_SHA256,
    ORDER_YAML_SHA256, PREFLIGHT_SHA256, SOURCE_PREFLIGHT_COMMIT,
    SYNTHETIC_RESULTS_DIR, CampaignError, RunnerRefusalError, family_for_trial, load_json,
    load_sealed_order, sha256_file, utc_now, write_json_exclusive,
)
from campaign_journal import CampaignExecutionLock, CampaignJournal
from campaign_provenance import validate_provenance
from runner_registry import load_runner_registry, registry_sha256


ARTIFACT_NAME = re.compile(r"^(\d{6})-attempt\.json$")


def _formal_cursor_snapshot() -> Dict[str, Any]:
    if not FORMAL_RESULTS_DIR.exists():
        return {"exists": False, "files": []}
    files = []
    for path in sorted(item for item in FORMAL_RESULTS_DIR.rglob("*") if item.is_file()):
        files.append({
            "path": path.relative_to(FORMAL_RESULTS_DIR).as_posix(),
            "sha256": sha256_file(path),
        })
    return {"exists": True, "files": files}


def _ensure_synthetic_run_path(run_dir: Path) -> None:
    parent = run_dir.resolve().parent
    if not (parent.name == "synthetic-validation"
            and parent.parent.name == "results"
            and parent.parent.parent.name == "campaign"):
        raise CampaignError(
            "synthetic results must be under campaign/results/synthetic-validation/<run-id>"
        )
    if run_dir.name in {"", ".", ".."}:
        raise CampaignError("invalid synthetic run ID")


class CampaignDispatcher:
    """Owns suite order authority; adapters never select or advance trials."""

    def __init__(
        self,
        run_id: str,
        adapters: Mapping[str, Any],
        results_root: Path = SYNTHETIC_RESULTS_DIR,
        provenance_report: Dict[str, Any] | None = None,
    ):
        if "/" in run_id or run_id in {"", ".", ".."}:
            raise CampaignError(f"invalid run ID: {run_id!r}")
        self.run_id = run_id
        self.run_dir = Path(results_root) / run_id
        _ensure_synthetic_run_path(self.run_dir)
        self.order = load_sealed_order()
        self.registry = load_runner_registry()
        self.adapters = dict(adapters)
        self.provenance = provenance_report or validate_provenance()
        if self.provenance.get("status") != "PASS":
            raise CampaignError("campaign provenance did not pass")
        self.journal = CampaignJournal(self.run_dir / "journal")
        self.artifacts_dir = self.run_dir / "attempt-artifacts"
        self.execution_lock_path = self.run_dir / ".campaign-execution.lock"
        self._cached_records = []
        self._initialize_or_resume()

    def _manifest_payload(self) -> Dict[str, Any]:
        return {
            "manifest_type": "E2_E5_synthetic_campaign_run_v1",
            "run_id": self.run_id,
            "created_at_utc": utc_now(),
            "dataset_class": DATASET_CLASS,
            "accepted_formal_result": False,
            "result_notice": NOT_FORMAL_RESULT,
            "formal_cursor_consumed": False,
            "formal_cursor_state_before": _formal_cursor_snapshot(),
            "source_preflight_commit": SOURCE_PREFLIGHT_COMMIT,
            "baseline_tag": BASELINE_TAG,
            "baseline_commit": BASELINE_COMMIT,
            "sealed_hashes": {
                "formal_preflight_v1_yaml_sha256": PREFLIGHT_SHA256,
                "canonical_policy_sha256": CANONICAL_POLICY_SHA256,
                "global_seed_registry_sha256": GLOBAL_REGISTRY_SHA256,
                "simulation_trial_order_v1_yaml_sha256": ORDER_YAML_SHA256,
                "simulation_trial_order_v1_txt_sha256": ORDER_TXT_SHA256,
            },
            "campaign_infrastructure_commit": self.provenance["campaign_infrastructure_commit"],
            "campaign_infrastructure_source_hashes": self.provenance[
                "campaign_infrastructure_source_hashes"
            ],
            "runner_registry_sha256": registry_sha256(self.registry),
            "formal_runner_registry": self.registry,
            "synthetic_adapter_policy": "deterministic-mixed-outcomes-v1",
            "authoritative_state": "append-only hash-chained suite journal",
            "population_count": len(self.order),
        }

    def _initialize_or_resume(self) -> None:
        manifest_path = self.run_dir / "campaign_run_manifest.json"
        existed = self.run_dir.exists()
        if existed and not manifest_path.exists():
            raise CampaignError(f"existing run directory lacks manifest; recovery required: {self.run_dir}")
        if not existed:
            self.run_dir.mkdir(parents=True, exist_ok=False)
            write_json_exclusive(manifest_path, self._manifest_payload())
            write_json_exclusive(self.run_dir / "provenance_manifest.json", self.provenance)
        manifest = load_json(manifest_path)
        required = {
            "run_id": self.run_id,
            "dataset_class": DATASET_CLASS,
            "accepted_formal_result": False,
            "result_notice": NOT_FORMAL_RESULT,
            "formal_cursor_consumed": False,
            "population_count": 610,
            "runner_registry_sha256": registry_sha256(self.registry),
        }
        mismatches = {key: (manifest.get(key), value) for key, value in required.items()
                      if manifest.get(key) != value}
        if mismatches:
            raise CampaignError(f"run manifest mismatch: {mismatches}")
        if manifest.get("sealed_hashes", {}).get("simulation_trial_order_v1_txt_sha256") != ORDER_TXT_SHA256:
            raise CampaignError("run manifest sealed order hash mismatch")
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.validate_state()

    def _runner_provenance(self, family: str) -> Dict[str, Any]:
        source = CAMPAIGN_DIR / "mock_runners.py"
        return {
            "adapter_kind": "synthetic_mock_only",
            "adapter_entrypoint": source.relative_to(CAMPAIGN_DIR.parents[2]).as_posix(),
            "adapter_source_sha256": sha256_file(source),
            "adapter_commit": self.provenance["campaign_infrastructure_commit"],
            "registered_formal_runner": self.registry["runners"][family],
        }

    def validate_state(self) -> Dict[str, Any]:
        temporary = sorted(path.as_posix() for path in self.run_dir.rglob("*.tmp-*"))
        if temporary:
            raise CampaignError(f"incomplete temporary files require recovery: {temporary}")
        records = self.journal.read()
        if len(records) > len(self.order):
            raise CampaignError("journal is longer than sealed permutation")
        referenced = set()
        trial_ids = []
        for position, record in enumerate(records, start=1):
            expected_trial = self.order[position - 1]
            expected_family = family_for_trial(expected_trial)
            if record.get("global_position") != position or record.get("trial_id") != expected_trial:
                raise CampaignError(f"journal is not exact sealed prefix at position {position}")
            if record.get("experiment") != expected_family:
                raise CampaignError(f"incorrect runner routing at position {position}")
            if record.get("attempt_status") not in ATTEMPT_STATUSES:
                raise CampaignError(f"invalid attempt status at position {position}")
            if (record.get("dataset_class") != DATASET_CLASS
                    or record.get("accepted_formal_result") is not False
                    or record.get("result_notice") != NOT_FORMAL_RESULT):
                raise CampaignError(f"non-synthetic labels at position {position}")
            relative = record.get("artifact_path")
            expected_relative = f"attempt-artifacts/{position:06d}-attempt.json"
            if relative != expected_relative or relative in referenced:
                raise CampaignError(f"artifact reference mismatch/duplicate at position {position}")
            referenced.add(relative)
            artifact_path = self.run_dir / relative
            if not artifact_path.is_file() or sha256_file(artifact_path) != record.get("artifact_sha256"):
                raise CampaignError(f"missing or hash-mismatched retained artifact at position {position}")
            artifact = load_json(artifact_path)
            identity = (artifact.get("global_position"), artifact.get("trial_id"),
                        artifact.get("experiment"), artifact.get("attempt_status"))
            if identity != (position, expected_trial, expected_family, record["attempt_status"]):
                raise CampaignError(f"retained artifact identity mismatch at position {position}")
            if (artifact.get("dataset_class") != DATASET_CLASS
                    or artifact.get("accepted_formal_result") is not False
                    or artifact.get("result_notice") != NOT_FORMAL_RESULT
                    or artifact.get("replacement_attempt") is not False):
                raise CampaignError(f"retained artifact labels/replacement mismatch at position {position}")
            trial_ids.append(expected_trial)
        if len(trial_ids) != len(set(trial_ids)):
            raise CampaignError("duplicate trial in suite journal")
        actual_artifacts = {
            path.relative_to(self.run_dir).as_posix()
            for path in self.artifacts_dir.iterdir()
            if path.is_file() and ARTIFACT_NAME.fullmatch(path.name)
        }
        unexpected_files = [path.name for path in self.artifacts_dir.iterdir()
                            if path.is_file() and not ARTIFACT_NAME.fullmatch(path.name)]
        orphans = sorted(actual_artifacts - referenced)
        missing = sorted(referenced - actual_artifacts)
        if orphans or missing or unexpected_files:
            raise CampaignError(
                f"artifact recovery required: orphan={orphans}, missing={missing}, "
                f"unexpected={unexpected_files}"
            )
        self._cached_records = records
        return {
            "retained_count": len(records),
            "next_position": len(records) + 1 if len(records) < len(self.order) else None,
            "complete": len(records) == len(self.order),
            "status_counts": dict(Counter(record["attempt_status"] for record in records)),
        }

    def _state_for_dispatch(self) -> Dict[str, Any]:
        """Reuse a locked verified prefix unless external state changed."""
        record_count = len(self.journal.record_files())
        artifact_count = sum(
            1 for path in self.artifacts_dir.iterdir()
            if path.is_file() and ARTIFACT_NAME.fullmatch(path.name)
        )
        temporary_exists = any(self.run_dir.rglob("*.tmp-*"))
        if (record_count != len(self._cached_records)
                or artifact_count != len(self._cached_records)
                or temporary_exists):
            return self.validate_state()
        records = self._cached_records
        return {
            "retained_count": len(records),
            "next_position": len(records) + 1 if len(records) < len(self.order) else None,
            "complete": len(records) == len(self.order),
            "status_counts": dict(Counter(record["attempt_status"] for record in records)),
        }

    def reject_selector(self, selector: str) -> None:
        raise CampaignError(
            f"selector {selector!r} forbidden: dispatcher may execute only the global next trial"
        )

    def dispatch_next(self, requested_trial_id: str | None = None) -> Dict[str, Any]:
        with CampaignExecutionLock(self.execution_lock_path):
            state = self._state_for_dispatch()
            position = state["next_position"]
            if position is None:
                raise CampaignError("sealed 610-attempt campaign is already complete")
            trial_id = self.order[position - 1]
            if requested_trial_id is not None and requested_trial_id != trial_id:
                raise CampaignError(
                    f"requested trial is not global next: requested={requested_trial_id}, next={trial_id}"
                )
            family = family_for_trial(trial_id)
            adapter = self.adapters.get(family)
            if adapter is None:
                raise CampaignError(
                    f"global next runner {family} unavailable at position {position}; skipping is forbidden"
                )
            artifact_path = self.artifacts_dir / f"{position:06d}-attempt.json"
            runner_provenance = self._runner_provenance(family)
            context = {
                "run_id": self.run_id,
                "run_dir": self.run_dir,
                "global_position": position,
                "exact_trial_id": trial_id,
                "artifact_path": artifact_path,
                "runner_provenance": runner_provenance,
                "sealed_provenance": {
                    "source_preflight_commit": SOURCE_PREFLIGHT_COMMIT,
                    "baseline_tag": BASELINE_TAG,
                    "baseline_commit": BASELINE_COMMIT,
                    "canonical_policy_sha256": CANONICAL_POLICY_SHA256,
                    "global_seed_registry_sha256": GLOBAL_REGISTRY_SHA256,
                    "simulation_trial_order_yaml_sha256": ORDER_YAML_SHA256,
                    "simulation_trial_order_txt_sha256": ORDER_TXT_SHA256,
                    "runner_registry_sha256": registry_sha256(self.registry),
                },
            }
            try:
                descriptor = adapter.run_exact_trial(trial_id, context)
            except (RunnerRefusalError, TimeoutError, Exception) as exc:
                if artifact_path.exists():
                    raise CampaignError(
                        "adapter raised after publishing an artifact; orphan recovery required"
                    ) from exc
                if isinstance(exc, RunnerRefusalError):
                    transport_status = "runner_refusal"
                elif isinstance(exc, TimeoutError):
                    transport_status = "timeout"
                else:
                    transport_status = "infrastructure_failure"
                failure_artifact = {
                    "record_type": "global_campaign_synthetic_attempt_v1",
                    "dataset_class": DATASET_CLASS,
                    "accepted_formal_result": False,
                    "result_notice": NOT_FORMAL_RESULT,
                    "global_position": position,
                    "trial_id": trial_id,
                    "experiment": family,
                    "attempt_status": transport_status,
                    "replacement_attempt": False,
                    "classification_scope": "campaign_transport_only",
                    "scientific_failure_semantics_modified": False,
                    "runner_exception": {
                        "type": type(exc).__name__,
                        "module": type(exc).__module__,
                        "message": str(exc),
                    },
                    "runner": runner_provenance,
                    "sealed_provenance": context["sealed_provenance"],
                }
                write_json_exclusive(artifact_path, failure_artifact)
                descriptor = {
                    "trial_id": trial_id,
                    "experiment": family,
                    "attempt_status": transport_status,
                    "artifact_path": artifact_path.relative_to(self.run_dir).as_posix(),
                    "artifact_sha256": sha256_file(artifact_path),
                    "runner_provenance": runner_provenance,
                }
            if descriptor.get("trial_id") != trial_id or descriptor.get("experiment") != family:
                raise CampaignError("runner descriptor identity mismatch")
            if descriptor.get("attempt_status") not in ATTEMPT_STATUSES:
                raise CampaignError("runner descriptor has invalid status")
            expected_relative = artifact_path.relative_to(self.run_dir).as_posix()
            if descriptor.get("artifact_path") != expected_relative:
                raise CampaignError("runner descriptor artifact path mismatch")
            if not artifact_path.is_file() or sha256_file(artifact_path) != descriptor.get("artifact_sha256"):
                raise CampaignError("runner did not return a completely retained artifact")
            record = self.journal.append({
                "record_type": "global_campaign_suite_journal_attempt_v1",
                "dataset_class": DATASET_CLASS,
                "accepted_formal_result": False,
                "result_notice": NOT_FORMAL_RESULT,
                "global_position": position,
                "trial_id": trial_id,
                "experiment": family,
                "attempt_status": descriptor["attempt_status"],
                "replacement_attempt": False,
                "artifact_path": expected_relative,
                "artifact_sha256": descriptor["artifact_sha256"],
                "runner_provenance": descriptor["runner_provenance"],
            }, prior_records=self._cached_records)
            self._cached_records = [*self._cached_records, record]
            return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synthetic-validation", action="store_true", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--trial-id", help="must exactly equal the derived global next trial")
    parser.add_argument("--selector", help="always rejected (for example, 'next E2')")
    args = parser.parse_args()
    from mock_runners import build_mock_adapters
    dispatcher = CampaignDispatcher(args.run_id, build_mock_adapters())
    if args.selector:
        dispatcher.reject_selector(args.selector)
    record = dispatcher.dispatch_next(args.trial_id)
    print(json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
