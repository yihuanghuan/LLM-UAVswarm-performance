"""Architectural guardrails for the frozen paper and legacy paths."""

import inspect
from pathlib import Path

import pytest

from location_allocate import candidate_mission_runtime
from location_allocate import formation_geometry
from location_allocate import paper_candidate_parser
from location_allocate import paper_lfs_validator
from location_allocate import paper_runtime
from location_allocate.legacy_scheduler import FormationGenerator
from location_allocate.policy_adapter import load_runtime_policy
from location_allocate.prompt_loader import load_paper_prompt_bundle


PAPER_POLICY = (
    Path(__file__).parents[2] / "lfs_policy" / "config"
    / "lfs_policy.paper_current.yaml"
)


def test_paper_modules_do_not_import_legacy_parser_or_geometry():
    parser_source = inspect.getsource(paper_candidate_parser)
    runtime_source = inspect.getsource(candidate_mission_runtime)
    ros_runtime_source = inspect.getsource(paper_runtime)
    validator_source = inspect.getsource(paper_lfs_validator)
    geometry_source = inspect.getsource(formation_geometry)

    assert "no_location" not in parser_source
    paper_source = (
        parser_source + runtime_source + ros_runtime_source
        + validator_source + geometry_source
    )
    assert "legacy_parser" not in paper_source
    assert "legacy_scheduler" not in paper_source
    assert "FormationGenerator" not in paper_source
    assert "task_sequences" not in paper_source


@pytest.mark.parametrize("formation", ["Triangle", "Polygon"])
def test_legacy_generator_keeps_historical_circle_reuse(formation):
    generator = FormationGenerator([0.0, 0.0, 2.0], 2.0)

    assert generator.generate(formation, 4) == generator.generate_circle(4)


def test_paper_policy_freezes_parallel_max_and_neutral_profile():
    config, policy = load_runtime_policy(PAPER_POLICY)

    assert config.allocator["parallel_d_plan_aggregation"] == "max"
    assert set(config.allocator) == {
        "sample_hz",
        "comparison_tolerance",
        "parallel_d_plan_aggregation",
    }
    assert config.timing["final_recheck_tolerance"] == 0.0
    assert set(policy.profile.style_gains.values()) == {1.0}
    assert policy.profile.task_adaptation_type == "identity"
    assert config.controller.smoothing_alpha == 1.0


def test_paper_final_policy_is_not_prematurely_declared():
    assert not (PAPER_POLICY.parent / "lfs_policy.paper_v1.yaml").exists()


def test_only_current_paper_prompt_and_schema_resources_exist():
    root = Path(__file__).parents[2]
    prompts = root / "location_allocate" / "prompts"
    schemas = root / "schemas"

    assert not list(prompts.glob("paper_candidate_en_v1_*"))
    assert not (schemas / "paper_candidate_schema_v1.json").exists()
    assert not (schemas / "lfs_schema.json").exists()
    assert (schemas / "legacy" / "lfs_schema_v1.json").is_file()
    bundle = load_paper_prompt_bundle()
    assert bundle.prompt_version == "paper-candidate-en-v2"
    assert bundle.schema_version == "paper-candidate-schema-v2"
