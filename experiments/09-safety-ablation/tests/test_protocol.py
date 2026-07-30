import json
from pathlib import Path

from location_allocate.lfs_validator import validate_and_compile_lfs

from experiment_common import (
    allocate_targets,
    load_configuration,
    paired_input_digest,
    perturb_groups,
    scenario_groups,
)
from run_batch import protocol_arms, protocol_trials, trial_command


def test_protocol_has_16_pilot_and_240_formal_trials():
    assert len(protocol_arms()) == 16
    trials = protocol_trials()
    assert sum(trial.phase == "pilot" for trial in trials) == 16
    assert sum(trial.phase == "formal" for trial in trials) == 240


def test_all_formal_variants_reuse_identical_seeds():
    trials = [trial for trial in protocol_trials() if trial.phase == "formal"]
    by_scenario = {}
    for trial in trials:
        by_scenario.setdefault(trial.scenario, {}).setdefault(
            trial.method, set()).add(trial.seed)
    for variants in by_scenario.values():
        assert list(variants) == ["B0", "P", "E", "Full"]
        seeds = list(variants.values())
        assert all(value == seeds[0] for value in seeds)
        assert len(seeds[0]) == 15


def test_only_representative_formal_seed_records_rosbag(tmp_path: Path):
    trials = protocol_trials()
    representative = next(
        trial for trial in trials
        if trial.phase == "formal" and trial.seed == 4201)
    ordinary = next(
        trial for trial in trials
        if trial.phase == "formal" and trial.seed == 4202)
    pilot = next(trial for trial in trials if trial.phase == "pilot")
    assert "--no-rosbag" not in trial_command(
        representative, "batch", False, tmp_path)
    assert "--no-rosbag" in trial_command(ordinary, "batch", False, tmp_path)
    assert "--no-rosbag" in trial_command(pilot, "batch", False, tmp_path)


def test_paired_digest_ignores_variant():
    _, _, scenario = load_configuration("s1_crossing_4", "B0")
    groups = [{
        "uav_ids": scenario["uav_ids"],
        "initial": scenario["initial_positions"],
        "targets": scenario["target_positions"],
    }]
    assert paired_input_digest(scenario, groups, 4201) == paired_input_digest(
        scenario, groups, 4201)


def test_s3_frozen_candidate_has_planning_layer_separation():
    defaults, _, scenario = load_configuration(
        "s3_staggered_dynamic_crossing", "B0")
    groups = perturb_groups(
        scenario_groups(scenario), 9001,
        float(scenario["randomization_range"]))
    _, distance = allocate_targets(
        groups, float(scenario["duration"]), "distance_hungarian",
        float(defaults["safety"]["d_assignment"]))
    _, safe = allocate_targets(
        groups, float(scenario["duration"]), "safety_aware",
        float(defaults["safety"]["d_assignment"]))
    assert safe["proximity_crossings"] < distance["proximity_crossings"]
    assert safe["min_distance"] >= distance["min_distance"] + 0.3


def test_all_pre_generated_lfs_artifacts_validate():
    root = Path(__file__).resolve().parents[1] / "configs" / "lfs"
    paths = sorted(root.glob("*.json"))
    assert len(paths) == 4
    for path in paths:
        compiled = validate_and_compile_lfs(
            json.loads(path.read_text(encoding="utf-8")),
            available_uav_ids=list(range(1, 11)))
        assert len(compiled["task_sequences"]) == 1
