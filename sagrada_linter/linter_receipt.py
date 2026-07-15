"""Emit a signed, offline-verifiable ER1 receipt for a Sagrada Linter check.

The linter's quiet rail: every gate check drops a real ER1 receipt into ``.sagrada/
receipts/`` so a stranger can recompute the verdict offline, byte-for-byte, with the
live ``er1-verify`` (Python) or ``er1_verify.mjs`` (JS) — no change to the frozen ER1
format.

Mapping (honest, and documented in SCOPE_OF_CERTIFICATION): a rule that was RETRACTED is
treated as **excluded from the live rule set**, so re-introducing it is a ``BANNED_ENTITY``
conflict under the frozen conflict predicate. A clean check emits an ``ALLOW`` (COHERENT)
receipt. Only the deterministic supersession/zombie signal ever produces a HALT — amber
never reaches this path (the conflict predicate only gates ``deterministic`` beliefs).
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Tuple

from .canonical import canonical_json
from . import conflict as C
from .decision import PreflightGate

# A zombie, decoupled from the scanner: (term, re_added_def, retract_sha, re_add_sha).
Zombie = Tuple[str, str, str, str]


def build_check_receipt(
    file_path: str,
    zombies: Iterable[Zombie],
    *,
    gate: Optional[PreflightGate] = None,
) -> dict:
    """Build + sign the ER1 receipt for one rule file's lint check.

    With zombies -> a HALT (BANNED_ENTITY) receipt; clean -> an ALLOW (COHERENT) receipt.
    """
    g = gate or PreflightGate()
    zlist = list(zombies)
    beliefs = [
        C.TypedBelief(
            belief_id=f"retracted:{term}",
            entity=term,
            rule=C.RULE_EXCLUDES,
            value="retracted",
            status=C.STATUS_ACTIVE,
            source_kind=C.SOURCE_DETERMINISTIC,
        )
        for term, _def, _r, _a in zlist
    ]
    asserts = {term: defn for term, defn, _r, _a in zlist}
    action = C.ProposedAction(tool="sagrada-linter", asserts=asserts, resource=file_path)
    return g.preflight(beliefs, action)


def _slug(s: str) -> str:
    """Filesystem-safe slug: path separators and anything exotic become ``-``."""
    s = s.replace(os.sep, "-").replace("/", "-")
    s = re.sub(r"[^A-Za-z0-9_-]+", "-", s)
    return re.sub(r"-{2,}", "-", s).strip("-") or "x"


def receipt_filename(repo_root: str, file_path: str, receipt: dict) -> str:
    """Speakable receipt name: ``<repo>-<file>-<week>-<shortid>.er1.json``.

    A stranger listing ``.sagrada/receipts/`` should see WHAT was certified and WHEN
    (ISO week), not a bare UUID. The short receipt-id suffix keeps names unique.
    """
    repo = _slug(os.path.basename(os.path.abspath(repo_root)))
    week = datetime.now(timezone.utc).strftime("%G-W%V")
    rid = str(receipt.get("receipt_id", "receipt")).replace("-", "")[:8] or "receipt"
    return f"{repo}-{_slug(file_path)}-{week}-{rid}.er1.json"


def write_receipt(receipt: dict, receipts_dir: str, filename: Optional[str] = None) -> str:
    """Write a receipt to ``receipts_dir`` (default name ``<receipt_id>.er1.json``).

    Written as **canonical JSON bytes** (RFC 8785) — byte-for-byte the form a verifier
    hashes — so the on-disk file and the verified claim cannot diverge. Returns the path.
    A name collision never overwrites: a numeric suffix is added instead.
    """
    os.makedirs(receipts_dir, exist_ok=True)
    if filename is None:
        rid = receipt.get("receipt_id", "receipt")
        filename = f"{rid}.er1.json"
    path = os.path.join(receipts_dir, filename)
    stem = filename[:-len(".er1.json")] if filename.endswith(".er1.json") else filename
    n = 2
    while os.path.exists(path):
        path = os.path.join(receipts_dir, f"{stem}-{n}.er1.json")
        n += 1
    with open(path, "wb") as fh:
        fh.write(canonical_json(receipt))
    return path


def emit_for_events(
    repo_path: str,
    by_file: dict,
    *,
    receipts_dir: Optional[str] = None,
    gate: Optional[PreflightGate] = None,
) -> List[str]:
    """Emit one ER1 receipt per scanned rule file (HALT if zombies, else ALLOW).

    ``by_file`` maps ``file_path -> [event, ...]`` where each event exposes ``.term``,
    ``.re_added_def``, ``.retracted_at``, ``.re_added_at`` (the scanner's ``ZombieEvent``).
    Returns the written receipt paths. Default dir = ``<repo>/.sagrada/receipts/``.
    """
    receipts_dir = receipts_dir or os.path.join(repo_path, ".sagrada", "receipts")
    g = gate or PreflightGate()
    paths: List[str] = []
    for f in sorted(by_file):
        events = by_file[f]
        zlist: List[Zombie] = [
            (e.term, e.re_added_def, e.retracted_at, e.re_added_at) for e in events
        ]
        receipt = build_check_receipt(f, zlist, gate=g)
        paths.append(write_receipt(receipt, receipts_dir,
                                   filename=receipt_filename(repo_path, f, receipt)))
    return paths


__all__ = ["Zombie", "build_check_receipt", "receipt_filename", "write_receipt",
           "emit_for_events"]
