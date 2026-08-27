"""Shared constants, canonicalization, registries, and snapshots for E2."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Dict, Iterable, List, Mapping, Tuple

import yaml


TOOLING_DIR = Path(__file__).resolve().parent
E2_DIR = TOOLING_DIR.parent
FORMAL_DIR = E2_DIR.parent
REPO_ROOT = FORMAL_DIR.parents[1]

PREFLIGHT_PATH = FORMAL_DIR / "formal_preflight_v1.yaml"
PROTOCOL_PATH = FORMAL_DIR / "protocols" / "E2_protocol_v1.yaml"
REGISTRY_PATH = E2_DIR / "e2_scenario_registry_v1.yaml"
GLOBAL_REGISTRY_PATH = FORMAL_DIR / "e2_e5_scenario_seed_registry_v1.yaml"
ORDER_YAML_PATH = FORMAL_DIR / "simulation_trial_order_v1.yaml"
ORDER_TXT_PATH = FORMAL_DIR / "simulation_trial_order_v1.txt"
WRAPPER_PATH = FORMAL_DIR / "harness" / "e2_commitment_wrapper.py"
POLICY_PATH = REPO_ROOT / "lfs_policy" / "config" / "lfs_policy.paper_current.yaml"
SYNTHETIC_RESULTS_DIR = E2_DIR / "results" / "synthetic-validation"
FORMAL_RESULTS_DIR = E2_DIR / "results" / "formal"

BASELINE_TAG = "paper-final-sim-v3"
BASELINE_COMMIT = "6cf402debf23851b1eff3edc6f3ab49eae7127c4"
SOURCE_PREFLIGHT_COMMIT = "36dba68c6b16681ec98500b49c5a83095de4b634"
CONFIGURATION_ID = "paper-current-v11-c0-f-frozen"
CANONICAL_POLICY_SHA256 = (
    "6b47d27f4253d7311e79ea51f6dd1cf0d0182e6df24374a94abae0aa6a135858"
)
EXPECTED_BRANCH = "formal/E2-commitment-timing-v1"
DATASET_CLASS = "synthetic_validation"
NOT_FORMAL_RESULT = "NOT_FORMAL_RESULT"
INVARIANT_FIELDS = ("task_id", "U", "F", "m", "s", "q")
COMMITMENT_FIELDS = ("c", "r", "T")

TRIAL_PATTERN = re.compile(
    r"^(E2-[A-Z]+-01)__(NO_SHIFT|SHIFT)__(EARLY|LATE)__S(\d+)$"
)
CONDITION_FROM_TOKEN = {
    "EARLY": "Early_Commitment",
    "LATE": "Information_Aligned_Late_Commitment",
}
TOKEN_FROM_CONDITION = {value: key for key, value in CONDITION_FROM_TOKEN.items()}


class E2ToolingError(RuntimeError):
    """Fail-closed E2 tooling error."""


def ensure_runtime_import_paths() -> None:
    """Expose the source-tree frozen packages and sealed harness to Python."""
    paths = (
        REPO_ROOT / "location_allocate",
        REPO_ROOT / "lfs_policy",
        FORMAL_DIR / "harness",
    )
    for path in reversed(paths):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, float) and not math.isfinite(value):
            return str(value)
        return value
    if is_dataclass(value):
        return json_safe(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return repr(value)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        json_safe(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_yaml(path: Path) -> Dict[str, Any]:
    value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise E2ToolingError(f"expected YAML mapping: {path}")
    return value


def write_json_exclusive(path: Path, value: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(json_safe(value), stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def load_scenario_registry(path: Path = REGISTRY_PATH) -> Dict[str, Any]:
    registry = load_yaml(path)
    scenarios = registry.get("scenarios")
    if not isinstance(scenarios, list):
        raise E2ToolingError("E2 registry scenarios is not a list")
    return registry


def scenario_index(registry: Dict[str, Any] | None = None) -> Dict[str, Dict[str, Any]]:
    registry = registry or load_scenario_registry()
    result = {str(item["scenario_id"]): item for item in registry["scenarios"]}
    if len(result) != len(registry["scenarios"]):
        raise E2ToolingError("duplicate scenario_id in E2 registry")
    return result


def parse_trial_id(trial_id: str) -> Dict[str, Any]:
    match = TRIAL_PATTERN.fullmatch(str(trial_id))
    if match is None:
        raise E2ToolingError(f"malformed E2 trial ID: {trial_id}")
    scenario_id, state_condition, token, seed = match.groups()
    return {
        "trial_id": str(trial_id),
        "scenario_id": scenario_id,
        "state_condition": state_condition,
        "commitment_condition": CONDITION_FROM_TOKEN[token],
        "seed": int(seed),
    }


def registered_trial_ids(
    order_path: Path = ORDER_TXT_PATH,
    registry: Dict[str, Any] | None = None,
    global_registry: Dict[str, Any] | None = None,
) -> List[str]:
    """Filter E2 IDs from the sealed global order without creating a new order."""
    registry = registry or load_scenario_registry()
    global_registry = global_registry or load_yaml(GLOBAL_REGISTRY_PATH)
    all_ids = Path(order_path).read_text(encoding="utf-8").splitlines()
    filtered = [trial_id for trial_id in all_ids if trial_id.startswith("E2-")]

    scenarios = list(scenario_index(registry))
    seeds = [int(value) for value in registry["seeds"]]
    experiment = global_registry["experiments"]["E2"]
    commitments = [str(value) for value in experiment["commitment_conditions"]]
    states = [str(value) for value in experiment["state_conditions"]]
    expected = {
        f"{scenario}__{state}__{TOKEN_FROM_CONDITION[commitment]}__S{seed}"
        for scenario in scenarios
        for seed in seeds
        for commitment in commitments
        for state in states
    }
    actual = set(filtered)
    problems = []
    if len(filtered) != 120:
        problems.append(f"count={len(filtered)}")
    if len(actual) != len(filtered):
        problems.append("duplicates present")
    if actual != expected:
        problems.append(
            f"missing={sorted(expected - actual)}, unregistered={sorted(actual - expected)}"
        )
    if len(scenarios) != 6 or len(seeds) != 5:
        problems.append(f"registry dimensions scenarios={len(scenarios)}, seeds={len(seeds)}")
    if experiment.get("registered_attempts") != 120:
        problems.append("global registered_attempts is not 120")
    if problems:
        raise E2ToolingError("invalid sealed E2 trial population: " + "; ".join(problems))
    for trial_id in filtered:
        parse_trial_id(trial_id)
    return filtered


def global_order_positions(order_path: Path = ORDER_TXT_PATH) -> Dict[str, int]:
    return {
        trial_id: position
        for position, trial_id in enumerate(
            Path(order_path).read_text(encoding="utf-8").splitlines(), start=1
        )
    }


def candidate_for_scenario(scenario: Dict[str, Any]) -> Dict[str, Any]:
    return deepcopy(scenario["candidate_ground_truth"])


def _snapshot_positions(
    scenario: Dict[str, Any], state_condition: str, registry: Dict[str, Any]
) -> Tuple[float, Dict[int, List[float]]]:
    common = registry["common"]
    if state_condition == "NO_SHIFT":
        epoch = float(common["no_shift_control"]["execute_epoch_s"])
        positions = common["parse_positions_m"]
    elif state_condition == "SHIFT":
        epoch = float(common["execute_epoch_s"])
        positions = scenario["shifted_execute_positions_m"]
    else:
        raise E2ToolingError(f"unknown state condition: {state_condition}")
    return epoch, {int(uid): list(position) for uid, position in positions.items()}


def snapshot_payload(
    scenario: Dict[str, Any], stage: str, state_condition: str = "NO_SHIFT",
    registry: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    registry = registry or load_scenario_registry()
    common = registry["common"]
    if stage == "parse":
        epoch = float(common["parse_epoch_s"])
        positions = {
            int(uid): list(position)
            for uid, position in common["parse_positions_m"].items()
        }
    elif stage == "execute":
        epoch, positions = _snapshot_positions(scenario, state_condition, registry)
    else:
        raise E2ToolingError(f"unknown snapshot stage: {stage}")
    velocity = [float(value) for value in common["velocity_for_every_snapshot_uav_mps"]]
    return {
        "epoch_s": epoch,
        "frame": str(common["snapshot_contract"]["frame"]),
        "states": {
            str(uid): {
                "position_m": [float(value) for value in position],
                "velocity_mps": velocity,
                "receive_timestamp_s": epoch,
                "source_timestamp_s": epoch,
                "timestamp_source": "source_time",
            }
            for uid, position in sorted(positions.items())
        },
        "warnings": [],
    }


def state_snapshot_from_payload(payload: Dict[str, Any]):
    ensure_runtime_import_paths()
    from location_allocate.lfs_types import StateSnapshot, UAVState

    states = {
        int(uid): UAVState(
            position=tuple(float(value) for value in state["position_m"]),
            receive_timestamp=float(state["receive_timestamp_s"]),
            velocity=tuple(float(value) for value in state["velocity_mps"]),
            source_timestamp=float(state["source_timestamp_s"]),
            timestamp_source=str(state["timestamp_source"]),
        )
        for uid, state in payload["states"].items()
    }
    return StateSnapshot(
        epoch=float(payload["epoch_s"]), states=states, warnings=tuple(payload["warnings"])
    )


def build_registered_snapshots(
    scenario: Dict[str, Any], state_condition: str,
    registry: Dict[str, Any] | None = None,
):
    registry = registry or load_scenario_registry()
    parse_payload = snapshot_payload(scenario, "parse", registry=registry)
    execute_payload = snapshot_payload(
        scenario, "execute", state_condition=state_condition, registry=registry
    )
    return (
        state_snapshot_from_payload(parse_payload),
        state_snapshot_from_payload(execute_payload),
        parse_payload,
        execute_payload,
    )


def crt_payload(executable: Any) -> Dict[str, Any]:
    return {
        "c": [float(value) for value in executable.center],
        "r": float(executable.radius),
        "T": float(executable.duration),
    }


def numeric_equal(left: Any, right: Any, tolerance: float = 1e-12) -> bool:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=tolerance)
    if isinstance(left, list) and isinstance(right, list) and len(left) == len(right):
        return all(numeric_equal(a, b, tolerance) for a, b in zip(left, right))
    if isinstance(left, dict) and isinstance(right, dict) and left.keys() == right.keys():
        return all(numeric_equal(left[key], right[key], tolerance) for key in left)
    return left == right


def file_hash_manifest_payload(run_dir: Path, exclude: Iterable[str] = ()) -> Dict[str, Any]:
    run_dir = Path(run_dir)
    excluded = set(exclude)
    files = []
    for path in sorted(item for item in run_dir.rglob("*") if item.is_file()):
        relative = path.relative_to(run_dir).as_posix()
        if relative in excluded:
            continue
        files.append({
            "path": relative,
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
        })
    return {
        "manifest_type": "E2_synthetic_validation_file_hash_manifest_v1",
        "dataset_class": DATASET_CLASS,
        "accepted_formal_result": False,
        "result_notice": NOT_FORMAL_RESULT,
        "self_excluded": True,
        "files": files,
    }
