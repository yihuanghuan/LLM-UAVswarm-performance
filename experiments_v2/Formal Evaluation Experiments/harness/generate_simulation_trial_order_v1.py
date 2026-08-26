#!/usr/bin/env python3
"""Generate the frozen E2-E5 global trial permutation without running trials."""

import hashlib
import random
import sys


ORDERING_SEED = 20260827
EXPECTED_CANONICAL_SHA256 = "6e37ae0aa3fa7e24e13f81301c67cdb5dfe3fc24fa148db03d3c680110f081ca"
EXPECTED_PERMUTATION_SHA256 = "db28bf8d734e1f206987519e91ff27c67b2d9ab2971aeb68c4e13735762f1dce"


def canonical_ids():
    result = []
    for scenario in [
        "E2-RSV-01", "E2-PES-01", "E2-RC-01",
        "E2-QS-01", "E2-AT-01", "E2-DF-01",
    ]:
        for shift in ["NO_SHIFT", "SHIFT"]:
            for condition in ["EARLY", "LATE"]:
                for seed in range(52101, 52106):
                    result.append(
                        f"{scenario}__{shift}__{condition}__S{seed}"
                    )
    for scenario in [
        "E3-A-01", "E3-A-02", "E3-B-01",
        "E3-B-02", "E3-C-01", "E3-C-02",
    ]:
        for condition in ["P1_F1", "P1_F0", "P0_F1", "P0_F0"]:
            for seed in range(53101, 53116):
                result.append(f"{scenario}__{condition}__S{seed}")
    for scenario in [
        "E4A-HORIZONTAL", "E4A-VERTICAL", "E4A-DIAGONAL-3D",
    ]:
        for style in ["smooth", "normal", "aggressive"]:
            for seed in range(54101, 54106):
                result.append(f"{scenario}__{style}__S{seed}")
    for scenario in [
        "E4B-FEASIBLE-EXPLICIT-T", "E4B-INFEASIBLE-EXPLICIT-T",
        "E4B-AUTO-T", "E4B-SAFETY-ACTIVE",
    ]:
        for style in ["smooth", "normal", "aggressive"]:
            for seed in range(54201, 54206):
                result.append(f"{scenario}__{style}__S{seed}")
    for scenario in [
        "E5-SIMPLE", "E5-REL-QUAL", "E5-SEQUENTIAL",
        "E5-PARALLEL", "E5-MIXED-HIGH",
    ]:
        for seed in range(55101, 55106):
            result.append(f"{scenario}__Full_Method__S{seed}")
    return result


def digest(ids):
    return hashlib.sha256(("\n".join(ids) + "\n").encode("utf-8")).hexdigest()


def main():
    ids = canonical_ids()
    if len(ids) != 610 or digest(ids) != EXPECTED_CANONICAL_SHA256:
        raise RuntimeError("canonical trial population does not match freeze")
    random.Random(ORDERING_SEED).shuffle(ids)
    if digest(ids) != EXPECTED_PERMUTATION_SHA256:
        raise RuntimeError("trial permutation does not match freeze")
    sys.stdout.write("\n".join(ids) + "\n")


if __name__ == "__main__":
    main()
