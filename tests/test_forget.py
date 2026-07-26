"""Certified Forgetting: the four steps, the full lifecycle, the fences."""
import json
import subprocess

from sagrada_linter.cli import main
from tests.test_read_restore import RULE, _git, make_zombie_repo


def make_live_repo(tmp_path):
    """A repo whose rule is alive and about to be forgotten — with a second
    rule that references the first (residue bait)."""
    repo = tmp_path / "live"
    repo.mkdir()
    _git(repo, "init", "--quiet")
    (repo / "CLAUDE.md").write_text(
        f"# Rules\n{RULE}\n- other — keep tests green\n")
    (repo / "AGENTS.md").write_text(
        "# Agents\n- ci_note — see deploy-gate before shipping anything\n")
    _git(repo, "add", "."); _git(repo, "commit", "-qm", "born")
    return repo


def test_forget_four_steps(tmp_path, capsys):
    repo = make_live_repo(tmp_path)
    rc = main(["forget", "CLAUDE.md", "2", "--reason",
               "policy migrated to CI", "--repo", str(repo)])
    out = capsys.readouterr().out
    assert rc == 0
    # 1. the edit
    assert "deploy-gate" not in (repo / "CLAUDE.md").read_text()
    # 2. the residue (the AGENTS.md reference, surface form)
    assert "residue — 1 current line(s)" in out and "AGENTS.md:2" in out
    # 3. the tombstone
    row = json.loads((repo / ".sagrada" / "tombstones.jsonl").read_text())
    assert row["term"] == "deploy_gate" and row["reason"] == "policy migrated to CI"
    assert row["residue"][0]["file"] == "AGENTS.md"
    # 4. the receipt — written, ALLOW, offline-verifiable via the bundled rail
    assert "ALLOW under the new doctrine" in out
    receipts = list((repo / ".sagrada" / "receipts").glob("*.er1.json"))
    assert len(receipts) == 1
    assert main(["verify", str(receipts[0])]) == 0


def test_forget_then_guard_holds_the_grave(tmp_path, capsys):
    repo = make_live_repo(tmp_path)
    main(["forget", "CLAUDE.md", "2", "--reason", "x", "--repo", str(repo)])
    _git(repo, "add", "."); _git(repo, "commit", "-qm", "forgotten with proof")
    main(["guard", "--repo", str(repo)])
    capsys.readouterr()
    # the forgotten rule returns, undeclared
    text = (repo / "CLAUDE.md").read_text()
    (repo / "CLAUDE.md").write_text(text.replace("# Rules\n", f"# Rules\n{RULE}\n"))
    rc = main(["guard", "--repo", str(repo), "--check"])
    out = capsys.readouterr().out
    assert rc == 1 and "deploy_gate" in out and "killed at" in out


def test_forget_refuses_non_rule_line(tmp_path, capsys):
    repo = make_live_repo(tmp_path)
    rc = main(["forget", "CLAUDE.md", "1", "--reason", "x", "--repo", str(repo)])
    assert rc == 2
    assert "not a structured rule line" in capsys.readouterr().err
    assert "# Rules" in (repo / "CLAUDE.md").read_text()  # untouched


def test_forget_refuses_traversal(tmp_path, capsys):
    repo = make_live_repo(tmp_path)
    outside = tmp_path / "outside.md"
    outside.write_text(f"{RULE}\n")
    rc = main(["forget", "../outside.md", "1", "--reason", "x",
               "--repo", str(repo)])
    assert rc == 2 and RULE in outside.read_text()


def test_no_residue_is_reported_honestly(tmp_path, capsys):
    repo = tmp_path / "solo"
    repo.mkdir()
    _git(repo, "init", "--quiet")
    (repo / "CLAUDE.md").write_text(f"# Rules\n{RULE}\n")
    _git(repo, "add", "."); _git(repo, "commit", "-qm", "born")
    rc = main(["forget", "CLAUDE.md", "2", "--reason", "x", "--repo", str(repo)])
    out = capsys.readouterr().out
    assert rc == 0 and "residue: none found at depth-1" in out
