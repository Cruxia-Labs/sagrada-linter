# Scope of Certification

Sagrada Linter is precise about what it proves. Read this before you rely on a receipt.

## The one-line version

> **Coherence, not correctness.** A receipt certifies that the verdict follows from the
> recorded rule-state and the recorded change — *not* that your rules are good, true, or
> complete. Garbage in, certified garbage out.

## What a receipt certifies

When `scan-history --receipt` writes an ER1 receipt, it certifies exactly this:

1. **The verdict is a deterministic function of the recorded inputs.** Given the rule-state
   and the action recorded *in the receipt*, the HALT/ALLOW verdict is recomputable by anyone,
   offline, with no access to us. Two independent reference verifiers (Python and a
   zero-dependency JavaScript one) reproduce it byte-for-byte.
2. **The record is tamper-evident.** The receipt is signed (Ed25519 over a canonical hash). Flip
   a single byte of the rules, the action, or the verdict and verification fails.

That's it. The receipt is **admissible, not accurate**: it proves the check was performed and
what it concluded — it does not vouch for your rules.

## What is _certified_ (deterministic — can fail your build)

- **Zombie prompts: a retracted rule re-added.** A rule that was removed in one commit and
  re-introduced in a later commit. This is read straight off the git diff — no model, no
  inference. In the receipt this is recorded as a `BANNED_ENTITY` conflict: a retracted rule is
  treated as *excluded from the live rule set*, so re-introducing it is a conflict the verifier
  recomputes deterministically.

## What is _not_ certified (advisory — never gates, never in a halt)

- **Semantic contradictions** between two *different* rules ("always X" vs "never X"). Detecting
  these requires judgment, not a diff. Sagrada does **not** do this in the certified path; such a
  finding would be advisory only and is **structurally barred from ever failing a build or
  appearing in a PR comment** — the conflict predicate only gates rules whose source is
  deterministic.
- **The truth or quality of your rules.** Sagrada has no opinion on whether "use PostgreSQL" is a
  good idea. It only tracks whether you're acting on a rule you already retracted.
- **Re-adds reworded in the same commit, and intentional reversals.** See the README "what it
  will not catch." Mark a deliberate reversal with `sagrada:allow`.
- **Imperative free-prose rules** with no `key: value` / `term — definition` structure. The
  deterministic extractor anchors only on structured rules; prose-only rule files yield fewer
  claims to track. We keep precision high by not guessing — see [BENCHMARKS.md](BENCHMARKS.md).

## Privacy

Everything runs locally. Your file contents never leave your machine — the scan is a git
subprocess plus standard-library text diffing, with no network calls and no model. The receipt
contains only what you choose to record.

## The receipt format

The receipt format is **ER1** — an open, offline-verifiable format designed so the *verifier* is
the simple part (a stranger can reimplement it in an afternoon and check your receipts without
trusting you). The two reference verifiers ship in this repo (`sagrada_linter/er1_verify.py`,
`sagrada_linter/er1_verify.mjs`) alongside frozen conformance vectors
(`sagrada_linter/golden_vectors.json`).
