"""Shared, side-effect-free helpers for the E5-v2 candidate protocol."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

import yaml


E5_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[4]
REGISTRY_PATH = E5_DIR / "E5_v2_registry.yaml"
SEED_REGISTRY_PATH = E5_DIR / "E5_v2_seed_registry.yaml"
ORDER_PATH = E5_DIR / "E5_v2_formal_trial_order.txt"
ORDER_METADATA_PATH = E5_DIR / "E5_v2_formal_trial_order_metadata.json"
CANDIDATES_PATH = E5_DIR / "E5_v2_scenario_design_candidates.yaml"
BASELINE_COMMIT = "6cf402debf23851b1eff3edc6f3ab49eae7127c4"
OLD_E5_SOURCE_COMMIT = "33538b91ab9e0c53b918cdc0e47e3b7fa6f08592"
OLD_E5_REGISTRY_PATH = (
    "experiments_v2/Formal Evaluation Experiments/E5/"
    "e5_end_to_end_registry_v1.yaml"
)
OLD_E5_REGISTRY_SHA256 = (
    "9bb6bc9b46b5211c50c8f2e29bd434235424beb2bb0fc36ec857a3298d89511e"
)
POLICY_SHA256 = (
    "6b47d27f4253d7311e79ea51f6dd1cf0d0182e6df24374a94abae0aa6a135858"
)
PRODUCTION_METHOD_PATHS = (
    "lfs_policy",
    "location_allocate",
    "minisnap_LADRC",
    "schemas",
    "uav_swarm_interfaces",
)
FORMAL_SEED_BASE = 5_202_000
FORMAL_ORDER_SEED = 520_260_902


def load_yaml(path: Path) -> Dict[str, Any]:
    """Load one mapping-valued YAML document."""
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected YAML mapping: {path}")
    return value


def canonical_json_bytes(value: Any) -> bytes:
    """Return the protocol's stable UTF-8 JSON representation."""
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def uav_ids(n: int) -> List[int]:
    """Enumerate registered IDs without an eight-UAV special case."""
    if n not in (8, 12, 16):
        raise ValueError("E5-v2 permits only registered N in {8,12,16}")
    return list(range(1, n + 1))


def flatten_conditions(registry: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    """Return the 12 scientific conditions in canonical registry order."""
    registry = registry or load_yaml(REGISTRY_PATH)
    result: List[Dict[str, Any]] = []
    for scenario in registry["scenarios"]["E5-v2A"]:
        result.append({
            "condition_id": scenario["scenario_id"],
            "substudy": "E5-v2A",
            "scenario_id": scenario["scenario_id"],
            "task_family": None,
            **scenario,
        })
    for cell in registry["scenarios"]["E5-v2B"]:
        result.append({
            "condition_id": cell["cell_id"],
            "substudy": "E5-v2B",
            "scenario_id": cell["cell_id"],
            **cell,
        })
    return result


def canonical_attempts(registry: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    """Materialize 60 attempts and assign one unique prospective seed each."""
    attempts: List[Dict[str, Any]] = []
    index = 0
    for condition in flatten_conditions(registry):
        for repeat in range(1, 6):
            index += 1
            attempts.append({
                "canonical_index": index,
                "attempt_id": f"{condition['condition_id']}-R{repeat}",
                "substudy": condition["substudy"],
                "scenario_id": condition["scenario_id"],
                "task_family": condition.get("task_family"),
                "N": int(condition["N"]),
                "cold_start_repeat": repeat,
                "seed": FORMAL_SEED_BASE + index,
            })
    return attempts


def stable_fisher_yates(items: Iterable[Dict[str, Any]], seed: int) -> List[Dict[str, Any]]:
    """Shuffle with SHA-256 counter draws, independent of Python RNG versions."""
    result = [dict(item) for item in items]
    counter = 0
    for upper in range(len(result) - 1, 0, -1):
        limit = (1 << 256) - ((1 << 256) % (upper + 1))
        while True:
            digest = hashlib.sha256(f"{seed}:{counter}".encode("ascii")).digest()
            counter += 1
            draw = int.from_bytes(digest, "big")
            if draw < limit:
                break
        selected = draw % (upper + 1)
        result[upper], result[selected] = result[selected], result[upper]
    return result


def ordered_attempts(registry: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    # Five prospectively defined strata each contain one attempt from every
    # condition. This preserves a deterministic seeded permutation while
    # interleaving substudies, swarm sizes, and task families over chronology.
    canonical = canonical_attempts(registry)
    ordered: List[Dict[str, Any]] = []
    for repeat in range(1, 6):
        stratum = [
            item for item in canonical if item["cold_start_repeat"] == repeat
        ]
        ordered.extend(stable_fisher_yates(stratum, FORMAL_ORDER_SEED + repeat))
    return ordered


def attempt_order_text(attempts: Iterable[Dict[str, Any]]) -> str:
    lines = []
    for slot, attempt in enumerate(attempts, 1):
        lines.append(
            f"{slot:03d}\t{attempt['attempt_id']}\tseed={attempt['seed']}\t"
            f"substudy={attempt['substudy']}\tN={attempt['N']}\t"
            f"family={attempt.get('task_family') or '-'}"
        )
    return "\n".join(lines) + "\n"
