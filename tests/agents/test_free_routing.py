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
def _config(**overrides):
    kwargs = {
        "entry": AgentRole.REASONER,
        "roles": {
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
        "max_turns": 20,
        "max_consecutive_invalid": 3,
    }
    kwargs.update(overrides)
    return RoutingConfig(**kwargs)


class _Speaker:
    def __init__(self, name):
        self.name = name


def _build(**overrides):
    cfg = _config(**overrides)
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
    # 25 hand-offs with no tool call is precisely what the idle bound catches,
    # so disable it here: this test is about the TURN CAP.
    gc, state = _build(max_idle_messages=None)
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
    # 6 consecutive failed compiles (default max_failed_compiles=6) -> stuck.
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
    for _ in range(8):
        gc.messages = gc.messages + [search_msg]
        sel(_Speaker(AgentRole.EXECUTOR.value), gc)
    assert state.consecutive_no_progress == 0
    assert state.reason != "stuck"


# --- idle bound: stop when work circulates but nothing is done ---------------
#
# The other two bounds key on TOOL CALLS, so a team that stops calling tools is
# invisible to them. On seed22_diff4_t0 the run ended with 21 consecutive agent
# messages and no tool call, stopped only by the turn cap, with 4 of 5
# submissions unused. Across 145 trials no SUCCESSFUL run exceeded 4 consecutive
# idle messages (median 1); failures reached 27 (median 6). Hence a default of 6.


def _idle_gc(**overrides):
    gc, state = _build(**overrides)
    return gc, state, gc.speaker_selection_method


def _say(gc, role, text):
    gc.messages = gc.messages + [{"name": role.value, "content": text, "text": text}]
    return gc.speaker_selection_method(_Speaker(role.value), gc)


def test_idle_bound_stops_a_handoff_loop() -> None:
    """The seed22 shape: perfect hand-offs, no tool calls, forever."""
    gc, state, _ = _idle_gc()
    roles = [AgentRole.ENGINEER, AgentRole.CRITIC]
    for i in range(6):
        _say(gc, roles[i % 2], f"Thinking.\nHANDOFF: {roles[(i + 1) % 2].value}")
    assert state.terminated
    assert state.reason == "stuck_idle"
    assert state.max_idle_messages_seen >= 6


def test_a_tool_call_resets_the_idle_counter() -> None:
    """Healthy interleaving must never trip the bound.

    This is the safety property the threshold was chosen for: across 145 trials
    no successful run exceeded 4 consecutive idle messages, so cutting a healthy
    run would convert successes into recorded failures.
    """
    # Each iteration costs two turns, so raise the cap: this test is about the
    # idle bound, not the turn cap.
    gc, state, _ = _idle_gc(max_turns=60)
    for i in range(10):
        _say(gc, AgentRole.ENGINEER, "Thinking.\nHANDOFF: critic")
        gc.messages = gc.messages + [_tool_msg(AgentRole.ENGINEER.value, f"theorem t{i} := by rfl")]
        gc.speaker_selection_method(_Speaker(AgentRole.ENGINEER.value), gc)
    assert not state.terminated
    assert state.max_idle_messages_seen <= 1


def test_the_idle_counter_resets_rather_than_accumulating() -> None:
    """Five idle messages, a tool call, five more: never six in a row."""
    gc, state, _ = _idle_gc()
    for _ in range(5):
        _say(gc, AgentRole.ENGINEER, "Thinking.\nHANDOFF: critic")
    assert not state.terminated
    gc.messages = gc.messages + [_tool_msg(AgentRole.ENGINEER.value, "theorem t := by rfl")]
    gc.speaker_selection_method(_Speaker(AgentRole.ENGINEER.value), gc)
    assert state.consecutive_idle_messages == 0
    for _ in range(5):
        _say(gc, AgentRole.ENGINEER, "Thinking.\nHANDOFF: critic")
    assert not state.terminated


def test_a_terminal_verdict_is_not_idle() -> None:
    """Messages leading to a deliberate stop were going somewhere."""
    gc, state, _ = _idle_gc()
    for _ in range(4):
        _say(gc, AgentRole.ENGINEER, "Thinking.\nHANDOFF: critic")
    _say(gc, AgentRole.CRITIC, "Verified.\nVERDICT: APPROVE")
    assert state.terminated
    assert state.reason == "clean"


def test_the_idle_reason_is_distinct_from_the_turn_cap() -> None:
    """A detected stall and an exhausted budget are different findings.

    Folding them into one reason would make it impossible to tell, in analysis,
    whether a run was stopped because the team stopped working or because it ran
    out of room.
    """
    gc, state, _ = _idle_gc()
    for _ in range(6):
        _say(gc, AgentRole.ENGINEER, "Thinking.\nHANDOFF: critic")
    assert state.reason == "stuck_idle"
    assert state.reason not in ("cap", "stuck")


def test_the_bound_can_be_disabled() -> None:
    """Needed to observe full coordination collapse on a subset."""
    from traj_eval.agents.free_routing import RoutingConfig

    assert RoutingConfig(entry=AgentRole.REASONER).max_idle_messages == 6
    off = RoutingConfig(entry=AgentRole.REASONER, max_idle_messages=None)
    assert off.max_idle_messages is None


# --- windowed repeat detection: catch cycles, not just adjacent repeats ------
#
# The bound used to compare each call only to the IMMEDIATELY previous one, so a
# team going round a loop never tripped it. On seed13_diff10_t0 the planner made
# 11 rv_periodogram calls with 3 distinct argument sets, cycling through the same
# period windows four times and receiving byte-identical results each time, while
# never submitting once. No two consecutive calls were identical, the idle bound
# could not see it (these are tool calls), and the no-progress bound ignores
# rv_periodogram by design.


def _call_msg(role, args: str, name: str = "check_lean") -> dict:
    return {
        "name": role.value,
        "content": None,
        "tool_calls": [
            {"id": "c", "type": "function", "function": {"name": name, "arguments": args}}
        ],
    }


def _emit(gc, role, args, name="check_lean"):
    gc.messages = gc.messages + [_call_msg(role, args, name)]
    return gc.speaker_selection_method(_Speaker(role.value), gc)


def test_a_cycle_of_distinct_calls_is_caught() -> None:
    """A B C A B C ... never repeats adjacently, but is still going nowhere."""
    gc, state = _build(max_turns=200)
    windows = ['{"code": "A"}', '{"code": "B"}', '{"code": "C"}']
    for i in range(12):
        _emit(gc, AgentRole.ENGINEER, windows[i % 3])
        if state.terminated:
            break
    assert state.terminated
    assert state.reason == "stuck_cycle"
    assert state.cycle_period == 3


def test_an_adjacent_repeat_still_reports_plain_stuck() -> None:
    """Period-1 perseveration keeps its original reason, so existing analysis
    of single-call repetition is unchanged."""
    gc, state = _build(max_turns=200)
    for _ in range(4):
        _emit(gc, AgentRole.ENGINEER, '{"code": "same"}')
    assert state.terminated
    assert state.reason == "stuck"
    assert not state.saw_cycle


def test_genuinely_distinct_calls_never_trip_the_bound() -> None:
    """The safety property: exploration must not look like a loop."""
    gc, state = _build(max_turns=200)
    for i in range(20):
        _emit(gc, AgentRole.ENGINEER, f'{{"code": "attempt {i}"}}')
    assert not state.terminated
    assert state.max_identical_calls_seen == 1


def test_a_repeat_beyond_the_window_is_forgotten() -> None:
    """The window bounds memory: an old call recurring after enough novel work
    is revisiting, not looping."""
    gc, state = _build(max_turns=200, call_history_window=3)
    _emit(gc, AgentRole.ENGINEER, '{"code": "first"}')
    for i in range(5):
        _emit(gc, AgentRole.ENGINEER, f'{{"code": "novel {i}"}}')
    _emit(gc, AgentRole.ENGINEER, '{"code": "first"}')
    assert not state.terminated
    assert state.consecutive_identical_calls == 1


def test_a_novel_call_resets_the_repeat_run() -> None:
    """Repeats must be consecutive to accumulate, or ordinary revisiting would
    slowly add up to a termination."""
    gc, state = _build(max_turns=200)
    for _ in range(3):
        _emit(gc, AgentRole.ENGINEER, '{"code": "same"}')
    assert state.consecutive_identical_calls == 3
    _emit(gc, AgentRole.ENGINEER, '{"code": "brand new"}')
    assert state.consecutive_identical_calls == 1
    assert not state.terminated


def test_the_tightest_loop_is_reported() -> None:
    """A B C B C A: the team is stuck in the B-C pair, so period 2, not 5."""
    gc, state = _build(max_turns=200)
    for code in ("A", "B", "C", "B", "C", "A"):
        _emit(gc, AgentRole.ENGINEER, f'{{"code": "{code}"}}')
        if state.terminated:
            break
    assert state.saw_cycle
    assert state.cycle_period == 2


def test_window_of_one_reduces_to_the_old_behaviour() -> None:
    """The generalisation must contain the special case it replaced."""
    gc, state = _build(max_turns=200, call_history_window=1)
    for code in ("A", "B", "A", "B", "A", "B"):
        _emit(gc, AgentRole.ENGINEER, f'{{"code": "{code}"}}')
    assert not state.terminated  # alternating never repeats adjacently


# --- tool errors are not perseveration --------------------------------------
#
# On seed13_diff10 a planner called rv_residual with the field name
# ``period_days`` instead of ``P_days``. The tool raised a bare KeyError, ag2
# surfaced it as the single word "Error: 'P_days'", and the planner repeated the
# identical call until the repeat bound stopped the run. Recording that as
# perseveration would blame the agent for a tool that told it nothing.


def _error_result(call_id: str, content: str = "Error: 'P_days'") -> dict:
    return {
        "name": AgentRole.EXECUTOR.value,
        "content": None,
        "tool_responses": [{"id": call_id, "content": content}],
    }


def _call_then_error(gc, role, args, content="Error: 'P_days'", i=0):
    gc.messages = gc.messages + [_call_msg(role, args)]
    gc.speaker_selection_method(_Speaker(role.value), gc)
    gc.messages = gc.messages + [_error_result(f"c{i}", content)]
    return gc.speaker_selection_method(_Speaker(AgentRole.EXECUTOR.value), gc)


def test_repeated_tool_errors_are_attributed_to_the_tool() -> None:
    gc, state = _build(max_turns=200)
    for i in range(4):
        _call_then_error(gc, AgentRole.ENGINEER, '{"planets": "bad"}', i=i)
        if state.terminated:
            break
    assert state.terminated
    assert state.reason == "stuck_tool_error"
    assert state.max_tool_errors_seen >= 3


def test_a_structured_error_dict_also_counts() -> None:
    """A tool that validates its own input returns {'error': ...} rather than
    raising, and that is equally uninformative if repeated."""
    gc, state = _build(max_turns=200)
    payload = "{'task_id': 't', 'error': \"planets[0] is missing 'P_days'\"}"
    for i in range(4):
        _call_then_error(gc, AgentRole.ENGINEER, '{"planets": "bad"}', payload, i=i)
        if state.terminated:
            break
    assert state.reason == "stuck_tool_error"


def test_repeating_a_call_that_WORKS_is_still_perseveration() -> None:
    """The distinction must not swallow real perseveration: a team resubmitting
    an identical call that returns fine is being stubborn."""
    gc, state = _build(max_turns=200)
    for i in range(4):
        gc.messages = gc.messages + [_call_msg(AgentRole.ENGINEER, '{"code": "same"}')]
        gc.speaker_selection_method(_Speaker(AgentRole.ENGINEER.value), gc)
        gc.messages = gc.messages + [
            {
                "name": AgentRole.EXECUTOR.value,
                "content": None,
                "tool_responses": [{"id": f"c{i}", "content": "{'compiled': False}"}],
            }
        ]
        gc.speaker_selection_method(_Speaker(AgentRole.EXECUTOR.value), gc)
        if state.terminated:
            break
    assert state.terminated
    assert state.reason in ("stuck", "stuck_cycle")
    assert state.max_tool_errors_seen == 0


def test_a_successful_result_resets_the_error_run() -> None:
    gc, state = _build(max_turns=200)
    _call_then_error(gc, AgentRole.ENGINEER, '{"planets": "bad"}', i=0)
    _call_then_error(gc, AgentRole.ENGINEER, '{"planets": "bad2"}', i=1)
    assert state.consecutive_tool_errors == 2
    gc.messages = gc.messages + [_call_msg(AgentRole.ENGINEER, '{"code": "fine"}')]
    gc.speaker_selection_method(_Speaker(AgentRole.ENGINEER.value), gc)
    gc.messages = gc.messages + [
        {
            "name": AgentRole.EXECUTOR.value,
            "content": None,
            "tool_responses": [{"id": "ok", "content": "{'compiled': True}"}],
        }
    ]
    gc.speaker_selection_method(_Speaker(AgentRole.EXECUTOR.value), gc)
    assert state.consecutive_tool_errors == 0


# --- never-submitted bound --------------------------------------------------
#
# The one pathology the other bounds structurally cannot see. On seed13_diff10 a
# team ran the full 60 turns making only novel, well-formed, SUCCESSFUL tool
# calls -- no idling, no repeats, no cycles, no errors -- and never submitted,
# because the planner and engineer captured the loop and the critic, the only
# holder of rv_submit, was never handed control. Every bound passed while the
# work converged on nothing.


def _busy(gc, i: int, tool: str = "check_lean", ok: str = "{'compiled': True}"):
    """One productive-looking round: a novel successful tool call."""
    gc.messages = gc.messages + [_call_msg(AgentRole.ENGINEER, f'{{"code": "novel {i}"}}', tool)]
    gc.speaker_selection_method(_Speaker(AgentRole.ENGINEER.value), gc)
    gc.messages = gc.messages + [
        {
            "name": AgentRole.EXECUTOR.value,
            "content": None,
            "tool_responses": [{"id": f"c{i}", "content": ok}],
        }
    ]
    gc.speaker_selection_method(_Speaker(AgentRole.EXECUTOR.value), gc)


def test_a_busy_run_that_never_submits_is_stopped() -> None:
    gc, state = _build(
        max_turns=40,
        submission_tools=frozenset({"rv_submit"}),
        submission_deadline_frac=0.5,
    )
    for i in range(40):
        _busy(gc, i)
        if state.terminated:
            break
    assert state.terminated
    assert state.reason == "stuck_no_submission"
    assert state.turns >= 20  # 50% of 40
    assert state.n_submission_calls == 0


def test_one_submission_disarms_the_bound_permanently() -> None:
    """The bound is about never reaching the goal, not about submitting slowly."""
    gc, state = _build(
        max_turns=40,
        submission_tools=frozenset({"check_lean"}),
        submission_deadline_frac=0.5,
    )
    _busy(gc, 0)  # check_lean IS the submission tool here
    assert state.n_submission_calls == 1
    for i in range(1, 40):
        _busy(gc, i)
        if state.terminated:
            break
    assert state.reason != "stuck_no_submission"


def test_the_bound_is_inert_without_configured_submission_tools() -> None:
    """Lean has no submission tool -- its terminal act is the APPROVE marker --
    so an empty set must leave the bound switched off."""
    gc, state = _build(max_turns=40, submission_deadline_frac=0.5)
    for i in range(30):
        _busy(gc, i)
        if state.terminated:
            break
    assert state.reason != "stuck_no_submission"


def test_the_deadline_scales_with_the_turn_budget() -> None:
    """A fraction, not a fixed count, because max_turns varies by tier."""
    for cap, expected in ((20, 10), (60, 30)):
        gc, state = _build(
            max_turns=cap,
            submission_tools=frozenset({"rv_submit"}),
            submission_deadline_frac=0.5,
        )
        for i in range(cap):
            _busy(gc, i)
            if state.terminated:
                break
        assert state.reason == "stuck_no_submission"
        assert state.turns == expected


def test_the_deadline_can_be_disabled() -> None:
    gc, state = _build(
        max_turns=30,
        submission_tools=frozenset({"rv_submit"}),
        submission_deadline_frac=None,
    )
    for i in range(30):
        _busy(gc, i)
        if state.terminated:
            break
    assert state.reason == "cap"
