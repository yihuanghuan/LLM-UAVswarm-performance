"""Shared paths and sealed-registry readers for E1 formal tooling."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

import yaml


TOOLING_DIR = Path(__file__).resolve().parent
E1_DIR = TOOLING_DIR.parent
FORMAL_DIR = E1_DIR.parent
REPO_ROOT = FORMAL_DIR.parents[1]

DATASET_PATH = E1_DIR / "e1_candidate_semantic_dataset_v1.jsonl"
DATASET_REGISTRY_PATH = E1_DIR / "e1_dataset_registry_v1.yaml"
ORDER_PATH = E1_DIR / "e1_inference_order_v1.yaml"
PROTOCOL_PATH = E1_DIR / "e1_protocol_v1.yaml"
PREFLIGHT_PATH = FORMAL_DIR / "formal_preflight_v1.yaml"
RUNTIME_MANIFEST_PATH = FORMAL_DIR / "llm_runtime_manifest_v1.yaml"

BASELINE_TAG = "paper-final-sim-v3"
BASELINE_COMMIT = "6cf402debf23851b1eff3edc6f3ab49eae7127c4"
SOURCE_PREFLIGHT_COMMIT = "36dba68c6b16681ec98500b49c5a83095de4b634"
FORMAL_PREFIX = "experiments_v2/Formal Evaluation Experiments/"

UNAVAILABLE = {"status": "unavailable"}
MISSING = {"status": "missing"}


class E1ToolingError(RuntimeError):
    """Fail-closed tooling error."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_yaml(path: Path) -> Dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise E1ToolingError(f"expected YAML mapping: {path}")
    return value


def load_dataset(path: Path = DATASET_PATH) -> List[Dict[str, Any]]:
    records = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise E1ToolingError(
                f"invalid dataset JSON at line {line_number}: {exc}"
            ) from exc
        if not isinstance(record, dict):
            raise E1ToolingError(
                f"dataset line {line_number} is not an object"
            )
        records.append(record)
    return records


def load_order(path: Path = ORDER_PATH) -> List[str]:
    raw = load_yaml(path).get("permutation")
    if not isinstance(raw, list):
        raise E1ToolingError("inference permutation is not a list")
    flattened: List[str] = []
    for row in raw:
        if isinstance(row, list):
            flattened.extend(str(item) for item in row)
        else:
            flattened.append(str(row))
    return flattened


def permutation_bytes(command_ids: Iterable[str]) -> bytes:
    return "".join(f"{command_id}\n" for command_id in command_ids).encode(
        "utf-8"
    )


def availability_text(ids: Iterable[int]) -> str:
    normalized = [int(value) for value in ids]
    return (
        f"Available UAV IDs: {normalized}\n"
        f"Total available UAVs: {len(normalized)}"
    )


def utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )
