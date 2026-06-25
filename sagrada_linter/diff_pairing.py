"""Diff two versions of a rule file and emit the claim-level Change stream (add / change /
remove). Pure stdlib (difflib) — the deterministic floor under the scanner; no model, no
network. A `change` carries the before/after pairing the flat document loses.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Callable, List, Optional, Tuple

from .md_claims import extract_line_claim

Claim = Tuple[str, str]               # (normalized_term, definition)
Extractor = Callable[[str], Optional[Claim]]

# Minimum token-Jaccard overlap to pair two term-mismatched lines as one rewrite
# (pass 2). Above it: a rescued rename (nix_config -> toml_config). Below it: an
# unrelated removal + addition that merely shared a replace hunk. A deterministic
# relatedness gate — the extractor is the upgrade for borderline pairs.
PAIR_SIM_THRESHOLD = 0.4

# Cross-hunk move/reword reconciliation is more speculative than in-hunk pairing
# (the lines are not diff-adjacent), so it uses a stricter gate.
CROSS_HUNK_SIM_THRESHOLD = 0.5


@dataclass
class Change:
    """One revision event located by the diff.

    ``kind`` is the delta type; the downstream layer maps it to an revision op.
    For ``change`` whose ``old_claim`` and ``new_claim`` carry *different* terms,
    the diff has paired a rewrite the term-matcher would have missed — anchor the
    belief's identity on the OLD term and let the classifier confirm revise vs.
    two-independent-ops (the diff localizes; the extractor judges the residue).
    """

    kind: str                          # "add" | "change" | "remove"
    old_line: Optional[str]            # present for change / remove
    new_line: Optional[str]            # present for change / add
    old_claim: Optional[Claim]         # (term, defn) extracted from old_line
    new_claim: Optional[Claim]         # (term, defn) extracted from new_line
    new_line_no: Optional[int] = None  # 1-based line in the NEW file (None for pure removals)

    @property
    def term(self) -> str:
        """The belief's anchor term: the new term for an add, otherwise the old
        term (identity is anchored on the pre-existing concept)."""
        if self.kind == "add":
            return self.new_claim[0] if self.new_claim else ""
        if self.old_claim:
            return self.old_claim[0]
        return self.new_claim[0] if self.new_claim else ""

    @property
    def is_rename(self) -> bool:
        """A change whose paired claims carry different terms — the noisy-term
        reversal the diff rescued (a flag for the classifier / receipt)."""
        return (
            self.kind == "change"
            and self.old_claim is not None
            and self.new_claim is not None
            and self.old_claim[0] != self.new_claim[0]
        )


def pair_changes(
    old_text: str,
    new_text: str,
    extract: Extractor = extract_line_claim,
    detect_moves: bool = True,
) -> List[Change]:
    """Diff two versions and emit the claim-level ``Change`` stream.

    The first version is ingested by diffing against the empty string
    (``pair_changes("", first)`` -> all adds), so the state-bootstrap is just a
    special case of the delta path. Cosmetic/reformat-only differences emit
    nothing. Pairing is term-stable first, then similarity-gated within a hunk;
    ``detect_moves`` then reconciles a belief deleted in one hunk and re-added
    (often reworded) in another into a single change.
    """
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    sm = SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    changes: List[Change] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag == "insert":
            changes.extend(_emit_adds(new_lines, j1, j2, extract))
        elif tag == "delete":
            changes.extend(_emit_removes(old_lines, i1, i2, extract))
        elif tag == "replace":
            changes.extend(_emit_replace(old_lines, new_lines, i1, i2, j1, j2, extract))
    if detect_moves:
        changes = reconcile_moves(changes)
    return changes


def reconcile_moves(changes: List[Change], threshold: float = CROSS_HUNK_SIM_THRESHOLD) -> List[Change]:
    """Cross-hunk move/reword detection (the dominant precision lever on real
    reorganized files). A belief whose line is deleted in one hunk and re-added
    in another — often *reworded*, so the noisy extractor gives it a different
    term — appears as a separate ``remove`` + ``add``. Match high-similarity
    (remove, add) pairs across hunks and promote each to a single ``change``,
    leaving genuine deletions/additions untouched. Deterministic; no extractor.
    """
    removes = [c for c in changes if c.kind == "remove"]
    adds = [c for c in changes if c.kind == "add"]
    out = [c for c in changes if c.kind == "change"]
    used_add = set()
    for rem in removes:
        best, best_sim = None, -1.0
        for i, ad in enumerate(adds):
            if i in used_add:
                continue
            sim = _similarity(rem.old_line or "", ad.new_line or "")
            if sim >= threshold and sim > best_sim:
                best, best_sim = i, sim
        if best is not None:
            used_add.add(best)
            ad = adds[best]
            out.append(Change("change", rem.old_line, ad.new_line,
                              rem.old_claim, ad.new_claim, ad.new_line_no))
        else:
            out.append(rem)  # a genuine deletion
    for i, ad in enumerate(adds):
        if i not in used_add:
            out.append(ad)  # a genuine addition
    return out


def summarize_changes(changes: List[Change]) -> dict:
    """Counts by kind — for the ingest stats line and regression assertions."""
    out = {"add": 0, "change": 0, "remove": 0, "rename": 0}
    for c in changes:
        out[c.kind] = out.get(c.kind, 0) + 1
        if c.is_rename:
            out["rename"] += 1
    return out


# --- internals -------------------------------------------------------------

def _claim_lines(lines: List[str], lo: int, hi: int, extract: Extractor):
    """[(line_text, (term, defn), 1based_line_no), ...] for claim-bearing lines."""
    out = []
    for idx in range(lo, hi):
        c = extract(lines[idx])
        if c is not None:
            out.append((lines[idx], c, idx + 1))
    return out


def _emit_adds(new_lines, j1, j2, extract) -> List[Change]:
    return [
        Change("add", None, line, None, claim, ln)
        for line, claim, ln in _claim_lines(new_lines, j1, j2, extract)
    ]


def _emit_removes(old_lines, i1, i2, extract) -> List[Change]:
    return [
        Change("remove", line, None, claim, None, None)
        for line, claim, _ in _claim_lines(old_lines, i1, i2, extract)
    ]


def _key(claim: Claim) -> Tuple[str, str]:
    return (claim[0], claim[1].strip())


def _tokens(s: str) -> set:
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def token_similarity(a: str, b: str) -> float:
    """Token-Jaccard of two strings — a deterministic relatedness signal,
    shared by the line differ (this module) and the claim-set differ."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


_similarity = token_similarity  # internal alias (back-compat within this module)


def _drop_unchanged(olds, news):
    """Remove claims that appear *identically* (term + defn) on both sides — they
    were swept into a replace hunk by changed neighbors, not actually revised."""
    used = set()
    keep_old = []
    for o in olds:
        match = None
        for ni, n in enumerate(news):
            if ni not in used and _key(n[1]) == _key(o[1]):
                match = ni
                break
        if match is None:
            keep_old.append(o)
        else:
            used.add(match)
    keep_new = [n for ni, n in enumerate(news) if ni not in used]
    return keep_old, keep_new


def _emit_replace(old_lines, new_lines, i1, i2, j1, j2, extract) -> List[Change]:
    """The heart of the fix. Within a replace hunk:
      0. drop claims unchanged on both sides (cosmetic / reflow noise);
      1. pair by stable TERM — same term + changed defn = an unambiguous revise
         (e.g. ``tests: 329`` -> ``tests: 328``);
      2. pair the remainder POSITIONALLY — this is the noisy-term reversal the
         deterministic floor missed: the diff KNOWS they're paired even though the
         extractor named them differently (``nix_config`` -> ``toml_config``);
      3. true leftovers -> remove / add.
    """
    olds = _claim_lines(old_lines, i1, i2, extract)
    news = _claim_lines(new_lines, j1, j2, extract)
    olds, news = _drop_unchanged(olds, news)

    changes: List[Change] = []
    paired_news = set()
    remaining_olds = []

    # pass 1 — stable-term revises
    for o_line, o_claim, _ in olds:
        match = None
        for ni, (_, n_claim, _) in enumerate(news):
            if ni not in paired_news and n_claim[0] == o_claim[0]:
                match = ni
                break
        if match is not None:
            n_line, n_claim, n_ln = news[match]
            paired_news.add(match)
            changes.append(Change("change", o_line, n_line, o_claim, n_claim, n_ln))
        else:
            remaining_olds.append((o_line, o_claim))

    leftover_news = [news[i] for i in range(len(news)) if i not in paired_news]

    # pass 2 — similarity-matched pairing of the term-unmatched remainder. Each
    # remaining old pairs with its most-similar leftover new ABOVE the gate (a
    # rescued rename); an old with no similar-enough new is a true removal, and
    # any unpaired new is a true addition. Candidate rewrites the extractor refines.
    used_leftover = set()
    for o_line, o_claim in remaining_olds:
        best, best_sim = None, -1.0
        for li, (n_line, _n_claim, _n_ln) in enumerate(leftover_news):
            if li in used_leftover:
                continue
            sim = _similarity(o_line, n_line)
            if sim >= PAIR_SIM_THRESHOLD and sim > best_sim:
                best, best_sim = li, sim
        if best is not None:
            used_leftover.add(best)
            n_line, n_claim, n_ln = leftover_news[best]
            changes.append(Change("change", o_line, n_line, o_claim, n_claim, n_ln))
        else:
            changes.append(Change("remove", o_line, None, o_claim, None, None))

    # pass 3 — unpaired news are true additions
    for li, (n_line, n_claim, n_ln) in enumerate(leftover_news):
        if li not in used_leftover:
            changes.append(Change("add", None, n_line, None, n_claim, n_ln))

    return changes
