"""Séance tests: exonerate / accuse / no-evidence, on synthetic transcripts."""
import json
import time

from sagrada_linter.scanner import ZombieEvent
from sagrada_linter.seance import evidence_key, exonerate, exonerate_all
from sagrada_linter.sessions import iter_session, list_sessions

T0 = 1_750_000_000  # retraction epoch
T1 = T0 + 40 * 86400  # re-add epoch


def _iso(unix):
    import datetime as dt
    return dt.datetime.fromtimestamp(unix, dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _write_session(root, name, events):
    proj = root / "projA"
    proj.mkdir(exist_ok=True)
    p = proj / name
    lines = []
    for unix, role, text in events:
        lines.append(json.dumps({
            "timestamp": _iso(unix),
            "message": {"role": role, "content": [{"type": "text", "text": text}]},
        }))
    p.write_text("\n".join(lines) + "\n")
    return p


def _zombie(term="deploy-rule", definition="Always run migrations manually before deploy"):
    return ZombieEvent(
        file="CLAUDE.md", term=term, retracted_at="aaa111",
        retracted_def=definition, re_added_at="bbb222", re_added_line=7,
        re_added_def=definition, changed_meaning=False,
        retracted_ts=T0, re_added_ts=T1)


def test_verbatim_restoration(tmp_path):
    _write_session(tmp_path, "s1.jsonl", [
        (T0 + 5 * 86400, "user",
         "please put this back in CLAUDE.md: Always run migrations manually before deploy"),
    ])
    hit = exonerate(_zombie(), str(tmp_path))
    assert hit is not None
    assert hit.verdict == "RESTORATION" and hit.tier == "verbatim"
    assert "migrations manually" in hit.quote


def test_reference_restoration_candidate(tmp_path):
    _write_session(tmp_path, "s1.jsonl", [
        (T1 - 86400, "user",
         "can you re-add the manual migrations rule for deploy? we need it for Q3"),
    ])
    hit = exonerate(_zombie(), str(tmp_path))
    assert hit is not None
    assert hit.verdict == "RESTORATION_CANDIDATE" and hit.tier == "reference"
    assert 0.5 <= hit.overlap <= 1.0


def test_out_of_window_request_does_not_exonerate(tmp_path):
    _write_session(tmp_path, "s1.jsonl", [
        # request BEFORE the retraction — cannot explain the revival
        (T0 - 10 * 86400, "user",
         "re-add the manual migrations rule for deploy please"),
    ])
    assert exonerate(_zombie(), str(tmp_path)) is None


def test_unrelated_chatter_stays_accused(tmp_path):
    _write_session(tmp_path, "s1.jsonl", [
        (T0 + 86400, "user", "let's bring back the dark theme on the settings page"),
        (T0 + 2 * 86400, "user", "migrations are slow today"),
    ])
    assert exonerate(_zombie(), str(tmp_path)) is None


def test_restore_verb_required_for_reference_tier(tmp_path):
    _write_session(tmp_path, "s1.jsonl", [
        # high overlap but no restoration verb — not evidence of a request
        (T0 + 86400, "user", "the manual migrations deploy rule was interesting"),
    ])
    assert exonerate(_zombie(), str(tmp_path)) is None


def test_verbatim_beats_reference_and_earlier_beats_later(tmp_path):
    _write_session(tmp_path, "s1.jsonl", [
        (T0 + 9 * 86400, "user", "re-add the manual migrations rule for deploy"),
        (T0 + 20 * 86400, "user",
         "restore: Always run migrations manually before deploy"),
    ])
    hit = exonerate(_zombie(), str(tmp_path))
    assert hit.tier == "verbatim"  # stronger tier wins despite being later


def test_worktree_open_window(tmp_path):
    z = _zombie()
    z.re_added_ts = 0  # worktree pseudo-commit: window opens to now
    _write_session(tmp_path, "s1.jsonl", [
        (int(time.time()) - 3600, "user",
         "put back: Always run migrations manually before deploy"),
    ])
    hit = exonerate(z, str(tmp_path))
    assert hit is not None and hit.verdict == "RESTORATION"


def test_exonerate_all_maps_by_key(tmp_path):
    _write_session(tmp_path, "s1.jsonl", [
        (T0 + 5 * 86400, "user",
         "put this back: Always run migrations manually before deploy"),
    ])
    z1 = _zombie()
    z2 = _zombie(term="other-rule", definition="Never push to main on Fridays")
    out = exonerate_all([z1, z2], str(tmp_path))
    assert evidence_key(z1) in out and evidence_key(z2) not in out
    # same file:line, different terms — keys must not collide
    assert evidence_key(z1) != evidence_key(z2)


def test_sessions_reader_drops_noise_and_tools(tmp_path):
    proj = tmp_path / "projB"
    proj.mkdir()
    p = proj / "s.jsonl"
    rows = [
        {"timestamp": _iso(T0), "message": {"role": "user", "content": [
            {"type": "text", "text": "<system-reminder>noise</system-reminder>"},
            {"type": "tool_use", "name": "Bash", "input": {}},
            {"type": "text", "text": "real words"}]}},
        {"timestamp": _iso(T0 + 1), "message": {"role": "assistant",
                                                "content": "plain string"}},
        {"not": "a message"},
    ]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    got = list(iter_session(str(p)))
    assert ("user" in {r for _, r, _ in got}) and len(got) == 2
    assert all("system-reminder" not in t for _, _, t in got)
    assert list_sessions(str(tmp_path)) == [str(p)]
