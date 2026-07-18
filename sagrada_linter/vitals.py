"""Vitals — the 0-100 belief-integrity score (SAGRADA-VITALS-METHOD v0.2, FROZEN).

Record-side only: computed deterministically from the repo's own git history via the
same primitives as the zombie scanner (walk_file_history -> pair_changes ->
extract_line_claim). No model, no network, no judgment call anywhere in the number.

The method is FROZEN — weights, inputs, window, rounding, and bands are fixed by
SAGRADA-VITALS-METHOD v0.2 (hash below; v0.2 = v0.1 formula with corrected event
accounting — active dedup, churn collapse, HEAD window anchor — public changelog in
the method doc). Any change here that alters a score is a method change and MUST
ship as v0.3+ with a public changelog. The revival semantics deliberately mirror ``scanner.py`` verbatim:
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
from .gitwalk import _git, walk_file_history
from .md_claims import extract_line_claim, strip_code_fences
from .scanner import ALLOW_MARKER, discover_rule_files

METHOD_VERSION = "SAGRADA-VITALS-METHOD v0.2"
# SHA-256 of docs/VITALS_METHOD_v0.2.md at freeze (2026-07-15); chained receipt in
# results/vitals/ (genesis = the v0.1 freeze receipt).
METHOD_SHA256 = "sha256:f747fe9f1f6f2814aacfff1f98597f8b2c325e00e6ddcae99c6b7ad95f860aae"

WINDOW_DAYS = 365
CHURN_MIN = 3   # v0.2: >=3 same-pair revivals collapse to one churn event

BANDS = (  # lower bound (inclusive) -> label; display only, never used in math.
    (90, "SOUND"),
    (75, "WATCH"),
    (45, "ROTTING"),
    (0, "OVERRUN"),
)

# Display names (ratified 2026-07-17). The CANONICAL strings above are frozen
# with the method: they appear in ``--json`` output, receipts, and sealed banks
# forever, so every historical artifact recomputes byte-for-byte. What humans
# see — the headline line and the badge — speaks the display ladder. A renamed
# canon would be a method change (v0.3+); a renamed display is not.
BAND_DISPLAY = {
    "SOUND": "CLEAR",      # an absence-claim: nothing detectable, not "good"
    "WATCH": "EXPOSED",    # at risk; attention, not yet judgment
    "ROTTING": "WALKING",  # dead rules are active among the living
    "OVERRUN": "ROTTED",   # decay complete
}


def display_band(canonical: str) -> str:
    """Human-facing name for a canonical band label (unknown labels pass through)."""
    return BAND_DISPLAY.get(canonical, canonical)


def monochrome_band(canonical: str) -> str:
    """MONOCHROME register form (design law, 2026-07-18): bracketed caps; the
    terminal band carries the plain-text terminal mark `*`. NOT SCORED is not
    a band and is never bracketed."""
    if canonical not in BAND_DISPLAY:
        return canonical
    name = BAND_DISPLAY[canonical]
    return f"[{name}]*" if canonical == "OVERRUN" else f"[{name}]"


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
    # v0.2: the window anchors to the repo's pinned HEAD, exactly as the method
    # text says — not to the newest rule-file commit (a repo whose rule files
    # went quiet must not be scored against a stale endpoint).
    head = _git(repo_path, ["log", "-1", "--format=%H %ct"])
    if head:
        sha, _, ts = head.strip().partition(" ")
        rec.snapshot_commit, rec.snapshot_ts = sha, int(ts or 0)
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

    # v0.2 accounting (method changelog items 1-2; formula untouched).
    # Churn collapse: >=3 revivals sharing one (retraction-commit -> revival-
    # commit) pair are ONE file-level churn event, for e and for a alike.
    pair_groups: Dict[Tuple[str, str], List[RuleEvent]] = {}
    for ev in revivals:
        pair_groups.setdefault((ev.retracted_at or "", ev.commit), []).append(ev)
    churn_pairs = {k for k, v in pair_groups.items() if len(v) >= CHURN_MIN}
    e_count = sum(1 for k in pair_groups if k in churn_pairs) + \
        sum(len(v) for k, v in pair_groups.items() if k not in churn_pairs)

    # Active dedup: one rule cannot be undead twice — latest event per
    # (file, term); active iff that latest event is a still-present revival.
    latest: Dict[Tuple[str, str], RuleEvent] = {}
    for ev in revivals:
        key = (ev.file, ev.term)
        cur = latest.get(key)
        if cur is None or (ev.ts, ev.commit) > (cur.ts, cur.commit):
            latest[key] = ev
    deduped = [ev for ev in latest.values()
               if (ev.file, ev.term) in rec.final_presence
               and not _later("death", ev)]
    active_plain = [ev for ev in deduped
                    if (ev.retracted_at or "", ev.commit) not in churn_pairs]
    churn_groups: Dict[Tuple[str, str], List[RuleEvent]] = {}
    for ev in deduped:
        k = (ev.retracted_at or "", ev.commit)
        if k in churn_pairs:
            churn_groups.setdefault(k, []).append(ev)
    a_count = len(active_plain) + len(churn_groups)

    # Mass deaths that later revive as churn collapse to one death.
    churn_death_commits = {k[0] for k in churn_pairs}
    death_by_commit: Dict[str, List[RuleEvent]] = {}
    for ev in deaths:
        death_by_commit.setdefault(ev.commit, []).append(ev)
    d_count, c_count = 0, 0
    for commit, evs in death_by_commit.items():
        if commit in churn_death_commits and len(evs) >= CHURN_MIN:
            d_count += 1                       # one collapsed death; revived -> not clean
        else:
            d_count += len(evs)
            c_count += sum(1 for ev in evs if not _later("revival", ev))

    return {
        "a": a_count, "e": e_count, "d": d_count, "c": c_count,
        "r": (c_count / d_count) if d_count > 0 else 0.0,
        "active_events": active_plain, "churn_groups": churn_groups,
        "window_days": window_days,
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
        ] + [
            {"file": members[0].file, "term": f"(file churn ×{len(members)})",
             "churn": True, "members": len(members),
             "terms": sorted(ev.term for ev in members),
             "revived_at": members[0].commit,
             "retracted_at": members[0].retracted_at, "ts": members[0].ts}
            for members in inp["churn_groups"].values()
        ],
        "not_measured": "agent answer correctness, code quality, security, or any "
                        "LLM output; only structured rules are tracked",
    }


def badge_json(score: int) -> Dict[str, object]:
    """shields.io endpoint JSON for the belief-integrity badge.

    Colors follow the token law (no gold anywhere): CLEAR is unmarked — plain
    ink, an absence-claim, never a medal of any color (founder-ratified
    2026-07-18) — and the found-states are one sienna, deepening with severity.
    """
    colors = {"SOUND": "#4A453C", "WATCH": "#C0714D",
              "ROTTING": "#AC5230", "OVERRUN": "#6B2E1F"}
    b = band(score)
    mark = "■ " if b == "OVERRUN" else ""  # terminal ink mark, ROTTED only
    return {"schemaVersion": 1, "label": "belief-integrity",
            "message": f"{score} ({mark}{display_band(b)})", "color": colors[b]}
