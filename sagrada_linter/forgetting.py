"""Certified Forgetting, v1 — retract with proof, on the existing rails.

Anyone can delete a rule. `forget` makes the deletion an EVENT with a record:

  1. the EDIT      — the rule line leaves the file (reality changes first;
                     the record may lag reality, never lead it)
  2. the RESIDUE   — every other current rule line that still references the
                     term, listed as a review queue (depth-1 textual
                     references, stated as such — deeper derivation tracing
                     is the engine's bounded-depth territory, not claimed)
  3. the TOMBSTONE — a dated ledger row: term, definition, reason, residue
  4. the RECEIPT   — a signed ER1 under the house mapping (retracted =
                     EXCLUDES): coherent under the new doctrine, offline-
                     recomputable. Any future re-assertion of the term
                     checks as BANNED_ENTITY against this same doctrine —
                     and `guard` will hold the grave with this kill on
                     record.

Forgetting is not an event but a maintained state: the scanner re-certifies
absence on every read, and the gate refuses undeclared resurrection.
"""
from __future__ import annotations

import json
import os
import re
from typing import List, Optional, Tuple

from . import conflict as C
from .decision import PreflightGate
from .linter_receipt import receipt_filename, write_receipt
from .md_claims import extract_line_claim, strip_code_fences
from .scanner import discover_rule_files

TOMBSTONES_REL = os.path.join(".sagrada", "tombstones.jsonl")
RECEIPTS_REL = os.path.join(".sagrada", "receipts")


def find_residue(repo_path: str, term: str,
                 skip: "Tuple[str, int] | None" = None) -> List[dict]:
    """Current rule lines (across all rule files) that still reference the
    term — depth-1 TEXTUAL references, a review queue, never a closure
    claim. ``skip`` = (file, line) of the rule being forgotten, for scans
    taken BEFORE the edit; pass None when scanning the post-edit file
    (release gate F2: a stale line number after deletion could mask real
    residue that shifted into that position)."""
    pat = re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE)
    # terms are normalized (hyphens->underscores); match the surface form too
    pat_surface = re.compile(
        r"\b" + re.escape(term.replace("_", "-")) + r"\b", re.IGNORECASE)
    out: List[dict] = []
    for f in discover_rule_files(repo_path):
        p = os.path.join(repo_path, f)
        try:
            content = open(p, encoding="utf-8").read()
        except OSError:
            continue
        for i, line in enumerate(strip_code_fences(content).splitlines(), 1):
            if (f, i) == skip or not line.strip():
                continue
            if pat.search(line) or pat_surface.search(line):
                out.append({"file": f, "line": i,
                            "text": line.strip()[:200]})
    return out


def forget(repo_path: str, file_rel: str, line_no: int, reason: str,
           date: str, gate: Optional[PreflightGate] = None) -> dict:
    """Execute the four steps. Returns a summary dict (term, residue,
    tombstone row, receipt path). Raises ValueError on a non-rule line;
    containment is the caller's job (the CLI reuses restore's guard)."""
    target = os.path.join(repo_path, file_rel)
    lines = open(target, encoding="utf-8").read().splitlines(keepends=True)
    if not (1 <= line_no <= len(lines)):
        raise ValueError(f"{file_rel} has {len(lines)} lines — no line {line_no}")
    raw = lines[line_no - 1]
    claim = extract_line_claim(raw)
    if claim is None:
        raise ValueError(
            f"{file_rel}:{line_no} is not a structured rule line — nothing "
            "to forget (the instrument only certifies what it can read)")
    term, definition = claim

    # 1. the edit — reality first
    del lines[line_no - 1]
    with open(target, "w", encoding="utf-8") as fh:
        fh.writelines(lines)

    # 2. the residue
    # F2 (release gate): the file was just edited — line numbers shifted,
    # so the pre-edit skip tuple is stale; the forgotten line is gone,
    # so everything found now IS residue.
    residue = find_residue(repo_path, term)

    # 3. the tombstone
    row = {"date": date, "file": file_rel, "line": line_no, "term": term,
           "definition": definition.strip()[:300], "reason": reason,
           "residue": residue}
    tpath = os.path.join(repo_path, TOMBSTONES_REL)
    os.makedirs(os.path.dirname(tpath), exist_ok=True)
    with open(tpath, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")

    # 4. the receipt — the new doctrine, coherent, signed
    g = gate or PreflightGate()
    beliefs = [C.TypedBelief(
        belief_id=f"retracted:{term}", entity=term, rule=C.RULE_EXCLUDES,
        value="retracted", status=C.STATUS_ACTIVE,
        source_kind=C.SOURCE_DETERMINISTIC)]
    action = C.ProposedAction(tool="sagrada-forget", asserts={},
                              resource=f"{file_rel}:{line_no}")
    receipt = g.preflight(beliefs, action)
    rdir = os.path.join(repo_path, RECEIPTS_REL)
    rpath = write_receipt(receipt, rdir,
                          receipt_filename(repo_path, file_rel, receipt))
    return {"term": term, "definition": definition, "residue": residue,
            "tombstone": row, "receipt_path": rpath,
            "verdict": receipt["decision"]["verdict"]}
