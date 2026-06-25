"""The preflight decision engine — the operator-side "verb" of the tool-boundary gate.

Given the current typed belief-state + a proposed action, decide ALLOW or HALT, and emit
a signed, chained action receipt. The HALT verdict is a deterministic function of the
beliefs + action (the `conflict` predicate); the receipt records the exact pre-state
snapshot + the raw action so an independent verifier can recompute the verdict offline.

This module produces the receipt; it never executes the action. (The agent observes; the
operator disposes.) The MCP gate (Phase 3) wraps a real tool call around `preflight()`.
"""
from __future__ import annotations

from typing import Optional

from . import conflict as C
from . import receipt as R


class PreflightGate:
    """Stateful per-session gate: holds the signing key and threads the receipt chain."""

    def __init__(self, private_key=None, *, seed: bytes = b"", operator_version: str = R.OPERATOR_VERSION):
        if private_key is None:
            private_key, _pub = R.generate_keypair()
        self._sk = private_key
        self.operator_version = operator_version
        self._chain_root = R.chain_root_from_seed(seed)
        self._prev_hash = self._chain_root          # genesis: prev == root
        self._sequence = 0

    @property
    def chain_root(self) -> str:
        return self._chain_root

    @property
    def sequence(self) -> int:
        return self._sequence

    def preflight(self, beliefs: list, action: C.ProposedAction) -> dict:
        """Run the gate on a proposed action. Returns a signed action receipt."""
        belief_records = [C.belief_to_record(b) for b in beliefs]
        pre_root = R.state_root(belief_records)

        c = C.conflict(beliefs, action)
        if c is not None:
            decision = {
                "verdict": "HALT",
                "reason_code": c.reason_code,
                "conflicting_belief_id": c.belief_id,
                "entity": c.entity,
                "current": c.current,
                "proposed": c.proposed,
            }
            post_root = None                         # HALT: no state transition
        else:
            decision = {
                "verdict": "ALLOW",
                "reason_code": "COHERENT",
                "conflicting_belief_id": None,
                "entity": None,
                "current": None,
                "proposed": None,
            }
            post_root = pre_root                      # checkpoint, not a mutation

        unsigned = R.build_receipt(
            decision=decision,
            beliefs=belief_records,
            action={"tool": action.tool, "asserts": dict(action.asserts), "resource": action.resource},
            pre_state_root=pre_root,
            post_state_root=post_root,
            prev_receipt_hash=self._prev_hash,
            chain_root_hash=self._chain_root,
            sequence_number=self._sequence,
            operator_version=self.operator_version,
        )
        signed = R.sign(unsigned, self._sk)

        # advance the chain
        self._prev_hash = R.receipt_hash(signed)
        self._sequence += 1
        return signed

    @staticmethod
    def is_halt(receipt: dict) -> bool:
        return receipt.get("decision", {}).get("verdict") == "HALT"


def halt_summary(receipt: dict) -> Optional[str]:
    """One-glance human line for the IDE modal, on HALT (content stays local)."""
    d = receipt.get("decision", {})
    if d.get("verdict") != "HALT":
        return None
    return (
        f"HALT [{d.get('reason_code')}]: action sets {d.get('entity')}={d.get('proposed')!r} "
        f"but current belief requires {d.get('current')!r} "
        f"(receipt {receipt.get('receipt_id','')[:8]}, {R.receipt_hash(receipt)[:14]}…)"
    )


__all__ = ["PreflightGate", "halt_summary"]
