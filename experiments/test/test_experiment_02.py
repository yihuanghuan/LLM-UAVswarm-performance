import json
import sys
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "experiments" / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lfs_ablation_experiment import (  # noqa: E402
    RunConfig,
    calculate_metrics,
    call_method,
    inspect_payload,
)


AVAILABLE_TEXT = "当前可用无人机编号: [1,2,3,4,5,6,7,8,9,10]，总数: 10"


def sample_item():
    return {
        "id": "simple_test",
        "type": "simple",
        "complexity": 1,
        "command": "1到3号机以[0,0,3]为中心组成半径2米的圆形编队，5秒完成",
        "ros_aux_info": AVAILABLE_TEXT,
        "expected_lfs": {
            "lfs_version": "1.0",
            "tasks": [{
                "task_id": 1,
                "U": [1, 2, 3],
                "F": "Circle",
                "c": [0, 0, 3],
                "r": 2,
                "T": 5,
                "m": "normal",
                "s": 1.0,
                "q": "direct",
            }],
        },
    }


def formal_payload(**overrides):
    task = {
        "task_id": 1,
        "U": [1, 2, 3],
        "F": "Circle",
        "c": [0, 0, 3],
        "r": 2,
        "T": 5,
        "m": "normal",
        "s": 1.0,
        "q": "direct",
    }
    task.update(overrides)
    return {"lfs_version": "1.0", "tasks": [task]}


def direct_payload():
    return {
        "tasks": [{
            "task_id": 1,
            "formation_type": "Circle",
            "duration": 5,
            "motion_style": "normal",
            "safety_factor": 1.0,
            "trigger": "direct",
            "uav_to_goal": [
                {"uav_id": 1, "goal": [2, 0, 3]},
                {"uav_id": 2, "goal": [-1, 1.7320508, 3]},
                {"uav_id": 3, "goal": [-1, -1.7320508, 3]},
            ],
        }],
    }


class FakeCompletions:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = 0

    def create(self, **_kwargs):
        payload = self.payloads[min(self.calls, len(self.payloads) - 1)]
        self.calls += 1
        usage = SimpleNamespace(prompt_tokens=100, completion_tokens=20)
        message = SimpleNamespace(content=json.dumps(payload, ensure_ascii=False))
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


class FakeClient:
    def __init__(self, payloads):
        self.chat = SimpleNamespace(completions=FakeCompletions(payloads))


def test_schema_only_compiles_unknown_uav_but_full_semantic_validator_rejects():
    payload = formal_payload(U=[1, 99])

    schema_only = inspect_payload("lfs_schema", payload, list(range(1, 11)))
    full = inspect_payload("lfs_schema_semantic", payload, list(range(1, 11)))

    assert schema_only["schema_valid"] is True
    assert schema_only["compilation_success"] is True
    assert schema_only["executable"] is False
    assert schema_only["error_stage"] == "execution"
    assert full["schema_valid"] is True
    assert full["semantic_valid"] is False
    assert full["compilation_success"] is False
    assert full["error_stage"] == "semantic"


def test_no_schema_method_does_not_retry_structurally_invalid_json():
    client = FakeClient([{"task_sequences": [{}]}])

    result, attempts = call_method(
        client,
        "task_json_no_schema",
        sample_item(),
        RunConfig(model="fake", max_retries=3),
        sleep_fn=lambda _seconds: None,
    )

    assert len(attempts) == 1
    assert result["retry_count"] == 0
    assert result["valid_json"] is True
    assert result["compilation_success"] is False
    assert result["executable"] is False


def test_direct_method_retries_native_contract_failure_then_succeeds():
    invalid = {"tasks": [{"task_id": 1}]}
    client = FakeClient([invalid, direct_payload()])

    result, attempts = call_method(
        client,
        "direct_waypoint",
        sample_item(),
        RunConfig(model="fake", max_retries=3),
        sleep_fn=lambda _seconds: None,
    )

    assert len(attempts) == 2
    assert result["retry_count"] == 1
    assert result["compilation_success"] is True
    assert result["executable"] is True
    assert result["invalid_formation_count"] == 0


def test_full_method_retries_semantic_failure():
    client = FakeClient([formal_payload(U=[1, 99]), formal_payload()])

    result, attempts = call_method(
        client,
        "lfs_schema_semantic",
        sample_item(),
        RunConfig(model="fake", max_retries=3),
        sleep_fn=lambda _seconds: None,
    )

    assert len(attempts) == 2
    assert attempts[0]["error_type"] == "semantic"
    assert result["semantic_valid"] is True
    assert result["executable"] is True


def test_metrics_count_missing_fields_and_wrong_formation_against_ground_truth():
    payload = formal_payload(F="Line")
    del payload["tasks"][0]["m"]
    inspection = {
        "rejection_category": "",
        "executable": False,
    }

    metrics = calculate_metrics("lfs_schema", sample_item(), payload, inspection)

    assert metrics["missing_field_count"] == 1
    assert metrics["required_field_slots"] == 8
    assert metrics["invalid_formation_count"] == 1
    assert metrics["formation_task_count"] == 1


def test_invalid_command_rejection_is_scored_separately():
    item = {
        "id": "invalid_test",
        "type": "invalid/ambiguous",
        "complexity": 2,
        "command": "99号机组成圆形",
        "ros_aux_info": AVAILABLE_TEXT,
        "expected_error": "unknown_uav",
    }
    inspection = inspect_payload(
        "lfs_schema_semantic",
        {"error": {"category": "unknown_uav"}},
        list(range(1, 11)),
    )

    metrics = calculate_metrics(
        "lfs_schema_semantic",
        item,
        {"error": {"category": "unknown_uav"}},
        inspection,
    )

    assert metrics["valid_input"] is False
    assert metrics["correct_rejection"] is True
    assert metrics["false_executable"] is False
