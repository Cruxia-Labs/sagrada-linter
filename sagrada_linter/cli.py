"""Sagrada Linter CLI — `sagrada-linter scan-history` / `verify`. Stdlib argparse (no
heavy deps)."""
import argparse
import dataclasses
import json
import os
import subprocess
import sys

from .scanner import (
    discover_rule_files,
    find_rule_files_on_disk,
    format_events,
    format_github_comment,
    inject_demo,
    scan_history_for_zombies,
)
from .linter_receipt import build_check_receipt, receipt_filename, write_receipt
from .decision import PreflightGate
from .gitwalk import git_env, walk_file_history


def _git_repo_state(repo_root: str) -> str:
    """``'ok'`` (repo with commits) | ``'empty'`` (a git repo with no commits yet) |
    ``'none'`` (not a git repository).

    Checked FIRST on every history-reading command so a wrong directory can never
    masquerade as a clean or healthy repo (the false-PASS guard)."""
    probe = subprocess.run(["git", "-C", repo_root, "rev-parse", "--git-dir"],
                           capture_output=True, text=True, env=git_env())
    if probe.returncode != 0:
        return "none"
    head = subprocess.run(["git", "-C", repo_root, "rev-parse", "--quiet", "--verify", "HEAD"],
                          capture_output=True, text=True, env=git_env())
    return "ok" if head.returncode == 0 else "empty"


def _commit_count(repo_root: str):
    """Commits reachable from HEAD, or ``None`` when unknown."""
    out = subprocess.run(["git", "-C", repo_root, "rev-list", "--count", "HEAD"],
                         capture_output=True, text=True, env=git_env())
    if out.returncode != 0:
        return None
    try:
        return int(out.stdout.strip())
    except ValueError:
        return None


NOT_A_REPO_MSG = ("not a git repository — scan-history reads history; "
                  "run inside a repo clone.")
EMPTY_REPO_MSG = "no commits yet — nothing has had a chance to die."
NEXT_MOVE_MSG = ("try: sagrada-linter scan-history --inject-demo (plants a zombie in a "
                 "throwaway copy and shows the catch) · score it: sagrada-linter vitals")


def _cmd_scan_history(args) -> int:
    targets = list(args.paths) if args.paths else []
    repo_root = args.repo
    unresolved: list = []
    if args.inject_demo:
        target = targets[0] if targets else None
        if target is None:
            on_disk = find_rule_files_on_disk(repo_root)
            if not on_disk:
                print("No rule file found to demo. Pass one, e.g. --inject-demo CLAUDE.md", file=sys.stderr)
                return 2
            target = on_disk[0]
        events = inject_demo(repo_root, target)
        if not events:
            print(f"could not plant a demo in '{target}': found no structured rule "
                  f"(`key: value` or `- term — definition`) to retract and re-add. Point "
                  f"--inject-demo at a file with structured rules, e.g. CLAUDE.md.", file=sys.stderr)
            return 2
        by_file = {target: events}
        scanned = []
    else:
        if len(targets) == 1 and os.path.isdir(targets[0]):
            repo_root = targets[0]                      # `scan-history .` -> the repo, auto-discover
            targets = []
        # Environment check comes FIRST: a non-git dir is an error (its own message +
        # exit code), never a silent clean pass; a commitless repo is honestly new.
        repo_state = _git_repo_state(repo_root)
        if repo_state == "none":
            print(NOT_A_REPO_MSG, file=sys.stderr)
            return 2
        if repo_state == "empty":
            print(EMPTY_REPO_MSG)
            return 0
        if not targets:
            scanned = discover_rule_files(repo_root)
        else:
            # Explicit target(s): keep only paths we can actually read — one with git history, or
            # (with --worktree) a file present on disk. Anything else is reported and EXCLUDED, so
            # we never print "coherent" or sign a receipt for a file that was never scanned.
            scanned = []
            for f in targets:
                has_history = bool(walk_file_history(repo_root, f))
                on_disk = args.worktree and os.path.isfile(os.path.join(repo_root, f))
                (scanned if (has_history or on_disk) else unresolved).append(f)
            for f in unresolved:
                print(f"error: '{f}' has no git history in {repo_root} "
                      f"(and no worktree copy) — not scanned.", file=sys.stderr)
        by_file = {}
        for f in scanned:
            ev = scan_history_for_zombies(repo_root, f, include_worktree=args.worktree)
            if ev:
                by_file[f] = ev

    if args.github_comment:
        print(format_github_comment(by_file))
    elif args.json:
        print(json.dumps({f: [dataclasses.asdict(e) for e in evs]
                          for f, evs in by_file.items()}, indent=2))
    else:
        n_scanned = None if args.inject_demo else len(scanned)
        print(format_events(by_file, color=sys.stdout.isatty(), n_scanned=n_scanned))
        if not args.inject_demo:
            n_commits = _commit_count(repo_root)
            across = (f" across {n_commits} commit{'s' if n_commits != 1 else ''}"
                      if n_commits is not None else "")
            print(f"scanned {len(scanned)} rule file{'s' if len(scanned) != 1 else ''}{across}")
            if scanned and not any(by_file.values()):
                print(NEXT_MOVE_MSG)

    # Receipts footer — printed on every real scan so the receipt rail is discoverable
    # (stderr: `--json` / `--github-comment` stdout stays machine-clean).
    if args.receipt and scanned:
        rdir = args.receipt_dir or os.path.join(repo_root, ".sagrada", "receipts")
        gate = PreflightGate()                          # ONE gate -> a continuous receipt chain
        written = []
        for f in scanned:
            evs = by_file.get(f, [])
            z = [(e.term, e.re_added_def, e.retracted_at, e.re_added_at) for e in evs]
            rcpt = build_check_receipt(f, z, gate=gate)
            written.append(write_receipt(rcpt, rdir,
                                         filename=receipt_filename(repo_root, f, rcpt)))
        target = written[0] if len(written) == 1 else os.path.join(rdir, "*.er1.json")
        print(f"receipts: {len(written)} written to {rdir}\n"
              f"  verify: uvx sagrada-linter verify {target}", file=sys.stderr)
    elif args.receipt and args.inject_demo:
        print("note: --receipt is a no-op with --inject-demo (the demo plants a zombie in a "
              "throwaway copy — there is no real history to sign). Run scan-history on a real "
              "repo to emit a receipt.", file=sys.stderr)
    elif args.receipt:
        print("note: nothing was scanned, so no receipt was written.", file=sys.stderr)
    elif not args.inject_demo:
        print("receipts: none written — add --receipt for a signed, offline-verifiable finding",
              file=sys.stderr)

    # An explicitly-named target we could not read is an error, not a clean pass: never let a
    # missing/typo'd path exit 0 as if it were checked.
    if unresolved and not scanned:
        return 2
    if unresolved and args.strict:
        return 1

    return 1 if (args.strict and any(by_file.values())) else 0


def _cmd_verify(args) -> int:
    verifier = os.path.join(os.path.dirname(__file__), "er1_verify.py")
    return subprocess.run([sys.executable, verifier] + args.receipts).returncode


def _cmd_check_action(args) -> int:
    from .preflight import check_action
    beliefs = []
    if args.beliefs:
        with open(args.beliefs, encoding="utf-8") as bf:
            beliefs = json.load(bf)
    with open(args.action, encoding="utf-8") as af:
        action = json.load(af)
    rdir = (args.receipt_dir or os.path.join(".", ".sagrada", "receipts")) if args.receipt else None
    receipt = check_action(beliefs, action, receipts_dir=rdir)
    decision = receipt.get("decision", {})
    verdict, rc = decision.get("verdict", "?"), decision.get("reason_code", "")
    if args.json:
        print(json.dumps(receipt, indent=2))
    else:
        print(verdict + (f"  {rc}" if rc else ""))
        if rdir:
            print(f"receipt written to {rdir}\n"
                  f"  verify: uvx sagrada-linter verify {os.path.join(rdir, '*.er1.json')}",
                  file=sys.stderr)
    return 1 if (args.strict and verdict == "HALT") else 0


def _cmd_vitals(args) -> int:
    import json as _json

    from .vitals import (METHOD_SHA256, METHOD_VERSION, badge_json, display_band,
                         vitals_for_repo)

    paths = list(args.paths) or None
    repo_state = _git_repo_state(args.repo)
    result = (vitals_for_repo(args.repo, paths=paths, window_days=args.window_days)
              if repo_state == "ok" else None)
    scored = bool(result and result["files_scanned"])

    if not scored:
        # FALSE-PASS GUARD: an empty dir, a non-git dir, or a repo whose rule files have
        # no git history is UNMEASURED, not healthy. The headline must say so — a score
        # of 100/CLEAR here would hand CI (and skeptics) a perfect grade for zero evidence.
        reason = {
            "none": "not a git repository — vitals reads committed history; "
                    "run inside a repo clone",
            "empty": "no commits yet — nothing has had a chance to die",
        }.get(repo_state, "no rule files with git history found in this repo")
        not_scored = {
            "method": METHOD_VERSION,
            "method_sha256": METHOD_SHA256,
            "scored": False,
            "score": None,
            "band": "NOT SCORED",
            "reason": reason,
            "files_scanned": (result or {}).get("files_scanned", []),
            "window_days": args.window_days,
            "not_measured": "everything — no rule files with git history were available "
                            "to score",
        }
        if args.badge_out:
            with open(args.badge_out, "w", encoding="utf-8") as f:
                _json.dump({"schemaVersion": 1, "label": "belief-integrity",
                            "message": "not scored", "color": "#9f9f9f"}, f, indent=2)
                f.write("\n")
        if args.json:
            print(_json.dumps(not_scored, indent=2, sort_keys=True))
        else:
            print("NOT SCORED — no rule files with git history")
            print(f"  reason: {reason}")
            print(f"  method: {METHOD_VERSION}  ·  window: {args.window_days}d")
        return 3 if args.strict else 0

    result["scored"] = True
    if args.badge_out:
        with open(args.badge_out, "w", encoding="utf-8") as f:
            _json.dump(badge_json(result["score"]), f, indent=2)
            f.write("\n")
    if args.json:
        print(_json.dumps(result, indent=2, sort_keys=True))
        return 0
    inp = result["inputs"]
    print(f"belief-integrity: {result['score']} / 100  ({display_band(result['band'])})")
    print(f"  method: {result['method']}  ·  window: {inp['window_days']}d  ·  "
          f"snapshot: {result['snapshot_commit'][:8]}")
    print(f"  inputs: active zombies={inp['a']}  revivals={inp['e']}  "
          f"deaths={inp['d']}  clean deaths={inp['c']}  reconciliation r={inp['r']:.2f}")
    for z in result["active_zombies"]:
        print(f"  ✗ ACTIVE  {z['file']}  {z['term']}  "
              f"(retracted {z['retracted_at'][:8]}, revived {z['revived_at'][:8]})")
    print(f"  not measured: {result['not_measured']}")
    return 0


_EPILOG = """\
examples:
  sagrada-linter scan-history .              scan this repo's rule files for zombie beliefs
  sagrada-linter scan-history --inject-demo  plant a zombie in a throwaway copy, watch the catch
  sagrada-linter vitals                      0-100 belief-integrity score (frozen method)

exit codes:
  0  clean (or report printed)
  1  findings, under --strict
  2  not a git repository / unreadable target
  3  vitals NOT SCORED (no rule files with git history), under --strict
"""


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="sagrada-linter",
        description="Catch zombie beliefs — dead rules (retracted AI rules) that crept "
                    "back into your repo.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sh = sub.add_parser("scan-history",
                        help="Scan your git history for zombie beliefs (dead rules re-added "
                             "after retraction).")
    sh.add_argument("paths", nargs="*",
                    help="Rule file(s) to scan, or a repo dir (e.g. '.'); omit to auto-discover in --repo.")
    sh.add_argument("--repo", "-r", default=".", help="Git repo to scan (default: current dir).")
    sh.add_argument("--inject-demo", action="store_true",
                    help="Plant a zombie into a throwaway copy of your rules and show the catch.")
    sh.add_argument("--json", action="store_true", help="Output events as JSON.")
    sh.add_argument("--github-comment", action="store_true", help="Print a GitHub PR-comment (markdown).")
    sh.add_argument("--receipt", action="store_true",
                    help="Emit a signed ER1 receipt per scanned file into .sagrada/receipts/.")
    sh.add_argument("--receipt-dir", default=None, help="Where to write receipts.")
    sh.add_argument("--worktree", action="store_true",
                    help="Also check the current (uncommitted) file content — catches a re-add staged for this commit.")
    sh.add_argument("--strict", action="store_true",
                    help="Exit non-zero if any zombie belief is found (for CI).")
    sh.set_defaults(func=_cmd_scan_history)

    v = sub.add_parser("verify", help="Verify ER1 receipts offline.")
    v.add_argument("receipts", nargs="+", help="Receipt JSON file(s).")
    v.set_defaults(func=_cmd_verify)

    ca = sub.add_parser("check-action",
                        help="Preflight a proposed agent action against its active constraints; emit a signed ER1 receipt.")
    ca.add_argument("--beliefs", default=None,
                    help="JSON file: [{entity, rule(equals|excludes|satisfies), value?}] — the active constraints.")
    ca.add_argument("--action", required=True,
                    help="JSON file: {tool, asserts:{entity:value}, resource} — the proposed action.")
    ca.add_argument("--receipt", action="store_true", help="Write a signed ER1 receipt into .sagrada/receipts/.")
    ca.add_argument("--receipt-dir", default=None, help="Where to write the receipt.")
    ca.add_argument("--json", action="store_true", help="Print the full receipt as JSON.")
    ca.add_argument("--strict", action="store_true", help="Exit non-zero on HALT (for CI / a hard gate).")
    ca.set_defaults(func=_cmd_check_action)

    vt = sub.add_parser("vitals",
                        help="Compute the 0-100 belief-integrity score (SAGRADA-VITALS-METHOD v0.1, frozen).")
    vt.add_argument("paths", nargs="*",
                    help="Rule file(s) to score; omit to auto-discover in --repo.")
    vt.add_argument("--repo", "-r", default=".", help="Git repo to score (default: current dir).")
    vt.add_argument("--window-days", type=int, default=365,
                    help="Trailing evaluation window (method default: 365).")
    vt.add_argument("--json", action="store_true", help="Output the full result as JSON.")
    vt.add_argument("--badge-out", default=None,
                    help="Write a shields.io endpoint JSON badge to this path.")
    vt.add_argument("--strict", action="store_true",
                    help="Exit 3 when the repo cannot be scored (NOT SCORED — no rule files "
                         "with git history). Catches CI wired to the wrong directory; a "
                         "NOT SCORED repo is unmeasured, never CLEAR.")
    vt.set_defaults(func=_cmd_vitals)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
