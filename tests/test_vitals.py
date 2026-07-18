"""Vitals: frozen reference table (exact) + synthetic-repo integration."""
import os
import subprocess
import time

import pytest

from sagrada_linter.vitals import (
    band, badge_json, collect_record, compute_vitals, vitals_for_repo, window_inputs,
)

# The method doc's reference table, verbatim (docs/VITALS_METHOD_v0.1.md).
# These are FROZEN — a failure here means the formula drifted from v0.1.
REFERENCE = [
    (0, 0, 0.0, 100, "SOUND"),
    (0, 1, 1.0, 96, "SOUND"),
    (0, 5, 0.5, 88, "WATCH"),
    (1, 1, 0.0, 67, "ROTTING"),
    (1, 1, 0.9, 75, "WATCH"),
    (3, 6, 0.2, 47, "ROTTING"),
    (8, 10, 0.0, 41, "OVERRUN"),
]


@pytest.mark.parametrize("a,e,r,want_score,want_band", REFERENCE)
def test_reference_table_exact(a, e, r, want_score, want_band):
    score = compute_vitals(a, e, r)
    assert score == want_score
    assert band(score) == want_band


def test_badge_json_shape():
    b = badge_json(94)
    assert b["schemaVersion"] == 1
    assert b["label"] == "belief-integrity"
    assert b["message"].startswith("94")


def test_badge_speaks_display_names_not_canonical():
    # The badge is presentation: display ladder, no gold, ink for CLEAR
    # (unmarked is the healthy state — founder-ratified 2026-07-18).
    assert badge_json(94)["message"] == "94 (CLEAR)"
    assert badge_json(94)["color"] == "#4A453C"
    assert badge_json(80)["message"] == "80 (EXPOSED)"
    assert badge_json(60)["message"] == "60 (WALKING)"
    # v1.1: the terminal band wears the ink mark ■ and the deepened fill —
    # no other band may (grayscale/monochrome discriminability law).
    assert badge_json(10)["message"] == "10 (■ ROTTED)"
    assert badge_json(10)["color"] == "#6B2E1F"
    for score in (94, 80, 60):
        assert "■" not in badge_json(score)["message"]
    for score in (94, 80, 60, 10):
        assert "#C2902E" not in badge_json(score).values()  # gold retired


def test_monochrome_register():
    # MONOCHROME.md law: bracketed caps; `*` on the terminal band only;
    # NOT SCORED is not a band and is never bracketed.
    from sagrada_linter.vitals import monochrome_band
    assert monochrome_band("SOUND") == "[CLEAR]"
    assert monochrome_band("WATCH") == "[EXPOSED]"
    assert monochrome_band("ROTTING") == "[WALKING]"
    assert monochrome_band("OVERRUN") == "[ROTTED]*"
    assert monochrome_band("NOT SCORED") == "NOT SCORED"


def test_display_band_maps_all_canonical_labels():
    from sagrada_linter.vitals import BAND_DISPLAY, BANDS, display_band
    assert {lbl for _, lbl in BANDS} == set(BAND_DISPLAY)
    assert display_band("SOUND") == "CLEAR"
    assert display_band("NOT SCORED") == "NOT SCORED"  # unknown passes through


def test_canonical_band_unchanged_by_display_layer():
    # The frozen method surface: result dicts / receipts keep canonical strings.
    assert band(100) == "SOUND" and band(75) == "WATCH"
    assert band(45) == "ROTTING" and band(0) == "OVERRUN"


def _git(repo, *args, env_ts=None):
    env = dict(os.environ,
               GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t.local",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t.local")
    if env_ts is not None:
        stamp = f"{env_ts} +0000"
        env["GIT_AUTHOR_DATE"] = stamp
        env["GIT_COMMITTER_DATE"] = stamp
    subprocess.run(["git", "-C", str(repo), *args], check=True, env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _commit(repo, content, msg, ts):
    (repo / "AGENTS.md").write_text(content)
    _git(repo, "add", "-A", env_ts=ts)
    _git(repo, "commit", "-m", msg, env_ts=ts)


NOW = int(time.time())
WEEK = 7 * 86400


@pytest.fixture()
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", ".")
    return r


def test_clean_repo_scores_100(repo):
    _commit(repo, "# Rules\ndb-target: use the prod db\n", "one", NOW - 3 * WEEK)
    _commit(repo, "# Rules\ndb-target: use the prod db\ntimeout: 30s\n", "two", NOW - WEEK)
    result = vitals_for_repo(str(repo))
    assert result["inputs"] == {"a": 0, "e": 0, "d": 0, "c": 0, "r": 0.0,
                                "window_days": 365}
    assert result["score"] == 100
    assert result["band"] == "SOUND"


def test_active_zombie_scores_67(repo):
    # birth -> death -> revival, all in-window; the corpse is present at HEAD.
    _commit(repo, "# Rules\nretry-policy: retry 3 times\ndb-target: use the staging db\n", "birth", NOW - 10 * WEEK)
    _commit(repo, "# Rules\ndb-target: use the staging db\n", "death", NOW - 6 * WEEK)
    _commit(repo, "# Rules\ndb-target: use the staging db\nretry-policy: retry 3 times\n", "revival", NOW - 2 * WEEK)
    result = vitals_for_repo(str(repo))
    inp = result["inputs"]
    # the death that got revived is not clean -> r = 0
    assert (inp["a"], inp["e"], inp["d"], inp["c"]) == (1, 1, 1, 0)
    assert result["score"] == 67 and result["band"] == "ROTTING"
    assert result["active_zombies"][0]["term"] == "retry_policy"


def test_laid_to_rest_deactivates(repo):
    # revival later retracted again -> no ACTIVE zombie; event history remains.
    _commit(repo, "# Rules\nretry-policy: retry 3 times\n", "birth", NOW - 10 * WEEK)
    _commit(repo, "# Rules\nplaceholder: keep this line\n", "death", NOW - 8 * WEEK)
    _commit(repo, "# Rules\nplaceholder: keep this line\nretry-policy: retry 3 times\n", "revival", NOW - 6 * WEEK)
    _commit(repo, "# Rules\nplaceholder: keep this line\n", "laid to rest", NOW - 2 * WEEK)
    result = vitals_for_repo(str(repo))
    inp = result["inputs"]
    assert inp["a"] == 0 and inp["e"] == 1
    # deaths: retry-policy (revived -> not clean), retry-policy again (clean) = d 2, c 1
    assert (inp["d"], inp["c"]) == (2, 1) and inp["r"] == 0.5
    # a=0 -> Z=0 regardless of r; e=1 -> score 96
    assert result["score"] == 96 and result["band"] == "SOUND"


def test_old_events_age_out_of_window(repo):
    # death+revival ~2 years ago, still present at HEAD: outside the 365d window
    # the events don't count, and the formula sees a clean record.
    _commit(repo, "# Rules\nretry-policy: retry 3 times\n", "birth", NOW - 120 * WEEK)
    _commit(repo, "# Rules\nplaceholder: keep this line\n", "death", NOW - 110 * WEEK)
    _commit(repo, "# Rules\nplaceholder: keep this line\nretry-policy: retry 3 times\n", "revival", NOW - 105 * WEEK)
    _commit(repo, "# Rules\nplaceholder: keep this line\nretry-policy: retry 3 times\nnew-rule: something new here\n", "recent", NOW - WEEK)
    result = vitals_for_repo(str(repo))
    assert result["inputs"]["a"] == 0 and result["inputs"]["e"] == 0
    assert result["score"] == 100


def test_allow_marker_opts_out(repo):
    _commit(repo, "# Rules\nretry-policy: retry 3 times\n", "birth", NOW - 10 * WEEK)
    _commit(repo, "# Rules\nplaceholder: keep this line\n", "death", NOW - 6 * WEEK)
    _commit(repo, "# Rules\nplaceholder: keep this line\nretry-policy: retry 3 times  <!-- sagrada:allow -->\n",
            "intentional reversal", NOW - 2 * WEEK)
    result = vitals_for_repo(str(repo))
    assert result["inputs"]["e"] == 0
    # the death stands and is clean (never revived as a zombie): d=1, c=1
    assert result["inputs"]["d"] == 1 and result["inputs"]["c"] == 1
    assert result["score"] == 100


def test_collect_record_snapshot_pins_head(repo):
    _commit(repo, "# Rules\ndb-target: use the prod db\n", "one", NOW - WEEK)
    rec = collect_record(str(repo))
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    assert rec.snapshot_commit == head
    assert ("AGENTS.md", "db_target") in rec.final_presence


# ---- SAGRADA-VITALS-METHOD v0.2 accounting (detector review W29) ----

def _mk_repo_v2(tmp_path, script):
    """script: list of CLAUDE.md contents, committed in order."""
    import subprocess
    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    import os
    env = {**os.environ, **env}
    for i, content in enumerate(script):
        (repo / "CLAUDE.md").write_text(content)
        subprocess.run(["git", "add", "."], cwd=repo, env=env, check=True)
        subprocess.run(["git", "commit", "-q", "-m", f"c{i}",
                        "--date", f"2026-01-{i+1:02d}T12:00:00"],
                       cwd=repo, env={**env,
                                      "GIT_COMMITTER_DATE": f"2026-01-{i+1:02d}T12:00:00"},
                       check=True)
    return repo


def test_v02_active_dedup_oscillation(tmp_path):
    """A term that oscillates twice is ONE active zombie, not two (ghostty case)."""
    rule = "build: zig build lib\n"
    other = "keep: yes\n"
    repo = _mk_repo_v2(tmp_path, [
        other + rule, other, other + rule,   # retract + revive #1
        other, other + rule,                 # retract + revive #2 (still present)
    ])
    result = vitals_for_repo(str(repo))
    assert result["inputs"]["a"] == 1
    assert len(result["active_zombies"]) == 1


def test_v02_churn_collapse(tmp_path):
    """>=3 terms swapping in one commit pair = one churn event (kilocode case)."""
    block = ("build: run the full build pipeline\n"
             "test: run the integration suite\n"
             "deploy: staging environment only\n"
             "review: two approvals required\n")
    repo = _mk_repo_v2(tmp_path, [
        block,                            # born
        "keep: this line stays here\n",   # mass retraction (one commit)
        block,                            # mass re-add (one commit) — file swap
    ])
    result = vitals_for_repo(str(repo))
    inp = result["inputs"]
    assert inp["a"] == 1, f"churn must collapse to one active, got {inp['a']}"
    assert inp["e"] == 1, f"churn must collapse to one event, got {inp['e']}"
    churn = [z for z in result["active_zombies"] if z.get("churn")]
    assert churn and churn[0]["members"] >= 3


def test_v02_head_window_anchor(tmp_path):
    """Window ends at repo HEAD, not the newest rule-file commit (F7)."""
    import subprocess, os
    repo = _mk_repo_v2(tmp_path, ["rule: x\n"])
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    (repo / "code.py").write_text("pass\n")
    subprocess.run(["git", "add", "."], cwd=repo, env=env, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "later non-rule commit",
                    "--date", "2026-06-01T12:00:00"],
                   cwd=repo, env={**env, "GIT_COMMITTER_DATE": "2026-06-01T12:00:00"},
                   check=True)
    rec = collect_record(str(repo))
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo,
                          capture_output=True, text=True).stdout.strip()
    assert rec.snapshot_commit == head
