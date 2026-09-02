#!/usr/bin/env python3
"""Render the prospective E5-v2 seed registry and 60-slot order."""

from __future__ import annotations

import argparse
import json
from collections import Counter

import yaml

from e5_v2_common import (
    FORMAL_ORDER_SEED,
    ORDER_METADATA_PATH,
    ORDER_PATH,
    REGISTRY_PATH,
    SEED_REGISTRY_PATH,
    attempt_order_text,
    canonical_attempts,
    canonical_json_bytes,
    load_yaml,
    ordered_attempts,
    sha256_bytes,
    sha256_file,
)


def seed_document():
    attempts = canonical_attempts()
    return {
        "registry_id": "E5-v2-formal-seeds-v1",
        "status": "FROZEN_CANDIDATE_FOR_HUMAN_REVIEW",
        "generation_rule": {
            "description": (
                "Assign seed 5,202,000 + one-based canonical attempt index; "
                "canonical conditions follow E5_v2_registry.yaml and repeats 1..5."
            ),
            "base": 5_202_000,
            "first_seed": 5_202_001,
            "last_seed": 5_202_060,
        },
        "collision_exclusions": {
            "E2": list(range(52_101, 52_106)),
            "E3": list(range(53_101, 53_116)),
            "E4A": list(range(54_101, 54_106)),
            "E4B": list(range(54_201, 54_206)),
            "old_E5_v1": list(range(55_101, 55_106)),
            "E5_v2_engineering_smoke": [9_900_008, 9_900_012, 9_900_016],
        },
        "formal_attempt_count": len(attempts),
        "attempts": attempts,
    }


def render_seed_yaml(document) -> str:
    return yaml.safe_dump(
        document, allow_unicode=True, sort_keys=False, width=1000
    )


def order_metadata(order, seed_yaml: str, order_text: str):
    counts = Counter((item["substudy"], item["N"], item.get("task_family")) for item in order)
    return {
        "metadata_id": "E5-v2-formal-order-metadata-v1",
        "status": "FROZEN_CANDIDATE_FOR_HUMAN_REVIEW",
        "permutation_algorithm": (
            "Create five chronological strata (repeat 1..5), each containing "
            "one attempt from every registered condition; independently apply "
            "Durstenfeld Fisher-Yates from last index to 1 with stratum seed "
            "permutation_seed+repeat. Each unbiased draw uses "
            "SHA-256('<decimal stratum seed>:<counter>') with rejection sampling; "
            "concatenate strata in repeat order."
        ),
        "permutation_seed": FORMAL_ORDER_SEED,
        "canonical_attempt_list_sha256": sha256_bytes(
            canonical_json_bytes(canonical_attempts())
        ),
        "seed_registry_sha256": sha256_bytes(seed_yaml.encode("utf-8")),
        "final_order_sha256": sha256_bytes(order_text.encode("utf-8")),
        "attempt_count": len(order),
        "substudy_counts": {
            "E5-v2A": sum(item["substudy"] == "E5-v2A" for item in order),
            "E5-v2B": sum(item["substudy"] == "E5-v2B" for item in order),
        },
        "E5_v2B_cell_counts": {
            f"N{n}-{family}": counts[("E5-v2B", n, family)]
            for n in (8, 12, 16)
            for family in ("SIMPLE", "UNDER_SPECIFIED", "COMPOSITIONAL")
        },
        "order_attempt_ids": [item["attempt_id"] for item in order],
    }


def render():
    seed_doc = seed_document()
    seed_yaml = render_seed_yaml(seed_doc)
    order = ordered_attempts(load_yaml(REGISTRY_PATH))
    order_text = attempt_order_text(order)
    metadata = order_metadata(order, seed_yaml, order_text)
    metadata_json = json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return seed_yaml, order_text, metadata_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    seed_yaml, order_text, metadata_json = render()
    if args.write:
        SEED_REGISTRY_PATH.write_text(seed_yaml, encoding="utf-8")
        ORDER_PATH.write_text(order_text, encoding="utf-8")
        ORDER_METADATA_PATH.write_text(metadata_json, encoding="utf-8")
    if args.check:
        expected = (
            (SEED_REGISTRY_PATH, seed_yaml),
            (ORDER_PATH, order_text),
            (ORDER_METADATA_PATH, metadata_json),
        )
        for path, content in expected:
            if path.read_text(encoding="utf-8") != content:
                raise SystemExit(f"stale/non-deterministic frozen artifact: {path}")
    print(json.dumps({
        "seed_registry_sha256": sha256_file(SEED_REGISTRY_PATH) if SEED_REGISTRY_PATH.exists() else sha256_bytes(seed_yaml.encode()),
        "order_sha256": sha256_file(ORDER_PATH) if ORDER_PATH.exists() else sha256_bytes(order_text.encode()),
        "attempt_count": 60,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
