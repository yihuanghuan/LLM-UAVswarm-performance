#!/usr/bin/env python3
"""Enforce C0 parameter ownership against the calibration mainline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Iterable

import yaml


DEFAULT_MANIFEST = Path("experiments/calibration/parameter_ownership.json")
VALID_STATUSES = {"PROVISIONAL", "FROZEN", "ARCHITECTURE_FROZEN"}
MISSING = object()


class OwnershipCheckError(RuntimeError):
    """Raised when a parameter ownership rule is invalid or violated."""


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _git(repo: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", *args], cwd=repo, check=False,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise OwnershipCheckError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout


def _load_json_bytes(data: bytes, source: str) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OwnershipCheckError(f"cannot parse {source}: {exc}") from exc
    if not isinstance(value, dict):
        raise OwnershipCheckError(f"{source} must contain a JSON object")
    return value


def _load_yaml_bytes(data: bytes, source: str) -> Any:
    try:
        return yaml.safe_load(data)
    except yaml.YAMLError as exc:
        raise OwnershipCheckError(f"cannot parse {source}: {exc}") from exc


def _normalize_status(raw: str) -> str:
    value = raw.replace("`", "").strip()
    if value.startswith("ARCHITECTURE_FROZEN"):
        return "ARCHITECTURE_FROZEN"
    if value.startswith("PROVISIONAL"):
        return "PROVISIONAL"
    if value.startswith("FROZEN"):
        return "FROZEN"
    raise OwnershipCheckError(f"unsupported ledger status: {raw}")


def _ledger_rows_text(text: str, source: str) -> dict[str, tuple[str, str | None]]:
    lines = text.splitlines()
    rows: dict[str, tuple[str, str | None]] = {}
    for line in lines:
        if not line.startswith("|") or "---" in line or "Parameter / group" in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 4:
            continue
        label = cells[0]
        status = _normalize_status(cells[2])
        owner = cells[3] if cells[3] != "—" else None
        if label in rows:
            raise OwnershipCheckError(f"duplicate ledger label in {source}: {label}")
        rows[label] = (status, owner)
    return rows


def _ledger_rows(path: Path) -> dict[str, tuple[str, str | None]]:
    try:
        return _ledger_rows_text(path.read_text(encoding="utf-8"), str(path))
    except OSError as exc:
        raise OwnershipCheckError(f"cannot read ledger {path}: {exc}") from exc


def _key_tuple(raw: Any, context: str) -> tuple[str, ...]:
    if not isinstance(raw, list) or not raw or not all(
        isinstance(item, str) and item for item in raw
    ):
        raise OwnershipCheckError(f"invalid key path in {context}: {raw!r}")
    return tuple(raw)


def _selectors(entry: dict[str, Any]) -> Iterable[tuple[str, tuple[str, ...]]]:
    locations = entry.get("locations")
    if not isinstance(locations, list) or not locations:
        raise OwnershipCheckError(f"{entry.get('id')} has no locations")
    for location in locations:
        if not isinstance(location, dict) or not isinstance(location.get("path"), str):
            raise OwnershipCheckError(f"invalid location in {entry.get('id')}")
        keys = location.get("keys")
        if not isinstance(keys, list) or not keys:
            raise OwnershipCheckError(f"empty keys in {entry.get('id')}")
        for raw_key in keys:
            yield location["path"], _key_tuple(raw_key, str(entry.get("id")))


def _validate_manifest(
    manifest: dict[str, Any], ledger: dict[str, tuple[str, str | None]]
) -> dict[str, dict[str, Any]]:
    if manifest.get("manifest_version") != 1:
        raise OwnershipCheckError("unsupported parameter manifest version")
    calibrations = manifest.get("allowed_calibrations")
    if not isinstance(calibrations, list) or not calibrations:
        raise OwnershipCheckError("allowed_calibrations must be a non-empty list")
    parameters = manifest.get("parameters")
    if not isinstance(parameters, list) or not parameters:
        raise OwnershipCheckError("parameters must be a non-empty list")

    by_id: dict[str, dict[str, Any]] = {}
    selector_owner: dict[tuple[str, tuple[str, ...]], str] = {}
    machine_calibrated_labels: set[str] = set()
    for entry in parameters:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            raise OwnershipCheckError("every parameter must have a string id")
        parameter_id = entry["id"]
        if parameter_id in by_id:
            raise OwnershipCheckError(f"duplicate parameter id: {parameter_id}")
        status = entry.get("status")
        owner = entry.get("owner")
        if status not in VALID_STATUSES:
            raise OwnershipCheckError(f"invalid status for {parameter_id}: {status}")
        if status == "ARCHITECTURE_FROZEN":
            if owner is not None:
                raise OwnershipCheckError(f"architecture parameter has owner: {parameter_id}")
        elif owner not in calibrations:
            raise OwnershipCheckError(f"invalid/missing owner for {parameter_id}")
        if status in {"FROZEN", "ARCHITECTURE_FROZEN"} and not all(
            isinstance(entry.get(field), str) and entry[field]
            for field in ("freeze_commit", "freeze_tag")
        ):
            raise OwnershipCheckError(f"frozen parameter lacks provenance: {parameter_id}")
        label = entry.get("ledger_label")
        if label not in ledger:
            raise OwnershipCheckError(f"parameter missing from ledger: {parameter_id}")
        if ledger[label] != (status, owner):
            raise OwnershipCheckError(
                f"ledger mismatch for {parameter_id}: ledger={ledger[label]}, "
                f"manifest={(status, owner)}"
            )
        if status != "ARCHITECTURE_FROZEN":
            if label in machine_calibrated_labels:
                raise OwnershipCheckError(f"duplicate calibrated ledger label: {label}")
            machine_calibrated_labels.add(label)
        for selector in _selectors(entry):
            if selector in selector_owner:
                raise OwnershipCheckError(
                    f"duplicate selector {selector}: {selector_owner[selector]} and "
                    f"{parameter_id}"
                )
            selector_owner[selector] = parameter_id
        by_id[parameter_id] = entry

    ledger_calibrated = {
        label for label, (status, _) in ledger.items()
        if status in {"PROVISIONAL", "FROZEN"}
    }
    if machine_calibrated_labels != ledger_calibrated:
        raise OwnershipCheckError(
            "machine manifest does not exactly cover ledger calibration rows; "
            f"missing={sorted(ledger_calibrated - machine_calibrated_labels)}, "
            f"extra={sorted(machine_calibrated_labels - ledger_calibrated)}"
        )
    return by_id


def _flatten(value: Any, prefix: tuple[str, ...] = ()) -> dict[tuple[str, ...], Any]:
    if isinstance(value, dict):
        result: dict[tuple[str, ...], Any] = {}
        for key, child in value.items():
            result.update(_flatten(child, prefix + (str(key),)))
        return result
    return {prefix: value}


def _is_prefix(prefix: tuple[str, ...], key: tuple[str, ...]) -> bool:
    return len(prefix) <= len(key) and key[:len(prefix)] == prefix


def _entry_for_change(
    path: str, key: tuple[str, ...], entries: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    matches = []
    for entry in entries.values():
        if any(p == path and _is_prefix(selector, key) for p, selector in _selectors(entry)):
            matches.append(entry)
    if len(matches) > 1:
        raise OwnershipCheckError(
            f"overlapping ownership for {path}:{'.'.join(key)}: "
            f"{[entry['id'] for entry in matches]}"
        )
    return matches[0] if matches else None


def _metadata_prefixes(manifest: dict[str, Any]) -> list[tuple[str, tuple[str, ...]]]:
    result = []
    for item in manifest.get("allowed_metadata_prefixes", []):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise OwnershipCheckError("invalid allowed_metadata_prefixes entry")
        result.append((item["path"], _key_tuple(item.get("keys"), "metadata")))
    return result


def _compare_manifest_contract(
    baseline: dict[str, Any], current: dict[str, Any], active: str,
    baseline_entries: dict[str, dict[str, Any]],
    current_entries: dict[str, dict[str, Any]],
) -> None:
    for field in ("governed_files", "allowed_calibrations", "allowed_metadata_prefixes"):
        if current.get(field) != baseline.get(field):
            raise OwnershipCheckError(f"ownership contract field changed: {field}")
    if set(baseline_entries) != set(current_entries):
        raise OwnershipCheckError("parameter ids may not be added or removed in a C0")
    immutable_fields = ("id", "ledger_label", "owner", "locations")
    for parameter_id, old in baseline_entries.items():
        new = current_entries[parameter_id]
        if any(old.get(field) != new.get(field) for field in immutable_fields):
            raise OwnershipCheckError(f"ownership metadata changed: {parameter_id}")
        old_status, new_status = old["status"], new["status"]
        if old_status in {"FROZEN", "ARCHITECTURE_FROZEN"}:
            if new != old:
                raise OwnershipCheckError(f"frozen manifest entry changed: {parameter_id}")
        elif new_status == "PROVISIONAL":
            if new != old:
                raise OwnershipCheckError(
                    f"provisional manifest entry changed before freeze: {parameter_id}"
                )
        elif not (new_status == "FROZEN" and old.get("owner") == active):
            raise OwnershipCheckError(f"invalid status transition for {parameter_id}")


def check_parameter_ownership(
    repo: Path, manifest_path: Path, active: str, baseline_ref: str | None
) -> int:
    current = _load_json_bytes(manifest_path.read_bytes(), str(manifest_path))
    if active not in current.get("allowed_calibrations", []):
        raise OwnershipCheckError(f"unsupported calibration: {active}")
    ledger_path = repo / current.get("source_ledger", "")
    ledger = _ledger_rows(ledger_path)
    current_entries = _validate_manifest(current, ledger)
    relative_manifest = manifest_path.relative_to(repo).as_posix()
    baseline_ref = baseline_ref or current.get("default_baseline_ref")
    if not isinstance(baseline_ref, str) or not baseline_ref:
        raise OwnershipCheckError("baseline ref is missing")
    baseline = _load_json_bytes(
        _git(repo, "show", f"{baseline_ref}:{relative_manifest}"),
        f"{baseline_ref}:{relative_manifest}",
    )
    baseline_ledger_path = baseline.get("source_ledger")
    if not isinstance(baseline_ledger_path, str) or not baseline_ledger_path:
        raise OwnershipCheckError("baseline source_ledger is missing")
    baseline_ledger_bytes = _git(
        repo, "show", f"{baseline_ref}:{baseline_ledger_path}"
    )
    try:
        baseline_ledger_text = baseline_ledger_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OwnershipCheckError("baseline ledger is not UTF-8") from exc
    baseline_ledger = _ledger_rows_text(
        baseline_ledger_text, f"{baseline_ref}:{baseline_ledger_path}"
    )
    baseline_entries = _validate_manifest(baseline, baseline_ledger)
    _compare_manifest_contract(
        baseline, current, active, baseline_entries, current_entries
    )

    metadata = _metadata_prefixes(current)
    governed_files = current.get("governed_files")
    if not isinstance(governed_files, list) or not governed_files:
        raise OwnershipCheckError("governed_files must be a non-empty list")
    allowed_changes = 0
    for path in governed_files:
        if not isinstance(path, str) or not path:
            raise OwnershipCheckError("invalid governed file path")
        baseline_yaml = _load_yaml_bytes(
            _git(repo, "show", f"{baseline_ref}:{path}"), f"{baseline_ref}:{path}"
        )
        try:
            current_yaml = _load_yaml_bytes((repo / path).read_bytes(), path)
        except OSError as exc:
            raise OwnershipCheckError(f"cannot read {path}: {exc}") from exc
        old_flat, new_flat = _flatten(baseline_yaml), _flatten(current_yaml)
        all_keys = set(old_flat) | set(new_flat)

        # Every parameter-file leaf must be owned or explicitly non-parameter metadata.
        for key in new_flat:
            if _entry_for_change(path, key, current_entries) is not None:
                continue
            if any(p == path and _is_prefix(prefix, key) for p, prefix in metadata):
                continue
            raise OwnershipCheckError(
                f"unowned parameter key: {path}:{'.'.join(key)}"
            )

        for key in sorted(all_keys):
            if old_flat.get(key, MISSING) == new_flat.get(key, MISSING):
                continue
            entry = _entry_for_change(path, key, baseline_entries)
            if entry is None:
                if any(p == path and _is_prefix(prefix, key) for p, prefix in metadata):
                    continue
                raise OwnershipCheckError(
                    f"unowned parameter change: {path}:{'.'.join(key)}"
                )
            if entry["status"] != "PROVISIONAL" or entry.get("owner") != active:
                raise OwnershipCheckError(
                    f"protected parameter changed: {entry['id']} "
                    f"(status={entry['status']}, owner={entry.get('owner')}, "
                    f"active={active}) at {path}:{'.'.join(key)}"
                )
            allowed_changes += 1

    print(
        f"ownership check {active} = PASS "
        f"(baseline={baseline_ref}, allowed_parameter_changes={allowed_changes})"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calibration", required=True)
    parser.add_argument("--baseline-ref", help="Git ref for the calibration branch base")
    parser.add_argument("--repo-root", type=Path, default=_repository_root())
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    manifest_path = args.manifest
    if not manifest_path.is_absolute():
        manifest_path = repo / manifest_path
    try:
        return check_parameter_ownership(
            repo, manifest_path, args.calibration, args.baseline_ref
        )
    except (OSError, OwnershipCheckError) as exc:
        print(f"ownership check {args.calibration} = FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
