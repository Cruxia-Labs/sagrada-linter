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
