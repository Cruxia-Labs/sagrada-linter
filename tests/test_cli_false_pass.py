"""Regression tests for the false-PASS flagship fix (UX audit 2026-07-14).

Three surfaces used to print a confident PASS where the truth was NOT-MEASURED:
  1. `scan-history` in a non-git dir exited 0 with a misdiagnosis,
  2. `scan-history` in a commitless repo looked like a clean pass,
  3. `vitals` scored an empty/non-git dir 100/SOUND.

The brand rule under test: the headline never outruns the receipt.
Also covers the receipt-naming and catch-line star treatment (days undead).
"""
import json
import os
import re
import subprocess

import pytest

from sagrada_linter.cli import main


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
    (repo / "CLAUDE.md").write_text(content)
    _git(repo, "add", "-A", env_ts=ts)
    _git(repo, "commit", "-m", msg, env_ts=ts)


@pytest.fixture()
def non_git_dir(tmp_path):
    d = tmp_path / "plain"
    d.mkdir()
    return d


@pytest.fixture()
def empty_repo(tmp_path):
    r = tmp_path / "empty"
    r.mkdir()
    _git(r, "init", "-q", ".")
    return r


@pytest.fixture()
def zombie_repo(tmp_path):
    r = tmp_path / "zrepo"
    r.mkdir()
    _git(r, "init", "-q", ".")
    _commit(r, "- db_engine: use PostgreSQL\n- fmt: strict JSON\n", "birth", 1704067200)
    _commit(r, "- fmt: strict JSON\n", "death", 1706745600)          # 2024-02-01
    _commit(r, "- db_engine: use PostgreSQL\n- fmt: strict JSON\n", "revival", 1710500400)  # 2024-03-15
    return r


# --- case 1: scan-history, non-git dir -------------------------------------

def test_scan_history_non_git_is_an_error_not_a_pass(non_git_dir, capsys):
    rc = main(["scan-history", "--repo", str(non_git_dir)])
    err = capsys.readouterr().err
    assert rc == 2
    assert "not a git repository" in err
    assert "coherent" not in err  # never claims a clean pass


# --- case 2: scan-history, git repo with no commits -------------------------

def test_scan_history_empty_repo_is_warm_not_a_coherence_claim(empty_repo, capsys):
    rc = main(["scan-history", "--repo", str(empty_repo)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "no commits yet — nothing has had a chance to die" in out
    assert "coherent" not in out


# --- case 3: vitals never says 100/SOUND for zero evidence -------------------

@pytest.mark.parametrize("fixture_name", ["non_git_dir", "empty_repo"])
def test_vitals_not_scored_headline(fixture_name, request, capsys):
    where = request.getfixturevalue(fixture_name)
    rc = main(["vitals", "--repo", str(where)])
    out = capsys.readouterr().out
    assert rc == 0
    assert out.startswith("NOT SCORED — no rule files with git history")
    assert "100" not in out
    assert "SOUND" not in out


@pytest.mark.parametrize("fixture_name", ["non_git_dir", "empty_repo"])
def test_vitals_strict_exits_3_when_not_scored(fixture_name, request, capsys):
    where = request.getfixturevalue(fixture_name)
    rc = main(["vitals", "--repo", str(where), "--strict"])
    assert rc == 3


def test_vitals_not_scored_json_is_null_not_100(non_git_dir, capsys):
    rc = main(["vitals", "--repo", str(non_git_dir), "--json"])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["score"] is None
    assert out["band"] == "NOT SCORED"
    assert out["scored"] is False


def test_vitals_scored_repo_still_scores(zombie_repo, capsys):
    rc = main(["vitals", "--repo", str(zombie_repo), "--strict"])
    out = capsys.readouterr().out
    assert rc == 0                       # --strict only bites when NOT SCORED
    assert "belief-integrity:" in out
    assert "NOT SCORED" not in out


# --- catch-line star treatment + receipts discoverability -------------------

def test_catch_line_carries_days_undead_and_dates(zombie_repo, capsys):
    rc = main(["scan-history", "--repo", str(zombie_repo)])
    out = capsys.readouterr().out
    assert rc == 0
    assert re.search(r"✗ CLAUDE\.md:\d+ db_engine — undead \d+ days? "
                     r"\(retracted [0-9a-f]{8} \d{4}-\d{2}-\d{2} → "
                     r"re-added [0-9a-f]{8} \d{4}-\d{2}-\d{2}\)", out)
    assert re.search(r"scanned 1 rule file across \d+ commits", out)


def test_scan_footer_points_at_receipts(zombie_repo, capsys):
    rc = main(["scan-history", "--repo", str(zombie_repo)])
    err = capsys.readouterr().err
    assert rc == 0
    assert "receipts: none written — add --receipt" in err

    rc = main(["scan-history", "--repo", str(zombie_repo), "--receipt"])
    err = capsys.readouterr().err
    assert "receipts: 1 written to" in err
    assert "uvx sagrada-linter verify" in err


def test_receipt_filename_is_speakable(zombie_repo, capsys):
    main(["scan-history", "--repo", str(zombie_repo), "--receipt"])
    capsys.readouterr()
    rdir = zombie_repo / ".sagrada" / "receipts"
    names = sorted(p.name for p in rdir.iterdir())
    assert len(names) == 1
    # <repo>-<file>-<ISO week>-<shortid>.er1.json
    assert re.fullmatch(r"zrepo-CLAUDE-md-\d{4}-W\d{2}-[0-9a-f]{8}\.er1\.json", names[0])
