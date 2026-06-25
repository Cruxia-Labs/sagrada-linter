# GitHub Action

Run Sagrada Linter on every pull request: it scans your rule-file history for **zombie
prompts** (a rule you retracted that crept back in), posts a PR comment, attaches a
verifiable **ER1 receipt** as a build artifact, and fails the check on a zombie.

Paste this into `.github/workflows/sagrada.yml`:

```yaml
name: Sagrada Linter
on:
  pull_request:
    paths:
      - "**/CLAUDE.md"
      - "**/AGENTS.md"
      - "**/.cursorrules"
      - ".cursor/rules/**"
      - ".github/copilot-instructions.md"

permissions:
  contents: read          # read the repo
  pull-requests: write    # post the result comment

jobs:
  zombie-prompts:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # full history — the scan reads your git history
      - uses: Cruxia-Labs/sagrada-linter@v0
```

## Notes

- **`fetch-depth: 0` is required.** The scan reads the git *history* of your rule files;
  a shallow checkout has nothing to scan.
- **No third-party network calls.** The Action needs only `contents: read` and (to
  comment) `pull-requests: write`. The linter itself makes no network calls — its only
  outputs are the PR comment and the ER1 receipt artifact, which stay inside **your** GitHub
  repo. Nothing is sent to us or any third party. (The comment and receipt do contain the
  conflicting rule text, by design, so a reviewer can see exactly what changed.)
- **The PR comment is deterministic-only.** It reports a finding only when a retracted
  rule was genuinely re-added in your history (no fuzzy/semantic matching), so it will
  not spam reviewers with maybes.
- **The receipt.** Every run uploads `sagrada-er1-receipts` — a signed, offline-verifiable
  record of the check that anyone can recompute with `sagrada-linter verify <receipt>` or
  `node sagrada_linter/er1_verify.mjs <receipt>`.

## Inputs

| Input | Default | Description |
|---|---|---|
| `paths` | _(auto-discover)_ | Space-separated rule files to scan. |
| `comment` | `true` | Post a PR comment with the result. |
| `fail-on-zombie` | `true` | Fail the check when a zombie prompt is found. |
