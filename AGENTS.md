# AGENTS.md

Conventions for working in **sagrada-linter** — for the AI agents (and humans) who develop it.
This file is itself a structured rule set, so our own linter scans it on every push: we run the
determinism we sell. See [`.github/workflows/dogfood.yml`](.github/workflows/dogfood.yml).

## Rules

- runtime: Python 3.9+, standard library only
- dependencies: exactly one runtime dependency — `cryptography` (for Ed25519); do not add more without a strong reason
- determinism: the scan path is byte-deterministic — no fuzzy matching, no model, no network
- conformance: `test_conformance.py` must stay green, and every receipt must verify in both Python and JavaScript
- receipts: ER1 receipts are canonical-JSON bytes (RFC 8785-compatible), signed with a fresh ephemeral Ed25519 key
- scope: coherence, not correctness — we certify that a verdict follows from the recorded rules, never that a rule is good
- format-naming: ER1 is an "open format", not a "standard" — that word is earned only when a second party recomputes the vectors
- attribution: commits are authored as Mars Ausili <mars@cruxia.ai>

## What the linter anchors on

- `key: value` — a structured rule (like every line above)
- `- term — definition` — a bullet with an em-dash
- A **bold label** at the start of a line

Free prose with no structured shape is never guessed at — that is the deterministic floor, by design.
