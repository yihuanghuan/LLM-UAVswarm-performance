import json
from types import SimpleNamespace

import pytest

from location_allocate import no_location


def candidate_payload():
    return {
        "lfs_version": "2.0",
        "mission": {"nodes": [{
            "type": "task",
            "task": {
                "task_id": 1,
                "U": [1, 2, 3],
                "F": "Circle",
                "c": {"mode": "auto"},
                "r": {"mode": "auto"},
                "T": {"mode": "auto"},
                "m": "normal",
                "s": 1.0,
                "q": "direct",
            },
        }]},
    }


class FakeCompletions:
    def __init__(self, payload):
        self.payload = payload

    def create(self, **_kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content=json.dumps(self.payload))
            )],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        )


class FakeClient:
    payload = None

    def __init__(self, **_kwargs):
        self.chat = SimpleNamespace(
            completions=FakeCompletions(type(self).payload)
        )


def configure_fake(monkeypatch, payload):
    FakeClient.payload = payload
    monkeypatch.setattr(no_location, "API_KEY", "test-key")
    monkeypatch.setattr(no_location, "OpenAI", FakeClient)
    monkeypatch.setattr(no_location, "append_llm_parse_log", lambda _row: None)
    monkeypatch.setattr(no_location.time, "sleep", lambda _seconds: None)


def test_candidate_parser_accepts_semantic_defaults(monkeypatch):
    configure_fake(monkeypatch, candidate_payload())

    parsed = no_location.parse_candidate_mission(
        "组成圆形", "当前可用无人机编号: [1,2,3]，总数: 3"
    )

    task = parsed["mission"]["nodes"][0]["task"]
    assert task["c"] == {"mode": "auto"}
    assert task["r"] == {"mode": "auto"}
    assert task["T"] == {"mode": "auto"}


def test_candidate_prompt_forbids_numerical_and_control_defaults():
    prompt = no_location.CANDIDATE_SYSTEM_PROMPT

    assert "Do not invent numeric c, r, or T" in prompt
    assert "LADRC gains" in prompt
    assert "task_sequences" in prompt
    assert "[0.0, 0.0, 1.5]" not in prompt


def test_candidate_parser_never_falls_back_to_legacy(monkeypatch):
    configure_fake(monkeypatch, {"task_sequences": []})

    with pytest.raises(no_location.CandidateParseError, match="non-Candidate"):
        no_location.parse_candidate_mission("组成圆形")


def test_legacy_parser_remains_explicitly_available(monkeypatch):
    payload = {
        "lfs_version": "1.0",
        "tasks": [{
            "task_id": 1,
            "U": [1, 2, 3],
            "F": "Circle",
            "c": [0.0, 0.0, 2.0],
            "r": 2.0,
            "T": 3.0,
            "m": "normal",
            "s": 1.0,
            "q": "direct",
        }],
    }
    configure_fake(monkeypatch, payload)

    parsed = no_location.parse_legacy_uav_command(
        "legacy fixture", "当前可用无人机编号: [1,2,3]，总数: 3"
    )

    assert parsed["task_sequences"][0]["duration_seconds"] == 3.0
