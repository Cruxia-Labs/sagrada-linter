"""The Gate — the retention half of the two-product truth.

The reading (Communion) shows what walks; the Gate keeps the graves kept.
`guard` writes a **lock** of every rule that died and still rests —
`.crux/lock.json`, committed like a lockfile — and `guard --check` compares
the CURRENT rule files against it: a locked-dead term present again without
paperwork (the `sagrada:allow` marker or a restorations-ledger entry) fails
with its kill history attached. `restore --reason` is the sanctioned path.

Shadow mode reports and never fails — teams earn trust in the instrument
before the instrument earns the right to block (board 9/9: the demo ends by
installing this; gpt_A's retention moment is `--check` firing on a stale
branch a week later).

Deterministic throughout: the lock derives from git history; the check is
arithmetic against the worktree. No model anywhere.
"""
from __future__ import annotations

import json
import os
import subprocess
from typing import Dict, List, Optional, Tuple

from .gitwalk import git_env
from .md_claims import extract_line_claim, strip_code_fences
from .scanner import ALLOW_MARKER, dead_rules, discover_rule_files

LOCK_REL = os.path.join(".crux", "lock.json")
LEDGER_REL = os.path.join(".sagrada", "restorations.jsonl")
SCHEMA = "crux-lock/v0"


def _head(repo: str) -> str:
    r = subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"],
                       capture_output=True, text=True, env=git_env())
    return r.stdout.strip() if r.returncode == 0 else ""


def build_lock(repo_path: str, paths: Optional[List[str]] = None) -> dict:
    files = paths if paths is not None else discover_rule_files(repo_path)
    graves: Dict[str, List[dict]] = {}
    for f in sorted(files):
        dead = dead_rules(repo_path, f)
        if dead:
            graves[f] = dead
    return {
        "schema": SCHEMA,
        "locked_at_commit": _head(repo_path),
        "graves": graves,
        "note": ("Rules recorded dead. Bringing one back requires paperwork: "
                 "`sagrada-linter restore FILE LINE --reason ...` (the marker "
                 "+ the ledger). An undeclared return fails guard --check "
                 "with the kill history attached."),
    }


def write_lock(repo_path: str, lock: dict) -> str:
    path = os.path.join(repo_path, LOCK_REL)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(lock, fh, indent=1, sort_keys=True)
        fh.write("\n")
    return path


def read_lock(repo_path: str) -> Optional[dict]:
    path = os.path.join(repo_path, LOCK_REL)
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except OSError:
        return None
    except json.JSONDecodeError:
        raise SystemExit(f"{LOCK_REL} is not valid JSON — regenerate with "
                         "`sagrada-linter guard` or fix by hand.")


def _ledger_terms(repo_path: str) -> set:
    """Terms with a declared restoration on the books (any file — the
    ledger row's quoted text is claim-parsed for its term)."""
    out = set()
    try:
        with open(os.path.join(repo_path, LEDGER_REL), encoding="utf-8") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                claim = extract_line_claim(row.get("text", ""))
                if claim is not None:
                    out.add((row.get("file", ""), claim[0]))
    except OSError:
        pass
    return out


def check_lock(repo_path: str, lock: Optional[dict] = None
               ) -> Tuple[List[dict], int]:
    """Compare CURRENT rule files against the lock.

    Returns (violations, sanctioned_count). A violation is a locked-dead
    term present today without the marker and without a ledger row —
    carrying its kill history so the failure message needs no archaeology.
    """
    lock = lock if lock is not None else read_lock(repo_path)
    if not lock:
        return [], 0
    ledger = _ledger_terms(repo_path)
    violations: List[dict] = []
    sanctioned = 0
    for f, graves in sorted(lock.get("graves", {}).items()):
        fpath = os.path.join(repo_path, f)
        try:
            content = open(fpath, encoding="utf-8").read()
        except OSError:
            continue  # file gone: its dead stay dead
        lines = strip_code_fences(content).splitlines()
        present: Dict[str, Tuple[int, str]] = {}
        for i, line in enumerate(lines, 1):
            claim = extract_line_claim(line)
            if claim is not None and claim[0] not in present:
                present[claim[0]] = (i, line)
        for grave in graves:
            term = grave["term"]
            hit = present.get(term)
            if hit is None:
                continue  # still resting
            line_no, line = hit
            if ALLOW_MARKER in line or (f, term) in ledger:
                sanctioned += 1
                continue
            violations.append({
                "file": f, "line": line_no, "term": term,
                "killed_at": grave["killed_at"], "killed_ts": grave["killed_ts"],
                "was": grave["definition"],
            })
    return violations, sanctioned


def format_violations(violations: List[dict], sanctioned: int,
                      shadow: bool) -> str:
    if not violations:
        base = "guard: every locked grave is kept"
        if sanctioned:
            base += f" · {sanctioned} declared restoration(s) sanctioned"
        return base + "."
    head = ("guard (shadow): the following would fail enforcement —"
            if shadow else "GUARD FAILED — undeclared resurrection:")
    out = [head]
    for v in violations:
        out.append(f"  {v['file']}:{v['line']}  {v['term']}")
        out.append(f"    killed at {v['killed_at'][:8]} — the record says: "
                   f"\"{v['was'].strip()[:100]}\"")
        out.append(f"    sanction it:  sagrada-linter restore {v['file']} "
                   f"{v['line']} --reason \"why it lives again\"")
    if sanctioned:
        out.append(f"  ({sanctioned} other return(s) properly declared)")
    return "\n".join(out)


WORKFLOW_YML = """\
name: sagrada guard
# Installed by `sagrada-linter guard`. SHADOW MODE by default: the check
# comments on what would fail but never blocks. When your team trusts the
# instrument, remove `--shadow` below to enforce.
on: [pull_request]
permissions:
  contents: read
jobs:
  guard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - run: pipx install sagrada-linter
      - run: sagrada-linter guard --check --shadow --repo .
"""
