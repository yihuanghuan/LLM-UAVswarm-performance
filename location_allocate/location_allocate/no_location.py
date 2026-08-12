"""Compatibility shim for the historical parser module."""

from .legacy import parser_v1 as _parser


API_KEY = _parser.API_KEY
BASE_URL = _parser.BASE_URL
MODEL_NAME = _parser.MODEL_NAME
OpenAI = _parser.OpenAI
httpx = _parser.httpx
time = _parser.time
append_llm_parse_log = _parser.append_llm_parse_log
LEGACY_SYSTEM_PROMPT = _parser.LEGACY_SYSTEM_PROMPT
LEGACY_FEW_SHOT_EXAMPLES = _parser.LEGACY_FEW_SHOT_EXAMPLES
classify_command_type = _parser.classify_command_type
purify_json_content = _parser.purify_json_content


def _sync_compatibility_overrides():
    _parser.API_KEY = API_KEY
    _parser.BASE_URL = BASE_URL
    _parser.MODEL_NAME = MODEL_NAME
    _parser.OpenAI = OpenAI
    _parser.httpx = httpx
    _parser.append_llm_parse_log = append_llm_parse_log


def parse_uav_command(user_command, ros_aux_info="", runtime_mode="candidate_v2"):
    _sync_compatibility_overrides()
    return _parser.parse_uav_command(user_command, ros_aux_info, runtime_mode)


def parse_candidate_mission(user_command, ros_aux_info=""):
    return _parser.parse_candidate_mission(user_command, ros_aux_info)


def parse_legacy_uav_command(user_command, ros_aux_info=""):
    _sync_compatibility_overrides()
    return _parser.parse_legacy_uav_command(user_command, ros_aux_info)


__all__ = [
    "LEGACY_FEW_SHOT_EXAMPLES",
    "LEGACY_SYSTEM_PROMPT",
    "classify_command_type",
    "parse_candidate_mission",
    "parse_legacy_uav_command",
    "parse_uav_command",
    "purify_json_content",
]
