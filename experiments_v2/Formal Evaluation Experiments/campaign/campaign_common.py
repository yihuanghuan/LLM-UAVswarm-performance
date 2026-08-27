"""Shared constants and fail-closed helpers for the global campaign."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List

import yaml


CAMPAIGN_DIR = Path(__file__).resolve().parent
FORMAL_DIR = CAMPAIGN_DIR.parent
REPO_ROOT = FORMAL_DIR.parents[1]
RESULTS_DIR = CAMPAIGN_DIR / "results"
SYNTHETIC_RESULTS_DIR = RESULTS_DIR / "synthetic-validation"
FORMAL_RESULTS_DIR = RESULTS_DIR / "formal"

PREFLIGHT_PATH = FORMAL_DIR / "formal_preflight_v1.yaml"
GLOBAL_REGISTRY_PATH = FORMAL_DIR / "e2_e5_scenario_seed_registry_v1.yaml"
ORDER_YAML_PATH = FORMAL_DIR / "simulation_trial_order_v1.yaml"
ORDER_TXT_PATH = FORMAL_DIR / "simulation_trial_order_v1.txt"
ORDER_GENERATOR_PATH = FORMAL_DIR / "harness" / "generate_simulation_trial_order_v1.py"
POLICY_PATH = REPO_ROOT / "lfs_policy" / "config" / "lfs_policy.paper_current.yaml"
RUNNER_REGISTRY_PATH = CAMPAIGN_DIR / "runner_registry_v1.json"
CAMPAIGN_MANIFEST_PATH = CAMPAIGN_DIR / "campaign_manifest_v1.json"

SOURCE_PREFLIGHT_COMMIT = "36dba68c6b16681ec98500b49c5a83095de4b634"
BASELINE_TAG = "paper-final-sim-v3"
BASELINE_COMMIT = "6cf402debf23851b1eff3edc6f3ab49eae7127c4"
CANONICAL_POLICY_SHA256 = "6b47d27f4253d7311e79ea51f6dd1cf0d0182e6df24374a94abae0aa6a135858"
GLOBAL_REGISTRY_SHA256 = "90313d33793940489edde631d397564378ae54fe3cfddf438e4a895d6132254d"
PREFLIGHT_SHA256 = "c9eb9752000d5023f2986ae13f5bf062db20064f29e04f679e92e58a85a1c5a5"
ORDER_YAML_SHA256 = "6674b6c2e03278e99590c6d3c9df7ada580180b92f24475a42d396972451b254"
ORDER_TXT_SHA256 = "db28bf8d734e1f206987519e91ff27c67b2d9ab2971aeb68c4e13735762f1dce"
CANONICAL_POPULATION_SHA256 = "6e37ae0aa3fa7e24e13f81301c67cdb5dfe3fc24fa148db03d3c680110f081ca"

DATASET_CLASS = "synthetic_validation"
NOT_FORMAL_RESULT = "NOT_FORMAL_RESULT"
ATTEMPT_STATUSES = {
    "success", "method_failure", "infrastructure_failure", "timeout", "runner_refusal"
}
FAMILIES = ("E2", "E3", "E4A", "E4B", "E5")
EXPECTED_COUNTS = {"E2": 120, "E3": 360, "E4A": 45, "E4B": 60, "E5": 25}


class CampaignError(RuntimeError):
    """A fail-closed campaign validation or dispatch error."""


class RunnerRefusalError(RuntimeError):
    """An invoked adapter explicitly refused the exact registered trial."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def load_json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CampaignError(f"cannot read JSON mapping {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CampaignError(f"expected JSON mapping: {path}")
    return value


def load_yaml(path: Path) -> Dict[str, Any]:
    try:
        value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise CampaignError(f"cannot read YAML mapping {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CampaignError(f"expected YAML mapping: {path}")
    return value


def fsync_directory(directory: Path) -> None:
    descriptor = os.open(str(directory), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write_exclusive(path: Path, data: bytes) -> None:
    """Publish a complete immutable file without ever replacing a target."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.tmp-{os.getpid()}-{os.urandom(6).hex()}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(str(temporary), flags, 0o444)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        fsync_directory(path.parent)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise
    else:
        temporary.unlink()
        fsync_directory(path.parent)


def write_json_exclusive(path: Path, value: Any) -> None:
    atomic_write_exclusive(path, json.dumps(
        value, ensure_ascii=False, sort_keys=True, indent=2
    ).encode("utf-8") + b"\n")


def family_for_trial(trial_id: str) -> str:
    for prefix, family in (("E4A-", "E4A"), ("E4B-", "E4B"), ("E2-", "E2"),
                           ("E3-", "E3"), ("E5-", "E5")):
        if trial_id.startswith(prefix):
            return family
    raise CampaignError(f"unrecognized registered trial family: {trial_id}")


def _canonical_population_from_sealed_generator() -> List[str]:
    """Load only canonical_ids(); never invoke the generator's shuffle/main."""
    spec = importlib.util.spec_from_file_location("sealed_trial_order_generator", ORDER_GENERATOR_PATH)
    if spec is None or spec.loader is None:
        raise CampaignError("cannot load sealed order generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ids = list(module.canonical_ids())
    digest = sha256_bytes(("\n".join(ids) + "\n").encode("utf-8"))
    if digest != CANONICAL_POPULATION_SHA256:
        raise CampaignError(f"sealed canonical population hash mismatch: {digest}")
    return ids


def load_sealed_order() -> List[str]:
    order_yaml = load_yaml(ORDER_YAML_PATH)
    global_registry = load_yaml(GLOBAL_REGISTRY_PATH)
    raw = ORDER_TXT_PATH.read_bytes()
    ids = raw.decode("utf-8").splitlines()
    problems: List[str] = []
    hashes = {
        "preflight": (sha256_file(PREFLIGHT_PATH), PREFLIGHT_SHA256),
        "global_registry": (sha256_file(GLOBAL_REGISTRY_PATH), GLOBAL_REGISTRY_SHA256),
        "order_yaml": (sha256_file(ORDER_YAML_PATH), ORDER_YAML_SHA256),
        "order_txt": (sha256_bytes(raw), ORDER_TXT_SHA256),
    }
    problems.extend(f"{name} hash {actual} != {expected}"
                    for name, (actual, expected) in hashes.items() if actual != expected)
    if not raw.endswith(b"\n"):
        problems.append("permutation does not end with LF")
    if len(ids) != 610 or len(set(ids)) != 610:
        problems.append(f"permutation count/unique={len(ids)}/{len(set(ids))}, expected 610/610")
    counts = Counter(family_for_trial(item) for item in ids)
    if dict(counts) != EXPECTED_COUNTS:
        problems.append(f"population breakdown {dict(counts)} != {EXPECTED_COUNTS}")
    canonical = _canonical_population_from_sealed_generator()
    if set(ids) != set(canonical):
        problems.append("permutation population differs from sealed canonical population")
    contract = order_yaml.get("execution_contract", {})
    for key in (
        "complete_permutation_file_is_authoritative", "run_in_generated_order",
        "finish_and_retain_an_attempt_before_advancing", "failed_attempts_are_not_replaced",
        "order_may_not_change_after_any_formal_outcome",
    ):
        if contract.get(key) is not True:
            problems.append(f"sealed execution contract {key} is not true")
    declared = global_registry.get("global_seed_policy", {}).get("deterministic_trial_order_sha256")
    if order_yaml.get("permutation_sha256") != ORDER_TXT_SHA256 or declared != ORDER_TXT_SHA256:
        problems.append("sealed manifests disagree on permutation hash")
    if order_yaml.get("canonical_population_sha256") != CANONICAL_POPULATION_SHA256:
        problems.append("sealed order YAML canonical population hash mismatch")
    if problems:
        raise CampaignError("sealed order validation failed: " + "; ".join(problems))
    return ids


def source_hashes(paths: Iterable[Path]) -> Dict[str, str]:
    return {path.relative_to(REPO_ROOT).as_posix(): sha256_file(path) for path in sorted(paths)}
