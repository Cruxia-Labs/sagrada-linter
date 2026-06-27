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
from .linter_receipt import build_check_receipt, write_receipt
from .decision import PreflightGate
from .gitwalk import walk_file_history


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
        if not targets:
            scanned = discover_rule_files(repo_root)
        elif len(targets) == 1 and os.path.isdir(targets[0]):
            repo_root = targets[0]                      # `scan-history .` -> the repo, auto-discover
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

    if args.receipt and scanned:
        rdir = args.receipt_dir or os.path.join(repo_root, ".sagrada", "receipts")
        gate = PreflightGate()                          # ONE gate -> a continuous receipt chain
        written = []
        for f in scanned:
            evs = by_file.get(f, [])
            z = [(e.term, e.re_added_def, e.retracted_at, e.re_added_at) for e in evs]
            written.append(write_receipt(build_check_receipt(f, z, gate=gate), rdir))
        print(f"{len(written)} receipt(s) written to {rdir} — "
              f"verify offline with `sagrada-linter verify` or `node er1_verify.mjs`.", file=sys.stderr)
    elif args.receipt and args.inject_demo:
        print("note: --receipt is a no-op with --inject-demo (the demo plants a zombie in a "
              "throwaway copy — there is no real history to sign). Run scan-history on a real "
              "repo to emit a receipt.", file=sys.stderr)
    elif args.receipt:
        print("note: nothing was scanned, so no receipt was written.", file=sys.stderr)

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
            print(f"receipt written to {rdir} — verify offline with `sagrada-linter verify` "
                  f"or `node er1_verify.mjs`.", file=sys.stderr)
    return 1 if (args.strict and verdict == "HALT") else 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="sagrada-linter",
        description="Catch zombie prompts — retracted AI rules that crept back into your repo.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sh = sub.add_parser("scan-history", help="Scan your git history for zombie prompts.")
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
    sh.add_argument("--strict", action="store_true", help="Exit non-zero if any zombie is found (for CI).")
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

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
