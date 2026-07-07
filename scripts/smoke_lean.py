"""Smoke test for Step 4e: the REAL Lean compiler in the loop.

Same stepped engineer<->executor loop as smoke_tools.py, but the tool is the
deterministic LeanCompiler (lean-interact backed) pointed at ~/lean_anchor,
not a fake. This is the first run where the agent's tool calls are checked by
the actual Lean kernel.

Run: uv run python scripts/smoke_lean.py     (needs OPENAI_API_KEY; first run
builds the Lean REPL, so it is slow once.)

What to look for in the trace:
  * TOOL_CALL / EXECUTION_RESULT events whose payload carries the real verdict
    (compiled / n_sorries / errors), stamped with the plan step;
  * whether the engineer iterates against real compiler feedback (calls, sees a
    real error, fixes, calls again) -- the whole point of an in-loop compiler.
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
from traj_eval.tools.lean_compiler import LeanCompiler
from traj_eval.trace_core.graph import causal_order
from traj_eval.trace_core.schema import EventType
from traj_eval.trace_core.storage import TrialLogWriter, read_trial

LOG_PATH = Path("data/smoke_lean.jsonl")
PROJECT_DIR = Path.home() / "lean_anchor"

# A genuine, tiny Lean task. The engineer must actually produce a compiling,
# sorry-free Lean proof; the critic gates it; the engineer can call check_lean
# to iterate against real kernel feedback within each step.
TASK = (
    "Prove the following Lean 4 theorem. You have a `check_lean` tool that "
    "type-checks Lean source against Mathlib -- use it to verify your proof "
    "compiles with no errors and no `sorry` before finishing. Include "
    "`import Mathlib` at the top of every snippet you check.\n\n"
    "Theorem to prove:\n"
    "    theorem add_comm_example (a b : Nat) : a + b = b + a\n\n"
    "Do it in two steps: first state the theorem with a `sorry` placeholder and "
    "check that it parses, then replace the `sorry` with a real proof and check "
    "that it compiles cleanly."
)


def main() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    print(f"Starting Lean compiler against {PROJECT_DIR} (first run is slow)...")
    compiler = LeanCompiler(PROJECT_DIR)
    print("Compiler ready.")

    llm_config = build_llm_config()
    ledger = RoutingLedger()
    step_context = StepContext()
    manager, user, groupchat = build_stepped_team(
        llm_config,
        ledger=ledger,
        step_context=step_context,
        lean_tool=compiler.as_tool(),
        max_tool_calls=4,
    )

    meta = make_trial_meta(
        trial_id="smoke_lean", task_id="add_comm", backbone="gpt-4o-mini", testbed="lean"
    )
    writer = TrialLogWriter(LOG_PATH, meta)
    observer = TraceObserver(
        writer, trial_id="smoke_lean", ledger=ledger, step_context=step_context
    )
    observer.attach([a for a in groupchat.agents if a.name != "user"])
    root = observer.record_task(TASK)

    user.initiate_chat(manager, message=TASK, clear_history=True)
    writer.close()

    _, events = read_trial(LOG_PATH)
    idmap = {e.event_id: f"{e.agent_role.value}#{e.seq}" for e in events}
    idmap[root] = "task#0"

    print("\n==================== trajectory ====================")
    for e in events:
        step = e.payload.get("step_idx")
        stamp = f"[s{step}.a{e.payload.get('attempt')}]" if step is not None else ""
        if e.event_type is EventType.TOOL_CALL:
            args = "; ".join(c.get("arguments", "")[:50] for c in e.payload.get("tool_calls", []))
            body = f"CALL check_lean({args})"
        elif e.event_type is EventType.EXECUTION_RESULT:
            # the tool result text is the rich dict's summary line
            body = "RESULT " + (e.payload.get("text", "") or "")[:70]
        else:
            body = (e.payload.get("text", "") or "").replace("\n", " ")[:50]
        print(f"  {e.agent_role.value:9s}#{e.seq} {e.event_type.value:17s} {stamp:8s} {body!r}")

    tool_calls = [e for e in events if e.event_type is EventType.TOOL_CALL]
    tool_results = [e for e in events if e.event_type is EventType.EXECUTION_RESULT]
    order = causal_order(events)

    print("\n==================== checks ====================")
    print(f"  TOOL_CALL events       : {len(tool_calls)}")
    print(f"  EXECUTION_RESULT events: {len(tool_results)}")
    print(f"  calls == results       : {len(tool_calls) == len(tool_results)}")
    print(f"  graph is DAG           : {len(order) == len(events)}")
    if tool_results:
        last = tool_results[-1].payload.get("text", "")
        print(f"  last compiler verdict  : {last[:80]!r}")


if __name__ == "__main__":
    main()
