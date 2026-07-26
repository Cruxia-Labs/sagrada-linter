"""End-to-end wedge tests: read (staged, html, strict) + restore round-trip."""
import json
import os
import subprocess

from sagrada_linter.cli import main

RULE = "- deploy-gate — Always run migrations manually before deploy"


def _git(repo, *argv):
    subprocess.run(["git", "-C", str(repo), *argv], check=True,
                   capture_output=True,
                   env={**os.environ,
                        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
                        "GIT_AUTHOR_DATE": "2026-01-05T00:00:00Z",
                        "GIT_COMMITTER_DATE": "2026-01-05T00:00:00Z"})


def make_zombie_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--quiet")
    f = repo / "CLAUDE.md"
    f.write_text(f"# Rules\n{RULE}\n- other — keep tests green\n")
    _git(repo, "add", "."); _git(repo, "commit", "-qm", "born")
    f.write_text("# Rules\n- other — keep tests green\n")
    _git(repo, "add", "."); _git(repo, "commit", "-qm", "killed: staging incident")
    f.write_text(f"# Rules\n{RULE}\n- other — keep tests green\n")
    _git(repo, "add", "."); _git(repo, "commit", "-qm", "merge old branch")
    return repo


def test_read_finds_the_walking_rule(tmp_path, capsys):
    repo = make_zombie_repo(tmp_path)
    rc = main(["read", str(repo), "--no-pace"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "WALKING" in out and "deploy_gate" in out
    assert "killed" in out and "revived" in out
    assert "active again" in out
    # fence: presence, never causation
    assert "obeyed" not in out.lower()


def test_read_strict_exits_nonzero_on_walking(tmp_path):
    repo = make_zombie_repo(tmp_path)
    assert main(["read", str(repo), "--no-pace", "--strict"]) == 1


def test_read_clean_repo_is_a_result_not_a_shrug(tmp_path, capsys):
    repo = tmp_path / "clean"
    repo.mkdir()
    _git(repo, "init", "--quiet")
    (repo / "CLAUDE.md").write_text("# Rules\n- only — one rule, never removed\n")
    _git(repo, "add", "."); _git(repo, "commit", "-qm", "born")
    rc = main(["read", str(repo), "--no-pace", "--strict"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "NO REVIVED RULES FOUND" in out
    assert "result, not a shrug" in out


def test_epitaphs_html_is_script_free_and_self_contained(tmp_path, capsys, monkeypatch):
    repo = make_zombie_repo(tmp_path)
    out_file = tmp_path / "epitaphs.html"
    rc = main(["read", str(repo), "--no-pace", "--html", str(out_file)])
    assert rc == 0 and out_file.exists()
    doc = out_file.read_text()
    assert "<script" not in doc.lower()
    assert "http://" not in doc and "https://" not in doc  # no fetches, no links out
    assert "deploy_gate" in doc and "WALKING" in doc
    assert "#1C1A16" in doc  # the Vigil paper — born dark, an artifact not a mode


def test_seance_exonerates_in_read(tmp_path, capsys):
    repo = make_zombie_repo(tmp_path)
    sessions = tmp_path / "projects" / "p1"
    sessions.mkdir(parents=True)
    (sessions / "s.jsonl").write_text(json.dumps({
        "timestamp": "2026-01-05T00:00:00Z",
        "message": {"role": "user", "content": [{"type": "text",
            "text": f"please put this back: {RULE[2:]}"}]},
    }) + "\n")
    rc = main(["read", str(repo), "--no-pace", "--strict",
               "--seance", str(tmp_path / "projects")])
    out = capsys.readouterr().out
    assert "RESTORED WITH INTENT" in out
    assert "put this back" in out
    assert rc == 0  # exonerated -> strict passes


def test_restore_round_trip_silences_the_scanner(tmp_path, capsys):
    repo = make_zombie_repo(tmp_path)
    rc = main(["restore", "CLAUDE.md", "2", "--reason",
               "needed for the Q3 migration", "--repo", str(repo)])
    assert rc == 0
    text = (repo / "CLAUDE.md").read_text()
    assert "sagrada:allow" in text and "Q3 migration" in text
    ledger = json.loads((repo / ".sagrada" / "restorations.jsonl").read_text())
    assert ledger["line"] == 2 and "Q3" in ledger["reason"]
    _git(repo, "add", "."); _git(repo, "commit", "-qm", "declared restoration")
    # the current line carries the marker: strict acquits, and the reading
    # shows the decision ON THE BOOKS — history preserved, verdict current
    # (an empty graveyard would rewrite history; this is the better truth)
    assert main(["read", str(repo), "--no-pace", "--strict"]) == 0
    out = capsys.readouterr().out
    assert "RESTORED WITH INTENT" in out
    assert "Q3 migration" in out          # the reason travels with the verdict
    assert "0 walking" not in out or "restored" in out.lower()


def test_restore_is_idempotent(tmp_path, capsys):
    repo = make_zombie_repo(tmp_path)
    assert main(["restore", "CLAUDE.md", "2", "--reason", "x", "--repo", str(repo)]) == 0
    assert main(["restore", "CLAUDE.md", "2", "--reason", "x", "--repo", str(repo)]) == 0
    assert (repo / "CLAUDE.md").read_text().count("sagrada:allow") == 1


def test_restore_rejects_bad_line(tmp_path):
    repo = make_zombie_repo(tmp_path)
    assert main(["restore", "CLAUDE.md", "999", "--reason", "x",
                 "--repo", str(repo)]) == 2


def test_read_rejects_nonexistent_path(tmp_path):
    assert main(["read", str(tmp_path / "nope"), "--no-pace"]) == 2


def test_restore_refuses_path_traversal(tmp_path):
    repo = make_zombie_repo(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text("- x — y\n")
    assert main(["restore", "../outside.md", "1", "--reason", "x",
                 "--repo", str(repo)]) == 2
    assert "sagrada:allow" not in outside.read_text()


def test_restore_sanitizes_comment_breakout(tmp_path):
    repo = make_zombie_repo(tmp_path)
    assert main(["restore", "CLAUDE.md", "2", "--reason",
                 "evil --> <script>x</script>", "--repo", str(repo)]) == 0
    line = (repo / "CLAUDE.md").read_text().splitlines()[1]
    # the marker comment must not be broken out of in the FILE...
    assert line.count("-->") == 1 and "<script>" not in line.split("<!--")[1].replace("›script›", "")
    # ...while the ledger keeps the reason verbatim
    ledger = json.loads((repo / ".sagrada" / "restorations.jsonl").read_text())
    assert ledger["reason"] == "evil --> <script>x</script>"


def test_clean_repo_html_baseline_is_written(tmp_path):
    repo = tmp_path / "clean"
    repo.mkdir()
    _git(repo, "init", "--quiet")
    (repo / "CLAUDE.md").write_text("# Rules\n- only — one rule\n")
    _git(repo, "add", "."); _git(repo, "commit", "-qm", "born")
    out_file = tmp_path / "baseline.html"
    assert main(["read", str(repo), "--no-pace", "--html", str(out_file)]) == 0
    doc = out_file.read_text()
    assert out_file.exists() and "0 WALKING" in doc and "<script" not in doc.lower()


def test_declared_restorations_isolated(tmp_path):
    from sagrada_linter.communion import declared_restorations
    from sagrada_linter.scanner import scan_history_for_zombies
    repo = make_zombie_repo(tmp_path)
    events = scan_history_for_zombies(str(repo), "CLAUDE.md")
    assert events and not declared_restorations(str(repo), {"CLAUDE.md": events})
    main(["restore", "CLAUDE.md", "2", "--reason", "why", "--repo", str(repo)])
    got = declared_restorations(str(repo), {"CLAUDE.md": events})
    assert len(got) == 1
    (ev,) = got.values()
    assert ev.verdict == "RESTORATION" and ev.tier == "declared" and "why" in ev.quote


def test_unknown_retraction_time_never_fully_acquits(tmp_path):
    import json as _json
    from sagrada_linter.seance import exonerate
    from sagrada_linter.scanner import ZombieEvent
    z = ZombieEvent(file="CLAUDE.md", term="deploy_gate", retracted_at="aaa",
                    retracted_def=RULE[2:], re_added_at="bbb", re_added_line=2,
                    re_added_def=RULE[2:], changed_meaning=False,
                    retracted_ts=0, re_added_ts=0)
    proj = tmp_path / "p"; proj.mkdir(parents=True)
    (proj / "s.jsonl").write_text(_json.dumps({
        "timestamp": "2026-01-01T00:00:00Z",
        "message": {"role": "user", "content": [{"type": "text",
            "text": f"put this back: {RULE[2:]}"}]}}) + "\n")
    hit = exonerate(z, str(tmp_path))
    assert hit is not None and hit.verdict == "RESTORATION_CANDIDATE"


def test_assistant_text_is_candidate_not_acquittal(tmp_path):
    import json as _json
    from sagrada_linter.seance import exonerate
    from sagrada_linter.scanner import ZombieEvent
    z = ZombieEvent(file="CLAUDE.md", term="deploy_gate", retracted_at="aaa",
                    retracted_def=RULE[2:], re_added_at="bbb", re_added_line=2,
                    re_added_def=RULE[2:], changed_meaning=False,
                    retracted_ts=1750000000, re_added_ts=1753456000)
    proj = tmp_path / "p"; proj.mkdir(parents=True)
    (proj / "s.jsonl").write_text(_json.dumps({
        "timestamp": "2025-07-01T00:00:00Z",   # inside the kill->revive window
        "message": {"role": "assistant", "content": [{"type": "text",
            "text": f"I re-added it: {RULE[2:]}"}]}}) + "\n")
    hit = exonerate(z, str(tmp_path))
    assert hit is not None and hit.verdict == "RESTORATION_CANDIDATE"
    assert hit.role == "assistant"
