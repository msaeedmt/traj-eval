"""Machine-readable role markers and a minimal decision parser (Step 2c).

The role prompts end their messages with a marked line so downstream code can
read the outcome without re-grepping prose:

    engineer  -> FINAL: <answer>
    critic    -> VERDICT: APPROVE   |  VERDICT: REJECT - <reason>
    executor  -> EXECUTION: OK - <answer>  |  EXECUTION: FAIL - <detail>

This module is the single source of truth for the marker strings. The selector
(group_chat) imports the verdict constants to route on; the observer imports
``parse_decision`` to stamp a structured ``decision`` field onto each event.

Minimal by design: this extracts only the *decision* (approve/reject, ok/fail)
and a flag that the engineer submitted a FINAL. The richer extraction of the
marker payload (the answer value, the reject reason, the failure detail) is
deferred until the anchor-validation design specifies what fields it needs.
"""

from __future__ import annotations

from traj_eval.trace_core.schema import AgentRole

# Verdict markers (also used by the selector to route critic -> {executor|engineer}).
VERDICT_APPROVE = "VERDICT: APPROVE"
VERDICT_REJECT = "VERDICT: REJECT"

# Executor markers.
EXECUTION_OK = "EXECUTION: OK"
EXECUTION_FAIL = "EXECUTION: FAIL"

# Engineer submission marker.
FINAL = "FINAL:"


def parse_decision(role: AgentRole, text: str) -> dict[str, object]:
    """Return minimal structured fields for a role's marker, or {} if none.

    Matching is case-insensitive and tolerant of surrounding whitespace, since
    the markers are emitted by an LLM and occasionally indented or re-cased.
    Only the decision is extracted (2c minimal scope).
    """
    upper = text.upper()

    if role is AgentRole.CRITIC:
        # Check REJECT before APPROVE is irrelevant (distinct strings), but be
        # explicit so a message mentioning both words in prose can't confuse us:
        # we key only off the marker line tokens.
        if VERDICT_APPROVE in upper:
            return {"decision": "approve"}
        if VERDICT_REJECT in upper:
            return {"decision": "reject"}
        return {}

    if role is AgentRole.EXECUTOR:
        if EXECUTION_OK in upper:
            return {"decision": "ok"}
        if EXECUTION_FAIL in upper:
            return {"decision": "fail"}
        return {}

    if role is AgentRole.ENGINEER:
        if FINAL in upper:
            return {"has_final": True}
        return {}

    return {}
