"""Load versioned paper prompt assets and compute reproducibility hashes."""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Tuple


PAPER_PROMPT_VERSION = "paper-candidate-en-v1"
PAPER_SCHEMA_VERSION = "paper-candidate-schema-v1"


@dataclass(frozen=True)
class PaperPromptBundle:
    system_prompt: str
    few_shot: Tuple[Any, ...]
    prompt_version: str
    prompt_hash: str
    schema_version: str
    schema_hash: str

    def render_examples(self) -> str:
        blocks = []
        for example in self.few_shot:
            blocks.append(
                "User instruction:\n" + example["user"] + "\n"
                "Availability information:\n" + example["availability"] + "\n"
                "Output:\n" + json.dumps(example["output"], separators=(",", ":"))
            )
        return "\n\n".join(blocks)


def _resource_paths() -> tuple[Path, Path, Path]:
    try:
        from ament_index_python.packages import get_package_share_directory

        share = Path(get_package_share_directory("location_allocate"))
        prompt_dir = share / "prompts"
        schema = share / "schemas" / "paper_candidate_schema_v1.json"
        if prompt_dir.is_dir() and schema.is_file():
            return (
                prompt_dir / "paper_candidate_en_v1_system.txt",
                prompt_dir / "paper_candidate_en_v1_fewshot.json",
                schema,
            )
    except Exception:
        pass
    root = Path(__file__).resolve().parents[1]
    return (
        root / "prompts" / "paper_candidate_en_v1_system.txt",
        root / "prompts" / "paper_candidate_en_v1_fewshot.json",
        root.parent / "schemas" / "paper_candidate_schema_v1.json",
    )


def load_paper_prompt_bundle() -> PaperPromptBundle:
    system_path, few_shot_path, schema_path = _resource_paths()
    system_bytes = system_path.read_bytes()
    few_shot_bytes = few_shot_path.read_bytes()
    schema_bytes = schema_path.read_bytes()
    prompt_hash = hashlib.sha256(
        system_bytes + b"\n--PAPER-FEWSHOT--\n" + few_shot_bytes
    ).hexdigest()
    return PaperPromptBundle(
        system_prompt=system_bytes.decode("utf-8").strip(),
        few_shot=tuple(json.loads(few_shot_bytes.decode("utf-8"))),
        prompt_version=PAPER_PROMPT_VERSION,
        prompt_hash=prompt_hash,
        schema_version=PAPER_SCHEMA_VERSION,
        schema_hash=hashlib.sha256(schema_bytes).hexdigest(),
    )


def load_paper_schema():
    return json.loads(_resource_paths()[2].read_text(encoding="utf-8"))
