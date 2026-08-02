# Benchmarks

Honest numbers on real repositories. We'd rather tell you where the deterministic catch
ends than oversell it — the boundary is what makes the result trustworthy.

## Method

We cloned public AI-developer-tool repositories, discovered their rule files
(`.cursorrules` / `CLAUDE.md` / `AGENTS.md` / `.cursor/rules/*`), and ran the deterministic
scanner over each file's full git history. **Precision** was measured by inspecting every
detected event by hand against the actual git diff. **Recall** was measured by injecting a
known cross-commit retract→re-add into each real rule file and checking it was caught.

Reproduce any line below with the public CLI:

```bash
git clone <repo> && cd <repo>
sagrada-linter scan-history .
```

## Detector validation corpus (June 2026, 14 repos)

This is the **precision/recall corpus** — a small hand-checkable set used to measure whether
the detector over-fires, not a survey of how common zombie rules are.

| | |
|---|---|
| Repositories attempted | 14 |
| Repositories cloned | 13 |
| With rule files at standard paths | 4 |
| Rule-file revisions scanned | 43 |

Repos with rule files: `openai/openai-agents-python`, `browser-use/browser-use`,
`princeton-nlp/SWE-agent`, `modelcontextprotocol/servers`.

**For prevalence, see the 400-repo survey** (July 2026): the top 80 by stars in each of five
package ecosystems, 393 readable, 57 of them — 14.5% — carrying at least one rule deleted on
the record and live in the file today. That figure is provisional: the false-positive
labelling pass over the flagged repos is not finished, so it can move.

## Precision: 0 false positives across 43 revisions

A naive matcher flagged **2** candidate events (in `openai/openai-agents-python`'s
`AGENTS.md`). On inspection, both were a rule **reworded within a single commit** — removed
and re-added in the *same* commit, which is a rewrite, not a retract→re-add. The scanner
correctly classifies these as rewrites (a zombie is strictly cross-commit), so the reported
count is **0 false positives**. The check did not over-fire on real, messy edits.

## Recall: 5 / 7 real rule files (controlled injection)

We injected a known cross-commit zombie into 7 real rule files and the scanner caught **5**.
The **2 misses** were Cursor `.cursor/rules/*.mdc` files written as imperative bullets —
e.g. `- Use python with type annotations`, `- Do not append to the README`. These have no
`key: value` / `term — definition` structure for the deterministic extractor to anchor on,
so it has nothing to track. This is the precision/recall tradeoff, stated plainly:

> The deterministic floor extracts **structured** rules (`key: value`, `- term — definition`,
> bold labels). Free-prose imperative rules are **not** extracted today. We keep precision at
> 100% by refusing to guess; richer extraction is on the roadmap, and it will be labeled as
> best-effort, never as the certified deterministic catch.

## What it does not catch (the boundary)

- A rule reworded **within the same commit** (a rewrite, not a zombie).
- An **intentional** reversal (silence it with `sagrada:allow`).
- **Semantic** contradictions between two different rules — not part of the deterministic check.
- **Imperative free-prose** rules with no `key: value` structure (see recall, above).
