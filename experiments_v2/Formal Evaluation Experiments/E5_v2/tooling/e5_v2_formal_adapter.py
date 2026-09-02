#!/usr/bin/env python3
"""Authorization gate for a future E5-v2 formal adapter (no backend here)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from e5_v2_common import REGISTRY_PATH, load_yaml, sha256_file


class FormalActivationError(RuntimeError):
    """Raised before any formal side effect when human activation is absent."""


def assert_formal_activation(
    registry_path: Path = REGISTRY_PATH,
    activation_record_path: Path | None = None,
) -> None:
    registry = load_yaml(registry_path)
    if registry.get("status") != "ACTIVATED_FOR_FORMAL_EXECUTION":
        raise FormalActivationError(
            "formal adapter refuses non-activated registry status: "
            f"{registry.get('status')}"
        )
    if activation_record_path is None or not activation_record_path.is_file():
        raise FormalActivationError("human activation record is required")
    activation = load_yaml(activation_record_path)
    if activation.get("human_approved") is not True:
        raise FormalActivationError("activation record lacks human_approved=true")
    if activation.get("registry_sha256") != sha256_file(registry_path):
        raise FormalActivationError("activation record registry hash mismatch")
    if registry.get("accepted_formal_results_created") is not False:
        raise FormalActivationError("registry already reports a formal result")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=REGISTRY_PATH)
    parser.add_argument("--activation-record", type=Path)
    parser.add_argument("--authorization-check", action="store_true", required=True)
    args = parser.parse_args()
    try:
        assert_formal_activation(args.registry, args.activation_record)
    except FormalActivationError as exc:
        print(json.dumps({
            "authorized": False,
            "accepted_formal_result": False,
            "formal_execution_started": False,
            "error": str(exc),
        }, sort_keys=True))
        return 2
    print(json.dumps({
        "authorized": True,
        "accepted_formal_result": False,
        "formal_execution_started": False,
        "notice": "Authorization gate passed; this design branch contains no formal execution backend.",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
