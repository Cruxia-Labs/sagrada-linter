"""Zombie-prompt scanner — the cold-conversion hero of the Sagrada Linter.

Walk a git repo's history of an AI-rule file (``.cursorrules`` / ``CLAUDE.md`` /
``AGENTS.md`` / system prompts) and deterministically detect **zombie prompt**
events: a rule that was RETRACTED in one commit and RE-ADDED in a later commit —
the "your agent is acting on a rule you already changed" failure, made measurable
on the user's OWN history with no setup.

Pure, deterministic, dependency-light — stdlib only (``git`` subprocess + ``difflib``
+ regex). NO ML, NO network, NO graph-build prerequisite. It reuses the diff-native
floor verbatim:

    walk_file_history (gitwalk)  -> file versions oldest->newest
    pair_changes      (diff_pairing) -> per-commit add/change/remove ``Change`` stream
    strip_code_fences (md_claims)    -> code samples never count as rules

A zombie is strictly **cross-commit**: a term REMOVED in commit A and ADDED in a
LATER commit B. A remove + re-add *within one commit* is a rewrite — ``pair_changes``
reconciles it to a ``change`` and it never counts as a zombie. This is the
determinism boundary applied to perception: no belief is inferred from prose, only
the bit-level retract/re-add deltas of the diff are read ("we never see it").
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .diff_pairing import pair_changes
from .gitwalk import walk_file_history
from .md_claims import extract_line_claim, strip_code_fences

# AI-rule files agents actually read as instructions. Basenames + a couple of
# path/suffix rules; matched against every path that ever appeared in history.
_RULE_BASENAMES = frozenset({
    "CLAUDE.md", "AGENTS.md", "GEMINI.md", "MEMORY.md", ".cursorrules",
})
_RULE_PATH_EXACT = frozenset({".github/copilot-instructions.md"})


def _is_rule_file(path: str) -> bool:
    base = os.path.basename(path)
    if base in _RULE_BASENAMES or path in _RULE_PATH_EXACT:
        return True
    if path.endswith(".cursorrules"):
        return True
    # Cursor "project rules" live under .cursor/rules/*.mdc (and some repos use .md)
    norm = "/" + path.replace(os.sep, "/")
    if "/.cursor/rules/" in norm and (path.endswith(".mdc") or path.endswith(".md")):
        return True
    return False


@dataclass
class ZombieEvent:
    """One retract -> re-add cycle located in a rule file's git history."""

    file: str
    term: str
    retracted_at: str                 # commit SHA where the rule was removed
    retracted_def: str                # its definition at retraction
    re_added_at: str                  # commit SHA where it came back
    re_added_line: Optional[int]      # 1-based line in the re-adding version
    re_added_def: str                 # its definition on re-add
    changed_meaning: bool             # re-added text differs from the retracted text

    def location(self) -> str:
        ln = f":{self.re_added_line}" if self.re_added_line is not None else ""
        return f"{self.file}{ln}"


def scan_history_for_zombies(repo_path: str, file_path: str) -> List[ZombieEvent]:
    """Walk one rule file's git history and return its zombie events, chronologically.

    Deterministic and offline. ``file_path`` is repo-relative. Returns ``[]`` for a
    file with no history (or no zombies).
    """
    versions = walk_file_history(repo_path, file_path)
    # term -> (retract_commit, retract_def); present IFF the term is currently retracted.
    retracted: Dict[str, Tuple[str, str]] = {}
    events: List[ZombieEvent] = []
    prev = ""
    for commit, _ts, content in versions:
        cur = strip_code_fences(content)
        for ch in pair_changes(prev, cur):
            if ch.kind == "remove" and ch.old_claim is not None:
                retracted[ch.old_claim[0]] = (commit, ch.old_claim[1])
            elif ch.kind == "add" and ch.new_claim is not None:
                term = ch.new_claim[0]
                prior = retracted.pop(term, None)
                # A zombie is strictly CROSS-COMMIT. A remove+add of the same term within
                # ONE commit is a reword the diff didn't pair (similarity < threshold) — a
                # rewrite, not a retract->re-add. Only flag when the retract was an EARLIER
                # commit (the rule was genuinely absent for a span, then came back).
                if prior is not None and prior[0] != commit:
                    r_commit, r_def = prior
                    events.append(ZombieEvent(
                        file=file_path,
                        term=term,
                        retracted_at=r_commit,
                        retracted_def=r_def,
                        re_added_at=commit,
                        re_added_line=ch.new_line_no,
                        re_added_def=ch.new_claim[1],
                        changed_meaning=(r_def.strip() != ch.new_claim[1].strip()),
                    ))
            elif ch.kind == "change" and ch.new_claim is not None:
                # a revise keeps the term live — it is not retracted anymore
                retracted.pop(ch.new_claim[0], None)
        prev = cur
    return events


def _candidate_rule_files(repo_path: str) -> List[str]:
    """Every rule-file path that ever appeared in the repo's history (sorted, unique)."""
    try:
        out = subprocess.run(
            ["git", "-C", repo_path, "log", "--all", "--pretty=format:", "--name-only"],
            capture_output=True, text=True, check=True,
        ).stdout
    except subprocess.CalledProcessError:
        return []
    paths = {p for p in out.splitlines() if p.strip()}
    return sorted(p for p in paths if _is_rule_file(p))


def find_rule_files_on_disk(repo_path: str) -> List[str]:
    """Rule files present in the working tree (repo-relative), sorted — for demos
    and for the no-git-history case."""
    out: List[str] = []
    for base in sorted(_RULE_BASENAMES):
        if os.path.isfile(os.path.join(repo_path, base)):
            out.append(base)
    cursor_rules = os.path.join(repo_path, ".cursor", "rules")
    if os.path.isdir(cursor_rules):
        for fn in sorted(os.listdir(cursor_rules)):
            if fn.endswith((".md", ".mdc")):
                out.append(os.path.join(".cursor", "rules", fn))
    copilot = ".github/copilot-instructions.md"
    if os.path.isfile(os.path.join(repo_path, copilot)):
        out.append(copilot)
    return out


def discover_rule_files(repo_path: str) -> List[str]:
    """Every rule-file path that ever appeared in the repo's git history (public)."""
    return _candidate_rule_files(repo_path)


def scan_repo(repo_path: str, paths: Optional[List[str]] = None) -> Dict[str, List[ZombieEvent]]:
    """Scan the given rule files (or auto-discover them) for zombie events.

    Returns ``{file_path: [ZombieEvent, ...]}`` for every file that has at least one
    event. Files with no zombies are omitted.
    """
    targets = paths if paths is not None else _candidate_rule_files(repo_path)
    result: Dict[str, List[ZombieEvent]] = {}
    for f in targets:
        events = scan_history_for_zombies(repo_path, f)
        if events:
            result[f] = events
    return result


# --- demo injection --------------------------------------------------------

def _git(repo: str, args: List[str], env: Optional[dict] = None) -> None:
    subprocess.run(["git", "-C", repo] + args, check=True,
                   capture_output=True, text=True, env=env)


def _first_claim_line(content: str) -> Optional[int]:
    """0-based index of the first claim-bearing line (code fences stripped)."""
    stripped = strip_code_fences(content).splitlines()
    for i, line in enumerate(stripped):
        if extract_line_claim(line) is not None:
            return i
    return None


def inject_demo(repo_path: str, file_path: str) -> List[ZombieEvent]:
    """Plant a zombie into a THROWAWAY copy of ``file_path`` and scan it, so a clean
    repo still sees the HALT fire on its own content. Never touches the real repo.

    Picks the first real rule in the file, retracts it in one commit, re-adds it in
    the next, and scans the throwaway history. Returns the (single) injected event,
    or ``[]`` if the file has no extractable rule.
    """
    src = os.path.join(repo_path, file_path)
    with open(src, encoding="utf-8") as fh:
        content = fh.read()
    idx = _first_claim_line(content)
    if idx is None:
        return []

    lines = content.splitlines()
    v1 = "\n".join(lines) + "\n"
    v2 = "\n".join(lines[:idx] + lines[idx + 1:]) + "\n"   # retract the rule
    v3 = v1                                                # re-add it (zombie)

    base = os.path.basename(file_path) or "RULES.md"
    env = dict(os.environ,
               GIT_AUTHOR_NAME="demo", GIT_AUTHOR_EMAIL="demo@local",
               GIT_COMMITTER_NAME="demo", GIT_COMMITTER_EMAIL="demo@local")
    tmp = tempfile.mkdtemp(prefix="sagrada-demo-")
    try:
        _git(tmp, ["init", "-q"])
        for version in (v1, v2, v3):
            with open(os.path.join(tmp, base), "w", encoding="utf-8") as fh:
                fh.write(version)
            _git(tmp, ["add", base], env=env)
            _git(tmp, ["commit", "-q", "-m", "demo", "--allow-empty"], env=env)
        return scan_history_for_zombies(tmp, base)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --- formatting ------------------------------------------------------------

def format_events(by_file: Dict[str, List[ZombieEvent]], *, color: bool = False) -> str:
    """Human-readable scan report. ``color`` adds ANSI for terminals."""
    def red(s: str) -> str:
        return f"\033[31m{s}\033[0m" if color else s

    def dim(s: str) -> str:
        return f"\033[2m{s}\033[0m" if color else s

    total = sum(len(v) for v in by_file.values())
    if total == 0:
        return "0 zombie-prompt events found. Your rule files are coherent over time. ✓"

    lines = [red(f"{total} zombie-prompt event(s) found") +
             " — a rule was retracted, then re-added later:\n"]
    for f in sorted(by_file):
        for ev in by_file[f]:
            verb = "re-added (meaning changed)" if ev.changed_meaning else "re-added"
            lines.append(f"  {red('✗')} {ev.location()}  {ev.term}")
            lines.append(dim(f"      retracted {ev.retracted_at[:8]}: {ev.retracted_def[:72]}"))
            lines.append(dim(f"      {verb} {ev.re_added_at[:8]}: {ev.re_added_def[:72]}"))
            lines.append("")
    return "\n".join(lines).rstrip()


# Public repo URL used in the PR-comment footer (Cruxia-Labs, the published linter).
REPO_URL = "https://github.com/Cruxia-Labs/sagrada-linter"


def format_github_comment(by_file: Dict[str, List[ZombieEvent]]) -> str:
    """Render a PR-comment in GitHub markdown.

    Only ever contains the DETERMINISTIC retract->re-add events — the scanner never
    produces a fuzzy/semantic finding, so amber can never reach a reviewer's PR by
    construction (the 'amber never gates / never surfaces' fence, held structurally).
    """
    total = sum(len(v) for v in by_file.values())
    if total == 0:
        return (
            "### 🟢 Sagrada Linter — no zombie prompts\n\n"
            "No retracted rule was re-introduced in this change. Your `.cursorrules` / "
            "`CLAUDE.md` / `AGENTS.md` are coherent over time."
        )
    plural = "s" if total != 1 else ""
    lines = [
        f"### 🔴 Sagrada Linter — {total} zombie prompt{plural} detected",
        "",
        "A rule that was **retracted** has been **re-added** — your agent may act on "
        "guidance you already changed.",
        "",
    ]
    for f in sorted(by_file):
        for ev in by_file[f]:
            verb = "re-added (meaning changed)" if ev.changed_meaning else "re-added"
            lines.append(f"- **`{ev.location()}`** — `{ev.term}`")
            lines.append(f"  - retracted in `{ev.retracted_at[:8]}`: {ev.retracted_def[:100]}")
            lines.append(f"  - {verb} in `{ev.re_added_at[:8]}`: {ev.re_added_def[:100]}")
    lines += [
        "",
        "<sub>Deterministic supersession check — every result is a real retract→re-add "
        "in your git history (no fuzzy matching). A verifiable ER1 receipt is attached to "
        f"this run. [What is this?]({REPO_URL})</sub>",
    ]
    return "\n".join(lines)
