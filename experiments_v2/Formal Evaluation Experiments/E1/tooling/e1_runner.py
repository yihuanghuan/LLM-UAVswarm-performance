#!/usr/bin/env python3
"""Sealed-order E1 runner using the frozen production Candidate parser."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import time
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional

from e1_common import (
    E1_DIR,
    MISSING,
    REPO_ROOT,
    RUNTIME_MANIFEST_PATH,
    UNAVAILABLE,
    E1ToolingError,
    availability_text,
    load_dataset,
    load_order,
    load_yaml,
    utc_now,
)
from e1_journal import EventJournal
from e1_provenance import ProvenanceError, validate_provenance
from e1_run_state import AttemptState, RunState


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return _json_safe(model_dump(mode="json"))
        except TypeError:
            return _json_safe(model_dump())
    if hasattr(value, "__dict__"):
        return _json_safe(vars(value))
    return repr(value)


def _attribute(value: Any, name: str, missing: Dict[str, str] = MISSING) -> Any:
    result = getattr(value, name, None)
    return _json_safe(result) if result is not None else dict(missing)


def _raw_content(response: Any) -> Any:
    try:
        content = response.choices[0].message.content
    except Exception:
        return dict(UNAVAILABLE)
    return content if content is not None else dict(MISSING)


def _usage(response: Any) -> Dict[str, Any]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {
            "prompt_tokens": dict(MISSING),
            "completion_tokens": dict(MISSING),
            "total_tokens": dict(MISSING),
        }
    return {
        key: _attribute(usage, key)
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
    }


def _response_metadata(response: Any) -> Dict[str, Any]:
    choice = None
    try:
        choice = response.choices[0]
    except Exception:
        pass
    return {
        "response_id": _attribute(response, "id", UNAVAILABLE),
        "created": _attribute(response, "created", UNAVAILABLE),
        "finish_reason": (
            _attribute(choice, "finish_reason", UNAVAILABLE)
            if choice is not None else dict(UNAVAILABLE)
        ),
        "system_fingerprint": _attribute(
            response, "system_fingerprint", UNAVAILABLE
        ),
        "service_tier": _attribute(response, "service_tier", UNAVAILABLE),
        "response_headers": dict(UNAVAILABLE),
        "provider_response_object": _json_safe(response),
    }


def _exception_record(exc: BaseException) -> Dict[str, Any]:
    return {
        "type": type(exc).__name__,
        "module": type(exc).__module__,
        "message": str(exc),
        "status_code": _attribute(exc, "status_code", UNAVAILABLE),
        "request_id": _attribute(exc, "request_id", UNAVAILABLE),
        "body": _attribute(exc, "body", UNAVAILABLE),
    }


def _replayed_exception(record: Dict[str, Any]) -> Exception:
    name = str(record.get("type") or "ReplayedProviderError")
    exception_type = type(name, (Exception,), {})
    return exception_type(str(record.get("message") or "replayed provider failure"))


class _InstrumentedCompletions:
    def __init__(
        self,
        underlying: Any,
        journal: EventJournal,
        command: Dict[str, Any],
        order_position: int,
        request_contract: Dict[str, Any],
    ) -> None:
        self._underlying = underlying
        self._journal = journal
        self._command = command
        self._order_position = order_position
        self._request_contract = request_contract
        self.local_call_index = 0
        self.current_attempt_index: Optional[int] = None

    def _state(self) -> RunState:
        return RunState.build(self._journal.read(), load_order())

    def _request_metadata(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        messages = _json_safe(kwargs.get("messages", dict(MISSING)))
        message_bytes = json.dumps(
            messages, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return {
            "model": kwargs.get("model", dict(MISSING)),
            "temperature": kwargs.get("temperature", dict(MISSING)),
            "top_p": kwargs.get("top_p", dict(MISSING)),
            "max_tokens": kwargs.get("max_tokens", dict(MISSING)),
            "response_format": _json_safe(
                kwargs.get("response_format", dict(MISSING))
            ),
            "timeout_seconds": kwargs.get("timeout", dict(MISSING)),
            "messages": messages,
            "messages_sha256": hashlib.sha256(message_bytes).hexdigest(),
        }

    def _assert_request_contract(self, metadata: Dict[str, Any]) -> None:
        expected = self._request_contract
        actual = {
            "model": metadata["model"],
            "temperature": metadata["temperature"],
            "top_p": metadata["top_p"],
            "max_tokens": metadata["max_tokens"],
            "response_format": metadata["response_format"],
            "timeout_seconds": metadata["timeout_seconds"],
        }
        if actual != expected:
            raise E1ToolingError(
                f"production parser request deviated from frozen manifest: "
                f"actual={actual!r}, expected={expected!r}"
            )

    def _replay(self, result: Dict[str, Any]) -> Any:
        if result["provider_status"] == "exception":
            raise _replayed_exception(result["exception"])
        raw_response = result["raw_response"]
        if not isinstance(raw_response, str):
            raise E1ToolingError("cannot replay provider response without raw text")
        usage_record = result["provider_token_usage"]
        usage = SimpleNamespace(**{
            key: (value if isinstance(value, int) else None)
            for key, value in usage_record.items()
        })
        metadata = result["response_metadata"]
        model = result["provider_returned_model_field"]
        return SimpleNamespace(
            id=(
                metadata.get("response_id")
                if isinstance(metadata.get("response_id"), str) else None
            ),
            model=model if isinstance(model, str) else None,
            created=(
                metadata.get("created")
                if isinstance(metadata.get("created"), int) else None
            ),
            choices=[SimpleNamespace(
                message=SimpleNamespace(content=raw_response),
                finish_reason=(
                    metadata.get("finish_reason")
                    if isinstance(metadata.get("finish_reason"), str) else None
                ),
            )],
            usage=usage,
        )

    def create(self, **kwargs: Any) -> Any:
        self.local_call_index += 1
        attempt_index = self.local_call_index
        self.current_attempt_index = attempt_index
        state = self._state()
        key = (self._command["id"], attempt_index)
        existing = state.attempts.get(key)
        request_metadata = self._request_metadata(kwargs)
        self._assert_request_contract(request_metadata)

        resumed_uncertain = existing is not None
        if existing is None:
            self._journal.append("attempt_started", {
                "command_id": self._command["id"],
                "attempt_index": attempt_index,
                "inference_position": self._order_position,
                "request_timestamp_utc": utc_now(),
                "request_metadata": request_metadata,
            })
            state = self._state()
            existing = state.attempts[key]
        elif existing.started["request_metadata"] != request_metadata:
            raise E1ToolingError("resumed request metadata differs from original")

        if existing.provider_result is not None:
            return self._replay(existing.provider_result)
        if resumed_uncertain:
            raise E1ToolingError(
                f"ambiguous formal attempt resume for {self._command['id']} "
                f"attempt {attempt_index}: attempt_started exists without "
                "provider_result; no provider request was issued and human "
                "governance review is required"
            )

        started = time.perf_counter()
        try:
            completions = self._underlying
            if hasattr(completions, "create_for_attempt"):
                response = completions.create_for_attempt(attempt_index, **kwargs)
            else:
                response = completions.create(**kwargs)
        except Exception as exc:
            latency_ms = (time.perf_counter() - started) * 1000.0
            self._journal.append("provider_result", {
                "command_id": self._command["id"],
                "attempt_index": attempt_index,
                "provider_status": "exception",
                "provider_returned_model_field": dict(UNAVAILABLE),
                "request_id": _attribute(exc, "request_id", UNAVAILABLE),
                "response_metadata": dict(UNAVAILABLE),
                "provider_wall_latency_ms": latency_ms,
                "provider_token_usage": {
                    "prompt_tokens": dict(MISSING),
                    "completion_tokens": dict(MISSING),
                    "total_tokens": dict(MISSING),
                },
                "raw_response": dict(UNAVAILABLE),
                "exception": _exception_record(exc),
                "resumed_uncertain_attempt": resumed_uncertain,
            })
            raise
        latency_ms = (time.perf_counter() - started) * 1000.0
        self._journal.append("provider_result", {
            "command_id": self._command["id"],
            "attempt_index": attempt_index,
            "provider_status": "returned",
            "provider_returned_model_field": _attribute(
                response, "model", UNAVAILABLE
            ),
            "request_id": _attribute(response, "id", UNAVAILABLE),
            "response_metadata": _response_metadata(response),
            "provider_wall_latency_ms": latency_ms,
            "provider_token_usage": _usage(response),
            "raw_response": _raw_content(response),
            "exception": dict(UNAVAILABLE),
            "resumed_uncertain_attempt": resumed_uncertain,
        })
        return response


class _InstrumentedOpenAI:
    def __init__(
        self,
        underlying_factory: Callable[..., Any],
        journal: EventJournal,
        command: Dict[str, Any],
        order_position: int,
        request_contract: Dict[str, Any],
    ) -> None:
        self._underlying_factory = underlying_factory
        self._journal = journal
        self._command = command
        self._order_position = order_position
        self._request_contract = request_contract
        self.last_completions: Optional[_InstrumentedCompletions] = None

    def __call__(self, **kwargs: Any) -> Any:
        client = self._underlying_factory(**kwargs)
        wrapped = _InstrumentedCompletions(
            client.chat.completions,
            self._journal,
            self._command,
            self._order_position,
            self._request_contract,
        )
        self.last_completions = wrapped
        return SimpleNamespace(chat=SimpleNamespace(completions=wrapped))


class FixtureOpenAI:
    """Synthetic fixture client; it never opens a network connection."""

    def __init__(self, planned_attempts: List[Dict[str, Any]], **_kwargs: Any):
        self.chat = SimpleNamespace(
            completions=_FixtureCompletions(planned_attempts)
        )


class _FixtureCompletions:
    def __init__(self, planned_attempts: List[Dict[str, Any]]) -> None:
        self._planned = planned_attempts

    def create_for_attempt(self, attempt_index: int, **_kwargs: Any) -> Any:
        if attempt_index > len(self._planned):
            raise RuntimeError(f"fixture lacks attempt {attempt_index}")
        planned = self._planned[attempt_index - 1]
        if "exception" in planned:
            details = planned["exception"]
            name = str(details.get("type", "FixtureProviderError"))
            raise type(name, (Exception,), {})(str(details.get("message", "fixture")))
        usage = planned.get("usage")
        usage_object = None
        if isinstance(usage, dict):
            usage_object = SimpleNamespace(
                prompt_tokens=usage.get("prompt_tokens"),
                completion_tokens=usage.get("completion_tokens"),
                total_tokens=usage.get("total_tokens"),
            )
        return SimpleNamespace(
            id=planned.get("response_id"),
            model=planned.get("model"),
            created=planned.get("created"),
            system_fingerprint=planned.get("system_fingerprint"),
            service_tier=planned.get("service_tier"),
            choices=[SimpleNamespace(
                message=SimpleNamespace(content=planned.get("raw_response")),
                finish_reason=planned.get("finish_reason"),
            )],
            usage=usage_object,
        )


@contextmanager
def _production_parser_instrumentation(
    parser: Any,
    openai_factory: _InstrumentedOpenAI,
    on_parse_log: Callable[[Dict[str, Any]], None],
    mock_mode: bool,
):
    originals = {
        "OpenAI": parser.OpenAI,
        "API_KEY": parser.API_KEY,
        "append_llm_parse_log": parser.append_llm_parse_log,
        "append_raw_response_log": parser.append_raw_response_log,
        "sleep": parser.time.sleep,
    }
    parser.OpenAI = openai_factory
    parser.append_llm_parse_log = on_parse_log
    parser.append_raw_response_log = lambda *_args, **_kwargs: None
    if mock_mode:
        parser.API_KEY = "synthetic-fixture-key"
        parser.time.sleep = lambda _seconds: None
    try:
        yield
    finally:
        parser.OpenAI = originals["OpenAI"]
        parser.API_KEY = originals["API_KEY"]
        parser.append_llm_parse_log = originals["append_llm_parse_log"]
        parser.append_raw_response_log = originals["append_raw_response_log"]
        parser.time.sleep = originals["sleep"]


def _terminal_stage(
    completion: Optional[Dict[str, Any]],
    provider_result: Optional[Dict[str, Any]],
) -> str:
    if provider_result and provider_result.get("provider_status") == "exception":
        return "provider_call"
    if not completion:
        return "parser_initialization"
    if completion.get("schema_valid") is True:
        return "candidate_early_validation"
    if completion.get("valid_json") is not True:
        return "parser_unparseable"
    reason = str(completion.get("error_reason", ""))
    if "schema validation failed" in reason:
        return "schema_validation"
    return "candidate_early_validation"


def _total_terminal_latency(attempts: List[AttemptState]) -> Any:
    latencies = []
    for attempt in attempts:
        if attempt.completed is None:
            return dict(MISSING)
        value = attempt.completed.get("attempt_wall_latency_ms")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return dict(MISSING)
        latencies.append(float(value))
    if not latencies:
        return dict(MISSING)
    return sum(latencies) + 2000.0 * max(0, len(latencies) - 1)


class E1Runner:
    def __init__(
        self,
        run_dir: Path,
        *,
        mock_mode: bool = False,
        fixture_commands: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        journal: Optional[EventJournal] = None,
    ) -> None:
        self.run_dir = Path(run_dir)
        self.journal = journal or EventJournal(self.run_dir / "journal")
        self.mock_mode = mock_mode
        self.fixture_commands = fixture_commands or {}
        self.dataset = load_dataset()
        self.records = {record["id"]: record for record in self.dataset}
        self.order = load_order()
        runtime = load_yaml(RUNTIME_MANIFEST_PATH)
        self.request_contract = {
            "model": runtime["provider"]["exact_model_name"],
            "temperature": runtime["decoding"]["temperature"],
            "top_p": runtime["decoding"]["top_p"],
            "max_tokens": runtime["decoding"]["max_tokens"],
            "response_format": runtime["decoding"]["response_format"],
            "timeout_seconds": runtime["retry_and_failure_policy"][
                "timeout_per_attempt_seconds"
            ],
        }

    def _load_parser(self):
        import sys

        package_root = REPO_ROOT / "location_allocate"
        if str(package_root) not in sys.path:
            sys.path.insert(0, str(package_root))
        from location_allocate import paper_candidate_parser

        if Path(paper_candidate_parser.__file__).resolve() != (
            REPO_ROOT / "location_allocate/location_allocate/paper_candidate_parser.py"
        ).resolve():
            raise E1ToolingError("production parser imported from wrong repository")
        return paper_candidate_parser

    def _underlying_factory(self, parser: Any, command_id: str):
        if not self.mock_mode:
            if parser.OpenAI is None:
                raise E1ToolingError("frozen OpenAI-compatible client unavailable")
            return parser.OpenAI
        attempts = self.fixture_commands.get(command_id)
        if attempts is None:
            raise E1ToolingError(f"fixture lacks command: {command_id}")
        return lambda **kwargs: FixtureOpenAI(attempts, **kwargs)

    def _ensure_provenance(self, report: Dict[str, Any]) -> None:
        events = self.journal.read()
        dataset_class = (
            "synthetic_validation" if self.mock_mode else "formal_evaluation"
        )
        payload = {
            "run_mode": "mock_synthetic" if self.mock_mode else "real_provider",
            "dataset_class": dataset_class,
            "accepted_formal_result": False,
            "result_status": (
                "synthetic_not_formal"
                if self.mock_mode else "pending_post_run_completeness_audit"
            ),
            "validation_report": report,
        }
        if not events:
            self.journal.append("provenance", payload)
            return
        state = RunState.build(events, self.order)
        if state.provenance is None:
            raise E1ToolingError("existing run lacks provenance")
        for key in (
            "run_mode", "dataset_class", "accepted_formal_result", "result_status"
        ):
            if state.provenance.get(key) != payload[key]:
                raise E1ToolingError(f"resume provenance mismatch: {key}")
        previous_report = state.provenance.get("validation_report", {})
        for key in (
            "source_final_preflight_commit",
            "runtime_baseline_tag",
            "runtime_baseline_commit",
        ):
            if previous_report.get(key) != report.get(key):
                raise E1ToolingError(f"resume frozen provenance mismatch: {key}")

    def _append_completion(
        self,
        command: Dict[str, Any],
        wrapper: _InstrumentedOpenAI,
        row: Dict[str, Any],
    ) -> None:
        completions = wrapper.last_completions
        if completions is None or completions.current_attempt_index is None:
            raise E1ToolingError("parser log has no matching provider attempt")
        attempt_index = completions.current_attempt_index
        if row.get("retry_count") != attempt_index - 1:
            raise E1ToolingError("production retry index mismatch")
        state = RunState.build(self.journal.read(), self.order)
        existing = state.attempts.get((command["id"], attempt_index))
        if existing is None or existing.provider_result is None:
            raise E1ToolingError("parser completion precedes provider evidence")
        if existing.completed is not None:
            return
        provider_result = existing.provider_result
        self.journal.append("attempt_completed", {
            "command_id": command["id"],
            "attempt_index": attempt_index,
            "format_compliant": bool(row.get("format_compliant")),
            "valid_json": bool(row.get("valid_json")),
            "schema_valid": bool(row.get("schema_valid")),
            "parser_error_type": row.get("error_type") or dict(UNAVAILABLE),
            "error_reason": row.get("error_reason") or dict(UNAVAILABLE),
            "attempt_wall_latency_ms": row.get("latency_ms"),
            "terminal_gate": _terminal_stage(row, provider_result),
        })

    def _run_command(self, parser: Any, command: Dict[str, Any], position: int):
        state = RunState.build(self.journal.read(), self.order)
        ambiguous = [
            attempt for attempt in state.attempts_for(command["id"])
            if attempt.started is not None and attempt.provider_result is None
        ]
        if ambiguous:
            attempt_indexes = [attempt.attempt_index for attempt in ambiguous]
            raise E1ToolingError(
                f"ambiguous formal attempt resume for {command['id']} attempt(s) "
                f"{attempt_indexes}: attempt_started exists without "
                "provider_result; no provider request was issued and human "
                "governance review is required"
            )
        underlying = self._underlying_factory(parser, command["id"])
        wrapper = _InstrumentedOpenAI(
            underlying,
            self.journal,
            command,
            position,
            self.request_contract,
        )

        def on_parse_log(row: Dict[str, Any]) -> None:
            self._append_completion(command, wrapper, row)

        try:
            with _production_parser_instrumentation(
                parser, wrapper, on_parse_log, self.mock_mode
            ):
                candidate = parser.parse_candidate_mission(
                    command["command"], availability_text(command["availability"])
                )
        except parser.CandidateParseError as exc:
            state = RunState.build(self.journal.read(), self.order)
            attempts = state.attempts_for(command["id"])
            last = attempts[-1] if attempts else None
            provider_result = last.provider_result if last else None
            completion = last.completed if last else None
            infrastructure = (
                provider_result is None
                or provider_result.get("provider_status") == "exception"
            )
            outcome = "infrastructure_failure" if infrastructure else "rejected"
            self.journal.append("command_terminal", {
                "command_id": command["id"],
                "inference_position": position,
                "outcome": outcome,
                "attempts_total": len(attempts),
                "total_latency_ms": _total_terminal_latency(attempts),
                "candidate": dict(UNAVAILABLE),
                "terminal_retry_outcome": {
                    "maximum_attempts": 3,
                    "attempts_used": len(attempts),
                    "terminal_gate": _terminal_stage(completion, provider_result),
                    "exception": _exception_record(exc),
                },
            })
            return
        except Exception as exc:
            state = RunState.build(self.journal.read(), self.order)
            attempts = state.attempts_for(command["id"])
            if any(attempt.completed is None for attempt in attempts):
                raise
            self.journal.append("command_terminal", {
                "command_id": command["id"],
                "inference_position": position,
                "outcome": "infrastructure_failure",
                "attempts_total": len(attempts),
                "total_latency_ms": _total_terminal_latency(attempts),
                "candidate": dict(UNAVAILABLE),
                "terminal_retry_outcome": {
                    "maximum_attempts": 3,
                    "attempts_used": len(attempts),
                    "terminal_gate": "parser_initialization",
                    "exception": _exception_record(exc),
                },
            })
            return

        state = RunState.build(self.journal.read(), self.order)
        attempts = state.attempts_for(command["id"])
        self.journal.append("command_terminal", {
            "command_id": command["id"],
            "inference_position": position,
            "outcome": "accepted",
            "attempts_total": len(attempts),
            "total_latency_ms": _total_terminal_latency(attempts),
            "candidate": candidate,
            "terminal_retry_outcome": {
                "maximum_attempts": 3,
                "attempts_used": len(attempts),
                "terminal_gate": "candidate_early_validation",
                "exception": dict(UNAVAILABLE),
            },
        })

    def run(
        self,
        *,
        max_new_commands: Optional[int] = None,
        provenance_report: Optional[Dict[str, Any]] = None,
    ) -> RunState:
        report = provenance_report or validate_provenance(
            require_clean=not self.mock_mode,
            verify_environment=not self.mock_mode,
        )
        self._ensure_provenance(report)
        state = RunState.build(self.journal.read(), self.order)
        completed_before = len(state.terminals)
        parser = self._load_parser()
        for position, command_id in enumerate(self.order, start=1):
            state = RunState.build(self.journal.read(), self.order)
            if position <= len(state.terminals):
                continue
            if max_new_commands is not None and (
                len(state.terminals) - completed_before >= max_new_commands
            ):
                break
            self._run_command(parser, self.records[command_id], position)
        return RunState.build(self.journal.read(), self.order)


def _load_fixture(path: Path) -> Dict[str, List[Dict[str, Any]]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    commands = raw.get("commands") if isinstance(raw, dict) else None
    if not isinstance(commands, dict):
        raise E1ToolingError("fixture must contain a commands mapping")
    return commands


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--execute-real-provider",
        action="store_true",
        help="explicitly authorize the sealed real-provider E1 run",
    )
    mode.add_argument(
        "--fixture",
        type=Path,
        help="run synthetic fixture responses only; no network inference",
    )
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--max-commands", type=int)
    args = parser.parse_args()

    mock_mode = args.fixture is not None
    run_id = args.run_id or utc_now().replace(":", "").replace("-", "")
    if args.run_dir is None:
        result_class = "synthetic-validation" if mock_mode else "formal"
        run_dir = E1_DIR / "results" / result_class / run_id
    else:
        run_dir = args.run_dir.resolve()
    if not mock_mode:
        formal_root = (E1_DIR / "results" / "formal").resolve()
        if not run_dir.resolve().is_relative_to(formal_root):
            raise E1ToolingError(
                f"real formal results must remain under {formal_root}"
            )
        if args.max_commands is not None:
            raise E1ToolingError("--max-commands is fixture-only")

    fixtures = _load_fixture(args.fixture) if mock_mode else None
    runner = E1Runner(
        run_dir,
        mock_mode=mock_mode,
        fixture_commands=fixtures,
    )
    state = runner.run(max_new_commands=args.max_commands)
    print(json.dumps({
        "run_dir": str(run_dir),
        "run_mode": "mock_synthetic" if mock_mode else "real_provider",
        "terminal_commands": len(state.terminals),
        "complete": len(state.terminals) == 120,
    }, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProvenanceError as exc:
        print(json.dumps(exc.report, indent=2, ensure_ascii=False))
        raise SystemExit(1)
