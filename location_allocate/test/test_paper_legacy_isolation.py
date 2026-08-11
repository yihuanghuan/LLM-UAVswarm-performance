"""Architectural guardrails for the frozen paper and legacy paths."""

import inspect
from pathlib import Path

import pytest

from location_allocate import candidate_mission_runtime
from location_allocate import formation_geometry
from location_allocate import paper_candidate_parser
from location_allocate.legacy_scheduler import FormationGenerator
from location_allocate.policy_adapter import load_runtime_policy


PAPER_POLICY = (
    Path(__file__).parents[2] / "lfs_policy" / "config"
    / "lfs_policy.paper_current.yaml"
)


def test_paper_modules_do_not_import_legacy_parser_or_geometry():
    parser_source = inspect.getsource(paper_candidate_parser)
    runtime_source = inspect.getsource(candidate_mission_runtime)
    geometry_source = inspect.getsource(formation_geometry)

    assert "no_location" not in parser_source
    assert "legacy_parser" not in parser_source + runtime_source
    assert "legacy_scheduler" not in runtime_source + geometry_source
    assert "FormationGenerator" not in runtime_source + geometry_source


@pytest.mark.parametrize("formation", ["Triangle", "Polygon"])
def test_legacy_generator_keeps_historical_circle_reuse(formation):
    generator = FormationGenerator([0.0, 0.0, 2.0], 2.0)

    assert generator.generate(formation, 4) == generator.generate_circle(4)


def test_paper_policy_freezes_parallel_max_and_neutral_profile():
    config, policy = load_runtime_policy(PAPER_POLICY)

    assert config.allocator["parallel_d_plan_aggregation"] == "max"
    assert config.timing["final_recheck_tolerance"] == 0.0
    assert set(policy.profile.style_gains.values()) == {1.0}
    assert policy.profile.task_adaptation_type == "identity"
    assert config.controller.smoothing_alpha == 1.0


def test_paper_final_policy_is_not_prematurely_declared():
    assert not (PAPER_POLICY.parent / "lfs_policy.paper_v1.yaml").exists()
