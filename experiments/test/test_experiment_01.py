import json
import sys
from pathlib import Path
from types import SimpleNamespace


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_experiment_01_dataset import build_dataset  # noqa: E402
from llm_parser_experiment import (  # noqa: E402
    RunConfig,
    call_method,
    evaluate_prediction,
    normalize_response,
    purify_json_content,
)
from plot_lfs_fix_baseline_comparison import (  # noqa: E402
    METHODS,
    build_comparison_rows,
)


AVAILABLE = list(range(1, 11))


def formal_task(**overrides):
    result = {
        "U": [1, 2, 3],
        "F": "Circle",
        "c": [0, 0, 3],
        "r": 2,
        "T": 5,
        "m": "normal",
        "s": 1,
        "q": "direct",
    }
    result.update(overrides)
    return result


def valid_item(command_type="simple", tasks=None):
    return {
        "id": "case",
        "type": command_type,
        "complexity": 1,
        "command": "test",
        "ros_aux_info": "当前可用无人机编号: [1,2,3,4]，总数: 4",
        "expected_lfs": {"lfs_version": "1.0", "tasks": tasks or [formal_task()]},
    }


def test_dataset_has_locked_distribution_and_unique_ids():
    rows = build_dataset()
    counts = {}
    for row in rows:
        counts[row["type"]] = counts.get(row["type"], 0) + 1
    assert len(rows) == 100
    assert len({row["id"] for row in rows}) == 100
    assert counts == {
        "simple": 18,
        "sequential": 18,
        "grouped": 18,
        "style-conditioned": 18,
        "safety-conditioned": 10,
        "invalid/ambiguous": 18,
    }


def test_plain_and_legacy_adapters_normalize_to_same_lfs():
    plain = normalize_response("plain_json", {"tasks": [{
        "uav_ids": [1, 2, 3], "formation": "Circle", "center": [0, 0, 3],
        "radius": 2, "duration": 5, "style": "normal", "safety_factor": 1,
        "trigger": "direct",
    }]}, AVAILABLE)
    legacy = normalize_response("few_shot_json", {"task_sequences": [{
        "uav_id": [1, 2, 3], "parametric_data": {"formation_type": "Circle", "formation_radius": 2},
        "global_center": [0, 0, 3], "duration_seconds": 5, "motion_profile": "normal",
        "iapf_safety_margin_factor": 1, "trigger_condition": "direct_execution",
    }]}, AVAILABLE)
    assert plain == legacy == {"lfs_version": "1.0", "tasks": [formal_task()]}


def test_plain_adapter_accepts_direct_object_and_common_aliases():
    normalized = normalize_response("plain_json", {
        "drone_ids": [1, 2, 3], "formation_type": "circular", "center": [0, 0, 3],
        "radius": 2, "duration_seconds": 5, "motion_profile": "normal",
        "safety_factor": 1, "execution": "direct",
    }, AVAILABLE)
    assert normalized["tasks"] == [formal_task()]


def test_json_purifier_removes_model_thinking_and_code_fences():
    raw = '<think>example {"not":"output"}</think>\n```json\n{"tasks": []}\n```'
    assert json.loads(purify_json_content(raw)) == {"tasks": []}


def test_dense_requires_complete_waypoints():
    payload = {"lfs_version": "1.0", "tasks": [{
        **formal_task(),
        "waypoints": [
            {"uav_id": 1, "position": [2, 0, 3]},
            {"uav_id": 2, "position": [-1, 1.732, 3]},
            {"uav_id": 3, "position": [-1, -1.732, 3]},
        ],
    }]}
    assert normalize_response("dense_waypoints", payload, AVAILABLE)["tasks"] == [formal_task()]
    payload["tasks"][0]["waypoints"].pop()
    try:
        normalize_response("dense_waypoints", payload, AVAILABLE)
    except ValueError as exc:
        assert "覆盖" in str(exc)
    else:
        raise AssertionError("incomplete dense waypoints should fail")


def test_lfs_draft_is_canonicalized_before_scoring():
    payload = {"lfs_version": "1.0", "tasks": [
        {"task_id": 1, "U": [1, 2, 3], "F": "Lineup", "c": [3, 0, 3], "r": 2, "T": 5},
        {"task_id": 2, "U": [1, 2, 3], "F": "Circle", "c": [0, 3, 3], "r": 2, "T": 7,
         "m": "aggressive", "s": 0.5, "depends_on": [1]},
    ]}

    normalized = normalize_response(
        "lfs_schema", payload, AVAILABLE,
        source_command="先组成一字长蛇阵，随后快速激进地组成圆形",
    )

    assert normalized["tasks"][0]["F"] == "Line"
    assert [task["q"] for task in normalized["tasks"]] == ["continuous", "direct"]
    assert normalized["tasks"][0]["m"] == "normal"
    assert normalized["tasks"][1]["m"] == "aggressive"
    assert normalized["tasks"][1]["s"] == 1.0


def test_grouped_task_order_is_ignored_but_sequence_order_is_not():
    first = formal_task(U=[1, 2], F="Circle")
    second = formal_task(U=[3, 4], F="Line")
    prediction = {"lfs_version": "1.0", "tasks": [second, first]}
    grouped = evaluate_prediction(valid_item("grouped", [first, second]), prediction)
    sequential = evaluate_prediction(valid_item("sequential", [first, second]), prediction)
    assert grouped["exact_task_accuracy"] == 1.0
    assert sequential["exact_task_accuracy"] == 0.0


def test_missing_and_extra_tasks_are_penalized():
    expected = [formal_task(), formal_task(U=[1, 2], F="Line")]
    metrics = evaluate_prediction(valid_item("sequential", expected), {"lfs_version": "1.0", "tasks": [expected[0]]})
    assert metrics["matched_task_coverage"] == 0.5
    assert metrics["field_accuracy"] == 0.5
    assert metrics["exact_task_accuracy"] == 0.0


def test_invalid_samples_only_score_rejection():
    item = {
        "id": "invalid", "type": "invalid/ambiguous", "complexity": 2,
        "command": "test", "ros_aux_info": "", "expected_error": "ambiguous",
    }
    metrics = evaluate_prediction(item, {"error": "ambiguous"})
    assert metrics["rejection_accuracy"] == 1.0
    assert metrics["field_accuracy"] == ""


class FakeCompletions:
    def __init__(self, contents):
        self.contents = iter(contents)

    def create(self, **_kwargs):
        content = next(self.contents)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        )


def test_api_runner_retries_invalid_json_and_accumulates_usage(monkeypatch):
    monkeypatch.setattr("llm_parser_experiment.time.sleep", lambda _seconds: None)
    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions([
        "not-json",
        json.dumps({"lfs_version": "1.0", "tasks": [formal_task()]}),
    ])))
    result, attempts = call_method(client, "lfs_schema", valid_item(), RunConfig(model="fake", max_retries=2))
    assert result["schema_valid"] is True
    assert result["retry_count"] == 1
    assert result["prompt_tokens"] == 20
    assert result["completion_tokens"] == 10
    assert len(attempts) == 2


def test_api_runner_stops_immediately_on_exhausted_plan():
    class ExhaustedCompletions:
        def create(self, **_kwargs):
            raise RuntimeError("已达到 Token Plan 用量上限 (2056)")

    client = SimpleNamespace(chat=SimpleNamespace(completions=ExhaustedCompletions()))
    result, attempts = call_method(client, "lfs_schema", valid_item(), RunConfig(model="fake", max_retries=3))
    assert result["error_type"] == "quota_exhausted"
    assert result["retry_count"] == 0
    assert len(attempts) == 1


def test_fixed_lfs_rows_selectively_replace_only_matching_baseline_rows():
    baseline = []
    for method in METHODS:
        for command_id in ("case_1", "case_2"):
            baseline.append({
                "command_id": command_id,
                "method": method,
                "exact_task_accuracy": "0.0",
            })
    fixed = [{
        "command_id": "case_2",
        "method": "lfs_schema",
        "exact_task_accuracy": "1.0",
    }]

    comparison = build_comparison_rows(baseline, fixed)

    assert len(comparison) == 8
    replaced = [
        row for row in comparison
        if row["method"] == "lfs_schema" and row["command_id"] == "case_2"
    ]
    assert replaced[0]["exact_task_accuracy"] == "1.0"
    assert replaced[0]["result_source"] == "fixed_lfs_rerun"
    assert sum(row["result_source"] == "fixed_lfs_rerun" for row in comparison) == 1


def test_fixed_lfs_comparison_rejects_duplicate_rerun_ids():
    baseline = [
        {"command_id": "case", "method": method}
        for method in METHODS
    ]
    fixed = [
        {"command_id": "case", "method": "lfs_schema"},
        {"command_id": "case", "method": "lfs_schema"},
    ]

    try:
        build_comparison_rows(baseline, fixed)
    except ValueError as exc:
        assert "重复" in str(exc)
    else:
        raise AssertionError("duplicate fixed LFS command IDs should fail")
