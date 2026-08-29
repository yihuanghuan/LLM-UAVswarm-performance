#!/usr/bin/env python3
"""Campaign-v2 coordinator and non-formal rehearsal engine.

The formal dispatch path is deliberately double locked: the frozen authorization
artifact plus a human-supplied, non-repository runtime token are both required.
This freeze/rehearsal module never supplies that token.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import os
import platform
from pathlib import Path
import subprocess
import sys
from typing import Any

from campaign_v2_common import (
    CampaignV2Error, FORMAL_ROOT, HERE, NONFORMAL_LABELS, ORDER_SHA256,
    PIN_INVENTORY_PATH, REHEARSAL_ROOT, TERMINAL_STATUSES, canonical_sha256,
    exclusive_json, family_for_trial, load_json, load_order, sha256_file,
    validate_manifest,
)


WORKER = HERE / "adapter_spec_worker.py"
AUTHORIZATION = HERE / "campaign_v2_launch_authorization.json"
FORMAL_LABELS = {
    "dataset_class": "formal_evaluation",
    "accepted_formal_result": True,
    "result_notice": None,
    "formal_cursor_consumed": True,
}


def validate_runtime_environment(*, require_launch_environment: bool) -> dict[str, Any]:
    """Verify the frozen numerical, simulator, and installed-runtime identity."""
    import numpy
    import scipy
    expected_files = {
        "/home/yihuang/PX4-Autopilot-formal-v1/Tools/simulation/gazebo-classic/sitl_multiple_run.sh": "8365fbae05cb80422c2ad0b475915b8c73277299dfdc30198b378ed0f8a4b91b",
        "/home/yihuang/PX4-Autopilot-formal-v1/Tools/simulation/gazebo-classic/sitl_gazebo-classic/models/iris/iris.sdf.jinja": "2e2cc07782e73a14515bbb739e02f3e593c06bb73c7039f71176c8bcdca2dd96",
        "/home/yihuang/learning/LLM_swarm_ws/formal_install_v1/ladrc_controller/lib/ladrc_controller/ladrc_position_controller_node": "4efd098c79606d275228893feba1211f2c62a53cfe84e6878b96ea47e98986ea",
        "/home/yihuang/learning/LLM_swarm_ws/formal_install_v1/uav_swarm_interfaces/share/uav_swarm_interfaces/msg/UAVExecutionCommand.msg": "10d329b9d8bc859a453ad62cb21a4eae11b1c57b85758d9a4cee1716e07a0058",
        "/home/yihuang/learning/LLM_swarm_ws/formal_install_v1/ladrc_controller/share/ladrc_controller/launch/swarm_launch.py": "eebe0d26d7d6d9408078c99dd735c4076b36eb79f1ebc8d02be64af24d9782dd",
        "/home/yihuang/learning/LLM_swarm_ws/formal_install_v1/lfs_policy/share/lfs_policy/config/lfs_policy.paper_current.yaml": "6b47d27f4253d7311e79ea51f6dd1cf0d0182e6df24374a94abae0aa6a135858",
    }
    files = {path: sha256_file(Path(path)) for path in expected_files}
    px4 = Path("/home/yihuang/PX4-Autopilot-formal-v1")
    gazebo_submodule = px4 / "Tools/simulation/gazebo-classic/sitl_gazebo-classic"
    identity = {
        "python": platform.python_version(), "numpy": numpy.__version__, "scipy": scipy.__version__,
        "px4_commit": _git(px4, "rev-parse", "HEAD"),
        "gazebo_submodule_commit": _git(gazebo_submodule, "rev-parse", "HEAD"),
        "file_sha256": files, "RMW_IMPLEMENTATION": os.getenv("RMW_IMPLEMENTATION"),
        "ROS_DOMAIN_ID": os.getenv("ROS_DOMAIN_ID"),
    }
    ok = (identity["python"] == "3.10.12" and identity["numpy"] == "1.24.4" and
          identity["scipy"] == "1.8.0" and files == expected_files and
          identity["px4_commit"] == "30e763b6780061d70a14894e3e8b06e6a656f9b8" and
          identity["gazebo_submodule_commit"] == "da7206e057703cc645770f02437013358b71e1c0")
    if require_launch_environment:
        ok = ok and identity["RMW_IMPLEMENTATION"] == "rmw_fastrtps_cpp" and identity["ROS_DOMAIN_ID"] == "42"
    identity["status"] = "PASS" if ok else "FAIL"
    if not ok:
        raise CampaignV2Error("frozen production runtime environment mismatch")
    return identity


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def verify_pins() -> dict[str, Any]:
    inventory = load_json(PIN_INVENTORY_PATH)
    details: dict[str, Any] = {}
    for family, pin in inventory["families"].items():
        root = Path(pin["checkout_path"])
        branch = _git(root, "branch", "--show-current")
        head = _git(root, "rev-parse", "HEAD")
        dirty = _git(root, "status", "--porcelain", "--untracked-files=all")
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", pin["execution_source_commit"], head],
            cwd=root, check=False,
        ).returncode == 0
        files = {rel: sha256_file(root / rel) for rel in pin["execution_bundle_files"]}
        bundle = canonical_sha256(files)
        ok = (branch == pin["checkout_branch"] and head == pin["checkout_head"] and
              not dirty and ancestor and files == pin["execution_file_sha256"] and
              bundle == pin["execution_bundle_sha256"])
        details[family] = {
            "status": "PASS" if ok else "FAIL", "checkout": str(root), "branch": branch,
            "head": head, "clean": not dirty, "source_is_ancestor": ancestor,
            "execution_source_commit": pin["execution_source_commit"],
            "execution_bundle_sha256": bundle,
        }
    if not all(item["status"] == "PASS" for item in details.values()):
        raise CampaignV2Error("one or more execution worktree pins failed")
    return {"status": "PASS", "families": details}


class Journal:
    def __init__(self, run_dir: Path):
        self.run_dir = Path(run_dir)
        self.path = self.run_dir / "suite-journal"

    def read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        files = sorted(self.path.glob("*-attempt.json"))
        if [p.name for p in files] != [f"{i:06d}-attempt.json" for i in range(1, len(files) + 1)]:
            raise CampaignV2Error("journal is not a contiguous append-only prefix")
        records = [load_json(path) for path in files]
        previous = None
        for index, record in enumerate(records, 1):
            material = dict(record)
            digest = material.pop("record_sha256", None)
            if record.get("global_position") != index or record.get("previous_record_sha256") != previous:
                raise CampaignV2Error(f"journal chain/index mismatch at {index}")
            if canonical_sha256(material) != digest:
                raise CampaignV2Error(f"journal record hash mismatch at {index}")
            previous = digest
        return records

    def append(self, payload: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
        position = len(records) + 1
        record = {**payload, "previous_record_sha256": records[-1]["record_sha256"] if records else None}
        record["record_sha256"] = canonical_sha256(record)
        exclusive_json(self.path / f"{position:06d}-attempt.json", record)
        return record


class Coordinator:
    def __init__(self, mode: str, run_dir: Path, *,
                 _isolated_formal_test_root: Path | None = None,
                 _isolated_runtime_validator: Any | None = None,
                 _isolated_authorization_path: Path | None = None):
        if mode not in {"rehearsal", "formal"}:
            raise CampaignV2Error("unsupported mode")
        self.mode = mode
        self.run_dir = Path(run_dir).resolve()
        self.order = load_order()
        self.manifest = validate_manifest()
        self.pins = load_json(PIN_INVENTORY_PATH)["families"]
        verify_pins()
        if mode == "rehearsal":
            try:
                self.run_dir.relative_to(REHEARSAL_ROOT.resolve())
            except ValueError as exc:
                raise CampaignV2Error("synthetic rehearsal root escaped isolated non-formal root") from exc
        else:
            formal_root = FORMAL_ROOT.resolve()
            if _isolated_formal_test_root is not None:
                isolated = Path(_isolated_formal_test_root).resolve()
                test_parent = (REHEARSAL_ROOT / "formal-mode-tests").resolve()
                try:
                    isolated.relative_to(test_parent)
                except ValueError as exc:
                    raise CampaignV2Error("isolated formal test root escaped its non-formal test area") from exc
                if (os.getenv("CAMPAIGN_V2_ISOLATED_FORMAL_TEST") != "1" or
                        self.run_dir != isolated):
                    raise CampaignV2Error("isolated formal test injection is not explicitly enabled")
                formal_root = isolated
            if self.run_dir != formal_root:
                raise CampaignV2Error("formal mode may use only Campaign-v2 formal root")
            runtime_validator = _isolated_runtime_validator or validate_runtime_environment
            if _isolated_runtime_validator is not None and _isolated_formal_test_root is None:
                raise CampaignV2Error("runtime-validator injection is restricted to isolated formal tests")
            runtime_validator(require_launch_environment=True)
            authorization_path = _isolated_authorization_path or AUTHORIZATION
            if _isolated_authorization_path is not None and _isolated_formal_test_root is None:
                raise CampaignV2Error("authorization injection is restricted to isolated formal tests")
            self._require_human_authorization(authorization_path)
        self.journal = Journal(self.run_dir)
        self._initialize()
        self.validate_state()

    def _require_human_authorization(self, authorization_path: Path) -> None:
        auth = load_json(authorization_path)
        if auth.get("authorization_status") != "authorized_for_future_human-triggered_formal_launch":
            raise CampaignV2Error("future formal authorization artifact is not valid")
        trigger_path = self.run_dir / "HUMAN_LAUNCH_TRIGGER.json"
        if not trigger_path.is_file():
            raise CampaignV2Error("missing future human launch-trigger artifact")
        trigger = load_json(trigger_path)
        supplied = os.environ.get("CAMPAIGN_V2_HUMAN_LAUNCH_TOKEN_SHA256")
        campaign_authorized = (trigger.get("authorize_campaign_v2") is True or
                               trigger.get("authorize_formal_attempt_1") is True)
        if (not campaign_authorized or
                trigger.get("campaign_manifest_sha256") != sha256_file(HERE / "campaign_v2_manifest.json") or
                supplied != sha256_file(trigger_path)):
            raise CampaignV2Error("independent human runtime launch token/trigger mismatch")

    def _expected_formal_launcher_manifest(self) -> dict[str, Any]:
        return {
            "schema": "campaign_v2_pristine_formal_root_manifest_v1",
            "artifact_class": "formal_campaign_metadata",
            "campaign_id": "E2-E5-final-paper-campaign-v2",
            "campaign_manifest_sha256": sha256_file(HERE / "campaign_v2_manifest.json"),
            "formal_campaign_started": False,
            "retained_formal_attempts": 0,
            "journal_records": 0,
            "accepted_formal_results": 0,
            "next_global_position": 1,
            "next_trial_id": self.order[0],
            "journal_is_cursor_authority": True,
            "formal_dispatch_authorized_in_this_phase": False,
        }

    def _initialize(self) -> None:
        meta = self.run_dir / "launcher_run_manifest.json"
        if self.mode == "formal":
            if not meta.is_file() or meta.is_symlink():
                raise CampaignV2Error("pristine formal root lacks frozen launcher manifest")
            if load_json(meta) != self._expected_formal_launcher_manifest():
                raise CampaignV2Error("frozen formal launcher manifest mismatch")
            return
        if not self.run_dir.exists():
            self.run_dir.mkdir(parents=True)
            exclusive_json(meta, {
                "schema": "campaign_v2_synthetic_rehearsal_manifest_v1", **NONFORMAL_LABELS,
                "campaign_manifest_sha256": sha256_file(HERE / "campaign_v2_manifest.json"),
                "global_order_sha256": ORDER_SHA256,
                "adapter_mode": "actual_pinned_entrypoints_spec_rehearsal",
                "physical_execution_performed": False,
                "real_provider_called": False,
            })
        elif not meta.is_file():
            raise CampaignV2Error("existing rehearsal root has no immutable run manifest")

    def validate_state(self) -> dict[str, Any]:
        temps = list(self.run_dir.rglob("*.tmp-*")) if self.run_dir.exists() else []
        if temps:
            raise CampaignV2Error("partial temporary write requires audited recovery")
        records = self.journal.read()
        if len(records) > len(self.order):
            raise CampaignV2Error("journal exceeds sealed 610-position campaign")
        expected_journal_names = {f"{i:06d}-attempt.json" for i in range(1, len(records) + 1)}
        expected_envelope_names = {f"{i:06d}-attempt.json" for i in range(1, len(records) + 1)}
        expected_adapter_names = {f"{i:06d}" for i in range(1, len(records) + 1)}
        journal_dir = self.run_dir / "suite-journal"
        envelope_dir = self.run_dir / "attempt-artifacts"
        adapter_dir = self.run_dir / "adapter-attempts"
        journal_names = {p.name for p in journal_dir.iterdir()} if journal_dir.exists() else set()
        envelope_names = {p.name for p in envelope_dir.iterdir()} if envelope_dir.exists() else set()
        adapter_names = {p.name for p in adapter_dir.iterdir()} if adapter_dir.exists() else set()
        if journal_names != expected_journal_names:
            raise CampaignV2Error("foreign/duplicate journal artifact; fail-closed recovery required")
        if envelope_names != expected_envelope_names:
            raise CampaignV2Error("orphan/foreign attempt envelope; fail-closed recovery required")
        if adapter_names != expected_adapter_names:
            raise CampaignV2Error("orphan/foreign adapter directory; fail-closed recovery required")
        if any(p.is_symlink() for directory in (journal_dir, envelope_dir, adapter_dir)
               if directory.exists() for p in directory.iterdir()):
            raise CampaignV2Error("symlinked retained artifact is not a durable campaign artifact")
        for position, record in enumerate(records, 1):
            trial = self.order[position - 1]
            family = family_for_trial(trial)
            if record.get("schema") != "campaign_v2_suite_journal_record_v1":
                raise CampaignV2Error(f"journal schema mismatch at {position}")
            if (record.get("trial_id"), record.get("experiment")) != (trial, family):
                raise CampaignV2Error(f"journal is not exact global-order prefix at {position}")
            expected_artifact_path = f"attempt-artifacts/{position:06d}-attempt.json"
            if record.get("artifact_path") != expected_artifact_path:
                raise CampaignV2Error(f"journal artifact path mismatch at {position}")
            if record.get("attempt_status") not in TERMINAL_STATUSES:
                raise CampaignV2Error(f"nonterminal/unknown journal status at {position}")
            labels = NONFORMAL_LABELS if self.mode == "rehearsal" else FORMAL_LABELS
            if any(record.get(k) != v for k, v in labels.items()):
                raise CampaignV2Error(f"journal dataset/formal label mismatch at {position}")
            artifact = self.run_dir / expected_artifact_path
            if not artifact.is_file() or sha256_file(artifact) != record.get("artifact_sha256"):
                raise CampaignV2Error(f"retained artifact missing/hash mismatch at {position}")
            payload = load_json(artifact)
            if payload.get("schema") != "campaign_v2_attempt_envelope_v1":
                raise CampaignV2Error(f"attempt envelope schema mismatch at {position}")
            if (payload.get("global_position"), payload.get("trial_id"), payload.get("experiment")) != (position, trial, family):
                raise CampaignV2Error(f"attempt envelope mismatch at {position}")
            if payload.get("attempt_status") != record.get("attempt_status"):
                raise CampaignV2Error(f"journal/envelope terminal status mismatch at {position}")
            if any(payload.get(k) != v for k, v in labels.items()):
                raise CampaignV2Error(f"attempt envelope dataset/formal label mismatch at {position}")
            expected_adapter_path = f"adapter-attempts/{position:06d}/attempt.json"
            if payload.get("adapter_artifact_path") != expected_adapter_path:
                raise CampaignV2Error(f"adapter artifact path mismatch at {position}")
            adapter = self.run_dir / expected_adapter_path
            if (not adapter.is_file() or adapter.is_symlink() or
                    sha256_file(adapter) != payload.get("adapter_artifact_sha256")):
                raise CampaignV2Error(f"adapter artifact missing/hash mismatch at {position}")
            adapter_payload = load_json(adapter)
            if ((adapter_payload.get("trial_id"), adapter_payload.get("experiment"),
                 adapter_payload.get("global_trial_position")) != (trial, family, position)):
                raise CampaignV2Error(f"adapter artifact identity mismatch at {position}")
            adapter_labels = {"dataset_class": labels["dataset_class"],
                              "accepted_formal_result": labels["accepted_formal_result"],
                              "result_notice": labels["result_notice"]}
            if any(adapter_payload.get(k) != v for k, v in adapter_labels.items()):
                raise CampaignV2Error(f"adapter artifact dataset/formal label mismatch at {position}")
        envelopes = sorted(envelope_dir.glob("*.json")) if envelope_dir.exists() else []
        adapters = sorted(p for p in adapter_dir.glob("*") if p.is_dir()) if adapter_dir.exists() else []
        if len(envelopes) != len(records) or len(adapters) != len(records):
            raise CampaignV2Error("orphan attempt/adapter artifact; fail-closed recovery required")
        return {
            "retained_count": len(records), "next_position": len(records) + 1 if len(records) < 610 else None,
            "next_trial_id": self.order[len(records)] if len(records) < 610 else None,
            "complete": len(records) == 610,
            "status_counts": dict(Counter(r["attempt_status"] for r in records)),
        }

    def reject_family_selector(self, family: str) -> None:
        state = self.validate_state()
        expected = family_for_trial(state["next_trial_id"]) if state["next_trial_id"] else None
        if family != expected:
            raise CampaignV2Error(f"manual {family} invocation refused; sealed global next is {expected}")
        raise CampaignV2Error("direct family dispatch forbidden; use suite dispatcher")

    def _context(self, position: int, trial: str, family: str, output: Path) -> dict[str, Any]:
        pin = self.pins[family]
        adapter_bundle = pin.get("adapter_declared_bundle") or {
            "schema": "campaign_v2_execution_bundle_v1",
            "files": pin["execution_file_sha256"],
            "bundle_sha256": pin["execution_bundle_sha256"],
        }
        return {
            "execution_mode": "spec_rehearsal" if self.mode == "rehearsal" else "formal",
            "dataset_class": "synthetic_validation" if self.mode == "rehearsal" else "formal_evaluation",
            "accepted_formal_result": self.mode == "formal",
            "formal_launch_authorized": self.mode == "formal",
            "launch_gate_status": "REHEARSAL_ONLY" if self.mode == "rehearsal" else "READY_FOR_FORMAL_LAUNCH",
            "trial_id": trial, "global_trial_position": position,
            # Adapters record the exact clean checkout HEAD. The separate
            # execution_source_commit identifies the last semantics-relevant
            # code change and is ancestry/hash gated by Campaign v2.
            "runner_commit": pin["checkout_head"],
            "runner_source_sha256": pin["execution_file_sha256"][pin["adapter_entrypoint"]],
            "runner_execution_tooling_bundle_schema": adapter_bundle["schema"],
            "runner_execution_tooling_file_sha256": adapter_bundle["files"],
            "runner_execution_tooling_bundle_sha256": adapter_bundle["bundle_sha256"],
            "policy_sha256": self.manifest["policy_sha256"],
            "protocol_sha256": pin["protocol_sha256"], "registry_sha256": pin["registry_sha256"],
            "global_trial_order_sha256": ORDER_SHA256, "attempt_output_dir": str(output),
        }

    def dispatch_next(self, *, requested_trial_id: str | None = None,
                      synthetic_terminal_status: str | None = None) -> dict[str, Any]:
        state = self.validate_state()
        position = state["next_position"]
        if position is None:
            raise CampaignV2Error("campaign rehearsal complete")
        trial = self.order[position - 1]
        if requested_trial_id is not None and requested_trial_id != trial:
            raise CampaignV2Error(f"requested trial {requested_trial_id} is not global next {trial}")
        family = family_for_trial(trial)
        output = self.run_dir / "adapter-attempts" / f"{position:06d}"
        envelope_path = self.run_dir / "attempt-artifacts" / f"{position:06d}-attempt.json"
        if output.exists() or envelope_path.exists():
            raise CampaignV2Error("duplicate/orphan output exists")
        context_path = self.run_dir / f".context-{position:06d}.json"
        exclusive_json(context_path, self._context(position, trial, family, output))
        pin = self.pins[family]
        try:
            completed = subprocess.run([
                sys.executable, str(WORKER), "--checkout", pin["checkout_path"],
                "--entrypoint", pin["adapter_entrypoint"], "--trial-id", trial,
                "--context", str(context_path),
            ], text=True, capture_output=True, check=True)
        finally:
            context_path.unlink(missing_ok=True)
        descriptor = json.loads(completed.stdout.strip().splitlines()[-1])
        adapter_path = Path(descriptor["artifact_path"]).resolve()
        try:
            adapter_relative = adapter_path.relative_to(self.run_dir).as_posix()
        except ValueError as exc:
            raise CampaignV2Error("adapter artifact escaped isolated campaign root") from exc
        if not adapter_path.is_file() or sha256_file(adapter_path) != descriptor.get("artifact_sha256"):
            raise CampaignV2Error("adapter result is not durable/hash matched")
        status = synthetic_terminal_status or descriptor.get("attempt_status")
        if status not in TERMINAL_STATUSES:
            raise CampaignV2Error(f"invalid terminal status: {status}")
        labels = NONFORMAL_LABELS if self.mode == "rehearsal" else FORMAL_LABELS
        envelope = {
            "schema": "campaign_v2_attempt_envelope_v1", **labels,
            "global_position": position, "trial_id": trial, "experiment": family,
            "attempt_status": status, "adapter_reported_status": descriptor.get("attempt_status"),
            "synthetic_terminal_fixture": synthetic_terminal_status,
            "replacement_attempt": False, "physical_execution_performed": False if self.mode == "rehearsal" else None,
            "real_provider_called": False if self.mode == "rehearsal" else None,
            "adapter_artifact_path": adapter_relative,
            "adapter_artifact_sha256": descriptor["artifact_sha256"],
            "execution_source_commit": pin["execution_source_commit"],
            "execution_bundle_sha256": pin["execution_bundle_sha256"],
            "analysis_schema_compatibility": "PASS",
        }
        exclusive_json(envelope_path, envelope)
        envelope_hash = sha256_file(envelope_path)
        records = self.journal.read()
        record = self.journal.append({
            "schema": "campaign_v2_suite_journal_record_v1", **labels,
            "global_position": position, "trial_id": trial, "experiment": family,
            "attempt_status": status, "replacement_attempt": False,
            "artifact_path": envelope_path.relative_to(self.run_dir).as_posix(),
            "artifact_sha256": envelope_hash,
        }, records)
        return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rehearsal-root", type=Path)
    parser.add_argument("--formal", action="store_true")
    parser.add_argument("--trial-id")
    parser.add_argument("--family")
    args = parser.parse_args()
    if args.formal:
        coordinator = Coordinator("formal", FORMAL_ROOT)
    elif args.rehearsal_root:
        coordinator = Coordinator("rehearsal", args.rehearsal_root)
    else:
        raise SystemExit("select --rehearsal-root or --formal")
    if args.family:
        coordinator.reject_family_selector(args.family)
    print(json.dumps(coordinator.dispatch_next(requested_trial_id=args.trial_id), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
