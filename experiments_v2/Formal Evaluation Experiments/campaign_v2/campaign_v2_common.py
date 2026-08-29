"""Fail-closed shared primitives for Campaign v2."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable


HERE = Path(__file__).resolve().parent
FORMAL_EVAL = HERE.parent
REPO_ROOT = FORMAL_EVAL.parents[1]
WORKSPACE = REPO_ROOT.parent
ORDER_PATH = FORMAL_EVAL / "simulation_trial_order_v1.txt"
REGISTRY_PATH = FORMAL_EVAL / "e2_e5_scenario_seed_registry_v1.yaml"
MANIFEST_PATH = HERE / "campaign_v2_manifest.json"
MANIFEST_SHA_PATH = HERE / "campaign_v2_manifest.sha256"
PIN_INVENTORY_PATH = HERE / "campaign_v2_pin_inventory.json"
FORMAL_ROOT = HERE / "results" / "formal"
REHEARSAL_ROOT = HERE / "results" / "synthetic-validation"

ORDER_SHA256 = "db28bf8d734e1f206987519e91ff27c67b2d9ab2971aeb68c4e13735762f1dce"
GLOBAL_REGISTRY_SHA256 = "90313d33793940489edde631d397564378ae54fe3cfddf438e4a895d6132254d"
POLICY_SHA256 = "6b47d27f4253d7311e79ea51f6dd1cf0d0182e6df24374a94abae0aa6a135858"
ANALYSIS_SEMANTICS_SHA256 = "f19440262a96d784177e5367e8de2a2ec50b7b6ca5b229d4a6d09816408c0db3"
ANALYSIS_BUNDLE_SHA256 = "9210245b12a108447cf03715ca6fd90e6ad3bf85fcab7a61e4dcfc6e5ac545b4"
EXPECTED_COUNTS = {"E2": 120, "E3": 360, "E4A": 45, "E4B": 60, "E5": 25}
TERMINAL_STATUSES = {"success", "method_failure", "timeout", "infrastructure_failure", "runner_refusal"}
NONFORMAL_LABELS = {
    "dataset_class": "synthetic_validation",
    "accepted_formal_result": False,
    "result_notice": "NOT_FORMAL_RESULT",
    "formal_cursor_consumed": False,
}


class CampaignV2Error(RuntimeError):
    """Any mismatch closes the launch/rehearsal gate."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def canonical_sha256(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def load_json(path: Path) -> dict[str, Any]:
    try:
        result = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CampaignV2Error(f"cannot load {path}: {exc}") from exc
    if not isinstance(result, dict):
        raise CampaignV2Error(f"expected JSON object: {path}")
    return result


def family_for_trial(trial_id: str) -> str:
    for prefix, family in (("E4A-", "E4A"), ("E4B-", "E4B"), ("E2-", "E2"),
                           ("E3-", "E3"), ("E5-", "E5")):
        if trial_id.startswith(prefix):
            return family
    raise CampaignV2Error(f"unregistered trial family: {trial_id}")


def load_order() -> list[str]:
    raw = ORDER_PATH.read_bytes()
    if sha256_bytes(raw) != ORDER_SHA256 or not raw.endswith(b"\n"):
        raise CampaignV2Error("sealed global order hash/termination mismatch")
    ids = raw.decode().splitlines()
    counts = Counter(map(family_for_trial, ids))
    if len(ids) != 610 or len(set(ids)) != 610 or dict(counts) != EXPECTED_COUNTS:
        raise CampaignV2Error(f"sealed population mismatch: {len(ids)}/{len(set(ids))}/{dict(counts)}")
    if sha256_file(REGISTRY_PATH) != GLOBAL_REGISTRY_SHA256:
        raise CampaignV2Error("global seed registry hash mismatch")
    return ids


def validate_manifest() -> dict[str, Any]:
    manifest = load_json(MANIFEST_PATH)
    declared = MANIFEST_SHA_PATH.read_text(encoding="ascii").strip()
    actual = sha256_file(MANIFEST_PATH)
    if declared != actual:
        raise CampaignV2Error(f"Campaign-v2 manifest hash mismatch: {actual}")
    expected = {
        "campaign_id": "E2-E5-final-paper-campaign-v2",
        "campaign_version": 2,
        "global_610_order_sha256": ORDER_SHA256,
        "global_seed_registry_sha256": GLOBAL_REGISTRY_SHA256,
        "policy_sha256": POLICY_SHA256,
        "analysis_semantics_sha256": ANALYSIS_SEMANTICS_SHA256,
        "formal_analysis_bundle_sha256": ANALYSIS_BUNDLE_SHA256,
    }
    bad = [key for key, value in expected.items() if manifest.get(key) != value]
    if bad:
        raise CampaignV2Error(f"manifest frozen identity mismatch: {bad}")
    return manifest


def exclusive_json(path: Path, value: Any) -> None:
    """Durably publish a new file; never overwrite an attempt or journal record."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode() + b"\n"
    temp = path.parent / f".{path.name}.tmp-{os.getpid()}-{os.urandom(6).hex()}"
    descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temp, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temp.exists():
            temp.unlink()


def inventory_hash(paths: Iterable[Path], base: Path) -> tuple[dict[str, str], str]:
    files = {p.relative_to(base).as_posix(): sha256_file(p) for p in sorted(paths) if p.is_file()}
    return files, canonical_sha256(files)
