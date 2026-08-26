"""Validated projection of the E1 append-only event journal."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from e1_common import E1ToolingError


ATTEMPT_EVENT_TYPES = {
    "attempt_started",
    "provider_result",
    "attempt_completed",
}


@dataclass
class AttemptState:
    command_id: str
    attempt_index: int
    started: Dict[str, Any] | None = None
    provider_result: Dict[str, Any] | None = None
    completed: Dict[str, Any] | None = None


@dataclass
class RunState:
    provenance: Dict[str, Any] | None = None
    attempts: Dict[Tuple[str, int], AttemptState] = field(default_factory=dict)
    terminals: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def build(cls, events: List[Dict[str, Any]], order: List[str]) -> "RunState":
        state = cls()
        current_position = 0
        for event in events:
            event_type = event.get("event_type")
            payload = event.get("payload")
            if not isinstance(payload, dict):
                raise E1ToolingError("journal event payload is not an object")
            if event_type == "provenance":
                if state.provenance is not None or event.get("sequence") != 1:
                    raise E1ToolingError("provenance must be the unique first event")
                state.provenance = payload
                continue
            if state.provenance is None:
                raise E1ToolingError("attempt event precedes provenance")
            if event_type in ATTEMPT_EVENT_TYPES:
                if current_position >= len(order):
                    raise E1ToolingError("attempt exists after all commands terminated")
                command_id = payload.get("command_id")
                attempt_index = payload.get("attempt_index")
                if command_id != order[current_position]:
                    raise E1ToolingError(
                        f"attempt violates inference order: {command_id}; expected "
                        f"{order[current_position]}"
                    )
                if not isinstance(attempt_index, int) or not 1 <= attempt_index <= 3:
                    raise E1ToolingError("attempt index must be in 1..3")
                key = (command_id, attempt_index)
                attempt = state.attempts.setdefault(
                    key, AttemptState(command_id, attempt_index)
                )
                if event_type == "attempt_started":
                    if attempt.started is not None:
                        raise E1ToolingError(f"duplicate attempt start: {key}")
                    prior = [
                        item for (cid, index), item in state.attempts.items()
                        if cid == command_id and index < attempt_index
                    ]
                    if len(prior) != attempt_index - 1 or any(
                        item.completed is None for item in prior
                    ):
                        raise E1ToolingError(
                            f"attempt {attempt_index} began before prior retries completed"
                        )
                    attempt.started = payload
                elif event_type == "provider_result":
                    if attempt.started is None or attempt.provider_result is not None:
                        raise E1ToolingError(
                            f"provider result lacks unique start: {key}"
                        )
                    attempt.provider_result = payload
                else:
                    if attempt.provider_result is None or attempt.completed is not None:
                        raise E1ToolingError(
                            f"attempt completion lacks unique provider result: {key}"
                        )
                    attempt.completed = payload
                continue
            if event_type == "command_terminal":
                if current_position >= len(order):
                    raise E1ToolingError("extra terminal command record")
                command_id = payload.get("command_id")
                if command_id != order[current_position]:
                    raise E1ToolingError(
                        f"terminal record violates inference order: {command_id}; "
                        f"expected {order[current_position]}"
                    )
                if payload.get("inference_position") != current_position + 1:
                    raise E1ToolingError("terminal inference position mismatch")
                command_attempts = sorted(
                    (
                        item for (cid, _), item in state.attempts.items()
                        if cid == command_id
                    ),
                    key=lambda item: item.attempt_index,
                )
                if any(item.completed is None for item in command_attempts):
                    raise E1ToolingError(
                        f"terminal command has incomplete attempt: {command_id}"
                    )
                if payload.get("attempts_total") != len(command_attempts):
                    raise E1ToolingError("terminal retry accounting mismatch")
                if payload.get("outcome") not in {
                    "accepted", "rejected", "infrastructure_failure"
                }:
                    raise E1ToolingError("unknown terminal outcome")
                state.terminals.append(payload)
                current_position += 1
                continue
            raise E1ToolingError(f"unknown journal event type: {event_type!r}")
        return state

    def attempts_for(self, command_id: str) -> List[AttemptState]:
        return sorted(
            (
                attempt for (cid, _), attempt in self.attempts.items()
                if cid == command_id
            ),
            key=lambda attempt: attempt.attempt_index,
        )

    def terminal_ids(self) -> List[str]:
        return [str(terminal["command_id"]) for terminal in self.terminals]
