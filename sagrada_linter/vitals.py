"""Vitals — the 0-100 belief-integrity score (SAGRADA-VITALS-METHOD v0.1, FROZEN).

Record-side only: computed deterministically from the repo's own git history via the
same primitives as the zombie scanner (walk_file_history -> pair_changes ->
extract_line_claim). No model, no network, no judgment call anywhere in the number.

The method is FROZEN — weights, inputs, window, rounding, and bands are fixed by
SAGRADA-VITALS-METHOD v0.1 (hash below, Ed25519 freeze receipt in the method repo).
Any change here that alters a score is a method change and MUST ship as v0.2+ with a
public changelog. The revival semantics deliberately mirror ``scanner.py`` verbatim:
same-commit rewords never count, ``sagrada:allow`` lines opt out, renames keep the
old term alive.

What the score does NOT measure (print this near every score): whether the repo's
agent answers correctly, code quality, security, or anything an LLM said. Only
STRUCTURED rules (``key: value`` / ``- term — definition``) are tracked; freeform
prose bullets are invisible to the detector. 100 means "no zombie beliefs
detectable in the record," not "this project is good."
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional, Set, Tuple

from .diff_pairing import pair_changes
from .gitwalk import walk_file_history
from .md_claims import extract_line_claim, strip_code_fences
from .scanner import ALLOW_MARKER, discover_rule_files

METHOD_VERSION = "SAGRADA-VITALS-METHOD v0.1"
# SHA-256 of docs/VITALS_METHOD_v0.1.md at freeze (2026-07-13); receipt:
# results/vitals/VITALS_METHOD_v0.1.receipt.json (state_root sha256:02ebe6aa...).
METHOD_SHA256 = "sha256:8d09871efbf6fae5d926d0372083afbdba7a5805b8960d68a1a5f3c8dff85e76"

WINDOW_DAYS = 365

BANDS = (  # lower bound (inclusive) -> label; display only, never used in math.
    (90, "SOUND"),
    (75, "WATCH"),
    (45, "ROTTING"),
    (0, "OVERRUN"),
)


@dataclass
class RuleEvent:
    """One death (retraction) or revival (zombie) of a structured rule term."""

    kind: str                    # "death" | "revival"
    file: str
    term: str
    commit: str
    ts: int                      # commit unix time
    retracted_at: str = ""       # revivals only: the death commit this revives
    changed_meaning: bool = False


@dataclass
class VitalsRecord:
    """Everything the formula needs, plus the receipts-grade event detail."""

    events: List[RuleEvent] = field(default_factory=list)
    final_presence: Set[Tuple[str, str]] = field(default_factory=set)  # (file, term) at snapshot
    snapshot_ts: int = 0
    snapshot_commit: str = ""
    files_scanned: List[str] = field(default_factory=list)


def _final_terms(content: str) -> Set[str]:
    terms: Set[str] = set()
    for line in strip_code_fences(content).splitlines():
        claim = extract_line_claim(line)
        if claim is not None:
            terms.add(claim[0])
    return terms


def collect_record(repo_path: str, paths: Optional[List[str]] = None) -> VitalsRecord:
    """Walk every rule file's committed history and collect deaths + revivals.

    Mirrors ``scanner.scan_history_for_zombies`` exactly on the revival side
    (same-commit skip, allow-marker opt-out, change-kind revival with the old
    term popped alive) and additionally records remove-kind deaths with commit
    timestamps — the inputs Vitals needs that the scanner does not emit.
    Committed history only: the snapshot is HEAD, never the worktree.
    """
    rec = VitalsRecord()
    files = paths if paths is not None else discover_rule_files(repo_path)
    for file_path in files:
        versions = walk_file_history(repo_path, file_path)
        if not versions:
            continue
        rec.files_scanned.append(file_path)
        retracted: Dict[str, Tuple[str, int]] = {}  # term -> (death commit, death ts)
        prev = ""
        for commit, ts, content in versions:
            cur = strip_code_fences(content)
            for ch in pair_changes(prev, cur):
                if ch.kind == "remove" and ch.old_claim is not None:
                    term = ch.old_claim[0]
                    retracted[term] = (commit, ts)
                    rec.events.append(RuleEvent("death", file_path, term, commit, ts))
                elif ch.kind == "add" and ch.new_claim is not None:
                    _revival(ch, commit, ts, file_path, retracted, rec)
                elif ch.kind == "change" and ch.new_claim is not None:
                    _revival(ch, commit, ts, file_path, retracted, rec)
                    if ch.old_claim is not None:
                        # rename/revise keeps the old term live — pop, no death.
                        retracted.pop(ch.old_claim[0], None)
            prev = cur
        last_commit, last_ts, last_content = versions[-1]
        for term in _final_terms(last_content):
            rec.final_presence.add((file_path, term))
        if last_ts > rec.snapshot_ts:
            rec.snapshot_ts, rec.snapshot_commit = last_ts, last_commit
    rec.events.sort(key=lambda e: (e.ts, e.commit, e.file, e.term))
    return rec


def _revival(ch, commit: str, ts: int, file_path: str,
             retracted: Dict[str, Tuple[str, int]], rec: VitalsRecord) -> None:
    term = ch.new_claim[0]
    prior = retracted.pop(term, None)
    if prior is None or prior[0] == commit:
        return
    if ch.new_line and ALLOW_MARKER in ch.new_line:
        return
    rec.events.append(RuleEvent("revival", file_path, term, commit, ts,
                                retracted_at=prior[0],
                                changed_meaning=False))


def window_inputs(rec: VitalsRecord, window_days: int = WINDOW_DAYS) -> Dict[str, object]:
    """Derive the frozen formula's inputs (a, e, d, c, r) over the trailing window."""
    start = rec.snapshot_ts - window_days * 86400
    in_w = [ev for ev in rec.events if start < ev.ts <= rec.snapshot_ts]
    revivals = [ev for ev in in_w if ev.kind == "revival"]
    deaths = [ev for ev in in_w if ev.kind == "death"]

    def _later(kind: str, ev: RuleEvent) -> bool:
        return any(o.kind == kind and o.file == ev.file and o.term == ev.term
                   and (o.ts, o.commit) > (ev.ts, ev.commit) for o in in_w)

    active = [ev for ev in revivals
              if (ev.file, ev.term) in rec.final_presence and not _later("death", ev)]
    clean = [ev for ev in deaths if not _later("revival", ev)]

    d = len(deaths)
    return {
        "a": len(active), "e": len(revivals), "d": d, "c": len(clean),
        "r": (len(clean) / d) if d > 0 else 0.0,
        "active_events": active, "window_days": window_days,
    }


def compute_vitals(a: int, e: int, r: float) -> int:
    """The frozen formula. Pure; matches the method doc's reference table exactly."""
    z = 45.0 * (1.0 - math.exp(-a))
    z_damped = z * (1.0 - 0.3 * r)
    ep = 15.0 * (1.0 - math.exp(-e / 3.0))
    raw = 100.0 - z_damped - ep
    score = int(Decimal(repr(raw)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return max(0, score)


def band(score: int) -> str:
    for lo, label in BANDS:
        if score >= lo:
            return label
    return "OVERRUN"


def vitals_for_repo(repo_path: str, paths: Optional[List[str]] = None,
                    window_days: int = WINDOW_DAYS) -> Dict[str, object]:
    """One repo -> the full Vitals result (inputs, score, band, event detail)."""
    rec = collect_record(repo_path, paths)
    inp = window_inputs(rec, window_days)
    score = compute_vitals(inp["a"], inp["e"], inp["r"])
    return {
        "method": METHOD_VERSION,
        "method_sha256": METHOD_SHA256,
        "score": score,
        "band": band(score),
        "inputs": {k: inp[k] for k in ("a", "e", "d", "c", "r", "window_days")},
        "snapshot_commit": rec.snapshot_commit,
        "snapshot_ts": rec.snapshot_ts,
        "files_scanned": rec.files_scanned,
        "active_zombies": [
            {"file": ev.file, "term": ev.term, "revived_at": ev.commit,
             "retracted_at": ev.retracted_at, "ts": ev.ts}
            for ev in inp["active_events"]
        ],
        "not_measured": "agent answer correctness, code quality, security, or any "
                        "LLM output; only structured rules are tracked",
    }


def badge_json(score: int) -> Dict[str, object]:
    """shields.io endpoint JSON for the belief-integrity badge."""
    colors = {"SOUND": "#2e7d4f", "WATCH": "#C2902E",
              "ROTTING": "#B85C38", "OVERRUN": "#8A3F28"}
    b = band(score)
    return {"schemaVersion": 1, "label": "belief-integrity",
            "message": f"{score} ({b})", "color": colors[b]}
