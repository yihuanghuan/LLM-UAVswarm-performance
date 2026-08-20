#!/usr/bin/env python3
"""Generate the complete deterministic C0-A-prereg-v3 conditional schedule."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
import random
import re


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs" / "c0a_prereg_v3.json"
DEFAULT_OUTPUT = ROOT / "trial_order_v3.json"
PROTOCOL = ROOT / "C0-A-prereg-v3.md"
ALL_FIELDS = (
    "stage",
    "candidate_id",
    "scenario_id",
    "signed_displacement_id",
    "seed",
    "duration_condition",
    "repetition",
    "trial_id",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-")


def number_code(value: float, width: int = 3) -> str:
    return f"{round(value * 100):0{width}d}"


def split_case(case_id: str) -> tuple[str, str]:
    scenario, displacement = case_id.split(":", 1)
    return scenario, displacement


def make_entry(
    *,
    stage: str,
    candidate_id: str,
    case_id: str,
    seed: int,
    repetition: int,
    duration_multiplier: float,
    activation: dict,
    candidate_parameters: dict,
) -> dict:
    scenario_id, signed_displacement_id = split_case(case_id)
    duration_code = number_code(duration_multiplier)
    trial_id = "-".join((
        "C0A-v3",
        slug(stage),
        slug(candidate_id),
        slug(scenario_id),
        slug(signed_displacement_id),
        f"D{duration_code}",
        f"S{seed}",
    ))
    return {
        "stage": stage,
        "candidate_id": candidate_id,
        "scenario_id": scenario_id,
        "signed_displacement_id": signed_displacement_id,
        "seed": seed,
        "duration_condition": {
            "kind": "T_MIN_MULTIPLIER",
            "value": duration_multiplier,
        },
        "repetition": repetition,
        "trial_id": trial_id,
        "activation": activation,
        "candidate_parameters": candidate_parameters,
    }


def shuffled(rng: random.Random, entries: list[dict]) -> list[dict]:
    rng.shuffle(entries)
    return entries


def a1_candidates(config: dict) -> list[tuple[str, dict]]:
    a1 = config["a1"]
    candidates = []
    for omega_c_multiplier, omega_o_multiplier in itertools.product(
        a1["omega_c_multipliers"], a1["omega_o_multipliers"]
    ):
        identifier = (
            f"A1-OC{number_code(omega_c_multiplier)}"
            f"-OO{number_code(omega_o_multiplier)}"
        )
        candidates.append((identifier, {
            "omega_c_multiplier": omega_c_multiplier,
            "omega_o_multiplier": omega_o_multiplier,
            "omega_c": [
                round(value * omega_c_multiplier, 12)
                for value in a1["baseline_omega_c"]
            ],
            "omega_o": [
                round(value * omega_o_multiplier, 12)
                for value in a1["baseline_omega_o"]
            ],
            "v_limit": a1["motion_limits"][0],
            "a_limit": a1["motion_limits"][1],
            "j_limit": a1["motion_limits"][2],
            "minimum_duration": a1["minimum_duration_s"],
        }))
    return candidates


def a2_candidates(config: dict) -> list[tuple[str, dict]]:
    candidates = []
    for package, minimum_duration in itertools.product(
        config["a2"]["motion_packages"],
        config["a2"]["minimum_duration_s"],
    ):
        v_limit, a_limit, j_limit = package
        identifier = (
            f"A2-V{number_code(v_limit, 3)}"
            f"-A{number_code(a_limit, 3)}"
            f"-J{number_code(j_limit, 4)}"
            f"-TF{number_code(minimum_duration, 3)}"
        )
        candidates.append((identifier, {
            "a1_winner_ref": "A1-WINNER",
            "v_limit": v_limit,
            "a_limit": a_limit,
            "j_limit": j_limit,
            "minimum_duration": minimum_duration,
        }))
    return candidates


def a3_candidates(config: dict) -> list[tuple[str, dict]]:
    candidates = []
    for omega_envelope, motion_multiplier in itertools.product(
        config["a3"]["omega_envelopes"],
        config["a3"]["motion_clamp_multipliers"],
    ):
        lower, upper = omega_envelope
        identifier = (
            f"A3-O{number_code(lower)}-{number_code(upper)}"
            f"-M{number_code(motion_multiplier)}"
        )
        candidates.append((identifier, {
            "a1_winner_ref": "A1-WINNER",
            "a2_winner_ref": "A2-WINNER",
            "omega_lower_multiplier": lower,
            "omega_upper_multiplier": upper,
            "motion_clamp_multiplier": motion_multiplier,
        }))
    return candidates


def generate(config: dict) -> dict:
    rng = random.Random(config["ordering_seed"])
    screening_seeds = config["screening_seeds"]
    confirmation_seeds = config["confirmation_seeds"]
    all_cases = list(config["single_uav_cases"])
    blocks: dict[str, list[dict]] = {}

    entries = []
    for (candidate_id, parameters), case_id, (repetition, seed) in itertools.product(
        a1_candidates(config),
        config["a1"]["screening_cases"],
        enumerate(screening_seeds, 1),
    ):
        entries.append(make_entry(
            stage="A1_SCREENING",
            candidate_id=candidate_id,
            case_id=case_id,
            seed=seed,
            repetition=repetition,
            duration_multiplier=config["a1"]["duration_multiplier"],
            activation={"type": "ALWAYS"},
            candidate_parameters=parameters,
        ))
    blocks["A1_SCREENING"] = shuffled(rng, entries)

    entries = []
    for rank, case_id, (repetition, seed) in itertools.product(
        range(1, config["confirmation_rank_slots"] + 1),
        all_cases,
        enumerate(confirmation_seeds, 1),
    ):
        candidate_id = f"A1-RANK-{rank:02d}"
        entries.append(make_entry(
            stage="A1_CONFIRMATION",
            candidate_id=candidate_id,
            case_id=case_id,
            seed=seed,
            repetition=repetition,
            duration_multiplier=config["a1"]["duration_multiplier"],
            activation={"type": "A1_SURVIVOR_RANK_AVAILABLE", "rank": rank},
            candidate_parameters={"candidate_ref": candidate_id},
        ))
    blocks["A1_CONFIRMATION"] = shuffled(rng, entries)

    entries = []
    for (candidate_id, parameters), case_id, duration, (repetition, seed) in itertools.product(
        a2_candidates(config),
        config["a2"]["screening_cases"],
        config["a2"]["duration_stress_multipliers"],
        enumerate(screening_seeds, 1),
    ):
        entries.append(make_entry(
            stage="A2_SCREENING",
            candidate_id=candidate_id,
            case_id=case_id,
            seed=seed,
            repetition=repetition,
            duration_multiplier=duration,
            activation={"type": "A1_WINNER_SELECTED"},
            candidate_parameters=parameters,
        ))
    blocks["A2_SCREENING"] = shuffled(rng, entries)

    entries = []
    for rank, case_id, duration, (repetition, seed) in itertools.product(
        range(1, config["confirmation_rank_slots"] + 1),
        all_cases,
        config["a2"]["duration_stress_multipliers"],
        enumerate(confirmation_seeds, 1),
    ):
        candidate_id = f"A2-RANK-{rank:02d}"
        entries.append(make_entry(
            stage="A2_CONFIRMATION",
            candidate_id=candidate_id,
            case_id=case_id,
            seed=seed,
            repetition=repetition,
            duration_multiplier=duration,
            activation={"type": "A2_SURVIVOR_RANK_AVAILABLE", "rank": rank},
            candidate_parameters={
                "candidate_ref": candidate_id,
                "a1_winner_ref": "A1-WINNER",
            },
        ))
    blocks["A2_CONFIRMATION"] = shuffled(rng, entries)

    entries = []
    for (candidate_id, parameters), case_id, (repetition, seed) in itertools.product(
        a3_candidates(config),
        config["a3"]["cases"],
        enumerate(confirmation_seeds, 1),
    ):
        entries.append(make_entry(
            stage="A3_VALIDATION",
            candidate_id=candidate_id,
            case_id=case_id,
            seed=seed,
            repetition=repetition,
            duration_multiplier=config["a3"]["duration_multiplier"],
            activation={"type": "A2_WINNER_SELECTED"},
            candidate_parameters=parameters,
        ))
    blocks["A3_VALIDATION"] = shuffled(rng, entries)

    entries = []
    for scenario_id in config["scale"]["scenario_order"]:
        scenario_entries = []
        for repetition, seed in enumerate(confirmation_seeds, 1):
            scenario_entries.append(make_entry(
                stage="SCALE_VALIDATION",
                candidate_id="FINAL-FROZEN-PACKAGE",
                case_id=(
                    f"{scenario_id}:"
                    f"{config['scale']['signed_displacement_id']}"
                ),
                seed=seed,
                repetition=repetition,
                duration_multiplier=config["scale"]["duration_multiplier"],
                activation={"type": "A3_WINNER_SELECTED"},
                candidate_parameters={
                    "a1_winner_ref": "A1-WINNER",
                    "a2_winner_ref": "A2-WINNER",
                    "a3_winner_ref": "A3-WINNER",
                    "uav_count": config["scale"]["uav_counts"][scenario_id],
                },
            ))
        entries.extend(shuffled(rng, scenario_entries))
    blocks["SCALE_VALIDATION"] = entries

    order = []
    for stage in (
        "A1_SCREENING",
        "A1_CONFIRMATION",
        "A2_SCREENING",
        "A2_CONFIRMATION",
        "A3_VALIDATION",
        "SCALE_VALIDATION",
    ):
        for entry in blocks[stage]:
            entry["schedule_index"] = len(order) + 1
            order.append(entry)

    return {
        "schema_version": 1,
        "calibration_id": config["calibration_id"],
        "protocol_version": config["protocol_version"],
        "dataset_class": config["dataset_class"],
        "protocol_sha256": sha256(PROTOCOL),
        "generator_sha256": sha256(Path(__file__)),
        "ordering_seed": config["ordering_seed"],
        "randomization": (
            f"one Python random.Random({config['ordering_seed']}) stream; stage blocks shuffled "
            "in protocol order; scale seeds shuffled within fixed M-1/M-4/M-8 order"
        ),
        "schedule_complete": True,
        "unresolved_protocol_ambiguity": 0,
        "fixed_conditions": config["fixed_conditions"],
        "stage_counts": {stage: len(items) for stage, items in blocks.items()},
        "potential_trial_count": len(order),
        "required_entry_fields": list(ALL_FIELDS),
        "entries": order,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    generated = json.dumps(generate(config), indent=2, sort_keys=True) + "\n"
    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != generated:
            raise SystemExit("trial order is missing or differs from deterministic generation")
        print(f"trial order deterministic check = PASS ({args.output})")
        return 0
    args.output.write_text(generated, encoding="utf-8")
    print(f"wrote {args.output} with {len(json.loads(generated)['entries'])} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
