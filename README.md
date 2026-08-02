# <img src="media/cruxia-mark.svg" width="30" alt=""> Sagrada Linter

A linter for the belief state of agent instruction files (`CLAUDE.md`, `AGENTS.md`,
`.cursorrules`, …): it reads their git history and reports rules that were retracted
in one commit and are back in the file today.

[![CI](https://github.com/Cruxia-Labs/sagrada-linter/actions/workflows/ci.yml/badge.svg)](https://github.com/Cruxia-Labs/sagrada-linter/actions)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://github.com/Cruxia-Labs/sagrada-linter/blob/main/LICENSE)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen)](#pre-commit)

```console
$ git clone https://github.com/Cruxia-Labs/sagrada-specimen && cd sagrada-specimen
$ uvx sagrada-linter read .
EXAMEN — sagrada-specimen
reading 1 rule file across 16 commits. nothing leaves this machine.

o RESTORED WITH INTENT  tone
    "Keep error messages plain and unfunny"
    killed   376ce593  2026-03-02
    returned 2ba05a7d  2026-03-28  — with the decision on the books:
    in-file · "restored 2026-04-02: the style guide never shipped"
    not a zombie. an intentional restoration, recorded.

+ WALKING  deploy_gate
    "Always run migrations manually before deploy"
    killed   e48323d1  2026-02-14
    revived  0f6c89af  2026-05-19
    active again in CLAUDE.md:2 today · walking 73 days

sagrada-specimen: 1 walking · 1 restored with intent
```

*(captured 2026-07-31 — the day count moves; the commits do not)*

That is the whole idea. The specimen is a scripted repository with known findings; run
the same command on a repository you own (use a full clone — a shallow `--depth 1`
clone has no history to read, and the tool says so rather than printing a clean result):

```bash
uvx sagrada-linter read .
```

Runs locally over your git history. No install, no signup, no API key, nothing leaves
your machine. On a clean history it says so plainly — and a clean result is a result:

```console
$ uvx sagrada-linter read .
EXAMEN — clean-repo
reading 1 rule file across 1 commits. nothing leaves this machine.

NO REVIVED RULES FOUND
every retraction in 1 rule file is still resting.
```

## What it does (and what it doesn't)

A snapshot checker reads rules as they are *right now*. Sagrada reads how they
*changed* — and flags one pattern that quietly breaks agents: a **retracted** rule
that came **back**. A merge, a stale branch, a second file nobody updated; agents
read whatever text survived.

It's deterministic. Every result is a real retract→re-add in your git history, located by
diffing consecutive versions of the file — **no fuzzy matching, no model, no guessing.**
"The same rule" means the same normalized structured line; a reworded rule does not count.

**What it will _not_ catch** (the edges, stated up front):

- A rule re-added with **completely different wording** — that reads as a rewrite, not a zombie.
- An **intentional** reversal you actually meant. Declare it — `sagrada-linter restore FILE LINE
  --reason "…"` writes a `sagrada:allow` marker on the line — and the reading shows the decision
  instead of an accusation (that's the `RESTORED WITH INTENT` entry above).
- **Semantic** contradictions between two *different* rules ("always X" vs "never X"). That is
  a fuzzier problem; it is **not** part of the deterministic check and never fails your build.
- **Imperative free-prose** rules with no structure (e.g. `- Use type annotations`). The
  deterministic floor anchors on structured rules (`key: value`, `- term — definition`); it
  refuses to guess at prose rather than risk a false positive. (Measured: see
  [BENCHMARKS.md](https://github.com/Cruxia-Labs/sagrada-linter/blob/main/BENCHMARKS.md).)

> Not `git log | grep`. Grep finds a string; it can't tell that a rule was *retracted* and then
> *re-asserted* across commits, pair the before/after, or tell a rewrite from a revival.

## The gate — `guard`

The reading reports; the gate enforces. `sagrada-linter guard` writes a lock of every dead
rule; `guard --check` then fails (exit 2) if an undeclared resurrection is present — with the
rule's kill history in the failure text. `guard --workflow` installs the GitHub Actions
workflow so the check runs on every PR.

This repository's specimen runs the gate on itself: its
[PR tab](https://github.com/Cruxia-Labs/sagrada-specimen/pulls) has real pull requests that
try to bring retired rules back and fail CI with the kill history attached — and one declared
restoration that passed.

## Removal with a record — `forget`

Deleting a rule line loses the reason it died. `sagrada-linter forget FILE LINE --reason "…"`
makes the removal itself an artifact: the line is deleted, a dated tombstone row is appended
to `.sagrada/tombstones.jsonl` (term, definition, reason, residue scan), and a signed receipt
is written beside it. Commit all three and the retirement is on the record — `guard` then
locks the grave.

## Belief-integrity score — `vitals`

```sh
sagrada-linter vitals            # 0-100 score for the current repo
sagrada-linter vitals --json     # full inputs + active-zombie detail
sagrada-linter vitals --badge-out badge.json   # shields.io endpoint JSON
```

A deterministic 0-100 score of one repo's belief hygiene over the trailing year, computed
under **SAGRADA-VITALS-METHOD v0.2** — a frozen, hash-committed formula (active zombies
dominate and saturate; historical revivals add a small memory penalty; retraction hygiene can
only *reduce* penalties, never add points). Record-side only: no model, no network, no
judgment call anywhere in the number. What it does **not** measure: whether your agent answers
correctly, code quality, security, or anything an LLM said — 100 means "no zombie beliefs
detectable in the record," nothing more. The GitHub Action publishes the score to the job
summary and uploads the badge (`vitals: true`, the default).

**Band names.** A repo reads `CLEAR` or `ROTTEN`. The strings frozen with the method are an
implementation detail of the receipt format: `--json` output and sealed records carry them
forever so every historical artifact recomputes byte-for-byte, and the display maps over
them. `WALKING` names a rule's state, never a repo's.

## Install

```bash
uvx sagrada-linter read .           # zero-install run (recommended)
pipx install sagrada-linter         # persistent CLI
pip install sagrada-linter          # into the current environment
```

Python 3.9+. One dependency (`cryptography`). Runs fully offline.
Verbs: `read` · `guard` · `forget` · `restore` · `scan-history` · `vitals` · `check-action` · `verify`.

## Pre-commit

Block a zombie before it lands. Add to `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/Cruxia-Labs/sagrada-linter
    rev: v0.2.1
    hooks:
      - id: sagrada-linter
```

## GitHub Action

The same check on every PR, with a comment on the offending line. See
[docs/GITHUB_ACTION.md](https://github.com/Cruxia-Labs/sagrada-linter/blob/main/docs/GITHUB_ACTION.md):

```yaml
- uses: actions/checkout@v4
  with: { fetch-depth: 0 }
- uses: Cruxia-Labs/sagrada-linter@v0
```

## Verify it yourself

Every check can drop a small **receipt** (`--receipt`) into `.sagrada/receipts/` — a signed,
chained record (`.er1.json`) of exactly what was checked and what the verdict was. It verifies
offline: a stranger recomputes it byte-for-byte with no install and no trust in us, in any of
three implementations on disjoint stacks (Python, Node, browser WebCrypto — spec and golden
vectors at [er1-spec](https://github.com/Cruxia-Labs/er1-spec)).

```bash
sagrada-linter read . --receipt
sagrada-linter verify .sagrada/receipts/*.er1.json     # Python — works from any install
# Or the zero-dependency JS reference verifier (one file; grab it from the repo):
#   curl -O https://raw.githubusercontent.com/Cruxia-Labs/sagrada-linter/v0.2.1/sagrada_linter/er1_verify.mjs
node er1_verify.mjs .sagrada/receipts/*.er1.json
```

See [SCOPE_OF_CERTIFICATION.md](https://github.com/Cruxia-Labs/sagrada-linter/blob/main/SCOPE_OF_CERTIFICATION.md)
for exactly what is certified and what is not.

## In your agent — decision-time receipts

`read` audits the past. To attest what an agent did *as it acts*, call `check_action` in your
loop (or from an MCP tool) **before** it runs a step: you get an `ALLOW` / `HALT` verdict **and** a
receipt of the exact constraint state the action was taken under — recomputable offline by anyone.

```python
from sagrada_linter import check_action

# your agent's active, deterministic constraints (from your rules / policy)
beliefs = [
    {"entity": "env:DEPLOY_TARGET", "rule": "equals", "value": "staging"},
    {"entity": "lib:boto3", "rule": "excludes"},
]
receipt = check_action(
    beliefs,
    {"tool": "shell", "asserts": {"env:DEPLOY_TARGET": "production"}, "resource": "deploy.sh"},
    receipts_dir=".sagrada/receipts",
)
if receipt["decision"]["verdict"] == "HALT":
    raise RuntimeError(receipt["decision"]["reason_code"])   # -> SUPERSEDED_VALUE
```

Or from the shell: `sagrada-linter check-action --beliefs beliefs.json --action action.json --receipt`.
Runs locally, no network — **we never see your files**. The receipt verifies offline,
so a relying party never has to trust the agent that produced it.

## The Index

[beliefrotindex.com](https://beliefrotindex.com) — a weekly census of zombie beliefs in
tracked public repos, scored with this linter under a frozen method. Named rows are
opt-in: run the reading, then
[self-list](https://github.com/Cruxia-Labs/sagrada-linter/issues/new?template=self-list.yml).

## Status

One person built this and nobody else has used it yet. A flagged rule can be one you re-added
on purpose — declare it with `restore` and the reading shows the decision instead of an
accusation. If it is wrong about your repository, that is exactly what we want to hear:
[open an issue](https://github.com/Cruxia-Labs/sagrada-linter/issues) with the two commits.

## License

Apache-2.0 © 2026 Cruxia (including the patent grant). Contributions welcome — see [CONTRIBUTING.md](https://github.com/Cruxia-Labs/sagrada-linter/blob/main/CONTRIBUTING.md).

---

*A zombie belief is the smallest, most checkable case of a general problem: systems that
re-assert rules they were told to drop. The linter catches the deterministic version of that —
and nothing fuzzier — and emits a receipt so the catch is something a stranger can re-verify,
not something you take on trust. → [Cruxia-Labs](https://github.com/Cruxia-Labs)*
