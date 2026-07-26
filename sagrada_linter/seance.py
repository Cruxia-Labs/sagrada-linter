"""The séance — exoneration by the user's own transcript. Deterministic, local.

A zombie is a retracted rule walking again WITHOUT a record of the decision.
But sometimes the record exists — one layer down, in the user's own agent
conversation: "put the retry rule back." That is not a zombie; it is a
RESTORATION, and the instrument must acquit as readily as it accuses
(board convergence 7/9; the founder's own question made this a feature).

No model participates. Matching is arithmetic over local JSONL transcripts:

  VERBATIM  — the rule's normalized text appears inside an in-window
              utterance. Strong evidence: verdict RESTORATION.
  REFERENCE — an in-window utterance uses a restoration verb (re-add,
              bring back, restore, put back, revert ...) AND shares >=50%
              of the rule's content words (min 2). Quotable evidence,
              labeled as such: verdict RESTORATION_CANDIDATE — surfaced as
              "possible exonerating evidence", never silently absolved.

The window is [retraction, re-add + slack]: the request to restore a rule
necessarily happens after it died and at (or shortly before) its return.
Presence of the request is proven by quote + timestamp; intent beyond the
quoted words is never claimed (presence-not-causation, applied to people).
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from .scanner import ZombieEvent
from .sessions import iter_session, list_sessions, session_start

RESTORE_VERB = re.compile(
    r"\b(re-?add(?:ed|ing)?|add(?:ed|ing)?\s+(?:it\s+|that\s+|this\s+|the\s+\S+\s+)?back"
    r"|restor(?:e|ed|ing)|bring(?:ing)?\s+(?:it\s+|that\s+|this\s+)?back"
    r"|brought\s+(?:it\s+|that\s+|this\s+)?back"
    r"|put(?:ting)?\s+(?:it\s+|that\s+|this\s+|the\s+\S+\s+)?back"
    r"|revert(?:ed|ing)?|un-?delete[ds]?|resurrect(?:ed|ing)?)\b",
    re.IGNORECASE,
)

_STOP = frozenset(
    "the a an and or not for with without to of in on at by from is are was "
    "were be been do does did will would should must may can it its this that "
    "these those you your we our use using never always all any".split()
)
_WORD = re.compile(r"[a-z0-9][a-z0-9_.-]{2,}")


@dataclass
class SeanceEvidence:
    """One quotable, timestamped utterance that speaks for the revival."""

    verdict: str        # RESTORATION | RESTORATION_CANDIDATE
    tier: str           # verbatim | reference
    session: str        # session file basename (no path)
    ts: str             # the utterance's own timestamp (as recorded)
    role: str           # user | assistant
    quote: str          # the matched line, trimmed
    overlap: float      # content-word overlap (1.0 for verbatim)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def _content_words(s: str) -> frozenset:
    """Crude prefix stems (6 chars) so 'manual' meets 'manually' and
    'migration' meets 'migrations' — deterministic, no linguistics."""
    return frozenset(w[:6] for w in _WORD.findall(_norm(s)) if w not in _STOP)


def _ts_key(iso_or_raw: str) -> str:
    """First 19 chars of an ISO timestamp — lexicographically comparable
    across 'Z' / '+00:00' suffix styles."""
    return (iso_or_raw or "")[:19]


def _unix_to_key(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()[:19]


def exonerate(event: ZombieEvent, sessions_root: str,
              slack_days: int = 3) -> Optional[SeanceEvidence]:
    """Search local transcripts for a restoration request covering ``event``.

    Returns the best evidence (verbatim beats reference; earlier beats
    later) or None. Window: [retracted_ts, re_added_ts + slack]; an unknown
    re-add time (worktree pseudo-commit) opens the window to now.
    """
    lo = _unix_to_key(event.retracted_ts) if event.retracted_ts > 0 else ""
    hi_unix = (event.re_added_ts if event.re_added_ts > 0 else int(time.time()))
    hi = _unix_to_key(hi_unix + slack_days * 86400)

    rule_text = _norm(event.re_added_def or event.retracted_def)
    rule_words = _content_words(f"{event.term} {event.re_added_def or event.retracted_def}")
    if not rule_text or not rule_words:
        return None

    hits: List[SeanceEvidence] = []
    for path in list_sessions(sessions_root):
        if _ts_key(session_start(path)) > hi:
            continue  # session began after the window closed
        base = path.rsplit("/", 1)[-1]
        for ts, role, text in iter_session(path):
            k = _ts_key(ts)
            if not k or k < lo or k > hi:
                continue
            for line in text.splitlines():
                nl = _norm(line)
                if not nl:
                    continue
                if rule_text in nl:
                    hits.append(SeanceEvidence(
                        verdict="RESTORATION", tier="verbatim", session=base,
                        ts=ts, role=role, quote=line.strip()[:300], overlap=1.0))
                    continue
                if RESTORE_VERB.search(nl):
                    words = _content_words(line)
                    common = rule_words & words
                    overlap = len(common) / len(rule_words)
                    if len(common) >= 2 and overlap >= 0.5:
                        hits.append(SeanceEvidence(
                            verdict="RESTORATION_CANDIDATE", tier="reference",
                            session=base, ts=ts, role=role,
                            quote=line.strip()[:300], overlap=round(overlap, 3)))
    if not hits:
        return None
    hits.sort(key=lambda h: (h.tier != "verbatim", _ts_key(h.ts)))
    return hits[0]


def evidence_key(event: ZombieEvent) -> str:
    """Two zombies can share a file:line (different terms, one line) —
    key evidence by location AND term."""
    return f"{event.location()}::{event.term}"


def exonerate_all(events: List[ZombieEvent], sessions_root: str,
                  slack_days: int = 3) -> dict:
    """Map evidence_key(event) -> SeanceEvidence (only where found)."""
    out = {}
    for ev in events:
        hit = exonerate(ev, sessions_root, slack_days=slack_days)
        if hit is not None:
            out[evidence_key(ev)] = hit
    return out
