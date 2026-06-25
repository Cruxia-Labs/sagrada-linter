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


def _cmd_scan_history(args) -> int:
    repo = args.repo
    if args.inject_demo:
        target = args.path
        if target is None:
            on_disk = find_rule_files_on_disk(repo)
            if not on_disk:
                print("No rule file found to demo. Pass one, e.g. --inject-demo CLAUDE.md", file=sys.stderr)
                return 2
            target = on_disk[0]
        events = inject_demo(repo, target)
        by_file = {target: events} if events else {}
        scanned = []
    elif args.path:
        events = scan_history_for_zombies(repo, args.path)
        by_file = {args.path: events} if events else {}
        scanned = [args.path]
    else:
        scanned = discover_rule_files(repo)
        by_file = {}
        for f in scanned:
            ev = scan_history_for_zombies(repo, f)
            if ev:
                by_file[f] = ev

    if args.github_comment:
        print(format_github_comment(by_file))
    elif args.json:
        print(json.dumps({f: [dataclasses.asdict(e) for e in evs]
                          for f, evs in by_file.items()}, indent=2))
    else:
        print(format_events(by_file, color=sys.stdout.isatty()))

    if args.receipt and scanned:
        rdir = args.receipt_dir or os.path.join(repo, ".sagrada", "receipts")
        written = []
        for f in scanned:
            evs = by_file.get(f, [])
            z = [(e.term, e.re_added_def, e.retracted_at, e.re_added_at) for e in evs]
            written.append(write_receipt(build_check_receipt(f, z), rdir))
        print(f"{len(written)} receipt(s) written to {rdir} — "
              f"verify offline with `sagrada-linter verify` or `node er1_verify.mjs`.", file=sys.stderr)

    return 1 if (args.strict and any(by_file.values())) else 0


def _cmd_verify(args) -> int:
    verifier = os.path.join(os.path.dirname(__file__), "er1_verify.py")
    return subprocess.run([sys.executable, verifier] + args.receipts).returncode


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="sagrada-linter",
        description="Catch zombie prompts — retracted AI rules that crept back into your repo.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sh = sub.add_parser("scan-history", help="Scan your git history for zombie prompts.")
    sh.add_argument("path", nargs="?", default=None,
                    help="A rule file to scan; omit to auto-discover all rule files.")
    sh.add_argument("--repo", "-r", default=".", help="Git repo to scan (default: current dir).")
    sh.add_argument("--inject-demo", action="store_true",
                    help="Plant a zombie into a throwaway copy of your rules and show the catch.")
    sh.add_argument("--json", action="store_true", help="Output events as JSON.")
    sh.add_argument("--github-comment", action="store_true", help="Print a GitHub PR-comment (markdown).")
    sh.add_argument("--receipt", action="store_true",
                    help="Emit a signed ER1 receipt per scanned file into .sagrada/receipts/.")
    sh.add_argument("--receipt-dir", default=None, help="Where to write receipts.")
    sh.add_argument("--strict", action="store_true", help="Exit non-zero if any zombie is found (for CI).")
    sh.set_defaults(func=_cmd_scan_history)

    v = sub.add_parser("verify", help="Verify ER1 receipts offline.")
    v.add_argument("receipts", nargs="+", help="Receipt JSON file(s).")
    v.set_defaults(func=_cmd_verify)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
