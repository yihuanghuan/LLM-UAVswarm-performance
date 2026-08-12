"""Explicit legacy-v1 parser entry point."""


def parse_legacy_uav_command(user_command: str, ros_aux_info: str = ""):
    """Load and invoke the historical parser only for explicit legacy mode."""
    from .legacy.parser_v1 import parse_legacy_uav_command as parse

    return parse(user_command, ros_aux_info)
