"""The Action Receipt — signed, chained, offline-verifiable record of a preflight decision.

Reuses the proven primitives from `the vendored canonical-JSON module`:
  - `canonical_json` (RFC 8785 canonical serialization — sorted keys, NFC, compact),
  - SHA-256 over the canonical body with `signature := null`,
  - Ed25519 over the raw 32-byte digest (b64url-encoded keys/sigs).

The schema carries the irreversible monetization/standard seams the boards said are
now-or-never (the signature covers the schema, so they cannot be retrofitted): per-belief
`source_kind`, `action_binding`, the receipt `chain`, `belief_class`/`halt_eligible`,
`coverage`, key/verification tiers, and witness slots.

Determinism fence (#3): `receipt_id` and `created_at` are signed metadata but are NOT
part of the *verified claim* — the verifier re-runs the conflict predicate over the
recorded beliefs + action, not over the timestamp/uuid.
"""
from __future__ import annotations

import base64
import datetime as _dt
import hashlib
import uuid
from typing import Optional

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.exceptions import InvalidSignature

from .canonical import canonical_json

SCHEMA_VERSION = "action-receipt/v0"
OPERATOR_VERSION = "sagrada-linter/0.1"


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _now_rfc3339() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def sha256_hex(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def args_hash(tool: str, asserts: dict, resource: str) -> str:
    """Bind the receipt to the exact tool request (the `action_binding`)."""
    return sha256_hex(canonical_json({"tool": tool, "asserts": asserts, "resource": resource}))


def state_root(belief_records: list) -> str:
    """Content-addressed root over the ordered belief snapshot (the pre/post state root)."""
    return sha256_hex(canonical_json(belief_records))


def generate_keypair() -> tuple[Ed25519PrivateKey, str]:
    """Return (private_key, base64url raw public-key string)."""
    sk = Ed25519PrivateKey.generate()
    pub = sk.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    return sk, _b64url(pub)


def receipt_body_for_hash(receipt: dict) -> dict:
    """The receipt with `signature := None` — what gets canonicalized + hashed + signed."""
    body = dict(receipt)
    body["signature"] = None
    return body


def receipt_hash(receipt: dict) -> str:
    return sha256_hex(canonical_json(receipt_body_for_hash(receipt)))


def receipt_digest(receipt: dict) -> bytes:
    return hashlib.sha256(canonical_json(receipt_body_for_hash(receipt))).digest()


def sign(receipt: dict, sk: Ed25519PrivateKey) -> dict:
    """Return a new receipt dict with the Ed25519 signature filled in."""
    pub = sk.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    sig = sk.sign(receipt_digest(receipt))
    out = dict(receipt)
    out["signature"] = {
        "algorithm": "ed25519",
        "public_key": _b64url(pub),
        "signature": _b64url(sig),
    }
    return out


def verify_signature(receipt: dict) -> bool:
    """True iff the embedded Ed25519 signature verifies the canonical body (tamper-evident)."""
    sigblock = receipt.get("signature")
    if not sigblock or sigblock.get("algorithm") != "ed25519":
        return False
    try:
        pub = _b64url_decode(sigblock["public_key"])
        sig = _b64url_decode(sigblock["signature"])
        Ed25519PublicKey.from_public_bytes(pub).verify(sig, receipt_digest(receipt))
        return True
    except (InvalidSignature, KeyError, ValueError):
        return False


def chain_root_from_seed(seed: bytes) -> str:
    return sha256_hex(seed)


def build_receipt(
    *,
    decision: dict,
    beliefs: list,                 # list of belief_to_record(...) dicts
    action: dict,                  # raw {tool, asserts, resource} — lets the verifier recompute
    pre_state_root: str,
    post_state_root: Optional[str],
    prev_receipt_hash: str,
    chain_root_hash: str,
    sequence_number: int,
    key_tier: str = "ephemeral",
    verification_tier: str = "local",
    operator_version: str = OPERATOR_VERSION,
    receipt_id: Optional[str] = None,
    created_at: Optional[str] = None,
) -> dict:
    """Assemble an unsigned action receipt (call `sign()` next)."""
    tool = action.get("tool", "")
    asserts = action.get("asserts", {})
    resource = action.get("resource", "")
    return {
        "schema_version": SCHEMA_VERSION,
        "receipt_id": receipt_id or str(uuid.uuid4()),
        "created_at": created_at or _now_rfc3339(),
        "chain": {
            "prev_receipt_hash": prev_receipt_hash,
            "chain_root_hash": chain_root_hash,
            "sequence_number": sequence_number,
        },
        "pre_state_root": pre_state_root,
        "post_state_root": post_state_root,
        "action": {"tool": tool, "asserts": asserts, "resource": resource},
        "action_binding": {
            "tool": tool,
            "args_hash": args_hash(tool, asserts, resource),
            "resource": resource,
        },
        "beliefs": beliefs,
        "decision": decision,
        "coverage": {
            "certified_modules": ["typed-config"],
            "exclusions": ["nl_extraction"],
        },
        "operator_version": operator_version,
        "key_tier": key_tier,
        "verification_tier": verification_tier,
        "witnesses": [],          # multi-signer slots (operator/org/witness) — empty for now
        "signature": None,
    }


__all__ = [
    "SCHEMA_VERSION", "OPERATOR_VERSION",
    "generate_keypair", "sign", "verify_signature",
    "receipt_hash", "receipt_digest", "args_hash", "sha256_hex",
    "chain_root_from_seed", "build_receipt",
]
