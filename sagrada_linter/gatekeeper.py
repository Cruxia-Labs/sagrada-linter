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
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(lock, fh, indent=1, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)  # never a torn lock (gate finding)
    return path


def _validate_lock(lock: dict, repo_path: str) -> dict:
    """Minimal schema + containment: a crafted or corrupted lock must fail
    loud, never read outside the repo or silently suppress checks."""
    if lock.get("schema") != SCHEMA:
        raise SystemExit(f"lock schema is not {SCHEMA} — regenerate with "
                         "`sagrada-linter guard`.")
    graves = lock.get("graves")
    if not isinstance(graves, dict):
        raise SystemExit("lock has no graves table — regenerate.")
    repo_real = os.path.realpath(repo_path)
    for f, rows in graves.items():
        target = os.path.realpath(os.path.join(repo_real, f))
        if not target.startswith(repo_real + os.sep):
            raise SystemExit(f"lock entry '{f}' resolves outside the repo — "
                             "refusing.")
        if not isinstance(rows, list) or not all(
                isinstance(r, dict) and "term" in r and "killed_at" in r
                for r in rows):
            raise SystemExit(f"lock entry '{f}' is malformed — regenerate.")
    return lock


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
    repo_real = os.path.realpath(repo_path)
    try:
        with open(os.path.join(repo_path, LEDGER_REL), encoding="utf-8") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                claim = extract_line_claim(row.get("text", ""))
                if claim is None:
                    continue
                # normalize the user-typed file field to repo-relative so
                # './CLAUDE.md' or an absolute path still sanctions the
                # lock's relative key (gate finding: a mismatch here
                # falsely BLOCKS a declared restoration — category-killer)
                raw = row.get("file", "")
                norm = os.path.relpath(
                    os.path.realpath(os.path.join(repo_real, raw)), repo_real)
                out.add((norm, claim[0]))
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
    lock = _validate_lock(lock, repo_path)
    ledger = _ledger_terms(repo_path)
    violations: List[dict] = []
    sanctioned = 0
    for f, graves in sorted(lock.get("graves", {}).items()):
        fpath = os.path.join(repo_path, f)
        try:
            content = open(fpath, encoding="utf-8").read()
        except OSError:
            continue  # file gone: its dead stay dead
        # strip_code_fences BLANKS lines in place — line numbers below are
        # original-file line numbers (md_claims docstring is the receipt)
        lines = strip_code_fences(content).splitlines()
        # EVERY occurrence, not just the first: a marked line must not
        # shield an unmarked duplicate of the same term (gate finding)
        present: Dict[str, List[Tuple[int, str]]] = {}
        for i, line in enumerate(lines, 1):
            claim = extract_line_claim(line)
            if claim is not None:
                present.setdefault(claim[0], []).append((i, line))
        for grave in graves:
            term = grave["term"]
            hits = present.get(term)
            if not hits:
                continue  # still resting
            unmarked = [(i, l) for i, l in hits if ALLOW_MARKER not in l]
            if not unmarked or (f, term) in ledger:
                sanctioned += 1
                continue
            line_no, _line = unmarked[0]
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
      # pinned: bump deliberately, never drift (supply-chain law)
      - run: pipx install sagrada-linter==0.2.0
      - run: sagrada-linter guard --check --shadow --repo .
"""
