import importlib.util
from pathlib import Path


ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "experiments/system_8uav/scripts/replay_parallel_group_d_plan.py"


def test_baseline_trial3_accepts_hard_feasible_residual_planning_risk():
    spec = importlib.util.spec_from_file_location("parallel_replay", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.replay()

    assert result["outcome"] == "accepted"
    assert result["d_hard"] == 1.0
    assert result["group_d_plan"] == 2.0
    assert result["d_hard"] <= result["final_min_distance"] < 2.0
    assert result["J_margin"] > 0.0
    assert result["final_metrics"]["hard_feasible"] is True
    assert result["final_metrics"]["planning_margin_met"] is False
    assert result["final_metrics"]["residual_planning_risk"] is True
    assert result["final_metrics"]["margin_intrusion_m"] > 0.0
    assert result["warnings"]
