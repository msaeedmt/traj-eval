"""Step 4d free-routing: the selector routes on agents' expressed markers and
accounts for termination. Drives the closure with fakes; no LLM.
"""

from __future__ import annotations

import pytest

pytest.importorskip("autogen", reason="agents extra (ag2) not installed")

from autogen import LLMConfig  # noqa: E402

from traj_eval.agents.free_routing import (  # noqa: E402
    RoleSpec,
    RoutingConfig,
    build_free_routing_team,
    finalize_run,
)
from traj_eval.trace_core.schema import AgentRole  # noqa: E402

_DUMMY = LLMConfig({"api_type": "openai", "model": "gpt-4o-mini", "api_key": "sk-dummy"})


def _fake_check_lean(code: str) -> str:
    "Check Lean."
    return "ok"


# Reasoner -> engineer; engineer -> {critic, reasoner} + check_lean; critic ->
# {engineer} + terminate. The triangle from the design discussion.
def _config():
    return RoutingConfig(
        entry=AgentRole.REASONER,
        roles={
            AgentRole.REASONER: RoleSpec(
                AgentRole.REASONER, handoff_targets=frozenset({AgentRole.ENGINEER})
            ),
            AgentRole.ENGINEER: RoleSpec(
                AgentRole.ENGINEER,
                handoff_targets=frozenset({AgentRole.CRITIC, AgentRole.REASONER}),
                tools=frozenset({"check_lean"}),
            ),
            AgentRole.CRITIC: RoleSpec(
                AgentRole.CRITIC,
                handoff_targets=frozenset({AgentRole.ENGINEER}),
                tools=frozenset({"check_lean"}),
                can_terminate=True,
            ),
        },
        max_turns=20,
        max_consecutive_invalid=3,
    )


class _Speaker:
    def __init__(self, name):
        self.name = name


def _build():
    cfg = _config()
    from traj_eval.agents.roles import make_critic, make_engineer, make_reasoner

    agents = {
        AgentRole.REASONER: make_reasoner(_DUMMY),
        AgentRole.ENGINEER: make_engineer(_DUMMY),
        AgentRole.CRITIC: make_critic(_DUMMY),
    }
    m, user, gc, state = build_free_routing_team(
        _DUMMY, config=cfg, agents=agents, tools={"check_lean": _fake_check_lean}
    )
    return gc, state


def _set(gc, name, content):
    gc.messages = gc.messages + [{"name": name, "content": content}]


def test_entry_routes_to_reasoner():
    gc, state = _build()
    sel = gc.speaker_selection_method
    nxt = sel(_Speaker("user"), gc)
    assert nxt.name == AgentRole.REASONER.value


def test_valid_handoff_routes():
    gc, state = _build()
    sel = gc.speaker_selection_method
    _set(gc, AgentRole.REASONER.value, "strategy ready.\nHANDOFF: engineer")
    nxt = sel(_Speaker(AgentRole.REASONER.value), gc)
    assert nxt.name == AgentRole.ENGINEER.value
    assert state.invalid_handoffs == 0


def test_tool_request_routes_to_executor():
    gc, state = _build()
    sel = gc.speaker_selection_method
    # native AG2 tool call (has tool_calls), not a TOOL: text marker
    gc.messages = gc.messages + [
        {
            "name": AgentRole.ENGINEER.value,
            "content": None,
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "check_lean", "arguments": "{}"},
                }
            ],
        }
    ]
    nxt = sel(_Speaker(AgentRole.ENGINEER.value), gc)
    assert nxt.name == AgentRole.EXECUTOR.value


def test_disallowed_tool_is_invalid():
    gc, state = _build()
    sel = gc.speaker_selection_method
    # reasoner may only call search_lemmas; calling check_lean is disallowed
    gc.messages = gc.messages + [
        {
            "name": AgentRole.REASONER.value,
            "content": None,
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "check_lean", "arguments": "{}"},
                }
            ],
        }
    ]
    sel(_Speaker(AgentRole.REASONER.value), gc)
    assert state.invalid_handoffs == 1


def test_disallowed_handoff_is_invalid_and_falls_back():
    gc, state = _build()
    sel = gc.speaker_selection_method
    # reasoner may only hand to engineer; handing to critic is disallowed
    _set(gc, AgentRole.REASONER.value, "skipping ahead.\nHANDOFF: critic")
    nxt = sel(_Speaker(AgentRole.REASONER.value), gc)
    assert state.invalid_handoffs == 1
    assert nxt.name == AgentRole.REASONER.value  # fallback to entry


def test_missing_marker_is_invalid():
    gc, state = _build()
    sel = gc.speaker_selection_method
    _set(gc, AgentRole.ENGINEER.value, "I rambled and forgot to hand off.")
    sel(_Speaker(AgentRole.ENGINEER.value), gc)
    assert state.invalid_handoffs == 1


def test_terminal_marker_ends_clean():
    gc, state = _build()
    sel = gc.speaker_selection_method
    _set(gc, AgentRole.CRITIC.value, "Looks faithful.\nVERDICT: APPROVE")
    nxt = sel(_Speaker(AgentRole.CRITIC.value), gc)
    assert nxt is None
    assert state.terminated and state.reason == "clean"


def test_stuck_after_consecutive_invalid():
    gc, state = _build()
    sel = gc.speaker_selection_method
    for _ in range(3):
        _set(gc, AgentRole.ENGINEER.value, "no marker")
        sel(_Speaker(AgentRole.ENGINEER.value), gc)
    assert state.terminated and state.reason == "stuck"


def test_cap_terminates():
    gc, state = _build()
    sel = gc.speaker_selection_method
    # drive turns up to the cap with valid hand-offs
    for _ in range(25):
        spk = AgentRole.REASONER.value
        _set(gc, spk, "HANDOFF: engineer")
        nxt = sel(_Speaker(spk), gc)
        if nxt is None:
            break
    assert state.terminated and state.reason == "cap"


def test_finalize_backfills_cap_reason():
    # A run that ended without our selector setting a reason (i.e. AG2's own
    # max_round stopped it) must be recorded as 'cap', never left None.
    _, state = _build()
    assert state.reason is None
    finalize_run(state)
    assert state.terminated and state.reason == "cap"


def test_finalize_preserves_existing_reason():
    _, state = _build()
    state.terminated, state.reason = True, "clean"
    finalize_run(state)
    assert state.reason == "clean"  # not overwritten
