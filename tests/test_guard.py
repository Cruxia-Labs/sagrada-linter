"""The Gate: lock build, undeclared-resurrection failure with kill history,
sanctioned paths (marker + ledger), shadow mode, workflow install."""
import json

from sagrada_linter.cli import main
from sagrada_linter.scanner import dead_rules
from tests.test_read_restore import RULE, _git, make_zombie_repo


def make_grave_repo(tmp_path):
    """A repo where the rule died and STAYED dead (a grave, not a zombie)."""
    repo = tmp_path / "grave"
    repo.mkdir()
    _git(repo, "init", "--quiet")
    f = repo / "CLAUDE.md"
    f.write_text(f"# Rules\n{RULE}\n- other — keep tests green\n")
    _git(repo, "add", "."); _git(repo, "commit", "-qm", "born")
    f.write_text("# Rules\n- other — keep tests green\n")
    _git(repo, "add", "."); _git(repo, "commit", "-qm", "killed: incident")
    return repo


def test_dead_rules_lists_the_grave_not_the_zombie(tmp_path):
    grave = make_grave_repo(tmp_path)
    dead = dead_rules(str(grave), "CLAUDE.md")
    assert [d["term"] for d in dead] == ["deploy_gate"]
    assert dead[0]["killed_at"] and dead[0]["killed_ts"] > 0
    # a revived rule is a zombie (scanner's domain), not a grave
    zrepo = make_zombie_repo(tmp_path)
    assert dead_rules(str(zrepo), "CLAUDE.md") == []


def test_guard_installs_lock_and_workflow(tmp_path, capsys):
    repo = make_grave_repo(tmp_path)
    assert main(["guard", "--repo", str(repo), "--workflow"]) == 0
    lock = json.loads((repo / ".crux" / "lock.json").read_text())
    assert lock["schema"] == "crux-lock/v0"
    assert [g["term"] for g in lock["graves"]["CLAUDE.md"]] == ["deploy_gate"]
    wf = (repo / ".github" / "workflows" / "sagrada-guard.yml").read_text()
    assert "--shadow" in wf and "fetch-depth: 0" in wf
    out = capsys.readouterr().out
    assert "1 grave(s)" in out


def test_undeclared_resurrection_fails_with_kill_history(tmp_path, capsys):
    repo = make_grave_repo(tmp_path)
    main(["guard", "--repo", str(repo)])
    f = repo / "CLAUDE.md"
    f.write_text(f"# Rules\n{RULE}\n- other — keep tests green\n")  # it returns
    rc = main(["guard", "--repo", str(repo), "--check"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "GUARD FAILED" in out and "deploy_gate" in out
    assert "killed at" in out and "the record says" in out
    assert "restore CLAUDE.md 2 --reason" in out  # the sanctioned path, offered


def test_shadow_mode_reports_but_passes(tmp_path, capsys):
    repo = make_grave_repo(tmp_path)
    main(["guard", "--repo", str(repo)])
    (repo / "CLAUDE.md").write_text(f"# Rules\n{RULE}\n")
    rc = main(["guard", "--repo", str(repo), "--check", "--shadow"])
    out = capsys.readouterr().out
    assert rc == 0 and "would fail enforcement" in out


def test_declared_restoration_is_sanctioned(tmp_path, capsys):
    repo = make_grave_repo(tmp_path)
    main(["guard", "--repo", str(repo)])
    (repo / "CLAUDE.md").write_text(f"# Rules\n{RULE}\n- other — keep\n")
    assert main(["restore", "CLAUDE.md", "2", "--reason", "Q3 needs it",
                 "--repo", str(repo)]) == 0
    rc = main(["guard", "--repo", str(repo), "--check"])
    out = capsys.readouterr().out
    assert rc == 0 and "sanctioned" in out


def test_new_rules_never_trip_the_guard(tmp_path, capsys):
    repo = make_grave_repo(tmp_path)
    main(["guard", "--repo", str(repo)])
    (repo / "CLAUDE.md").write_text(
        "# Rules\n- other — keep tests green\n- brand_new — a fresh law\n")
    assert main(["guard", "--repo", str(repo), "--check"]) == 0


def test_check_without_lock_is_loud(tmp_path, capsys):
    repo = make_grave_repo(tmp_path)
    assert main(["guard", "--repo", str(repo), "--check"]) == 2
    assert "install the gate first" in capsys.readouterr().err


def test_rename_creates_a_grave(tmp_path):
    repo = tmp_path / "ren"
    repo.mkdir()
    _git(repo, "init", "--quiet")
    f = repo / "CLAUDE.md"
    f.write_text("# R\n- old-gate — run migrations manually\n")
    _git(repo, "add", "."); _git(repo, "commit", "-qm", "born")
    f.write_text("# R\n- new-gate — run migrations manually\n")  # rename
    _git(repo, "add", "."); _git(repo, "commit", "-qm", "renamed")
    dead = dead_rules(str(repo), "CLAUDE.md")
    assert "old_gate" in [d["term"] for d in dead]


def test_marked_duplicate_does_not_shield_unmarked_copy(tmp_path, capsys):
    repo = make_grave_repo(tmp_path)
    main(["guard", "--repo", str(repo)])
    (repo / "CLAUDE.md").write_text(
        f"# Rules\n{RULE} <!-- sagrada:allow — restored 2026-07-26: ok -->\n"
        f"{RULE}\n")  # second copy, unmarked
    rc = main(["guard", "--repo", str(repo), "--check"])
    out = capsys.readouterr().out
    assert rc == 1 and ":3" in out  # the unmarked line, correctly numbered


def test_ledger_path_normalization_sanctions(tmp_path, capsys):
    repo = make_grave_repo(tmp_path)
    main(["guard", "--repo", str(repo)])
    (repo / "CLAUDE.md").write_text(f"# Rules\n{RULE}\n- other — keep\n")
    # restore typed with a './' path — must still sanction the lock's
    # relative key (a mismatch here falsely blocks: category-killer)
    assert main(["restore", "./CLAUDE.md", "2", "--reason", "q3",
                 "--repo", str(repo)]) == 0
    assert main(["guard", "--repo", str(repo), "--check"]) == 0


def test_crafted_lock_traversal_refused(tmp_path, capsys):
    import pytest
    repo = make_grave_repo(tmp_path)
    (repo / ".crux").mkdir(exist_ok=True)
    (repo / ".crux" / "lock.json").write_text(json.dumps({
        "schema": "crux-lock/v0",
        "graves": {"../outside.md": [{"term": "x", "killed_at": "a",
                                      "killed_ts": 1, "definition": "d"}]}}))
    with pytest.raises(SystemExit):
        main(["guard", "--repo", str(repo), "--check"])


def test_check_json_is_machine_clean(tmp_path, capsys):
    repo = make_grave_repo(tmp_path)
    main(["guard", "--repo", str(repo)])
    (repo / "CLAUDE.md").write_text(f"# Rules\n{RULE}\n")
    capsys.readouterr()
    rc = main(["guard", "--repo", str(repo), "--check", "--json", "--shadow"])
    out = capsys.readouterr().out
    parsed = json.loads(out)  # stdout is pure JSON
    assert rc == 0 and parsed["violations"][0]["term"] == "deploy_gate"
