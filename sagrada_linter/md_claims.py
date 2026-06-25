"""Markdown-aware claim extractor.

The existing regex DecisionExtractor targets AI-coding-tool prose
("Decision:", "We'll use X") and returns nothing on markdown memory files
(CLAUDE.md / MEMORY.md). This extractor handles the patterns those files
actually use — `key: value`, `- term — definition`, `**bold**: definition` —
and emits (normalized_term, definition) pairs, one per term per file version.

Uses a vendored term-normalizer (terms._normalize_term).
"""

import re
from typing import List, Tuple

from .terms import _normalize_term

_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")

# "- <term> — <def>"  /  "- <term> -- <def>"  (em-dash or double-hyphen bullet)
_DASH = re.compile(r"^[\-\*]\s+(.+?)\s+(?:—|--)\s+(.+)$")
# "<term>: <def>"  optionally led by a single list marker
_COLON = re.compile(r"^[\-\*]?\s*(.+?):\s+(.+)$")

MIN_DEF_LEN = 8
MAX_TERM_WORDS = 10
MAX_TERM_LEN = 80

# Callout glyphs that mark an illustrative example bullet ("- ❌ Wrong: ...",
# "- ✅ Correct: ...") rather than an asserted belief. Such bullets otherwise
# normalize to junk terms (`_wrong`/`_correct`) — skip them at extraction.
_EXAMPLE_MARKERS = frozenset("❌✅✔✗✓🚫⛔❎☑")


def strip_code_fences(text: str) -> str:
    """Blank out lines inside fenced code blocks (``` or ~~~), preserving line
    positions, so code samples never become claims and code edits never diff as
    belief changes. The fence delimiter lines are blanked too.

    Phase-4 hardening: on real agent-instruction files the heuristic extractor
    grabbed fenced "wrong vs correct" example lines as claims (`_correct`/`_wrong`)
    — pure noise. Stripping fences before extraction/diffing removes it
    deterministically (no model needed)."""
    out = []
    in_fence = False
    marker = None
    for line in text.splitlines():
        s = line.lstrip()
        if s.startswith("```") or s.startswith("~~~"):
            tok = s[:3]
            if not in_fence:
                in_fence, marker = True, tok
            elif tok == marker:
                in_fence, marker = False, None
            out.append("")            # blank the fence line itself
            continue
        out.append("" if in_fence else line)
    return "\n".join(out)


def _clean_term(raw: str) -> str:
    """Strip markdown decoration from a term candidate."""
    raw = raw.strip()
    raw = re.sub(r"^[\-\*\|>#\s]+", "", raw)  # leading list/heading/table markers
    m = _BOLD.search(raw) or _CODE.search(raw)
    if m and len(m.group(1).strip()) >= 2:
        raw = m.group(1)  # term is the bolded/code-spanned label
    raw = _BOLD.sub(r"\1", raw)
    raw = _CODE.sub(r"\1", raw)
    return raw.strip()


def extract_line_claim(line: str):
    """Extract a single (normalized_term, definition) claim from one line,
    or None. Used both for whole-file extraction and for line-located checks."""
    s = line.strip()
    if not s or s.startswith("#") or s.startswith("```") or s.startswith("|"):
        return None  # headings, code fences, tables → skip
    body = re.sub(r"^[\-\*]\s*", "", s)  # peek past a leading list marker
    if body[:1] in _EXAMPLE_MARKERS:
        return None  # an illustrative ❌/✅ example bullet, not a belief
    m = _DASH.match(s) or _COLON.match(s)
    if not m:
        return None
    term = _clean_term(m.group(1))
    defn = m.group(2).strip()
    if not term or len(term.split()) > MAX_TERM_WORDS:
        return None  # prose sentence grabbed as a "term" → skip
    nterm = _normalize_term(term)
    if not (2 <= len(nterm) <= MAX_TERM_LEN) or len(defn) < MIN_DEF_LEN:
        return None
    return nterm, defn


def extract_markdown_claims(text: str) -> List[Tuple[str, str]]:
    """Extract (normalized_term, definition) claims from markdown text.

    One claim per normalized term per call (first occurrence wins), so a single
    file version yields a clean snapshot of its asserted beliefs.
    """
    claims: List[Tuple[str, str]] = []
    seen = set()
    for line in text.splitlines():
        c = extract_line_claim(line)
        if c is None or c[0] in seen:
            continue
        seen.add(c[0])
        claims.append(c)
    return claims
