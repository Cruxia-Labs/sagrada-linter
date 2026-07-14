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
