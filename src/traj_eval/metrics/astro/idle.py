"""Idle runs: stretches where the team talks without calling any tool.

Motivating case
---------------
On seed22_diff4_t0 the trace ends with TWENTY consecutive agent messages that
make no tool call at all -- planner -> engineer -> planner ping-pong until
``max_turns`` cut the run off. The team had used 1 of its 5 submissions and never
used another. None of the controller's bounds could see it:

  * the no-progress bound counts ``rv_fit`` results reporting ``ok: false``, and
    there were no tool calls to report anything;
  * the identical-call bound compares tool-call signatures, and there were none;
  * ``max_turns`` did stop it -- the most expensive way possible, since every
    turn resends the whole history and cost grows roughly quadratically in turn
    count. Those last twenty turns carried the largest context and produced
    nothing.

Both existing bounds are tool-call-based, so a team that stops calling tools is
invisible to them. This module measures the gap so a threshold can be chosen
from data rather than guessed.

What counts as idle
-------------------
An agent MESSAGE (not a tool call, not an execution result) that carries no
terminal verdict. Consecutive such messages form an idle run.

The LENGTH of a run is the signal, not the count of idle messages. In this trace
format a tool call is its own event, so every agent message is trivially "a
message that is not a tool call" -- counting them would mark 100% of every trial
as idle and mean nothing. What separates a healthy trial from a stalled one is
the interleaving: healthy runs are length 1 (an agent reasons, hands off, the
next one calls a tool), whereas seed22's tail is 21 messages with no tool call
anywhere between them.

So the waste is the EXCESS over one message per run: a run of length 1 costs
nothing beyond normal operation, a run of length 21 wastes 20 turns.

The two questions a stop rule needs answered, and which this module exists to
answer, are: how long do idle runs get, and does a long one ever occur on a
trial that goes on to SUCCEED? The second decides whether a bound is safe. A
threshold that would have cut a successful run converts a slow success into a
recorded failure and corrupts the very failure statistics the project measures.

Pure trace analysis: no LLM, no evaluator, no network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from traj_eval.metrics.astro.artifacts import AstroTrialArtifacts
from traj_eval.trace_core.schema import EventType, TraceEvent

# Roles whose messages are the team talking. The executor only ever reports tool
# results, and the system role posts the task, so neither can be idle.
EXCLUDED_ROLES = frozenset({"executor", "system", "user"})


@dataclass(frozen=True)
class IdleRun:
    """One stretch of consecutive agent messages that called no tool."""

    start_seq: int
    end_seq: int
    length: int
    roles: list[str] = field(default_factory=list)
    ended_by: str = "unknown"  # 'tool_call' | 'terminal' | 'end_of_trace'

    @property
    def role_cycle(self) -> str:
        return " -> ".join(self.roles)

    @property
    def is_terminal(self) -> bool:
        """Did the run continue to the end of the trace?

        A terminal idle run is the expensive case: the team never recovered and
        the episode was stopped by the turn cap rather than by any decision.
        """
        return self.ended_by == "end_of_trace"


@dataclass(frozen=True)
class IdleReport:
    """Idle-run statistics for one trial."""

    trial_id: str | None
    task_id: str | None
    runs: list[IdleRun] = field(default_factory=list)
    n_agent_messages: int = 0
    n_tool_calls: int = 0
    last_seq: int = 0

    @property
    def max_idle_run(self) -> int:
        return max((r.length for r in self.runs), default=0)

    @property
    def excess_idle_messages(self) -> int:
        """Messages beyond the first in each run: the actual churn.

        One message per run is normal interleaving and costs nothing extra; only
        the repeats are waste. Zero on a healthy trial, 20 on seed22.
        """
        return sum(r.length - 1 for r in self.runs)

    @property
    def excess_share(self) -> float | None:
        """Churn as a fraction of all agent messages.

        A blunt cost proxy, but conservative in the right direction: churn sits
        at the END of a trial, carrying the largest context, and every turn
        resends the whole history -- so these are the most expensive messages in
        the run.
        """
        if not self.n_agent_messages:
            return None
        return self.excess_idle_messages / self.n_agent_messages

    @property
    def terminal_idle_run(self) -> IdleRun | None:
        """The idle run the trace ended on, if it ended in one."""
        return self.runs[-1] if self.runs and self.runs[-1].is_terminal else None

    @property
    def wasted_tail(self) -> int:
        """Messages spent in a terminal idle run: what a stop rule would save."""
        tail = self.terminal_idle_run
        return tail.length if tail else 0

    def would_trip(self, threshold: int) -> bool:
        """Would a 'stop after N idle messages' rule have fired on this trial?"""
        return self.max_idle_run >= threshold

    def messages_saved(self, threshold: int) -> int:
        """Agent messages a threshold-N rule would have avoided.

        Only the FIRST run to reach the threshold matters: the rule stops the
        episode there, so everything after it -- idle or not -- never happens.
        Counting every long run would overstate the saving.
        """
        cumulative = 0
        for run in self.runs:
            if run.length >= threshold:
                # Stop at the threshold-th message of this run; the rest of the
                # trial is never produced.
                return self.n_agent_messages - (cumulative + threshold)
            cumulative += run.length
        return 0


def analyse_idle_runs(
    events: list[TraceEvent],
    artifacts: AstroTrialArtifacts | None = None,
    *,
    trial_id: str | None = None,
    task_id: str | None = None,
) -> IdleReport:
    """Find every idle run in one trial's events.

    Walks the events in order. ``artifacts`` is accepted for symmetry with the
    other analysis entry points but is not required, since everything needed is
    in the raw events.
    """
    runs: list[IdleRun] = []
    current: list[tuple[int, str]] = []
    n_agent_messages = 0
    n_tool_calls = 0
    last_seq = 0

    def close(ended_by: str) -> None:
        nonlocal current
        if current:
            runs.append(
                IdleRun(
                    start_seq=current[0][0],
                    end_seq=current[-1][0],
                    length=len(current),
                    roles=[role for _, role in current],
                    ended_by=ended_by,
                )
            )
            current = []

    for event in events:
        role = getattr(event.agent_role, "value", str(event.agent_role))
        last_seq = max(last_seq, event.seq)

        if event.event_type is EventType.TOOL_CALL:
            n_tool_calls += 1
            close("tool_call")
            continue
        if event.event_type is EventType.EXECUTION_RESULT:
            # A result belongs to the call that preceded it; it neither starts
            # nor breaks an idle run.
            continue
        if event.event_type is not EventType.MESSAGE:
            continue
        if role in EXCLUDED_ROLES:
            continue

        n_agent_messages += 1
        # A terminal verdict ends the episode deliberately, so the messages
        # before it were leading somewhere -- not idle churn.
        if event.payload.get("decision"):
            close("terminal")
            continue
        current.append((event.seq, role))

    close("end_of_trace")

    return IdleReport(
        trial_id=trial_id,
        task_id=task_id,
        runs=runs,
        n_agent_messages=n_agent_messages,
        n_tool_calls=n_tool_calls,
        last_seq=last_seq,
    )


def summarise(report: IdleReport) -> dict[str, Any]:
    """Flat dict for reporting/serialisation."""
    tail = report.terminal_idle_run
    return {
        "trial_id": report.trial_id,
        "task_id": report.task_id,
        "n_agent_messages": report.n_agent_messages,
        "n_tool_calls": report.n_tool_calls,
        "n_idle_runs": len(report.runs),
        "max_idle_run": report.max_idle_run,
        "excess_idle_messages": report.excess_idle_messages,
        "excess_share": report.excess_share,
        "ended_in_idle_run": tail is not None,
        "wasted_tail": report.wasted_tail,
        "longest_run_roles": max(
            (r.role_cycle for r in report.runs),
            key=lambda s: s.count("->"),
            default="",
        ),
    }
