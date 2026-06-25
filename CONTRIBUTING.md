# Contributing

Thanks for helping make agent rule files coherent over time.

## The fastest ways to help

- **Report a miss or a misfire.** If Sagrada flagged something that wasn't a zombie, or missed
  one that was, open an issue with the rule file (or a minimal snippet) and what you expected.
  Real cases are how we tune the deterministic floor without sacrificing precision.
- **Add rule-grammar coverage.** The extractor anchors on `key: value`, `- term — definition`,
  and bold labels. If your rule files use a different structured shape, a PR with examples is
  welcome.

## Write an independent ER1 verifier (the high-value one)

The receipt format (ER1) is meant to be a *standard*, not one tool's output. The proof of that
is a **second, independent implementation** that recomputes the same verdicts. This repo ships
two reference verifiers (Python + JavaScript) and a frozen conformance suite
(`sagrada_linter/golden_vectors.json`). If you write a verifier in another language that passes
those vectors byte-for-byte, open a PR adding it to a conformance list — that's the single most
valuable contribution, because it turns "a file we write" into "a format anyone can recompute."

## Principles we hold

- **Coherence, not correctness.** We never claim a rule is *good* — only that you're acting on
  one you already retracted.
- **Precision over recall.** When in doubt, don't flag it. A false positive in a reviewer's face
  costs more than a quiet miss.
- **Deterministic gates only.** Anything fuzzy is advisory and never fails a build.
