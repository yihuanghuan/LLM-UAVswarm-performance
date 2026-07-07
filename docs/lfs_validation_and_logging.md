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
- Updated the LLM prompt and few-shot examples so the model now emits formal LFS directly:
  - `lfs_version`
  - `tasks`
  - `U`, `F`, `c`, `r`, `T`, `m`, `s`, `q`
- Added package dependency declarations for the LLM parser, schema validator, and safety-aware allocator.

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

The LLM-facing interface now asks for formal LFS, while the ROS scheduler-facing interface remains `task_sequences`. This keeps the paper-facing LFS representation aligned with the implementation without changing the controller or topic protocol.

## Dependency Declarations

`location_allocate/setup.py` now declares the Python packages used by the parser and allocation layer:

- `jsonschema`
- `openai`
- `httpx`
- `numpy`
- `scipy`

`location_allocate/package.xml` declares the ROS/system Python dependencies that have stable package names:

- `python3-jsonschema`
- `python3-numpy`
- `python3-scipy`

## Validation

Local checks performed during implementation:

- Formal LFS payload compiles to scheduler-compatible `task_sequences`.
- Legacy `task_sequences` payload validates and remains compatible.
- Invalid UAV IDs fail semantic validation.
- Missing API key returns a structured parser error and writes a parse log row.
- The prompt examples now use formal LFS and compile back to scheduler-compatible payloads.
- Safety-aware allocator tests pass with the declared NumPy/SciPy dependency path.
