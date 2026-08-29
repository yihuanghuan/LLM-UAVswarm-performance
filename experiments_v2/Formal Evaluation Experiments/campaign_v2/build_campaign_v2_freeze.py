#!/usr/bin/env python3
"""Build deterministic Campaign-v2 pin inventory and immutable manifest."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

from campaign_v2_common import HERE, FORMAL_EVAL, REPO_ROOT, canonical_sha256, sha256_file


WORKSPACE = REPO_ROOT.parent
COMMON_PRODUCTION = [
    "lfs_policy/config/lfs_policy.paper_current.yaml",
    "location_allocate/location_allocate/execution_profile_compiler.py",
    "location_allocate/location_allocate/motion_limits.py",
    "location_allocate/location_allocate/timing_resolution.py",
    "location_allocate/location_allocate/safety_aware_allocator.py",
]
CONFIG = {
    "E2": {
        "checkout": WORKSPACE / "e2_adapter_worktree", "branch": "formal/E2-formal-adapter-v1",
        "head": "c361d21360252b4b6d24a615c421825b40ae1c59", "source": "c361d21360252b4b6d24a615c421825b40ae1c59",
        "tool_dir": "experiments_v2/Formal Evaluation Experiments/E2/tooling",
        "entrypoint": "experiments_v2/Formal Evaluation Experiments/E2/tooling/e2_formal_adapter.py",
        "protocol": "9ea7234db111b69cccb72315eed26e4abf117955eb20a2d593f2d854ea0b40e3",
        "registry": "8215a5d8248c946c480ca4c8cb41e2afac28e6021c9f308a068580da69369bae",
        "extra": [],
    },
    "E3": {
        "checkout": WORKSPACE / "campaign_v2_pinned_worktrees/e3_source", "branch": "formal/E3-protocol-v3-active",
        "head": "fe1f06ea8cd30f2846afa47294169c556ade1926", "source": "fe1f06ea8cd30f2846afa47294169c556ade1926",
        "activation_commit": "16de9c7ffd83b67925fc5817f33665727ccbb75f",
        "tool_dir": "experiments_v2/Formal Evaluation Experiments/E3/tooling",
        "entrypoint": "experiments_v2/Formal Evaluation Experiments/E3/tooling/e3_formal_adapter.py",
        "protocol": "2eea03e2bb33aa1c10c1ae104b965f909690f00c8caee4446291faf2c9893013",
        "registry": "b56344c6cd257e99851523d640d9a89d6def994884877e2303d8fab836e0faf2",
        "extra": ["experiments-legacy/system_8uav/scripts/wait_swarm_ready.py",
                  "experiments_v2/Formal Evaluation Experiments/harness/e3_wrench_driver.py"],
        "declared_bundle_sha256": "2f3ee3619914895d8dfe7530a528281204a9d4c01ee2537fae62e135d66f6dda",
        "declared_bundle_files": [
            "experiments-legacy/system_8uav/scripts/wait_swarm_ready.py",
            "experiments_v2/Formal Evaluation Experiments/E3/tooling/e3_formal_adapter.py",
            "experiments_v2/Formal Evaluation Experiments/E3/tooling/e3_formal_backend.py",
            "experiments_v2/Formal Evaluation Experiments/E3/tooling/e3_physical_trial.py",
            "experiments_v2/Formal Evaluation Experiments/E3/tooling/e3_runtime_diagnostics.py",
            "experiments_v2/Formal Evaluation Experiments/E3/tooling/e3_trial_registry.py",
            "experiments_v2/Formal Evaluation Experiments/E3/tooling/e3_wrench_compat.py",
            "experiments_v2/Formal Evaluation Experiments/harness/e3_wrench_driver.py",
        ],
    },
    "E4A": {
        "checkout": WORKSPACE / "campaign_v2_pinned_worktrees/e4a_source", "branch": "formal/E4A-formal-adapter-v1",
        "head": "7ca02a1bc079f1f36d4bb9a4f29344fcae54a059", "source": "7ca02a1bc079f1f36d4bb9a4f29344fcae54a059",
        "tool_dir": "experiments_v2/Formal Evaluation Experiments/E4/tooling_e4a",
        "entrypoint": "experiments_v2/Formal Evaluation Experiments/E4/tooling_e4a/e4a_formal_adapter.py",
        "protocol": "5a7eeb923aebcfb068827c6513a37e856dc8d6f05166a4b84775b33572bd83d0",
        "registry": "48779a6667759955dd7dab2d8509f61a5439cca51a4bf98fcb48b6d17c499f95",
        "extra": ["experiments_v2/Calibration Experiments/C0-F-motion-style/results/C0-F_motion_style_freeze/frozen_motion_style_policy.yaml"],
    },
    "E4B": {
        "checkout": WORKSPACE / "campaign_v2_pinned_worktrees/e4b_source", "branch": "formal/E4B-formal-adapter-v1",
        "head": "71451469a2cd8cdd375977636beb0b906b6e94e1", "source": "71451469a2cd8cdd375977636beb0b906b6e94e1",
        "tool_dir": "experiments_v2/Formal Evaluation Experiments/E4/tooling_e4b",
        "entrypoint": "experiments_v2/Formal Evaluation Experiments/E4/tooling_e4b/e4b_formal_adapter.py",
        "protocol": "5a7eeb923aebcfb068827c6513a37e856dc8d6f05166a4b84775b33572bd83d0",
        "registry": "48779a6667759955dd7dab2d8509f61a5439cca51a4bf98fcb48b6d17c499f95",
        "extra": [],
    },
    "E5": {
        "checkout": WORKSPACE / "campaign_v2_pinned_worktrees/e5_source", "branch": "formal/E5-formal-adapter-v1",
        "head": "6abaf2b53136d2d5e4d64cde8b9c9acb72ab2485", "source": "6abaf2b53136d2d5e4d64cde8b9c9acb72ab2485",
        "tool_dir": "experiments_v2/Formal Evaluation Experiments/E5/tooling",
        "entrypoint": "experiments_v2/Formal Evaluation Experiments/E5/tooling/e5_formal_adapter.py",
        "protocol": "116002154cd2395b6a9f55d7c1aae6e0a2c42440f0ceaa827a1a8cb02828319c",
        "registry": "9bb6bc9b46b5211c50c8f2e29bd434235424beb2bb0fc36ec857a3298d89511e",
        "extra": [
            "experiments_v2/Formal Evaluation Experiments/llm_runtime_manifest_v1.yaml",
            "location_allocate/location_allocate/candidate_dispatch.py",
            "location_allocate/location_allocate/late_resolution.py",
            "location_allocate/location_allocate/paper_candidate_parser.py",
            "location_allocate/location_allocate/paper_runtime.py",
            "location_allocate/location_allocate/prompt_loader.py",
            "location_allocate/prompts/paper_candidate_en_v2_fewshot.json",
            "location_allocate/prompts/paper_candidate_en_v2_system.txt",
            "schemas/paper_candidate_schema_v2.json",
        ],
    },
}


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def build_inventory() -> dict:
    families = {}
    for family, config in CONFIG.items():
        root = config["checkout"]
        tracked = git(root, "ls-files", config["tool_dir"]).splitlines()
        files = sorted({p for p in tracked if p.endswith(".py")} | set(COMMON_PRODUCTION) | set(config["extra"]))
        hashes = {path: sha256_file(root / path) for path in files}
        item = {
            "checkout_path": str(root), "checkout_branch": config["branch"],
            "checkout_head": config["head"], "execution_source_commit": config["source"],
            "adapter_entrypoint": config["entrypoint"], "protocol_sha256": config["protocol"],
            "registry_sha256": config["registry"], "execution_bundle_files": files,
            "execution_file_sha256": hashes, "execution_bundle_sha256": canonical_sha256(hashes),
        }
        if "activation_commit" in config:
            item["protocol_activation_commit"] = config["activation_commit"]
        if "declared_bundle_sha256" in config:
            declared = {path: sha256_file(root / path) for path in config["declared_bundle_files"]}
            if canonical_sha256({"schema": "e3_execution_tooling_bundle_v1", "files": declared}) != config["declared_bundle_sha256"]:
                raise RuntimeError("E3 adapter-declared execution bundle mismatch")
            item["adapter_declared_bundle"] = {
                "schema": "e3_execution_tooling_bundle_v1", "files": declared,
                "bundle_sha256": config["declared_bundle_sha256"],
            }
        families[family] = item
    result = {"schema": "campaign_v2_pin_inventory_v1", "families": families}
    result["canonical_inventory_sha256"] = canonical_sha256(result)
    return result


def build_manifest(inventory: dict) -> dict:
    environment_manifest = FORMAL_EVAL / "simulation_environment_manifest_v1.yaml"
    build_lock = FORMAL_EVAL / "environment/workspace_build_lock_v1.yaml"
    return {
        "schema": "campaign_v2_immutable_launch_manifest_v1",
        "campaign_id": "E2-E5-final-paper-campaign-v2", "campaign_version": 2,
        "scientific_use": "final_paper_evaluation", "formal_campaign_started": False,
        "baseline_tag": "paper-final-sim-v3", "baseline_commit": "6cf402debf23851b1eff3edc6f3ab49eae7127c4",
        "policy_sha256": "6b47d27f4253d7311e79ea51f6dd1cf0d0182e6df24374a94abae0aa6a135858",
        "family_pins": {family: {
            "checkout_branch": item["checkout_branch"], "checkout_head": item["checkout_head"],
            "execution_source_commit": item["execution_source_commit"],
            "execution_bundle_sha256": item["execution_bundle_sha256"],
            "protocol_sha256": item["protocol_sha256"], "registry_sha256": item["registry_sha256"],
        } for family, item in inventory["families"].items()},
        "E2_preserved_scorer_commit": "c361d21360252b4b6d24a615c421825b40ae1c59",
        "E2_preserved_scorer_sha256": "7b7725a6cba5fc3ba89636db5a87d2f26a65bfc8c85e764dfd16dfa7f4cfc48a",
        "analysis_branch": "formal/analysis-v1",
        "analysis_freeze_audit_head": "023bf48e521e3a6d2383da4699d8820dcf603da7",
        "analysis_tooling_source_commit": "5546e2b673e3368574c2118ecc1943fab382f745",
        "analysis_semantics_sha256": "f19440262a96d784177e5367e8de2a2ec50b7b6ca5b229d4a6d09816408c0db3",
        "formal_analysis_bundle_sha256": "9210245b12a108447cf03715ca6fd90e6ad3bf85fcab7a61e4dcfc6e5ac545b4",
        "global_seed_registry_sha256": "90313d33793940489edde631d397564378ae54fe3cfddf438e4a895d6132254d",
        "global_610_order_sha256": "db28bf8d734e1f206987519e91ff27c67b2d9ab2971aeb68c4e13735762f1dce",
        "population": {"E2": 120, "E3": 360, "E4A": 45, "E4B": 60, "E5": 25, "total": 610},
        "pin_inventory_sha256": inventory["canonical_inventory_sha256"],
        "numeric_environment": {"python": "3.10.12", "numpy": "1.24.4", "scipy": "1.8.0"},
        "runtime_environment": {
            "simulation_environment_manifest_sha256": sha256_file(environment_manifest),
            "workspace_build_lock_sha256": sha256_file(build_lock), "os": "Ubuntu 22.04.5 LTS",
            "kernel": "6.8.0-138-generic", "architecture": "x86_64", "ros_distribution": "humble",
            "rmw_implementation": "rmw_fastrtps_cpp", "rmw_package_version": "6.2.9",
            "ROS_DOMAIN_ID": 42, "gazebo": "Gazebo Classic 11.10.2",
            "px4_commit": "30e763b6780061d70a14894e3e8b06e6a656f9b8",
            "gazebo_classic_submodule_commit": "da7206e057703cc645770f02437013358b71e1c0",
            "formal_install_prefix": "/home/yihuang/learning/LLM_swarm_ws/formal_install_v1",
        },
        "provider": {
            "name": "MiniMax", "base_url": "https://api.minimax.chat/v1",
            "exact_model_name": "MiniMax-M2.7-highspeed",
            "llm_runtime_manifest_sha256": "2760697ad2230e335f7955f67b2cac2f4b6d44487743ef760ac6754cb12a3a14",
            "prompt_sha256": "ed9e83e971d05f034065f82298599463d9d3e20f6b79e508f68233da79b0c4da",
            "fewshot_sha256": "385ab2d0d99bc51c3862c289e28a9a95fa0bd5df1436b68bd0ebf30bb5a83958",
            "schema_sha256": "be6063a533f05b8d0b6e87353a40fb294975261fa1514cd5d34ced19ce2bffe7",
            "retry_policy": "frozen runtime manifest; no campaign-level replacement retry",
        },
        "journal_policy": {
            "authority": "append-only suite journal", "derive_next_from_retained_length": True,
            "cursor_txt_is_not_authoritative": True, "replacement_attempts_forbidden": True,
            "pre_dispatch_failure_consumes_position": False,
            "terminal_retained_statuses_consume_position": ["success", "method_failure", "timeout", "infrastructure_failure"],
            "analysis_failure_after_retention": "advance then pause; preserve raw evidence; never re-execute",
        },
        "failure_accounting_policy": "all retained dispatched attempts remain in registered all-attempt denominator; infrastructure and method outcomes remain distinct",
        "operational_pause_policy": {
            "P0": "one protocol/provenance/order/environment/root-integrity violation => immediate hard pause",
            "P1": "one confirmed provider capacity failure => pre-dispatch no consume; retained dispatch advances then pauses; non-formal health recovery required",
            "P2": "pause after two consecutive infrastructure/operational failures globally or within one family",
            "P3": "pause after three consecutive operational failures where applicable",
        },
        "restart_resume_semantics": "validate manifest, order, pins, journal prefix and retained artifact hashes; derive next as retained_count+1",
        "campaign_v1_supersession_reference": "campaign_v1_supersession_record.json",
        "campaign_v1_used_for_final_scientific_analysis": False,
        "E3_campaign_v2_epoch": "single final E3-v3 implementation from position 1; no Campaign-v1 epoch replay",
        "formal_dispatch_requires_independent_human_runtime_token": True,
    }


def main() -> int:
    inventory = build_inventory()
    write(HERE / "campaign_v2_pin_inventory.json", inventory)
    manifest = build_manifest(inventory)
    write(HERE / "campaign_v2_manifest.json", manifest)
    (HERE / "campaign_v2_manifest.sha256").write_text(sha256_file(HERE / "campaign_v2_manifest.json") + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
