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
- **Least privilege.** The Action needs only `contents: read` and (to comment)
  `pull-requests: write`. It makes no other network calls — your file contents never
  leave the runner.
- **The PR comment is deterministic-only.** It reports a finding only when a retracted
  rule was genuinely re-added in your history (no fuzzy/semantic matching), so it will
  not spam reviewers with maybes.
- **The receipt.** Every run uploads `sagrada-er1-receipts` — a signed, offline-verifiable
  record of the check that a stranger can recompute with `er1-verify` or `er1_verify.mjs`.

## Inputs

| Input | Default | Description |
|---|---|---|
| `paths` | _(auto-discover)_ | Space-separated rule files to scan. |
| `comment` | `true` | Post a PR comment with the result. |
| `fail-on-zombie` | `true` | Fail the check when a zombie prompt is found. |
