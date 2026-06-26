"""Sagrada Linter — catch zombie prompts (retracted AI rules that crept back in)."""
from .scanner import (
    ZombieEvent,
    scan_history_for_zombies,
    scan_repo,
    discover_rule_files,
    inject_demo,
    format_events,
    format_github_comment,
)
from .linter_receipt import build_check_receipt, write_receipt
from .preflight import check_action

__version__ = "0.1.0"
__all__ = [
    "ZombieEvent", "scan_history_for_zombies", "scan_repo", "discover_rule_files",
    "inject_demo", "format_events", "format_github_comment",
    "build_check_receipt", "write_receipt", "check_action",
]
