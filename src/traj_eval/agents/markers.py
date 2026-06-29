"""Machine-readable role markers and a minimal decision parser (Step 2c; 4d).

The role prompts end their messages with a marked line so downstream code can
read the outcome without re-grepping prose:

    engineer  -> FINAL: <answer>
    critic    -> VERDICT: APPROVE   |  VERDICT: REJECT - <reason>
    executor  -> EXECUTION: OK - <answer>  |  EXECUTION: FAIL - <detail>

Free-routing markers (Step 4d): under agent-chosen routing, an agent ends its
message by naming who acts next, or which tool to run:

    HANDOFF: <agent_role>     -- hand control to another agent
    TOOL: <tool_name>         -- request a tool call (the controller routes to
                                 the executor, which runs it)

These are how coordination becomes a *measured choice*: the controller routes on
the expressed target, and the gap between what an agent is ALLOWED to reach and
what it actually names is a coordination signal. Parsing lives here (the single
source of truth for marker strings); validating a target against an agent's
allowed set is the controller's job, not this module's.

This module is substrate-agnostic: it knows marker grammar, not Lean. Minimal by
design -- it extracts the decision / handoff target / tool name, not the full
payload.
"""

from __future__ import annotations

import re

from traj_eval.trace_core.schema import AgentRole

# Verdict markers (also used by the selector to route critic -> {executor|engineer}).
VERDICT_APPROVE = "VERDICT: APPROVE"
VERDICT_REJECT = "VERDICT: REJECT"

# Executor markers.
EXECUTION_OK = "EXECUTION: OK"
EXECUTION_FAIL = "EXECUTION: FAIL"

# Engineer submission marker.
FINAL = "FINAL:"

# Free-routing markers (4d).
HANDOFF = "HANDOFF:"
TOOL = "TOOL:"

# A handoff/tool marker line: the keyword, then the target token (a role name or
# tool name). Case-insensitive; tolerant of surrounding whitespace.
_HANDOFF_RE = re.compile(r"HANDOFF:\s*([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)
_TOOL_RE = re.compile(r"TOOL:\s*([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)


def parse_handoff(text: str) -> dict[str, object]:
    """Extract an expressed handoff or tool request from a message, or {}.

    Returns at most one of:
      {"tool_request": "<tool>"}    -- agent requested a tool call
      {"handoff_target": "<role>"}  -- agent named who acts next
    A TOOL request takes precedence if both appear (a tool call is the more
    immediate action). The target is lowercased for a stable match against
    role/tool names; validity is judged by the controller, not here.
    """
    text = text or ""
    m_tool = _TOOL_RE.search(text)
    if m_tool:
        return {"tool_request": m_tool.group(1).lower()}
    m_hand = _HANDOFF_RE.search(text)
    if m_hand:
        return {"handoff_target": m_hand.group(1).lower()}
    return {}


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
