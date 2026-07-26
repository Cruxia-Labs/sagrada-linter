"""The Communion — the staged first reading of a repo's belief history.

`sagrada-linter read .` — the acquisition half of the two-product truth
(the gate is the retention half). Beats, per the composite demo the board
converged on:

  custody -> reconstruction -> [D3: exoneration-first | reveal-first]
  -> epitaphs (commit pair, days walking) -> cross-examination hint
  -> clean-baseline path -> the gate offer

Copy laws enforced here, not by authors: presence never causation ("active
again", never "obeyed"); the villain is the rot, never a repo; a clean
reading is a signed baseline, never an anticlimax; no scores, no
percentiles. Display strings come from lexicon.LEX (naming indirection).

The Epitaph file is a Vigil-surface artifact (THE ORDINARY v1.2 R5):
script-free, self-contained, grief-toned warm charcoal — verification is
the CLI's job (`sagrada-linter verify`), so the card stays inert.
"""
from __future__ import annotations

import html
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import os
import re

from .lexicon import LEX
from .md_claims import extract_line_claim, strip_code_fences
from .scanner import ALLOW_MARKER, ZombieEvent
from .seance import SeanceEvidence, evidence_key

# ── Vigil palette (vendored values; law + canonical tokens live in the
#    design system's tokens.css — re-tunable there, synced here) ──
VIGIL = {
    "paper": "#1C1A16", "card": "#23201A", "line": "#3B362C",
    "ink": "#ECE5D6", "ink2": "#B9B1A1", "ink3": "#8C8577",
    "sienna": "#CB6B47", "sienna_text": "#D98B6B", "teal": "#8CBABD",
    "rubric": "#D0654E",
}


def _date(ts: int) -> str:
    if ts <= 0:
        return "worktree"
    return datetime.fromtimestamp(ts, timezone.utc).date().isoformat()


def _c(text: str, code: str, color: bool) -> str:
    return f"\033[{code}m{text}\033[0m" if color else text


class Stage:
    """Beat printer: quiet pacing on a TTY, silent in pipes and tests."""

    def __init__(self, pace: float):
        self.pace = pace if sys.stdout.isatty() else 0.0

    def beat(self, text: str = "") -> None:
        print(text, flush=True)
        if self.pace:
            time.sleep(self.pace)


def declared_restorations(repo_root: str,
                          by_file: Dict[str, List[ZombieEvent]]) -> Dict[str, SeanceEvidence]:
    """A revived term whose CURRENT line carries the allow-marker is a
    DECLARED restoration — the paperwork exists in the file itself
    (`sagrada-linter restore` writes it). Historical revival events on such
    terms are acquitted at read time; the history is not rewritten, the
    verdict about TODAY is. Returned as synthetic evidence so every
    downstream surface (ordering, tally, epitaph file, --strict) inherits
    the acquittal uniformly."""
    out: Dict[str, SeanceEvidence] = {}
    for fpath, events in by_file.items():
        try:
            content = open(os.path.join(repo_root, fpath), encoding="utf-8").read()
        except OSError:
            continue
        marked: Dict[str, str] = {}
        for line in strip_code_fences(content).splitlines():
            if ALLOW_MARKER not in line:
                continue
            claim = extract_line_claim(line)
            if claim is None:
                continue
            m = re.search(re.escape(ALLOW_MARKER) + r"(.*?)(?:-->|$)", line)
            marked[claim[0]] = (m.group(1).strip(" —-:") if m else "")[:200]
        for ev in events:
            note = marked.get(ev.term)
            if note is not None:
                out[evidence_key(ev)] = SeanceEvidence(
                    verdict="RESTORATION", tier="declared", session="in-file",
                    ts="", role="record", quote=note or "declared restoration",
                    overlap=1.0)
    return out


def epitaph_lines(ev: ZombieEvent, evidence: Optional[SeanceEvidence],
                  color: bool) -> List[str]:
    """One finding, rendered as its epitaph (terminal form)."""
    days = ev.days_undead()
    out: List[str] = []
    if evidence is not None and evidence.verdict == "RESTORATION":
        mark = _c("o RESTORED WITH INTENT", "32", color)
        out.append(f"{mark}  {ev.term}")
        out.append(f'    "{ev.re_added_def.strip()[:120]}"')
        out.append(f"    killed   {ev.retracted_at[:8]}  {_date(ev.retracted_ts)}")
        out.append(f"    returned {ev.re_added_at[:8]}  {_date(ev.re_added_ts)}  — with the decision on the books:")
        stamp = f"{evidence.ts[:19]} · " if evidence.ts else ""
        out.append(f'    {stamp}{evidence.session} · "{evidence.quote[:140]}"')
        out.append("    not a zombie. an intentional restoration, recorded.")
        return out
    walking = _c("+ WALKING", "31;1", color)
    out.append(f"{walking}  {ev.term}")
    out.append(f'    "{ev.re_added_def.strip()[:120]}"')
    out.append(f"    killed   {ev.retracted_at[:8]}  {_date(ev.retracted_ts)}")
    out.append(f"    revived  {ev.re_added_at[:8]}  {_date(ev.re_added_ts)}")
    where = ev.location()
    dtxt = f" · walking {days} day{'s' if days != 1 else ''}" if days is not None else ""
    out.append(f"    active again in {where} today{dtxt}")
    if evidence is not None:  # RESTORATION_CANDIDATE
        out.append("    possible exonerating evidence (labeled candidate, not absolution):")
        out.append(f'      {evidence.ts[:19]} · {evidence.session} · "{evidence.quote[:120]}"')
        out.append(f"      restore it properly: sagrada-linter restore {ev.file} "
                   f"{ev.re_added_line or 0} --reason \"...\"")
    return out


def run_reading(*, repo_label: str, scanned: List[str], n_commits: Optional[int],
                by_file: Dict[str, List[ZombieEvent]],
                evidence: Dict[str, SeanceEvidence],
                order: str, pace: float, color: bool,
                seance_used: bool) -> None:
    """The staged terminal experience. Pure rendering — every verdict was
    decided upstream by arithmetic (scanner) and transcript match (séance)."""
    st = Stage(pace)
    events = [(f, e) for f, evs in sorted(by_file.items()) for e in evs]
    exonerated = [(f, e) for f, e in events
                  if evidence.get(evidence_key(e), None) is not None
                  and evidence[evidence_key(e)].verdict == "RESTORATION"]
    accused = [(f, e) for f, e in events if (f, e) not in exonerated]

    # custody
    st.beat(f"{LEX['experience'].upper()} — {repo_label}")
    across = f" across {n_commits} commits" if n_commits else ""
    st.beat(f"reading {len(scanned)} rule file{'s' if len(scanned) != 1 else ''}"
            f"{across}. nothing leaves this machine.")
    st.beat("")

    if not events:
        st.beat(_c("NO REVIVED RULES FOUND", "1", color))
        st.beat(f"every retraction in {len(scanned)} rule file"
                f"{'s' if len(scanned) != 1 else ''} is still resting.")
        st.beat("this is a result, not a shrug: add --receipt for a signed clean baseline")
        st.beat("that future runs (and CI) can defend.")
        return

    groups = ([exonerated, accused] if order == "exoneration-first"
              else [accused, exonerated])
    for group in groups:
        for f, e in group:
            for line in epitaph_lines(e, evidence.get(evidence_key(e)), color):
                st.beat(line)
            st.beat("")

    n_z = len(accused)
    n_r = len(exonerated)
    tally = f"{n_z} walking"
    if n_r:
        tally += f" · {n_r} restored with intent"
    st.beat(_c(tally, "1", color))
    if not seance_used:
        st.beat("(transcripts not consulted — add --seance to check your own"
                " sessions for restoration requests)")
    st.beat("")
    st.beat("do not trust this reading:")
    st.beat("  every line above is recomputable from your own git history —")
    st.beat("  add --receipt, then: sagrada-linter verify <receipt> (offline, byte-for-byte)")


# ── the Epitaph file (Vigil artifact: script-free, self-contained) ──────────

def write_epitaphs_html(path: str, *, repo_label: str,
                        events: List[ZombieEvent],
                        evidence: Dict[str, SeanceEvidence],
                        receipt_note: str = "") -> None:
    v = VIGIL
    cards = []
    for e in events:
        ev = evidence.get(evidence_key(e))
        restored = ev is not None and ev.verdict == "RESTORATION"
        days = e.days_undead()
        status = ("RESTORED WITH INTENT" if restored else
                  (f"walking {days} days" if days is not None else "walking"))
        state_color = v["ink2"] if restored else v["sienna"]
        seance_row = ""
        if ev is not None:
            label = ("the decision, on the books" if restored
                     else "possible exonerating evidence (candidate)")
            seance_row = (
                f'<div class="row s"><span>{html.escape(label)}</span>'
                f'<span class="m">{html.escape(ev.ts[:19])} · '
                f'&ldquo;{html.escape(ev.quote[:140])}&rdquo;</span></div>')
        cards.append(f"""
<article class="epitaph{' rest' if restored else ''}">
  <div class="term">{html.escape(e.term)}</div>
  <div class="def">&ldquo;{html.escape((e.re_added_def or '').strip()[:160])}&rdquo;</div>
  <div class="row"><span>killed</span><span class="m">{html.escape(e.retracted_at[:8])} · {_date(e.retracted_ts)}</span></div>
  <div class="row"><span>{'returned' if restored else 'revived'}</span><span class="m">{html.escape(e.re_added_at[:8])} · {_date(e.re_added_ts)}</span></div>
  <div class="row"><span>status</span><span class="m" style="color:{state_color}">{status}</span></div>
  {seance_row}
  <div class="row"><span>where</span><span class="m">{html.escape(e.location())} · present in the file today</span></div>
</article>""")
    walking = sum(1 for e in events
                  if not (evidence.get(evidence_key(e))
                          and evidence[evidence_key(e)].verdict == "RESTORATION"))
    rested = len(events) - walking
    tally = f"{walking} WALKING" + (f" · {rested} RESTORED" if rested else "")
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(LEX['artifact_plural'])} — {html.escape(repo_label)}</title>
<style>
/* THE VIGIL (R5) — a dark ARTIFACT, not a mode. No scripts, no fetches:
   verification is the CLI's job (sagrada-linter verify). */
body {{ margin:0; background:{v['paper']}; color:{v['ink']};
  font: 16px/1.6 Georgia, 'Times New Roman', serif; }}
.wrap {{ max-width:640px; margin:0 auto; padding:48px 24px 80px; }}
h1 {{ font-size:26px; font-weight:normal; letter-spacing:.02em; margin:0 0 4px; }}
.m {{ font-family: ui-monospace, Menlo, monospace; font-size:12.5px; color:{v['ink2']}; }}
.tally {{ font-family: ui-monospace, Menlo, monospace; font-size:14px;
  border:1px solid {v['line']}; display:inline-block; padding:4px 12px;
  margin:14px 0 26px; color:{v['ink']}; }}
.epitaph {{ border:1px solid {v['line']}; background:{v['card']};
  padding:18px 20px 12px; margin:0 0 18px; border-radius:3px; }}
.epitaph.rest {{ opacity:.82; }}
.term {{ font-family: ui-monospace, Menlo, monospace; font-size:13px;
  letter-spacing:.06em; color:{v['sienna_text']}; margin-bottom:6px; }}
.epitaph.rest .term {{ color:{v['ink2']}; }}
.def {{ font-style: italic; font-size:17px; margin:0 0 12px; }}
.row {{ display:flex; justify-content:space-between; gap:16px;
  border-top:1px solid {v['line']}; padding:5px 0; font-size:13px;
  color:{v['ink2']}; }}
.row.s span:last-child {{ text-align:right; max-width:70%; }}
footer {{ margin-top:30px; border-top:1px solid {v['line']}; padding-top:14px; }}
footer p {{ margin:6px 0; font-size:13px; color:{v['ink2']}; }}
</style></head><body><div class="wrap">
<h1>{html.escape(LEX['artifact_plural'])}</h1>
<div class="m">{html.escape(repo_label)} · read locally · nothing left the machine</div>
<div class="tally">{tally}</div>
{''.join(cards)}
<footer>
<p>every date and hash above is recomputable from this repository's own git
history — no model judged any of it.</p>
<p class="m">verify: uvx sagrada-linter verify &lt;receipt&gt;{html.escape(receipt_note)}</p>
</footer>
</div></body></html>
"""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)
