# Dogfooded ER1 receipts

`agents-md-coherent.er1.json` is a real receipt this project emitted when it scanned its **own**
rule file (`AGENTS.md`) — the verdict is `ALLOW` (COHERENT): no retracted rule was re-added. It's
the literal artifact the [dogfood workflow](../../.github/workflows/dogfood.yml) uploads on every push.

Re-verify it yourself, offline, in either language — no install beyond the verifier, no trust in us:

```bash
python er1_verify.py agents-md-coherent.er1.json   # Python reference verifier
node er1_verify.mjs agents-md-coherent.er1.json     # zero-dependency JavaScript verifier
```

Get the two verifiers from [er1-spec](https://github.com/Cruxia-Labs/er1-spec). Flip a single byte of
the receipt and both reject it.
