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
