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
    make_key_progress_verdict,
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


def test_no_progress_bound_terminates_stuck():
    gc, state = _build()
    sel = gc.speaker_selection_method
    # 6 consecutive verifier rejections (default max_no_progress=6) -> stuck.
    result = None
    for _ in range(6):
        gc.messages = gc.messages + [_exec_result(False)]
        result = sel(_Speaker(AgentRole.EXECUTOR.value), gc)
    assert state.terminated and state.reason == "stuck"
    assert state.max_no_progress_seen >= 6
    assert result is None


def test_success_resets_no_progress_counter():
    gc, state = _build()
    sel = gc.speaker_selection_method
    # 5 failures, then a success, then 5 more: never hits 6 in a row -> not stuck
    for _ in range(5):
        gc.messages = gc.messages + [_exec_result(False)]
        sel(_Speaker(AgentRole.EXECUTOR.value), gc)
    gc.messages = gc.messages + [_exec_result(True)]
    sel(_Speaker(AgentRole.EXECUTOR.value), gc)
    assert state.consecutive_no_progress == 0
    for _ in range(5):
        gc.messages = gc.messages + [_exec_result(False)]
        sel(_Speaker(AgentRole.EXECUTOR.value), gc)
    assert state.reason != "stuck"


def test_search_result_does_not_count_as_no_progress():
    gc, state = _build()
    sel = gc.speaker_selection_method
    # a search_lemmas result has no 'compiled' key, so the verdict is None ->
    # must not increment. Exploration is not thrashing.
    search_msg = {
        "name": AgentRole.EXECUTOR.value,
        "content": None,
        "tool_responses": [{"id": "s", "content": "Top matches (name ...)"}],
        "text": "Top matches (name ...)",
    }
    for _ in range(8):
        gc.messages = gc.messages + [search_msg]
        sel(_Speaker(AgentRole.EXECUTOR.value), gc)
    assert state.consecutive_no_progress == 0
    assert state.reason != "stuck"


# --- the progress-verdict seam (domain-adaptable no-progress bound) ----------
#
# The no-progress bound is framework-agnostic; only WHICH tool result counts as
# "the verifier accepted" is the domain's business. Lean reads check_lean's
# ``compiled``; astro's tools return a uniform ``ok``. Keeping the machinery
# identical and varying one key is what makes cross-regime comparison of
# structural signatures (RQ iii) a measurement rather than two hand-tuned
# heuristics. These tests pin that seam directly on RoutingConfig -- no group
# chat needed, since read_progress is pure.


def _verifier_result(payload: dict) -> dict:
    """An executor result carrying one tool response. ag2 repr()s the dict."""
    return {"tool_responses": [{"id": "t", "content": repr(payload)}]}


def test_default_verdict_reads_the_lean_key() -> None:
    """A config that sets no verdict keeps Lean's behaviour unchanged."""
    config = RoutingConfig(entry=AgentRole.REASONER)
    assert config.progress_verdict is None
    assert config.read_progress(_verifier_result({"compiled": True})) is True
    assert config.read_progress(_verifier_result({"compiled": False})) is False


def test_custom_verdict_reads_its_own_key_and_not_leans() -> None:
    """An astro-style config keys on 'ok' and ignores Lean's key entirely."""
    config = RoutingConfig(
        entry=AgentRole.PLANNER, progress_verdict=make_key_progress_verdict("ok")
    )
    assert config.read_progress(_verifier_result({"ok": True, "rms_ms": 1.2})) is True
    assert config.read_progress(_verifier_result({"ok": False, "error": "no convergence"})) is False
    # Lean's key must be invisible to an astro config, or the two domains would
    # silently share a bound while measuring different things.
    assert config.read_progress(_verifier_result({"compiled": False})) is None


def test_non_verifier_results_return_none() -> None:
    """None is load-bearing: exploration must not count toward the bound.

    A tool that is not the domain's verifier (Lean's search_lemmas, astro's
    periodogram) yields None, so raw retries are not scored as thrashing -- the
    proposal treats retry counts as a hypothesis to test, not a failure signal.
    """
    lean = RoutingConfig(entry=AgentRole.REASONER)
    astro = RoutingConfig(entry=AgentRole.PLANNER, progress_verdict=make_key_progress_verdict("ok"))
    assert lean.read_progress(_verifier_result({"results": ["Nat.add_comm"]})) is None
    assert astro.read_progress(_verifier_result({"peaks_days": [5.28, 2.64]})) is None


@pytest.mark.parametrize(
    "message",
    [
        {},  # no tool_responses at all
        {"tool_responses": []},  # empty list
        {"tool_responses": [{"id": "t", "content": ""}]},  # empty content
        {"tool_responses": [{"id": "t", "content": "not a dict("}]},  # unparseable
        {"tool_responses": [{"id": "t", "content": "[1, 2, 3]"}]},  # parses, not a dict
    ],
)
def test_malformed_results_are_ignored_not_counted(message: dict) -> None:
    """A malformed tool result must never be read as a rejection.

    Counting it would let a transport hiccup masquerade as agent thrashing and
    terminate a healthy run as 'stuck'.
    """
    config = RoutingConfig(entry=AgentRole.REASONER)
    assert config.read_progress(message) is None


def test_first_matching_response_wins_across_multiple_tools() -> None:
    """One turn can carry several tool responses; the verdict reads the verifier."""
    config = RoutingConfig(entry=AgentRole.REASONER)
    message = {
        "tool_responses": [
            {"id": "a", "content": repr({"results": ["Nat.add_comm"]})},
            {"id": "b", "content": repr({"compiled": False, "errors": ["unknown id"]})},
        ]
    }
    assert config.read_progress(message) is False
