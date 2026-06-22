"""Smoke test for Step 4d: stepped team with an in-loop compiler tool.

Uses a FAKE deterministic checker (not real Lean) so this exercises only the
plumbing -- tool registration, the engineer<->executor routing loop, and that
the observer logs TOOL_CALL / EXECUTION_RESULT events with the right step
stamps. Swap the fake for the real lean_interact-backed check_lean in Step 4e.

Run: uv run python scripts/smoke_tools.py   (needs OPENAI_API_KEY)
"""

from __future__ import annotations

from pathlib import Path

from traj_eval.agents import (
    RoutingLedger,
    StepContext,
    TraceObserver,
    build_llm_config,
    build_stepped_team,
    make_trial_meta,
)
from traj_eval.trace_core.graph import causal_order
from traj_eval.trace_core.schema import EventType
from traj_eval.trace_core.storage import TrialLogWriter, read_trial

LOG_PATH = Path("data/smoke_tools.jsonl")

# A fake compiler: deterministic, returns a canned verdict. The engineer is told
# (via the task) that it MUST call this before declaring a step done, so we can
# observe the tool round-trip without installing Lean.
_FAKE_CALLS: list[str] = []


def fake_check_lean(code: str) -> str:
    """Pretend to type-check Lean source. Deterministic stand-in for Step 4e."""
    _FAKE_CALLS.append(code)
    has_sorry = "sorry" in code
    return (
        f"compiled: true; sorries: {1 if has_sorry else 0}; "
        f"errors: none; note: FAKE checker (smoke only)"
    )


TASK = (
    "Prove informally that the sum 1+2+3 equals 6, in two steps. For EACH step "
    "you MUST call the check_lean tool on a short Lean snippet before finishing "
    "the step. This is a plumbing smoke test; the snippet need not be meaningful."
)


def main() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    llm_config = build_llm_config()
    ledger = RoutingLedger()
    step_context = StepContext()
    manager, user, groupchat = build_stepped_team(
        llm_config,
        ledger=ledger,
        step_context=step_context,
        lean_tool=fake_check_lean,
        max_tool_calls=3,
    )

    meta = make_trial_meta(
        trial_id="smoke_tools", task_id="sum6", backbone="gpt-4o-mini", testbed="lean"
    )
    writer = TrialLogWriter(LOG_PATH, meta)
    observer = TraceObserver(
        writer, trial_id="smoke_tools", ledger=ledger, step_context=step_context
    )
    # attach to every agent except the user proxy: the user only re-sends the
    # task (already logged by record_task), while the executor MUST be hooked
    # since it speaks the tool result. Mirrors smoke_stepped's exclusion.
    observer.attach([a for a in groupchat.agents if a.name != "user"])
    root = observer.record_task(TASK)

    user.initiate_chat(manager, message=TASK, clear_history=True)
    writer.close()

    meta_out, events = read_trial(LOG_PATH)
    idmap = {e.event_id: f"{e.agent_role.value}#{e.seq}" for e in events}
    idmap[root] = "task#0"

    print("\n==================== trajectory ====================")
    for e in events:
        parents = [idmap.get(p, p[:8]) for p in e.caused_by]
        step = e.payload.get("step_idx")
        stamp = f"[s{step}.a{e.payload.get('attempt')}]" if step is not None else ""
        if e.event_type is EventType.TOOL_CALL:
            body = "CALL " + ",".join(c.get("name", "?") for c in e.payload.get("tool_calls", []))
        elif e.event_type is EventType.EXECUTION_RESULT:
            body = "RESULT " + (e.payload.get("text", "")[:40])
        else:
            body = (e.payload.get("text", "") or "").replace("\n", " ")[:40]
        print(f"  {e.agent_role.value:9s}#{e.seq} {e.event_type.value:17s} {stamp:8s} {body!r}")
        if parents:
            print(f"             caused_by={parents}")

    tool_calls = [e for e in events if e.event_type is EventType.TOOL_CALL]
    tool_results = [e for e in events if e.event_type is EventType.EXECUTION_RESULT]

    order = causal_order(events)

    print("\n==================== checks ====================")
    print(f"  TOOL_CALL events       : {len(tool_calls)}")
    print(f"  EXECUTION_RESULT events: {len(tool_results)}")
    print(f"  fake checker invoked   : {len(_FAKE_CALLS)} time(s)")
    print(f"  calls == results       : {len(tool_calls) == len(tool_results)}")
    all_stamped = all("step_idx" in e.payload for e in tool_calls + tool_results)
    print(f"  all tool events stamped: {all_stamped}")
    print(f"  graph is DAG           : {len(order) == len(events)}")


if __name__ == "__main__":
    main()
