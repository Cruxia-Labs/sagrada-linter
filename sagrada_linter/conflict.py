"""The deterministic conflict predicate — the load-bearing core of the preflight gate.

This is the ONE piece of logic that both the producer (`decision.py`, which runs it
against the live belief-state from the engine) and the independent verifier
(`verifier.py`, which re-runs it against the snapshot recorded *in the receipt*) must
compute identically. It is therefore pure: **stdlib only, no engine, no network, no
clock, no randomness.** A stranger's offline verifier imports exactly this module (or a
byte-equivalent re-implementation) and nothing else from us.

A TypedBelief is a CONSTRAINT on an entity ("deploy.target must equal staging",
"lib:boto3 is banned", "dep:numpy must satisfy >=2.0"). A ProposedAction asserts facts
about entities (it deploys to production, it imports boto3, it installs numpy 1.26).
A HALT fires iff a proposed assertion violates a CURRENT, ACTIVE, DETERMINISTIC belief.

Fence (non-negotiable #1): a belief with ``source_kind == "nl_extracted"`` is ADVISORY
and NEVER gates a halt. Only ``deterministic`` (typed) beliefs are ``halt_eligible``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Rule kinds a typed belief can impose on its entity.
RULE_EQUALS = "equals"        # the action's value for the entity must equal `value`
RULE_EXCLUDES = "excludes"    # the entity (e.g. a banned lib/pattern) must not be used
RULE_SATISFIES = "satisfies"  # the action's value must satisfy a version constraint `value`

SOURCE_DETERMINISTIC = "deterministic"
SOURCE_NL = "nl_extracted"

STATUS_ACTIVE = "active"
STATUS_SUPERSEDED = "superseded"


@dataclass(frozen=True)
class TypedBelief:
    """One current constraint on an entity, extracted from structured config."""
    belief_id: str
    entity: str                       # e.g. "deploy.target", "lib:boto3", "dep:numpy"
    rule: str                         # equals | excludes | satisfies
    value: str                        # expected value / banned marker / version constraint
    status: str = STATUS_ACTIVE       # active | superseded
    source_kind: str = SOURCE_DETERMINISTIC

    @property
    def belief_class(self) -> str:
        return "CERTIFIED" if self.source_kind == SOURCE_DETERMINISTIC else "BEST_EFFORT"

    @property
    def halt_eligible(self) -> bool:
        # Fence #1: only active, deterministic beliefs can gate a halt.
        return self.status == STATUS_ACTIVE and self.source_kind == SOURCE_DETERMINISTIC


@dataclass(frozen=True)
class ProposedAction:
    """What the agent is about to do, as assertions about entities."""
    tool: str                         # e.g. "deploy", "pip_install", "write_file"
    asserts: dict = field(default_factory=dict)  # {entity: value} the action establishes/uses
    resource: str = ""                # optional resource URN the action touches


@dataclass(frozen=True)
class Conflict:
    """The first violation found — the receipt's `decision` records this."""
    belief_id: str
    entity: str
    reason_code: str                  # SUPERSEDED_VALUE | BANNED_ENTITY | CONSTRAINT_VIOLATION
    current: str                      # the belief's required/banned/constraint value
    proposed: str                     # what the action asserted


# ── version comparison for the `satisfies` rule (minimal, deterministic) ──

def _parse_ver(s: str) -> tuple:
    out = []
    for part in str(s).strip().split("."):
        num = ""
        for ch in part:
            if "0" <= ch <= "9":          # ASCII digits only — matches the JS verifier (no Unicode digits)
                num += ch
            else:
                break
        out.append(int(num) if num else 0)
    return tuple(out)


def _ver_cmp(a: str, b: str) -> int:
    pa, pb = _parse_ver(a), _parse_ver(b)
    n = max(len(pa), len(pb))
    pa += (0,) * (n - len(pa))
    pb += (0,) * (n - len(pb))
    return (pa > pb) - (pa < pb)


def _compatible(proposed: str, constraint: str) -> bool:
    """PEP 440 compatible-release (`~=`): `proposed` must be >= `constraint` AND share its prefix
    (every component except the constraint's last must match). `~=X` with one component = `>=X`.
    e.g. `~=2.0` allows 2.5 but not 3.0; `~=2.0.1` allows 2.0.5 but not 2.1.0."""
    if _ver_cmp(proposed, constraint) < 0:
        return False
    cv = _parse_ver(constraint)
    if len(cv) < 2:
        return True
    prefix = cv[:-1]
    pv = _parse_ver(proposed)
    pv += (0,) * (len(prefix) - len(pv))
    return pv[:len(prefix)] == prefix


def _satisfies(proposed: str, constraint: str) -> bool:
    """True iff `proposed` version satisfies `constraint` (>=, >, <=, <, ==, =, ~=, bare)."""
    c = constraint.strip()
    for op in (">=", "<=", "==", "~=", ">", "<", "="):
        if c.startswith(op):
            target = c[len(op):].strip()
            if op == "~=":
                return _compatible(proposed, target)
            cmp = _ver_cmp(proposed, target)
            if op == ">=":
                return cmp >= 0
            if op == ">":
                return cmp > 0
            if op == "<=":
                return cmp <= 0
            if op == "<":
                return cmp < 0
            return cmp == 0  # == or =
    # bare version constraint → exact match
    return _ver_cmp(proposed, c) == 0


def conflict(beliefs: list, action: ProposedAction) -> Optional[Conflict]:
    """Return the FIRST conflict between the action and a current typed belief, else None.

    Deterministic and order-stable: beliefs are evaluated in the given order. NL/advisory
    and superseded beliefs are skipped (they can never gate a halt).
    """
    for b in beliefs:
        if not b.halt_eligible:
            continue
        if b.rule == RULE_EXCLUDES:
            # The banned entity is "used" if it appears as an asserted entity.
            if b.entity in action.asserts:
                return Conflict(b.belief_id, b.entity, "BANNED_ENTITY", b.value,
                                str(action.asserts.get(b.entity, "used")))
        elif b.entity in action.asserts:
            proposed = str(action.asserts[b.entity])
            if b.rule == RULE_EQUALS:
                if proposed != b.value:
                    return Conflict(b.belief_id, b.entity, "SUPERSEDED_VALUE", b.value, proposed)
            elif b.rule == RULE_SATISFIES:
                if not _satisfies(proposed, b.value):
                    return Conflict(b.belief_id, b.entity, "CONSTRAINT_VIOLATION", b.value, proposed)
    return None


def belief_to_record(b: TypedBelief) -> dict:
    """The canonical, receipt-embeddable snapshot of a belief (ordered, JSON-ready)."""
    return {
        "belief_id": b.belief_id,
        "belief_class": b.belief_class,
        "entity": b.entity,
        "rule": b.rule,
        "source_kind": b.source_kind,
        "status": b.status,
        "value": b.value,
    }


def belief_from_record(r: dict) -> TypedBelief:
    return TypedBelief(
        belief_id=r["belief_id"],
        entity=r["entity"],
        rule=r["rule"],
        value=r["value"],
        status=r.get("status", STATUS_ACTIVE),
        source_kind=r.get("source_kind", SOURCE_DETERMINISTIC),
    )


__all__ = [
    "TypedBelief", "ProposedAction", "Conflict", "conflict",
    "belief_to_record", "belief_from_record",
    "RULE_EQUALS", "RULE_EXCLUDES", "RULE_SATISFIES",
    "SOURCE_DETERMINISTIC", "SOURCE_NL", "STATUS_ACTIVE", "STATUS_SUPERSEDED",
]
