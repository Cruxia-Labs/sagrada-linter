"""Release-gate fixes (2026-07-29): shallow clones never read clean; the
zero line claims nothing it can't see; the reading ends shareable."""
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sagrada_linter.scanner import format_events, is_shallow_repo  # noqa: E402

ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
       "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def _git(repo, *argv):
    subprocess.run(["git", "-C", str(repo), *argv], check=True,
                   capture_output=True, env=ENV)


def _mk_repo(tmp_path, n_commits=3):
    r = tmp_path / "src"
    r.mkdir()
    _git(r, "init", "-q")
    for i in range(n_commits):
        (r / "CLAUDE.md").write_text(f"- rule {i} — always do the thing v{i}\n")
        _git(r, "add", "-A")
        _git(r, "commit", "-q", "-m", f"c{i}")
    return r


def test_shallow_clone_detected(tmp_path):
    src = _mk_repo(tmp_path)
    shallow = tmp_path / "shallow"
    subprocess.run(["git", "clone", "-q", "--depth", "1",
                    f"file://{src}", str(shallow)], check=True, env=ENV)
    assert is_shallow_repo(str(shallow)) is True
    assert is_shallow_repo(str(src)) is False


def test_shallow_scan_refuses_clean_verdict(tmp_path):
    src = _mk_repo(tmp_path)
    shallow = tmp_path / "shallow"
    subprocess.run(["git", "clone", "-q", "--depth", "1",
                    f"file://{src}", str(shallow)], check=True, env=ENV)
    out = subprocess.run(
        [sys.executable, "-m", "sagrada_linter.cli", "scan-history", "."],
        cwd=str(shallow), capture_output=True, text=True, env=ENV)
    assert out.returncode == 2
    assert "shallow" in (out.stderr + out.stdout).lower()
    assert "resting" not in out.stdout  # no clean line ships on shallow


def test_zero_line_claims_nothing(tmp_path):
    line = format_events({}, n_scanned=2)
    assert "coherent" not in line
    assert "✓" not in line  # no medal glyph
    assert "still resting" in line


def test_reading_ends_on_verify_then_paste_block(tmp_path, capsys):
    from sagrada_linter.communion import run_reading
    run_reading(repo_label="specimen", scanned=["CLAUDE.md"], n_commits=4,
                by_file={}, evidence={}, order="exoneration-first",
                pace=0.0, color=False, seance_used=True)
    out = capsys.readouterr().out
    # zero-findings path keeps its own copy; non-zero ordering asserted below
    assert "NO REVIVED RULES FOUND" in out


def test_nonzero_reading_order_and_paste_block(tmp_path, capsys):
    from sagrada_linter.communion import run_reading
    from sagrada_linter.scanner import ZombieEvent
    ev = ZombieEvent(file="CLAUDE.md", term="deploy_gate",
                     retracted_at="a" * 8, retracted_def="old",
                     re_added_at="b" * 8, re_added_line=2,
                     re_added_def="old", changed_meaning=False)
    run_reading(repo_label="specimen", scanned=["CLAUDE.md"], n_commits=4,
                by_file={"CLAUDE.md": [ev]}, evidence={},
                order="exoneration-first", pace=0.0, color=False,
                seance_used=True)
    out = capsys.readouterr().out
    assert "specimen: 1 walking" in out            # self-quoting tally
    assert out.index("keep the graves kept") < out.index("do not trust")
    assert "copy this" in out                      # the paste block exists
    assert out.rstrip().endswith("-" * 49)         # and closes the reading
