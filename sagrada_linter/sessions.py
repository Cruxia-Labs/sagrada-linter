"""Local agent-session reader (Claude Code JSONL) — the séance's substrate.

Vendored port of the engine's ``sagrada_revise/session_adapter.py``
(provenance: cruxia-engine @ foundry 2026-07-26; kept stdlib-only, no new
dependencies). Reads ONLY when the user explicitly opts in (`--seance`):
conversation logs are the user's own private record — the tool never
searches them silently, and nothing read here ever leaves the machine.

Yields (timestamp, role, text) for user/assistant TEXT blocks only; tool
calls, tool results, and injected harness noise are dropped.
"""
from __future__ import annotations

import json
import os
from typing import Iterator, List, Tuple

NOISE_PREFIXES = (
    "<system-reminder", "<ide_", "<command-", "<local-command",
    "<task-notification", "Caveat:",
)


def _text_blocks(content) -> List[str]:
    if isinstance(content, str):
        return [content]
    out: List[str] = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                out.append(block.get("text", ""))
    return out


def iter_session(path: str) -> Iterator[Tuple[str, str, str]]:
    """Yield (timestamp, role, text) for one session JSONL, event order."""
    try:
        fh = open(path, encoding="utf-8")
    except OSError:
        return
    with fh:
        for line in fh:
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = ev.get("message")
            if not isinstance(msg, dict):
                continue
            role = msg.get("role")
            if role not in ("user", "assistant"):
                continue
            ts = ev.get("timestamp") or ""
            for text in _text_blocks(msg.get("content")):
                t = text.strip()
                if not t or any(t.startswith(p) for p in NOISE_PREFIXES):
                    continue
                yield ts, role, t


def session_start(path: str) -> str:
    """First timestamp in the file (scans <=50 head lines); '9999' on failure
    so unreadable files sort last and are never mistaken for early."""
    try:
        with open(path, encoding="utf-8") as fh:
            for i, line in enumerate(fh):
                if i >= 50:
                    break
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = ev.get("timestamp")
                if ts:
                    return ts
    except OSError:
        pass
    return "9999"


def list_sessions(projects_root: str) -> List[str]:
    """All top-level session JSONL files under each project dir, sorted by
    start time. Flat listing one level deep (nested transcript dirs such as
    subagents/ are intentionally not visited)."""
    found: List[str] = []
    try:
        project_dirs = [os.path.join(projects_root, d)
                        for d in os.listdir(projects_root)]
    except OSError:
        return []
    for pd in project_dirs:
        if not os.path.isdir(pd):
            continue
        try:
            entries = os.listdir(pd)
        except OSError:
            continue
        for name in entries:
            if name.endswith(".jsonl"):
                p = os.path.join(pd, name)
                if os.path.isfile(p):
                    found.append(p)
    return sorted(found, key=session_start)
