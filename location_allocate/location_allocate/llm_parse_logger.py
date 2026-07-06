import csv
from pathlib import Path
from typing import Any, Dict


LOG_COLUMNS = [
    "command_id",
    "command_type",
    "raw_command",
    "prompt_tokens",
    "completion_tokens",
    "latency_ms",
    "valid_json",
    "schema_valid",
    "field_accuracy",
    "retry_count",
    "error_type",
]


def append_llm_parse_log(row: Dict[str, Any]) -> None:
    log_path = _repo_root() / "logs" / "llm_parse_log.csv"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    normalized = {column: row.get(column, "") for column in LOG_COLUMNS}
    write_header = not log_path.exists()
    with log_path.open("a", newline="", encoding="utf-8") as log_file:
        writer = csv.DictWriter(log_file, fieldnames=LOG_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow(normalized)


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    return here.parents[2]
