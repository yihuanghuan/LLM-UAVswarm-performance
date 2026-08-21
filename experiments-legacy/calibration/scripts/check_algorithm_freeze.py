#!/usr/bin/env python3
"""Fail when an immutable paper algorithm file differs from the freeze tag."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


DEFAULT_MANIFEST = Path("experiments/calibration/algorithm_freeze_manifest.json")


class FreezeCheckError(RuntimeError):
    """Raised when the algorithm freeze contract is invalid or violated."""


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _git(repo: Path, *args: str, binary: bool = False) -> str | bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise FreezeCheckError(f"git {' '.join(args)} failed: {detail}")
    if binary:
        return result.stdout
    return result.stdout.decode("utf-8").strip()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_relative_path(raw_path: Any) -> Path:
    if not isinstance(raw_path, str) or not raw_path:
        raise FreezeCheckError("manifest contains an empty/non-string path")
    path = Path(raw_path)
    if path.is_absolute() or ".." in path.parts:
        raise FreezeCheckError(f"manifest path is not repository-relative: {raw_path}")
    return path


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FreezeCheckError(f"cannot load {path}: {exc}") from exc
    if data.get("hash_algorithm") != "sha256":
        raise FreezeCheckError("algorithm manifest must use sha256")
    if not isinstance(data.get("algorithm_components"), dict):
        raise FreezeCheckError("algorithm_components must be an object")
    return data


def check_algorithm_freeze(repo: Path, manifest_path: Path) -> int:
    """Validate manifest provenance and immutable working-tree file hashes."""
    manifest = _load_manifest(manifest_path)
    tag = manifest.get("freeze_tag")
    expected_commit = manifest.get("freeze_commit")
    expected_tree = manifest.get("freeze_tree")
    if not all(isinstance(value, str) and value for value in (
        tag, expected_commit, expected_tree
    )):
        raise FreezeCheckError("freeze tag, commit and tree must be non-empty")

    tag_type = _git(repo, "cat-file", "-t", tag)
    if tag_type != "tag":
        raise FreezeCheckError(f"{tag} is not an annotated tag")
    actual_commit = _git(repo, "rev-parse", f"{tag}^{{commit}}")
    actual_tree = _git(repo, "rev-parse", f"{tag}^{{tree}}")
    if actual_commit != expected_commit:
        raise FreezeCheckError(
            f"freeze tag resolves to {actual_commit}, expected {expected_commit}"
        )
    if actual_tree != expected_tree:
        raise FreezeCheckError(
            f"freeze tree is {actual_tree}, expected {expected_tree}"
        )

    components = manifest["algorithm_components"]
    immutable = manifest.get("immutable_algorithm_components")
    parameter_components = manifest.get("parameter_components")
    if not isinstance(immutable, list) or not isinstance(parameter_components, list):
        raise FreezeCheckError(
            "manifest must classify immutable and parameter components"
        )
    immutable_set = set(immutable)
    parameter_set = set(parameter_components)
    component_set = set(components)
    if immutable_set & parameter_set:
        raise FreezeCheckError("a component cannot be both immutable and parameterized")
    if immutable_set | parameter_set != component_set:
        missing = component_set - (immutable_set | parameter_set)
        unknown = (immutable_set | parameter_set) - component_set
        raise FreezeCheckError(
            f"component classification mismatch; unclassified={sorted(missing)}, "
            f"unknown={sorted(unknown)}"
        )

    seen_paths: set[str] = set()
    immutable_count = 0
    parameter_count = 0
    for component_name, entries in components.items():
        if not isinstance(entries, list) or not entries:
            raise FreezeCheckError(f"component {component_name} has no files")
        for entry in entries:
            if not isinstance(entry, dict):
                raise FreezeCheckError(f"invalid entry in {component_name}")
            relative = _safe_relative_path(entry.get("path"))
            relative_text = relative.as_posix()
            if relative_text in seen_paths:
                raise FreezeCheckError(f"duplicate manifest path: {relative_text}")
            seen_paths.add(relative_text)

            recorded_hash = entry.get("sha256")
            if not isinstance(recorded_hash, str) or len(recorded_hash) != 64:
                raise FreezeCheckError(f"invalid SHA-256 for {relative_text}")
            baseline_data = _git(
                repo, "show", f"{tag}:{relative_text}", binary=True
            )
            baseline_hash = _sha256(baseline_data)
            if baseline_hash != recorded_hash:
                raise FreezeCheckError(
                    f"manifest hash drift for {relative_text}: tag={baseline_hash}, "
                    f"manifest={recorded_hash}"
                )

            if component_name in parameter_set:
                parameter_count += 1
                continue
            current_path = repo / relative
            try:
                current_hash = _sha256(current_path.read_bytes())
            except OSError as exc:
                raise FreezeCheckError(
                    f"immutable algorithm file unavailable: {relative_text}: {exc}"
                ) from exc
            if current_hash != baseline_hash:
                raise FreezeCheckError(
                    f"immutable algorithm drift: {relative_text}: "
                    f"current={current_hash}, baseline={baseline_hash}"
                )
            immutable_count += 1

    print(
        "algorithm freeze check = PASS "
        f"(tag={tag}, immutable_files={immutable_count}, "
        f"parameter_files_delegated={parameter_count})"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=_repository_root(),
        help="repository root (default: inferred from this script)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help=f"manifest path relative to repo (default: {DEFAULT_MANIFEST})",
    )
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    manifest_path = args.manifest
    if not manifest_path.is_absolute():
        manifest_path = repo / manifest_path
    try:
        return check_algorithm_freeze(repo, manifest_path)
    except FreezeCheckError as exc:
        print(f"algorithm freeze check = FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
