"""Standalone conformance test for the public sagrada-linter package.

Engine-free: imports only `sagrada_linter` + stdlib. This is what the repo's CI runs and
what a stranger runs after `pip install -e . && pytest test_conformance.py` to confirm the
tool works and its receipts verify offline in both languages.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

import sagrada_linter
from sagrada_linter.scanner import scan_history_for_zombies
from sagrada_linter.linter_receipt import build_check_receipt, write_receipt

PKG = os.path.dirname(sagrada_linter.__file__)
NODE = shutil.which("node")


def _git(r, *a):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    subprocess.run(["git", "-C", r, *a], check=True, capture_output=True, text=True, env=env)


def _fixture():
    r = tempfile.mkdtemp()
    _git(r, "init", "-q")
    for text, msg in [
        ("- db_engine: use PostgreSQL with a pool\n- fmt: strict JSON\n", "v1"),
        ("- fmt: strict JSON\n", "retract"),
        ("- db_engine: use PostgreSQL with a pool\n- fmt: strict JSON\n", "zombie"),
    ]:
        open(os.path.join(r, "CLAUDE.md"), "w").write(text)
        _git(r, "add", "CLAUDE.md")
        _git(r, "commit", "-q", "-m", msg, "--allow-empty")
    return r


def _receipt_for_fixture():
    r = _fixture()
    ev = scan_history_for_zombies(r, "CLAUDE.md")
    z = [(e.term, e.re_added_def, e.retracted_at, e.re_added_at) for e in ev]
    d = tempfile.mkdtemp()
    return ev, write_receipt(build_check_receipt("CLAUDE.md", z), d)


def test_scanner_catches_cross_commit_zombie():
    r = _fixture()
    ev = scan_history_for_zombies(r, "CLAUDE.md")
    assert len(ev) == 1 and ev[0].term == "db_engine"


def test_same_commit_reword_is_not_a_zombie():
    # A rule reworded within ONE commit is a rewrite, not a retract->re-add. Locked here
    # because a naive matcher false-flags it (a real precision invariant for this release).
    r = tempfile.mkdtemp()
    _git(r, "init", "-q")
    for text, msg in [
        ("- alpha: a stable padding rule that stays put right here\n"
         "- tests: see the tests folder readme file for the short guide\n", "v1"),
        ("- alpha: a stable padding rule that stays put right here\n"
         "- tests: completely different snapshot guidance now entirely reworded\n", "same-commit reword"),
    ]:
        open(os.path.join(r, "CLAUDE.md"), "w").write(text)
        _git(r, "add", "CLAUDE.md")
        _git(r, "commit", "-q", "-m", msg, "--allow-empty")
    assert scan_history_for_zombies(r, "CLAUDE.md") == []


def test_worktree_catches_uncommitted_re_add():
    # The pre-commit gate: a re-add staged for this commit must be caught with --worktree.
    r = tempfile.mkdtemp()
    _git(r, "init", "-q")
    for text, msg in [
        ("- db_engine: use PostgreSQL with a pool\n- fmt: strict JSON\n", "v1"),
        ("- fmt: strict JSON\n", "retract"),
    ]:
        open(os.path.join(r, "CLAUDE.md"), "w").write(text)
        _git(r, "add", "CLAUDE.md")
        _git(r, "commit", "-q", "-m", msg, "--allow-empty")
    open(os.path.join(r, "CLAUDE.md"), "w").write(
        "- db_engine: use PostgreSQL with a pool\n- fmt: strict JSON\n")  # uncommitted re-add
    assert scan_history_for_zombies(r, "CLAUDE.md") == []
    wt = scan_history_for_zombies(r, "CLAUDE.md", include_worktree=True)
    assert len(wt) == 1 and wt[0].re_added_at == "WORKTREE"


def test_sagrada_allow_suppresses_intentional_reversal():
    r = tempfile.mkdtemp()
    _git(r, "init", "-q")
    for text, msg in [
        ("- db_engine: use PostgreSQL with a pool\n", "v1"),
        ("- other: a padding rule to keep the file non-empty\n", "retract"),
        ("- db_engine: use PostgreSQL with a pool  <!-- sagrada:allow -->\n", "intentional re-add"),
    ]:
        open(os.path.join(r, "CLAUDE.md"), "w").write(text)
        _git(r, "add", "CLAUDE.md")
        _git(r, "commit", "-q", "-m", msg, "--allow-empty")
    assert scan_history_for_zombies(r, "CLAUDE.md") == []


def test_tilde_equals_is_compatible_release_not_exact():
    # PEP 440 ~=2.0 means >=2.0, <3.0 — NOT exact equality. Locks the verifier predicate.
    from sagrada_linter.conflict import _satisfies
    assert _satisfies("2.5", "~=2.0") is True       # within [2.0, 3.0)
    assert _satisfies("2.0", "~=2.0") is True        # the floor is allowed
    assert _satisfies("3.0", "~=2.0") is False       # excluded upper bound
    assert _satisfies("1.9", "~=2.0") is False       # below the floor


def test_receipt_emits_and_verifies_in_both_languages():
    ev, p = _receipt_for_fixture()
    assert json.load(open(p))["decision"]["verdict"] == "HALT"
    assert subprocess.run([sys.executable, os.path.join(PKG, "er1_verify.py"), p]).returncode == 0
    if NODE:
        assert subprocess.run([NODE, os.path.join(PKG, "er1_verify.mjs"), p]).returncode == 0


def test_golden_vectors_verify_in_both_languages():
    gv = os.path.join(PKG, "golden_vectors.json")
    assert subprocess.run([sys.executable, os.path.join(PKG, "er1_verify.py"), gv]).returncode == 0
    if NODE:
        assert subprocess.run([NODE, os.path.join(PKG, "er1_verify.mjs"), gv]).returncode == 0


def test_tampered_receipt_fails():
    _ev, p = _receipt_for_fixture()
    obj = json.load(open(p))
    obj["decision"]["proposed"] = "TAMPERED"
    json.dump(obj, open(p, "w"), indent=2, sort_keys=True)
    assert subprocess.run([sys.executable, os.path.join(PKG, "er1_verify.py"), p]).returncode != 0


def test_check_action_emits_verifiable_receipt(tmp_path):
    """check-action: a proposed action that violates an active constraint -> HALT + a receipt
    that recomputes under the reference verifier."""
    import json, subprocess, sys, os
    from sagrada_linter import check_action
    beliefs = [{"entity": "env:DEPLOY_TARGET", "rule": "equals", "value": "staging"},
               {"entity": "lib:boto3", "rule": "excludes"}]
    # value flip -> SUPERSEDED_VALUE
    r = check_action(beliefs, {"tool": "shell", "asserts": {"env:DEPLOY_TARGET": "production"},
                               "resource": "deploy.sh"})
    assert r["decision"]["verdict"] == "HALT"
    assert r["decision"]["reason_code"] == "SUPERSEDED_VALUE"
    # banned entity
    r2 = check_action(beliefs, {"tool": "shell", "asserts": {"lib:boto3": "import"}, "resource": "x.py"})
    assert r2["decision"]["verdict"] == "HALT" and r2["decision"]["reason_code"] == "BANNED_ENTITY"
    # coherent -> ALLOW
    r3 = check_action(beliefs, {"tool": "shell", "asserts": {"env:DEPLOY_TARGET": "staging"},
                                "resource": "deploy.sh"})
    assert r3["decision"]["verdict"] == "ALLOW"
    # the HALT receipt recomputes under the bundled Python reference verifier
    d = tmp_path / "rcpt"
    check_action(beliefs, {"tool": "shell", "asserts": {"env:DEPLOY_TARGET": "production"},
                           "resource": "deploy.sh"}, receipts_dir=str(d))
    rcpt = next(d.glob("*.er1.json"))
    verifier = os.path.join(os.path.dirname(__file__), "sagrada_linter", "er1_verify.py")
    out = subprocess.run([sys.executable, verifier, str(rcpt)], capture_output=True, text=True)
    assert "VERIFIED" in out.stdout and "FAIL" not in out.stdout.upper()
