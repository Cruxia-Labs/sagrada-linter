# <img src="media/cruxia-mark.svg" width="30" alt=""> Sagrada Linter

A linter for agent rule files (`CLAUDE.md`, `AGENTS.md`, `.cursorrules`): it reads their
git history and reports rules that were retracted in one commit and re-added in a later one.

[![CI](https://github.com/Cruxia-Labs/sagrada-linter/actions/workflows/ci.yml/badge.svg)](https://github.com/Cruxia-Labs/sagrada-linter/actions)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://github.com/Cruxia-Labs/sagrada-linter/blob/main/LICENSE)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen)](#pre-commit)

```console
$ git clone https://github.com/Cruxia-Labs/sagrada-specimen && cd sagrada-specimen
$ uvx sagrada-linter scan-history .
2 zombie-prompt event(s) found — a rule was retracted, then re-added later:

  ✗ CLAUDE.md:4  tone
      retracted 376ce593: Keep error messages plain and unfunny
      re-added 2ba05a7d: Keep error messages plain and unfunny

  ✗ CLAUDE.md:2  deploy_gate
      retracted e48323d1: Always run migrations manually before deploy
      re-added 0f6c89af: Always run migrations manually before deploy
```

That is the whole idea. The specimen above is a scripted repository with known findings;
run the same command on a repository you own (use a full clone — a shallow `--depth 1`
clone has no history to read):

```bash
uvx sagrada-linter scan-history .
```

Runs locally over your git history. No install, no signup, no API key, nothing leaves
your machine. On a clean history:

```console
$ uvx sagrada-linter scan-history .
0 zombie beliefs found — 1 rule file(s) read; every retraction on record is still resting.
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
  refuses to guess at prose rather than risk a false positive. (Measured: see [BENCHMARKS.md](https://github.com/Cruxia-Labs/sagrada-linter/blob/main/BENCHMARKS.md).)

The deterministic catch is small and sharp; every result is a diff you can open.

> Not `git log | grep`. Grep finds a string; it can't tell that a rule was *retracted* and then
> *re-asserted* across commits, pair the before/after, or tell a rewrite from a revival.

## Belief-integrity score (`vitals`) — unreleased, on `main` only

*Not in the PyPI release yet; run from a checkout if you want it early.*

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

**Band names — canonical vs display.** The score falls into one of four bands. The
*canonical* strings frozen with the method — `SOUND / WATCH / ROTTING / OVERRUN` — are what
`--json` output, receipts, and sealed records carry, forever: every historical artifact
recomputes byte-for-byte. What the headline and the badge *say* is the display ladder:

| canonical (method, `--json`, receipts) | display (headline, badge) | meaning |
|---|---|---|
| `SOUND` | **CLEAR** | nothing detectable in the record — an absence-claim, not a medal |
| `WATCH` | **EXPOSED** | at risk; attention, not yet judgment |
| `ROTTING` | **WALKING** | dead rules are active among the living |
| `OVERRUN` | **ROTTED** | decay complete |

We renamed the display; the receipts never moved.

## Install

```bash
uvx sagrada-linter scan-history .   # zero-install run (recommended)
pipx install sagrada-linter         # persistent CLI
pip install sagrada-linter          # into the current environment
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
[docs/GITHUB_ACTION.md](https://github.com/Cruxia-Labs/sagrada-linter/blob/main/docs/GITHUB_ACTION.md):

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
sagrada-linter verify .sagrada/receipts/*.er1.json     # Python — works from any install
# Or the zero-dependency JS reference verifier (one file; grab it from the repo):
#   curl -O https://raw.githubusercontent.com/Cruxia-Labs/sagrada-linter/v0.1.0/sagrada_linter/er1_verify.mjs
node er1_verify.mjs .sagrada/receipts/*.er1.json
```

The receipt format is **ER1** — open, and built so the verifier is the simple part: see
[SCOPE_OF_CERTIFICATION.md](https://github.com/Cruxia-Labs/sagrada-linter/blob/main/SCOPE_OF_CERTIFICATION.md) for exactly what is certified and what is not.

## In your agent — decision-time receipts

`scan-history` audits the past. To attest what an agent did *as it acts*, call `check_action` in your
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
Runs locally, no network — **we never see your files**. The receipt verifies in Python or zero-dep JS,
so a relying party never has to trust the agent that produced it.

## License

Apache-2.0 © 2026 Cruxia (including the patent grant). Contributions welcome — see [CONTRIBUTING.md](https://github.com/Cruxia-Labs/sagrada-linter/blob/main/CONTRIBUTING.md).


---

*A zombie belief is the smallest, most checkable case of a general problem: systems that re-assert beliefs they were told to drop. The linter catches the deterministic version of that — and nothing fuzzier. It emits an ER1 receipt so the catch is something a stranger can re-verify, not something you take on trust. It's the first verb in a family. → [Cruxia-Labs](https://github.com/Cruxia-Labs)*
