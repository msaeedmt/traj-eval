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

_DUMMY = LLMConfig(
    {"api_type": "openai", "model": "gpt-4o-mini", "api_key": "test-placeholder"}
)


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


def _build_tool_routing(post_tool_route=None):
    from traj_eval.agents.roles import make_critic, make_engineer, make_reasoner

    cfg = RoutingConfig(
        entry=AgentRole.REASONER,
        roles={
            AgentRole.REASONER: RoleSpec(
                AgentRole.REASONER,
                handoff_targets=frozenset({AgentRole.ENGINEER}),
                tools=frozenset({"route_next_agent"}),
            ),
            AgentRole.ENGINEER: RoleSpec(
                AgentRole.ENGINEER,
                handoff_targets=frozenset({AgentRole.REASONER, AgentRole.CRITIC}),
                tools=frozenset({"check_lean", "route_next_agent"}),
            ),
            AgentRole.CRITIC: RoleSpec(
                AgentRole.CRITIC,
                handoff_targets=frozenset({AgentRole.ENGINEER}),
                tools=frozenset({"finish_run"}),
                can_terminate=True,
            ),
        },
        max_turns=20,
        max_failed_compiles=0,
        allow_marker_handoffs=False,
        allow_terminal_markers=False,
        tool_result_routing=True,
    )
    agents = {
        AgentRole.REASONER: make_reasoner(_DUMMY),
        AgentRole.ENGINEER: make_engineer(_DUMMY),
        AgentRole.CRITIC: make_critic(_DUMMY),
    }

    def route_next_agent(target: str, reason: str):
        return {"ok": True, "handoff_target": target, "reason": reason}

    def finish_run():
        return {"ok": True, "run_complete": True}

    _, _, gc, state = build_free_routing_team(
        _DUMMY,
        config=cfg,
        agents=agents,
        tools={
            "check_lean": _fake_check_lean,
            "route_next_agent": route_next_agent,
            "finish_run": finish_run,
        },
        post_tool_route=post_tool_route,
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


def test_engineer_can_handoff_back_to_reasoner():
    gc, state = _build()
    sel = gc.speaker_selection_method
    _set(gc, AgentRole.ENGINEER.value, "strategy appears wrong.\nHANDOFF: reasoner")
    nxt = sel(_Speaker(AgentRole.ENGINEER.value), gc)
    assert nxt.name == AgentRole.REASONER.value
    assert state.invalid_handoffs == 0


def test_critic_can_send_back_to_engineer():
    gc, state = _build()
    sel = gc.speaker_selection_method
    _set(gc, AgentRole.CRITIC.value, "proof does not match the task.\nHANDOFF: engineer")
    nxt = sel(_Speaker(AgentRole.CRITIC.value), gc)
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


def test_finalize_distinguishes_early_framework_stop():
    _, state = _build()
    assert state.reason is None
    finalize_run(state)
    assert state.terminated and state.reason == "framework_stop"


def test_finalize_backfills_cap_after_turn_budget():
    _, state = _build()
    state.turns = state.turn_budget
    finalize_run(state)
    assert state.terminated and state.reason == "cap"


def test_finalize_preserves_existing_reason():
    _, state = _build()
    state.terminated, state.reason = True, "clean"
    finalize_run(state)
    assert state.reason == "clean"  # not overwritten


def _tool_msg(name, code):
    import json

    return {
        "name": name,
        "content": None,
        "tool_calls": [
            {
                "id": "c",
                "type": "function",
                "function": {"name": "check_lean", "arguments": json.dumps({"code": code})},
            }
        ],
    }


def test_perseveration_bound_terminates_stuck():
    gc, state = _build()
    sel = gc.speaker_selection_method
    bad = "import Mathlib\ntheorem t := by rw [Nat.add_succ, ih]"
    # default max_identical_calls=4: the 4th identical submission trips 'stuck'
    results = []
    for _ in range(5):
        gc.messages = gc.messages + [_tool_msg(AgentRole.ENGINEER.value, bad)]
        results.append(sel(_Speaker(AgentRole.ENGINEER.value), gc))
    assert state.terminated and state.reason == "stuck"
    assert state.max_identical_calls_seen >= 4
    # once stuck, the selector returned None (no next speaker)
    assert results[-1] is None


def test_distinct_calls_do_not_trip_bound():
    gc, state = _build()
    sel = gc.speaker_selection_method
    for i in range(5):
        gc.messages = gc.messages + [_tool_msg(AgentRole.ENGINEER.value, f"attempt number {i}")]
        nxt = sel(_Speaker(AgentRole.ENGINEER.value), gc)
        assert nxt.name == AgentRole.EXECUTOR.value  # each routes to executor
    assert state.reason != "stuck"
    assert state.consecutive_identical_calls == 1  # last one was unique


def _exec_result(compiled):
    # an executor tool-result message carrying a check_lean verdict (repr dict)
    d = {"compiled": compiled, "sorry_free": True, "n_sorries": 0, "summary": "x"}
    return {
        "name": AgentRole.EXECUTOR.value,
        "content": None,
        "tool_responses": [{"id": "c", "content": repr(d)}],
        "text": repr(d),
    }


def _dict_result(value):
    return {
        "name": AgentRole.EXECUTOR.value,
        "content": None,
        "tool_responses": [{"id": "c", "content": repr(value)}],
    }


def _json_result(value):
    import json

    return {
        "name": AgentRole.EXECUTOR.value,
        "content": None,
        "tool_responses": [{"id": "c", "content": json.dumps(value)}],
    }


def test_tool_result_routes_to_requested_agent():
    gc, state = _build_tool_routing()
    sel = gc.speaker_selection_method
    gc.messages = gc.messages + [
        _tool_msg(AgentRole.REASONER.value, "route"),
        _dict_result(
            {
                "ok": True,
                "handoff_target": "engineer",
                "route_kind": "agent_tool_handoff",
            }
        ),
    ]

    nxt = sel(_Speaker(AgentRole.EXECUTOR.value), gc)

    assert nxt.name == AgentRole.ENGINEER.value
    assert state.tool_handoffs == 1


def test_json_tool_result_routes_to_requested_agent():
    gc, state = _build_tool_routing()
    sel = gc.speaker_selection_method
    gc.messages = gc.messages + [
        _tool_msg(AgentRole.REASONER.value, "route"),
        _json_result({"ok": True, "handoff_target": "engineer"}),
    ]

    nxt = sel(_Speaker(AgentRole.EXECUTOR.value), gc)

    assert nxt.name == AgentRole.ENGINEER.value
    assert state.tool_handoffs == 1


def test_malformed_tool_json_stops_without_replaying_broken_assistant_prefill():
    gc, state = _build_tool_routing()
    sel = gc.speaker_selection_method
    gc.messages = gc.messages + [
        _tool_msg(AgentRole.REASONER.value, "broken call"),
        {
            "name": AgentRole.EXECUTOR.value,
            "content": "Error: Unterminated string. The argument must be in JSON format.",
            "tool_responses": [
                {
                    "id": "c",
                    "content": "Error: Unterminated string. The argument must be in JSON format.",
                }
            ],
        },
    ]

    nxt = sel(_Speaker(AgentRole.EXECUTOR.value), gc)

    assert nxt is None
    assert state.terminated and state.reason == "stuck"
    assert state.tool_protocol_errors == 1


def test_post_tool_fallback_routes_visibly_after_tool_result():
    def fallback(role, called):
        if role is AgentRole.REASONER and "route_next_agent" in called:
            return AgentRole.ENGINEER, "controller_plan_ready_fallback"
        return None

    gc, state = _build_tool_routing(post_tool_route=fallback)
    sel = gc.speaker_selection_method
    call = {
        "name": AgentRole.REASONER.value,
        "content": None,
        "tool_calls": [
            {
                "id": "route",
                "type": "function",
                "function": {
                    "name": "route_next_agent",
                    "arguments": '{"target":"engineer","reason":"ready"}',
                },
            }
        ],
    }
    gc.messages = gc.messages + [call]
    assert sel(_Speaker(AgentRole.REASONER.value), gc).name == AgentRole.EXECUTOR.value
    gc.messages = gc.messages + [_dict_result({"ok": True})]

    nxt = sel(_Speaker(AgentRole.EXECUTOR.value), gc)

    assert nxt.name == AgentRole.ENGINEER.value
    assert state.controller_fallback_routes == 1
    assert state.tool_handoffs == 1


def test_explicit_tool_target_wins_over_controller_fallback():
    def fallback(role, called):
        if role is AgentRole.ENGINEER and "check_lean" in called:
            return AgentRole.REASONER, "controller_fallback"
        return None

    gc, state = _build_tool_routing(post_tool_route=fallback)
    sel = gc.speaker_selection_method
    gc.messages = gc.messages + [_tool_msg(AgentRole.ENGINEER.value, "proof")]
    assert sel(_Speaker(AgentRole.ENGINEER.value), gc).name == AgentRole.EXECUTOR.value
    gc.messages = gc.messages + [
        _dict_result({"ok": True, "handoff_target": "critic"})
    ]

    nxt = sel(_Speaker(AgentRole.EXECUTOR.value), gc)

    assert nxt.name == AgentRole.CRITIC.value
    assert state.tool_handoffs == 1
    assert state.controller_fallback_routes == 0


def test_completion_denial_suppresses_controller_fallback():
    def fallback(role, called):
        if role is AgentRole.REASONER:
            return AgentRole.ENGINEER, "controller_fallback"
        return None

    gc, state = _build_tool_routing(post_tool_route=fallback)
    sel = gc.speaker_selection_method
    call = {
        "name": AgentRole.REASONER.value,
        "content": None,
        "tool_calls": [
            {
                "id": "route",
                "type": "function",
                "function": {
                    "name": "route_next_agent",
                    "arguments": '{"target":"engineer","reason":"ready"}',
                },
            }
        ],
    }
    gc.messages = gc.messages + [call]
    assert sel(_Speaker(AgentRole.REASONER.value), gc).name == AgentRole.EXECUTOR.value
    gc.messages = gc.messages + [_dict_result({"ok": False, "error": "gate denied"})]

    nxt = sel(_Speaker(AgentRole.EXECUTOR.value), gc)

    assert nxt.name == AgentRole.REASONER.value
    assert state.completion_gate_denials == 1
    assert state.controller_fallback_routes == 0


def test_invalid_controller_fallback_counts_as_invalid_route():
    def fallback(role, called):
        return AgentRole.CRITIC, "invalid_for_reasoner"

    gc, state = _build_tool_routing(post_tool_route=fallback)
    sel = gc.speaker_selection_method
    call = {
        "name": AgentRole.REASONER.value,
        "content": None,
        "tool_calls": [
            {
                "id": "route",
                "type": "function",
                "function": {
                    "name": "route_next_agent",
                    "arguments": '{"target":"engineer","reason":"ready"}',
                },
            }
        ],
    }
    gc.messages = gc.messages + [call]
    assert sel(_Speaker(AgentRole.REASONER.value), gc).name == AgentRole.EXECUTOR.value
    gc.messages = gc.messages + [_dict_result({"ok": True})]

    nxt = sel(_Speaker(AgentRole.EXECUTOR.value), gc)

    assert nxt.name == AgentRole.REASONER.value
    assert state.invalid_handoffs == 1
    assert state.controller_fallback_routes == 0


def test_orphan_executor_result_does_not_reuse_a_caller():
    gc, state = _build()
    sel = gc.speaker_selection_method
    gc.messages = gc.messages + [_exec_result(False)]

    nxt = sel(_Speaker(AgentRole.EXECUTOR.value), gc)

    assert nxt.name == AgentRole.REASONER.value
    assert state.invalid_handoffs == 1
    assert state.consecutive_failed_compiles == 0


def test_duplicate_executor_result_cannot_reuse_previous_tool_caller():
    gc, state = _build()
    sel = gc.speaker_selection_method
    gc.messages = gc.messages + [
        _tool_msg(AgentRole.ENGINEER.value, "proof"),
        _exec_result(False),
    ]
    assert sel(_Speaker(AgentRole.EXECUTOR.value), gc).name == AgentRole.ENGINEER.value
    assert state.consecutive_failed_compiles == 1
    gc.messages = gc.messages + [_exec_result(False)]

    nxt = sel(_Speaker(AgentRole.EXECUTOR.value), gc)

    assert nxt.name == AgentRole.REASONER.value
    assert state.invalid_handoffs == 1
    assert state.consecutive_failed_compiles == 1


def test_failed_compile_tool_result_forces_reasoner_recovery():
    gc, state = _build_tool_routing()
    sel = gc.speaker_selection_method
    gc.messages = gc.messages + [
        _tool_msg(AgentRole.ENGINEER.value, "bad proof"),
        _dict_result(
            {
                "compiled": False,
                "handoff_target": "reasoner",
                "route_kind": "failed_compile_recovery",
            }
        ),
    ]

    nxt = sel(_Speaker(AgentRole.EXECUTOR.value), gc)

    assert nxt.name == AgentRole.REASONER.value
    assert state.forced_recoveries == 1


def test_tool_completion_terminates_without_text_verdict():
    gc, state = _build_tool_routing()
    sel = gc.speaker_selection_method
    gc.messages = gc.messages + [
        {
            "name": AgentRole.CRITIC.value,
            "content": None,
            "tool_calls": [
                {
                    "id": "c",
                    "type": "function",
                    "function": {"name": "finish_run", "arguments": "{}"},
                }
            ],
        },
        _dict_result({"ok": True, "run_complete": True}),
    ]

    assert sel(_Speaker(AgentRole.EXECUTOR.value), gc) is None
    assert state.terminated and state.reason == "clean"


def test_marker_handoff_is_rejected_in_tool_mode():
    gc, state = _build_tool_routing()
    sel = gc.speaker_selection_method
    _set(gc, AgentRole.REASONER.value, "HANDOFF: engineer")

    nxt = sel(_Speaker(AgentRole.REASONER.value), gc)

    assert state.invalid_handoffs == 1
    assert nxt.name == AgentRole.REASONER.value


def test_non_linear_free_routing_loop_is_possible():
    gc, state = _build()
    sel = gc.speaker_selection_method

    observed = []

    _set(gc, AgentRole.REASONER.value, "initial proof strategy.\nHANDOFF: engineer")
    observed.append(sel(_Speaker(AgentRole.REASONER.value), gc).name)

    gc.messages = gc.messages + [_tool_msg(AgentRole.ENGINEER.value, "bad attempt")]
    observed.append(sel(_Speaker(AgentRole.ENGINEER.value), gc).name)

    gc.messages = gc.messages + [_exec_result(False)]
    observed.append(sel(_Speaker(AgentRole.EXECUTOR.value), gc).name)

    _set(gc, AgentRole.ENGINEER.value, "the strategy needs revision.\nHANDOFF: reasoner")
    observed.append(sel(_Speaker(AgentRole.ENGINEER.value), gc).name)

    _set(gc, AgentRole.REASONER.value, "revised proof strategy.\nHANDOFF: engineer")
    observed.append(sel(_Speaker(AgentRole.REASONER.value), gc).name)

    _set(gc, AgentRole.ENGINEER.value, "proof now compiles.\nHANDOFF: critic")
    observed.append(sel(_Speaker(AgentRole.ENGINEER.value), gc).name)

    _set(gc, AgentRole.CRITIC.value, "statement mismatch.\nHANDOFF: engineer")
    observed.append(sel(_Speaker(AgentRole.CRITIC.value), gc).name)

    _set(gc, AgentRole.ENGINEER.value, "fixed final proof.\nHANDOFF: critic")
    observed.append(sel(_Speaker(AgentRole.ENGINEER.value), gc).name)

    _set(gc, AgentRole.CRITIC.value, "faithful and verified.\nVERDICT: APPROVE")
    observed.append(sel(_Speaker(AgentRole.CRITIC.value), gc))

    assert observed == [
        AgentRole.ENGINEER.value,
        AgentRole.EXECUTOR.value,
        AgentRole.ENGINEER.value,
        AgentRole.REASONER.value,
        AgentRole.ENGINEER.value,
        AgentRole.CRITIC.value,
        AgentRole.ENGINEER.value,
        AgentRole.CRITIC.value,
        None,
    ]
    assert state.invalid_handoffs == 0
    assert state.terminated and state.reason == "clean"


def test_no_progress_bound_terminates_stuck():
    gc, state = _build()
    sel = gc.speaker_selection_method
    # 6 consecutive failed compiles (default max_failed_compiles=6) -> stuck.
    result = None
    for attempt in range(6):
        gc.messages = gc.messages + [
            _tool_msg(AgentRole.ENGINEER.value, f"attempt {attempt}"),
            _exec_result(False),
        ]
        result = sel(_Speaker(AgentRole.EXECUTOR.value), gc)
    assert state.terminated and state.reason == "stuck"
    assert state.max_failed_compiles_seen >= 6
    assert result is None


def test_success_resets_no_progress_counter():
    gc, state = _build()
    sel = gc.speaker_selection_method
    # 5 failures, then a success, then 5 more: never hits 6 in a row -> not stuck
    for attempt in range(5):
        gc.messages = gc.messages + [
            _tool_msg(AgentRole.ENGINEER.value, f"before success {attempt}"),
            _exec_result(False),
        ]
        sel(_Speaker(AgentRole.EXECUTOR.value), gc)
    gc.messages = gc.messages + [
        _tool_msg(AgentRole.ENGINEER.value, "successful attempt"),
        _exec_result(True),
    ]
    sel(_Speaker(AgentRole.EXECUTOR.value), gc)
    assert state.consecutive_failed_compiles == 0
    for attempt in range(5):
        gc.messages = gc.messages + [
            _tool_msg(AgentRole.ENGINEER.value, f"after success {attempt}"),
            _exec_result(False),
        ]
        sel(_Speaker(AgentRole.EXECUTOR.value), gc)
    assert state.reason != "stuck"


def test_search_result_does_not_count_as_failed_compile():
    gc, state = _build()
    sel = gc.speaker_selection_method
    # a search_lemmas result has no 'compiled' key -> must not increment
    search_msg = {
        "name": AgentRole.EXECUTOR.value,
        "content": None,
        "tool_responses": [{"id": "s", "content": "Top matches (name ...)"}],
        "text": "Top matches (name ...)",
    }
    for attempt in range(8):
        search_call = {
            "name": AgentRole.ENGINEER.value,
            "content": None,
            "tool_calls": [
                {
                    "id": "s",
                    "type": "function",
                    "function": {
                        "name": "search_lemmas",
                        "arguments": f'{{"query": "attempt {attempt}"}}',
                    },
                }
            ],
        }
        gc.messages = gc.messages + [search_call, search_msg]
        sel(_Speaker(AgentRole.EXECUTOR.value), gc)
    assert state.consecutive_failed_compiles == 0
    assert state.reason != "stuck"
