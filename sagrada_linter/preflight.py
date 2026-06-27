"""Decision-time gate — check a PROPOSED agent action against its active constraints, and get a
signed ER1 receipt attesting the constraint state the action was taken under.

This is the agent / MCP surface (vs. `scan-history`, which audits git history after the fact). Call
`check_action(...)` inside your loop *before* the agent acts: it returns an ALLOW / HALT verdict and a
receipt a stranger can recompute offline, in any language, with no trust in you.

Pure and local by construction — the conflict predicate is ~30 lines of stdlib, there is no network
call on this path, and nothing leaves your machine. "We never see your files" is architecture, not a
promise.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import conflict as C
from .decision import PreflightGate
from .linter_receipt import write_receipt

_RULES = {"equals": C.RULE_EQUALS, "excludes": C.RULE_EXCLUDES, "satisfies": C.RULE_SATISFIES}


def check_action(
    beliefs: List[Dict[str, Any]],
    action: Dict[str, Any],
    *,
    gate: Optional[PreflightGate] = None,
    receipts_dir: Optional[str] = None,
) -> dict:
    """Preflight a proposed action against the active deterministic constraints.

    ``beliefs``: a list of ``{"entity", "rule", "value"?}`` where ``rule`` is ``equals`` /
    ``excludes`` / ``satisfies`` (optional ``status`` = ``active``/``superseded``, ``source`` =
    ``deterministic``/``nl_extracted`` — an ``nl_extracted`` belief is carried but never gates).
    ``action``: ``{"tool", "asserts": {entity: value}, "resource"}``.

    Returns the signed ER1 receipt dict (``receipt["decision"]["verdict"]`` is ``ALLOW`` or ``HALT``).
    If ``receipts_dir`` is given, the receipt is also written there as canonical-JSON bytes.
    """
    g = gate or PreflightGate()
    typed: List[C.TypedBelief] = []
    for i, b in enumerate(beliefs):
        rule = _RULES.get(str(b.get("rule", "")).lower())
        if rule is None:
            raise ValueError(f"beliefs[{i}]: 'rule' must be one of {sorted(_RULES)} (got {b.get('rule')!r})")
        if "entity" not in b:
            raise ValueError(f"beliefs[{i}]: missing 'entity'")
        typed.append(C.TypedBelief(
            belief_id=b.get("belief_id", f"belief:{b['entity']}"),
            entity=b["entity"],
            rule=rule,
            value=str(b.get("value", "")),
            status=b.get("status", C.STATUS_ACTIVE),
            # Accept either the documented ``source`` key or the on-wire ``source_kind`` alias.
            # Default is deterministic (fail-closed): an unlabelled constraint gates by design.
            source_kind=b.get("source", b.get("source_kind", C.SOURCE_DETERMINISTIC)),
        ))
    act = C.ProposedAction(
        tool=action.get("tool", "agent"),
        asserts=dict(action.get("asserts", {})),
        resource=action.get("resource", ""),
    )
    receipt = g.preflight(typed, act)
    if receipts_dir:
        write_receipt(receipt, receipts_dir)
    return receipt


__all__ = ["check_action"]
