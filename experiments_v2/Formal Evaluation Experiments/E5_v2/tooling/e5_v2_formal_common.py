"""Shared fail-closed primitives for E5-v2 formal execution infrastructure."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List

from e5_v2_activation_common import ACTIVATION_MANIFEST_PATH
from e5_v2_common import (
    BASELINE_COMMIT,
    E5_DIR,
    ORDER_PATH,
    POLICY_SHA256,
    REGISTRY_PATH,
    REPO_ROOT,
    SEED_REGISTRY_PATH,
    canonical_json_bytes,
    flatten_conditions,
    load_yaml,
    ordered_attempts,
    sha256_bytes,
    sha256_file,
    uav_ids,
)


CONFIG_PATH = E5_DIR / "E5_v2_formal_execution_config.yaml"
ANALYSIS_PATH = E5_DIR / "E5_v2_analysis_contract.md"
CLASSIFICATION_PATH = E5_DIR / "E5_v2_formal_classification_policy_v1.md"
RAW_POLICY_PATH = E5_DIR / "E5_v2_raw_storage_policy_v1.md"
TOOLING_BUNDLE_PATH = E5_DIR / "E5_v2_formal_execution_tooling_bundle.json"
FORMAL_ROOT = E5_DIR / "results/formal_v2"
ATTEMPTS_ROOT = FORMAL_ROOT / "attempts"
JOURNAL_ROOT = FORMAL_ROOT / "campaign_journal"
RAW_LEDGER_ROOT = E5_DIR / "E5_v2_raw_archive_ledger"
EXPECTED_REGISTRY_SHA256 = (
    "e915575f23b1bd83810f3a8e5aa8092806b9076960c5a2f1fc2bb5faa73ad985"
)
EXPECTED_SEED_SHA256 = (
    "1815deba3fab9c756603a358b4a3900b67ffb9bcb3e9f757282ab8894595d0cb"
)
EXPECTED_ORDER_SHA256 = (
    "4ec9ee0e8de0cc4b015bfd3858365fe8bf0a07aeddcb591ab6f91221a7bb8f69"
)
EXPECTED_ANALYSIS_SHA256 = (
    "05802cb32e8dc2f990d9e0144f2cfd118b87228ab0c441578e084aeefc0d008a"
)


class FormalInfrastructureError(RuntimeError):
    """A mismatch that must close the formal launch/campaign gate."""


class EvidenceIntegrityError(FormalInfrastructureError):
    """Raw or compact evidence integrity was lost; campaign must stop."""


def canonical_sha256(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def load_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FormalInfrastructureError(f"cannot load JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise FormalInfrastructureError(f"expected JSON object: {path}")
    return value


def exclusive_json(path: Path, value: Any) -> None:
    """Durably publish one immutable JSON file without overwriting."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(
        value, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True
    ).encode("utf-8") + b"\n"
    temporary = path.parent / f".{path.name}.tmp-{os.getpid()}-{os.urandom(6).hex()}"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def inventory(root: Path) -> List[Dict[str, Any]]:
    root = Path(root)
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(root.rglob("*")) if path.is_file()
    ]


def verify_frozen_identities() -> None:
    expected = {
        REGISTRY_PATH: EXPECTED_REGISTRY_SHA256,
        SEED_REGISTRY_PATH: EXPECTED_SEED_SHA256,
        ORDER_PATH: EXPECTED_ORDER_SHA256,
        ANALYSIS_PATH: EXPECTED_ANALYSIS_SHA256,
        REPO_ROOT / "lfs_policy/config/lfs_policy.paper_current.yaml": POLICY_SHA256,
    }
    mismatches = {
        str(path): sha256_file(path)
        for path, digest in expected.items() if sha256_file(path) != digest
    }
    if mismatches:
        raise FormalInfrastructureError(f"frozen identity mismatch: {mismatches}")


def load_attempt_specs() -> List[Dict[str, Any]]:
    """Compile the 60 exact-order trial specs without executing a command."""
    verify_frozen_identities()
    registry = load_yaml(REGISTRY_PATH)
    conditions = {item["scenario_id"]: item for item in flatten_conditions(registry)}
    specs = []
    for position, attempt in enumerate(ordered_attempts(registry), 1):
        condition = conditions[attempt["scenario_id"]]
        ids = uav_ids(int(attempt["N"]))
        spec = {
            "schema": "E5_v2_formal_trial_spec_v1",
            "campaign_position": position,
            **attempt,
            "uav_ids": ids,
            "exact_command": condition["exact_command"],
            "mission_timeout_s": float(condition["mission_timeout_s"]),
            "candidate_semantic_ground_truth": condition[
                "candidate_semantic_ground_truth"
            ],
            "candidate_ground_truth_sha256": canonical_sha256(
                condition["candidate_semantic_ground_truth"]
            ),
            "registry_sha256": EXPECTED_REGISTRY_SHA256,
            "seed_registry_sha256": EXPECTED_SEED_SHA256,
            "order_sha256": EXPECTED_ORDER_SHA256,
            "analysis_contract_sha256": EXPECTED_ANALYSIS_SHA256,
            "policy_sha256": POLICY_SHA256,
            "production_baseline": BASELINE_COMMIT,
        }
        specs.append(spec)
    if len(specs) != 60 or len({item["attempt_id"] for item in specs}) != 60:
        raise FormalInfrastructureError("formal population is not exactly 60 unique attempts")
    return specs


def runtime_submission(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Return the only payload visible to the real semantic frontend worker."""
    return {
        "schema": "E5_v2_runtime_submission_v1",
        "campaign_position": spec["campaign_position"],
        "attempt_id": spec["attempt_id"],
        "seed": spec["seed"],
        "N": spec["N"],
        "uav_ids": list(spec["uav_ids"]),
        "exact_command": spec["exact_command"],
        "mission_timeout_s": spec["mission_timeout_s"],
        "policy_path": str(
            REPO_ROOT / "lfs_policy/config/lfs_policy.paper_current.yaml"
        ),
    }


def raw_topics(n: int) -> List[str]:
    config = load_yaml(CONFIG_PATH)["raw_capture"]
    topics = list(config["global_topics"])
    for uid in uav_ids(n):
        topics.extend(f"/uav{uid}/{suffix}" for suffix in config["per_uav_suffixes"])
        topics.extend(f"/px4_{uid}/{suffix}" for suffix in config["per_px4_suffixes"])
    return topics


def build_launch_plan(spec: Dict[str, Any], transaction_root: Path) -> Dict[str, Any]:
    """Construct, but never execute, the exact N-dependent process plan."""
    config = load_yaml(CONFIG_PATH)
    runtime = config["runtime"]
    controls = config["controller"]
    ids = uav_ids(int(spec["N"]))
    ids_launch = "[" + ",".join(str(value) for value in ids) + "]"
    px4_root = Path(runtime["px4_root"])
    transaction_root = Path(transaction_root)
    submission_path = transaction_root / "runtime_submission.json"
    semantic_result_path = transaction_root / "semantic_result.json"
    raw_pending = Path(runtime["raw_archive_root"]) / ".pending" / (
        f"{spec['campaign_position']:06d}__{spec['attempt_id']}"
    )
    return {
        "N": spec["N"],
        "uav_ids": ids,
        "environment": {
            "ROS_DOMAIN_ID": str(runtime["ros_domain_id"]),
            "RMW_IMPLEMENTATION": runtime["rmw_implementation"],
            "ROS_HOME": str(transaction_root / "ros_home"),
            "E5_V2_FORMAL_SEED": str(spec["seed"]),
            "E5_V2_ATTEMPT_ID": spec["attempt_id"],
        },
        "agent": ["MicroXRCEAgent", "udp4", "-p", "8888"],
        "sitl": [
            "bash",
            str(px4_root / "Tools/simulation/gazebo-classic/sitl_multiple_run.sh"),
            "-n", str(spec["N"]), "-m", "iris", "-w", "empty",
        ],
        "controllers": [
            "ros2", "launch", "ladrc_controller", "swarm_launch.py",
            f"uav_ids:={ids_launch}",
            f"control_mode:={controls['control_mode']}",
            f"avoidance_mode:={controls['avoidance_mode']}",
            f"iapf_escape_mode:={controls['iapf_escape_mode']}",
            "lfs_policy_file:=" + str(
                REPO_ROOT / "lfs_policy/config/lfs_policy.paper_current.yaml"
            ),
        ],
        "readiness": [
            "/usr/bin/python3",
            str(Path(__file__).with_name("e5_v2_formal_readiness.py")),
            "--uav-ids", ",".join(map(str, ids)),
            "--timeout", str(runtime["readiness_timeout_s"]),
            "--hold", str(runtime["readiness_hold_s"]),
            "--freshness", str(runtime["freshness_timeout_s"]),
            "--minimum-altitude", str(runtime["minimum_altitude_m"]),
            "--speed-tolerance", str(runtime["speed_tolerance_mps"]),
        ],
        "rosbag": [
            "ros2", "bag", "record", "--storage", config["raw_capture"]["storage_id"],
            "-o", str(raw_pending / "rosbag"), *raw_topics(int(spec["N"])),
        ],
        "semantic_worker": [
            runtime["semantic_python"],
            str(Path(__file__).with_name("e5_v2_formal_trial.py")),
            "--runtime-submission", str(submission_path),
            "--output", str(semantic_result_path),
        ],
        "runtime_submission_path": str(submission_path),
        "semantic_result_path": str(semantic_result_path),
        "raw_pending_root": str(raw_pending),
        "topic_count": len(raw_topics(int(spec["N"]))),
    }


def _git(root: Path, *arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=root, text=True).strip()


def verify_runtime_environment() -> Dict[str, Any]:
    """Verify the frozen simulator/install environment before physical effects."""
    import numpy
    import scipy
    import httpx
    import openai

    config = load_yaml(CONFIG_PATH)
    runtime = config["runtime"]
    pins = config["runtime_pins"]
    install = Path(runtime["install_root"])
    px4 = Path(runtime["px4_root"])
    semantic_python = Path(runtime["semantic_python"]).resolve()
    if Path(sys.executable).resolve() != semantic_python:
        raise FormalInfrastructureError(
            f"formal orchestrator must use pinned interpreter {semantic_python}")
    roots = {"install": install, "px4": px4}
    actual_files = {}
    for label in pins["file_sha256"]:
        prefix, relative = label.split("/", 1)
        actual_files[label] = sha256_file(roots[prefix] / relative)
    actual = {
        "python": platform.python_version(),
        "numpy": numpy.__version__,
        "scipy": scipy.__version__,
        "openai": openai.__version__,
        "httpx": httpx.__version__,
        "px4_commit": _git(px4, "rev-parse", "HEAD"),
        "gazebo_submodule_commit": _git(
            px4 / "Tools/simulation/gazebo-classic/sitl_gazebo-classic",
            "rev-parse", "HEAD",
        ),
        "file_sha256": actual_files,
    }
    if any(actual[key] != pins[key] for key in actual):
        raise FormalInfrastructureError(f"formal runtime pin mismatch: {actual}")
    return {"status": "PASS", **actual}


def validate_external_launch_authorization(path: Path) -> Dict[str, Any]:
    """Require a separately supplied launch manifest and non-repository token."""
    authorization = load_yaml(Path(path))
    bundle = load_json(TOOLING_BUNDLE_PATH)
    expected = {
        "schema": "E5_v2_formal_launch_authorization_v1",
        "authorized": True,
        "registry_sha256": EXPECTED_REGISTRY_SHA256,
        "formal_execution_tooling_bundle_sha256": bundle["bundle_sha256"],
        "start_position": 1,
        "continuous_exact_order": True,
    }
    mismatches = {
        key: authorization.get(key)
        for key, value in expected.items() if authorization.get(key) != value
    }
    supplied = os.environ.get("E5_V2_FORMAL_LAUNCH_TOKEN_SHA256")
    if mismatches or supplied != sha256_file(Path(path)):
        raise FormalInfrastructureError(
            f"separate formal launch authorization mismatch: {mismatches}"
        )
    return authorization


def verify_final_tooling_bundle() -> Dict[str, Any]:
    """Verify every frozen execution input against the final bundle manifest."""
    bundle = load_json(TOOLING_BUNDLE_PATH)
    records = bundle.get("files")
    if bundle.get("schema") != "E5_v2_formal_execution_tooling_bundle_v1":
        raise FormalInfrastructureError("final tooling bundle schema mismatch")
    if not isinstance(records, list) or not records:
        raise FormalInfrastructureError("final tooling bundle has no files")
    if canonical_sha256(records) != bundle.get("bundle_sha256"):
        raise FormalInfrastructureError("final tooling bundle aggregate mismatch")
    prohibited = {"e5_v2_engineering_smoke.py", "e5_v2_wait_ready.py"}
    for record in records:
        path = REPO_ROOT / record["path"]
        if path.name in prohibited:
            raise FormalInfrastructureError("engineering smoke entered formal bundle")
        if not path.is_file() or sha256_file(path) != record["sha256"]:
            raise FormalInfrastructureError(f"formal tooling bundle drift: {path}")
    return bundle
