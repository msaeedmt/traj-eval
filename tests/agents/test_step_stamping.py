"""Step 2a: the observer stamps the shared step pointer onto the right events.

This drives the observer directly with a fake AG2 sender and a hand-advanced
StepContext -- no LLM, no group chat -- so the stamping contract is pinned
without paying for a real run. The end-to-end controller path is exercised
separately by scripts/smoke_stepped.py (which makes real calls).

Contract under test:
  * engineer and critic events carry ``step_idx``/``attempt`` from the context;
  * planner and system events do not (they are not part of a plan step);
  * the stamp reflects the context value at emit time, so advancing the context
    between turns yields the per-step / per-attempt sequence the accumulation
    layer relies on.

Requires the ``agents`` extra (ag2) because the observer imports autogen at
module load; skipped cleanly when it is absent.
"""

from __future__ import annotations

import pytest

pytest.importorskip("autogen", reason="agents extra (ag2) not installed")

from traj_eval.agents.observer import StepContext, TraceObserver  # noqa: E402
from traj_eval.trace_core.schema import AgentRole  # noqa: E402
from traj_eval.trace_core.storage import read_trial  # noqa: E402


class _FakeAgent:
    """Minimal stand-in for an AG2 ConversableAgent: only ``name`` is read."""

    def __init__(self, name: str) -> None:
        self.name = name


def _emit(observer: TraceObserver, role: AgentRole, text: str) -> None:
    """Invoke the observer's message hook as AG2 would, for one turn."""
    sender = _FakeAgent(role.value)
    recipient = _FakeAgent("chat_manager")
    observer._record_message(sender, {"content": text}, recipient, silent=False)


def test_stamps_engineer_and_critic_not_planner(tmp_path):
    from traj_eval.agents.observer import make_trial_meta
    from traj_eval.trace_core.storage import TrialLogWriter

    ctx = StepContext()
    path = tmp_path / "t.jsonl"
    meta = make_trial_meta("t", task_id="x", backbone="dummy", testbed="lean")
    writer = TrialLogWriter(path, meta)
    obs = TraceObserver(writer, trial_id="t", step_context=ctx)

    # Plan step 0, first attempt.
    _emit(obs, AgentRole.PLANNER, "<step>a</step><step>b</step>")
    _emit(obs, AgentRole.ENGINEER, "work\nFINAL: ok")
    _emit(obs, AgentRole.CRITIC, "VERDICT: REJECT - wrong")

    # Step 0 repair: controller would bump attempt before the engineer speaks.
    ctx.attempt = 1
    _emit(obs, AgentRole.ENGINEER, "fixed\nFINAL: ok")
    _emit(obs, AgentRole.CRITIC, "VERDICT: APPROVE")

    # Advance to step 1, attempt resets.
    ctx.step_idx = 1
    ctx.attempt = 0
    _emit(obs, AgentRole.ENGINEER, "second\nFINAL: ok")
    _emit(obs, AgentRole.CRITIC, "VERDICT: APPROVE")
    writer.close()

    _, events = read_trial(path)
    by_role = lambda r: [e for e in events if e.agent_role is r]  # noqa: E731

    # Planner is never stamped.
    assert "step_idx" not in by_role(AgentRole.PLANNER)[0].payload

    eng = by_role(AgentRole.ENGINEER)
    crit = by_role(AgentRole.CRITIC)
    assert [(e.payload["step_idx"], e.payload["attempt"]) for e in eng] == [(0, 0), (0, 1), (1, 0)]
    assert [(c.payload["step_idx"], c.payload["attempt"]) for c in crit] == [(0, 0), (0, 1), (1, 0)]


def test_no_context_means_no_stamp(tmp_path):
    from traj_eval.agents.observer import make_trial_meta
    from traj_eval.trace_core.storage import TrialLogWriter

    path = tmp_path / "t.jsonl"
    meta = make_trial_meta("t", task_id="x", backbone="dummy", testbed="lean")
    writer = TrialLogWriter(path, meta)
    obs = TraceObserver(writer, trial_id="t")  # no step_context

    _emit(obs, AgentRole.ENGINEER, "work\nFINAL: ok")
    writer.close()

    _, events = read_trial(path)
    assert "step_idx" not in events[0].payload
