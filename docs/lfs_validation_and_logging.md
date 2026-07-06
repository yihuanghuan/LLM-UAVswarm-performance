# LFS Validation and LLM Logging Changes

## Summary

This update formalizes the LLM parsing layer around a Language-to-Formation Specification (LFS) while preserving the scheduler's existing `task_sequences` runtime contract.

## What Changed

- Added `schemas/lfs_schema.json` with support for two accepted payloads:
  - Formal LFS tasks using `U`, `F`, `c`, `r`, `T`, `m`, `s`, and `q`.
  - Existing scheduler-compatible tasks using `task_sequences`.
- Added `location_allocate.lfs_validator` to run JSON schema validation, semantic validation, and formal-LFS-to-scheduler compilation.
- Updated `no_location.py` so the parsing flow is now:
  - purify model output
  - `json.loads`
  - JSON schema validation
  - semantic validation
  - task compilation for the existing scheduler
- Replaced the hardcoded API key with environment variables:
  - `LLM_API_KEY`
  - `MINIMAX_API_KEY`
- Added LLM parse attempt logging to `logs/llm_parse_log.csv`.

## Log Fields

The CSV log contains:

- `command_id`
- `command_type`
- `raw_command`
- `prompt_tokens`
- `completion_tokens`
- `latency_ms`
- `valid_json`
- `schema_valid`
- `field_accuracy`
- `retry_count`
- `error_type`

## Compatibility Notes

`location_allocate.py` still consumes the same `task_sequences` structure as before. Formal LFS payloads are compiled into that structure before execution, so the existing formation generator, topology allocator, and ROS publishers continue to work unchanged.

Runtime logs are intentionally ignored by git through `logs/` in `.gitignore`.

## Validation

Local checks performed during implementation:

- Formal LFS payload compiles to scheduler-compatible `task_sequences`.
- Legacy `task_sequences` payload validates and remains compatible.
- Invalid UAV IDs fail semantic validation.
- Missing API key returns a structured parser error and writes a parse log row.
