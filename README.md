# Sagrada Linter

**Catch the AI rules you already changed before they break your build — a local linter for your `.cursorrules`, `CLAUDE.md`, and `AGENTS.md`.**

[![CI](https://github.com/Cruxia-Labs/sagrada-linter/actions/workflows/ci.yml/badge.svg)](https://github.com/Cruxia-Labs/sagrada-linter/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen)](#pre-commit)

Your agent keeps acting on rules you already changed. You retract a guideline in
`.cursorrules` / `CLAUDE.md` / `AGENTS.md`, and a few edits later it creeps back in — the
build breaks, the agent does the thing you told it to stop doing, and you can't see why.
These are **zombie prompts**, and they're invisible to a snapshot — they only exist in the
*history* of your rule files.

Sagrada Linter reads that history and catches them.

```console
$ sagrada-linter scan-history .

2 zombie-prompt events found — a rule was retracted, then re-added later:

  ✗ CLAUDE.md:14  output_format
      retracted a1b2c3d4: always return strict JSON, never prose
      re-added  9f8e7d6c: always return strict JSON, never prose

  ✗ .cursorrules:7  test_runner
      retracted 5e4d3c2b: use pytest, never unittest
      re-added (meaning changed) 0a1b2c3d: prefer pytest; unittest is acceptable
```

## Try it on your own repo (30 seconds, nothing installed)

```bash
uvx sagrada-linter scan-history .
```

It runs over **your** git history and tells you how many zombie prompts already happened
in your repo — with the exact `file:line` and the commit where each rule was retracted.
No install, no signup, no API key, nothing leaves your machine. If your rule files are
already clean, it says so:

```console
$ uvx sagrada-linter scan-history .
0 zombie-prompt events found. Your rule files are coherent over time. ✓
```

Clean history? See it fire on your own files anyway:

```bash
uvx sagrada-linter scan-history --inject-demo CLAUDE.md
```

## What it actually does (and what it doesn't)

The thing a normal linter can't see: **coherence over time.** A snapshot checker reads your
rules as they are *right now*. Sagrada reads how they *changed* — and flags the one pattern
that quietly breaks agents: a rule you **retracted** that came **back**.

It's deterministic. Every result is a real retract→re-add in your git history, located by
diffing consecutive versions of the file — **no fuzzy matching, no model, no guessing.** When
it flags something, it's because the bytes say so.

**What it will _not_ catch** (so you know the edges):

- A rule re-added with **completely different wording** in the *same* commit it was removed —
  that reads as a rewrite, not a zombie.
- An **intentional** reversal you actually meant. (Mark it with `sagrada:allow` to silence it.)
- **Semantic** contradictions between two *different* rules ("always X" vs "never X"). That's
  a fuzzier problem; it is **not** part of the deterministic check and never fails your build.
- **Imperative free-prose** rules with no `key: value` shape (e.g. `- Use type annotations`).
  The deterministic floor anchors on structured rules (`key: value`, `- term — definition`); it
  refuses to guess at prose rather than risk a false positive. (Measured: see [BENCHMARKS.md](BENCHMARKS.md).)

This honesty is the point: the deterministic catch is small and sharp, and you can trust every
result because the tool never pretends to know more than the diff does.

> Not `git log | grep`. Grep finds a string; it can't tell that a rule was *retracted* and then
> *re-asserted* across commits, pair the before/after, or tell a rewrite from a revival.

## Install

```bash
uvx sagrada-linter           # zero-install run (recommended)
pipx install sagrada-linter  # persistent CLI
pip install sagrada-linter   # into the current environment
```

Python 3.9+. One dependency (`cryptography`). Runs fully offline.

## Pre-commit

Block a zombie before it lands. Add to `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/Cruxia-Labs/sagrada-linter
    rev: v0.1.0
    hooks:
      - id: sagrada-linter
```

## GitHub Action

Catch zombies on every PR, with a comment on the offending line. See
[docs/GITHUB_ACTION.md](docs/GITHUB_ACTION.md):

```yaml
- uses: actions/checkout@v4
  with: { fetch-depth: 0 }
- uses: Cruxia-Labs/sagrada-linter@v0
```

## Verify it yourself

Every check can drop a small **receipt** (`--receipt`) into `.sagrada/receipts/` — a signed,
chained record of exactly what was checked and what the verdict was. It's offline-verifiable:
a stranger recomputes it byte-for-byte, in two languages, with no install and no trust in us.

```bash
sagrada-linter scan-history . --receipt
sagrada-linter verify .sagrada/receipts/*.er1.json     # Python
node sagrada_linter/er1_verify.mjs .sagrada/receipts/*.er1.json   # JavaScript, zero-dependency
```

The receipt format is **ER1** — open, and built so the verifier is the simple part: see
[SCOPE_OF_CERTIFICATION.md](SCOPE_OF_CERTIFICATION.md) for exactly what is certified and what is not.

## License

MIT © Cruxia. Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).
