import subprocess
from pathlib import Path

import yaml


REPO = Path(__file__).parents[2]
SCRIPT = (
    REPO / "experiments_v2/Calibration Experiments/C0-F-motion-style/"
    "motion_style_calibration_pipeline/static_preflight.py"
)
POLICY = REPO / "lfs_policy/config/lfs_policy.paper_current.yaml"


def run(policy):
    return subprocess.run(
        [str(Path("/home/yihuang/learning/LLM_swarm_ws/llm_env/bin/python")),
         str(SCRIPT), "--policy", str(policy), "--check-only"],
        cwd=REPO, text=True, capture_output=True,
    )


def write_mutation(tmp_path, mutate):
    data = yaml.safe_load(POLICY.read_text(encoding="utf-8"))
    mutate(data)
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def test_current_policy_passes_c0f_preflight():
    result = run(POLICY)
    assert result.returncode == 0, result.stdout + result.stderr


def test_c0f_owned_change_is_permitted(tmp_path):
    policy = write_mutation(
        tmp_path,
        lambda data: data["execution_profile"]["style_gains"].update(smooth=0.85),
    )
    result = run(policy)
    assert result.returncode == 0, result.stdout + result.stderr


def test_upstream_change_is_rejected(tmp_path):
    policy = write_mutation(
        tmp_path, lambda data: data["motion_limits"].update(velocity=4.9)
    )
    result = run(policy)
    assert result.returncode != 0
    assert "motion_limits.velocity" in result.stdout
