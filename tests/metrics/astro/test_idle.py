"""Tests for idle-run detection. Pure trace analysis: no LLM, no evaluator.

Idle runs are the gap the controller's existing bounds cannot see: both the
no-progress bound and the identical-call bound key on TOOL CALLS, so a team that
stops calling tools entirely is invisible to them. seed22_diff4_t0 ended with 21
consecutive agent messages and no tool call, stopped only by max_turns.
"""

from __future__ import annotations

import uuid

import pytest

from traj_eval.metrics.astro.idle import analyse_idle_runs, summarise
from traj_eval.trace_core.schema import AgentRole, EventType, TraceEvent


class Builder:
    """Assemble a trace from a compact script."""

    def __init__(self) -> None:
        self.events: list[TraceEvent] = []
        self._seq = 0

    def _add(self, event_type: EventType, role: AgentRole, payload: dict) -> Builder:
        self.events.append(
            TraceEvent(
                event_id=str(uuid.uuid4()),
                trial_id="t",
                seq=self._seq,
                timestamp="2026-01-01T00:00:00Z",
                event_type=event_type,
                agent_role=role,
                caused_by=[],
                payload=payload,
            )
        )
        self._seq += 1
        return self

    def msg(
        self, role: AgentRole, *, handoff: str | None = None, decision: str | None = None
    ) -> Builder:
        payload: dict = {"text": "..."}
        if handoff:
            payload["handoff_target"] = handoff
        if decision:
            payload["decision"] = decision
        return self._add(EventType.MESSAGE, role, payload)

    def tool(self, role: AgentRole) -> Builder:
        self._add(
            EventType.TOOL_CALL,
            role,
            {"tool_calls": [{"id": f"c{self._seq}", "name": "rv_fit", "arguments": "{}"}]},
        )
        return self._add(
            EventType.EXECUTION_RESULT,
            AgentRole.EXECUTOR,
            {"tool_responses": [{"id": f"c{self._seq - 1}", "content": "{'ok': True}"}]},
        )


def test_a_healthy_trial_has_runs_of_length_one() -> None:
    """Reason, call a tool, reason, call a tool: no churn at all."""
    b = Builder()
    b.tool(AgentRole.PLANNER).msg(AgentRole.PLANNER, handoff="engineer")
    b.tool(AgentRole.ENGINEER).msg(AgentRole.ENGINEER, handoff="critic")
    b.tool(AgentRole.CRITIC).msg(AgentRole.CRITIC, decision="approve")
    report = analyse_idle_runs(b.events, trial_id="t")
    assert report.max_idle_run == 1
    assert report.excess_idle_messages == 0
    assert report.terminal_idle_run is None


def test_a_ping_pong_tail_is_one_long_run() -> None:
    """The seed22 shape: work circulates with nothing being done."""
    b = Builder()
    b.tool(AgentRole.PLANNER).msg(AgentRole.PLANNER, handoff="engineer")
    for _ in range(5):
        b.msg(AgentRole.ENGINEER, handoff="planner").msg(AgentRole.PLANNER, handoff="engineer")
    report = analyse_idle_runs(b.events, trial_id="t")
    assert report.max_idle_run == 11  # the handoff that started it, plus 10
    assert report.excess_idle_messages == 10
    assert report.terminal_idle_run is not None
    assert report.wasted_tail == 11


def test_a_tool_call_breaks_a_run() -> None:
    b = Builder()
    b.msg(AgentRole.PLANNER).msg(AgentRole.ENGINEER)
    b.tool(AgentRole.ENGINEER)
    b.msg(AgentRole.ENGINEER)
    report = analyse_idle_runs(b.events, trial_id="t")
    assert [r.length for r in report.runs] == [2, 1]
    assert report.runs[0].ended_by == "tool_call"


def test_a_terminal_verdict_is_not_churn() -> None:
    """Messages leading to a deliberate stop were going somewhere."""
    b = Builder()
    b.msg(AgentRole.PLANNER).msg(AgentRole.CRITIC, decision="approve")
    report = analyse_idle_runs(b.events, trial_id="t")
    assert report.runs[0].ended_by == "terminal"
    assert report.terminal_idle_run is None


def test_executor_and_system_messages_are_not_agent_turns() -> None:
    """Only the team talking counts; the executor just reports results."""
    b = Builder()
    b.msg(AgentRole.SYSTEM)
    b.msg(AgentRole.EXECUTOR)
    b.msg(AgentRole.PLANNER)
    report = analyse_idle_runs(b.events, trial_id="t")
    assert report.n_agent_messages == 1


def test_would_trip_matches_the_longest_run() -> None:
    b = Builder()
    for _ in range(4):
        b.msg(AgentRole.PLANNER)
    report = analyse_idle_runs(b.events, trial_id="t")
    assert report.would_trip(4)
    assert not report.would_trip(5)


def test_messages_saved_counts_only_up_to_the_first_trip() -> None:
    """The rule stops the episode, so nothing after the trip is ever produced.

    Counting every long run would overstate the saving.
    """
    b = Builder()
    for _ in range(6):  # first run: trips a threshold of 3 at message 3
        b.msg(AgentRole.PLANNER)
    b.tool(AgentRole.ENGINEER)
    for _ in range(4):  # never happens under the rule
        b.msg(AgentRole.PLANNER)
    report = analyse_idle_runs(b.events, trial_id="t")
    assert report.n_agent_messages == 10
    assert report.messages_saved(3) == 7
    assert report.messages_saved(20) == 0  # never trips, saves nothing


def test_summarise_is_serialisable() -> None:
    b = Builder().msg(AgentRole.PLANNER).msg(AgentRole.ENGINEER)
    out = summarise(analyse_idle_runs(b.events, trial_id="t", task_id="task"))
    assert out["max_idle_run"] == 2
    assert out["excess_idle_messages"] == 1
    assert out["ended_in_idle_run"] is True
    assert out["trial_id"] == "t"


def test_an_empty_trace_does_not_crash() -> None:
    report = analyse_idle_runs([], trial_id="t")
    assert report.max_idle_run == 0
    assert report.excess_share is None
    assert not report.would_trip(1)


@pytest.mark.parametrize("threshold", [3, 5, 10])
def test_a_healthy_trial_is_never_cut(threshold: int) -> None:
    """The safety property a stop rule depends on.

    A threshold that cuts a healthy run would convert successes into recorded
    failures and corrupt the failure statistics the project measures.
    """
    b = Builder()
    for _ in range(8):
        b.tool(AgentRole.ENGINEER).msg(AgentRole.ENGINEER, handoff="critic")
    assert not analyse_idle_runs(b.events, trial_id="t").would_trip(threshold)
