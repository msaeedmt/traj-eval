"""Smoke test for free-routing (Step 4d): reasoner -> engineer <-> critic, with
agent-chosen hand-offs.

By default uses the REAL Lean compiler (lean-interact, against ~/lean_anchor):
the agents must produce a genuinely compiling, sorry-free proof, and the
engineer iterates against real kernel errors. Set TRAJ_EVAL_FAKE_LEAN=1 to use
a fake checker instead, for testing coordination dynamics without the kernel.

Run: uv run python scripts/smoke_free.py
     TRAJ_EVAL_FAKE_LEAN=1 uv run python scripts/smoke_free.py   # fake compiler

What to look for:
  * a trajectory of HANDOFF / tool-call choices the agents made themselves;
  * with the real compiler: does the engineer iterate against real errors?
  * the termination reason (clean / cap / stuck) and coordination stats.
"""

from __future__ import annotations

import os
from pathlib import Path

from traj_eval.agents import (
    RoutingLedger,
    StepContext,
    TraceObserver,
    build_llm_config,
    make_trial_meta,
)
from traj_eval.agents.free_routing import finalize_run
from traj_eval.agents.lean_team import build_lean_free_team
from traj_eval.trace_core.graph import causal_order
from traj_eval.trace_core.storage import TrialLogWriter, read_trial

LOG_PATH = Path("data/smoke_free.jsonl")
PROJECT_DIR = Path.home() / "lean_anchor"

_FAKE_CALLS: list[str] = []


def fake_check_lean(code: str) -> str:
    "Type-check Lean source. Reports compile status, errors, and remaining sorries."
    _FAKE_CALLS.append(code)
    has_sorry = "sorry" in code
    return f"compiled: true; sorries: {1 if has_sorry else 0}; errors: none; note: FAKE"


def fake_search_lemmas(query: str) -> str:
    "Search the library for lemmas matching a natural-language description."
    return "Nat.add_comm : ∀ (n m : ℕ), n + m = m + n  [FAKE result]"


# TASK = (
#     "Prove this Lean 4 theorem:\n"
#     "    theorem add_comm_example (a b : Nat) : a + b = b + a\n"
#     "The reasoner should give a strategy, the engineer should formalise and "
#     "verify it with check_lean, and the critic should review faithfulness."
# )

TASK = (
    "Prove this Lean 4 theorem:\n"
    "    theorem inv_mul_rev {G : Type*} [Group G] (a b : G) : (a * b)⁻¹ = b⁻¹ * a⁻¹\n"
)


def main() -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    use_fake = os.environ.get("TRAJ_EVAL_FAKE_LEAN") == "1"

    if use_fake:
        print("Using FAKE Lean checker (TRAJ_EVAL_FAKE_LEAN=1).")
        check_tool, search_tool = fake_check_lean, fake_search_lemmas
    else:
        from traj_eval.tools.lean_compiler import LeanCompiler
        from traj_eval.tools.lean_search import make_search_lemmas

        print(f"Starting REAL Lean compiler against {PROJECT_DIR} (first run is slow)...")
        compiler = LeanCompiler(PROJECT_DIR)
        print("Compiler ready.")
        check_tool, search_tool = compiler.as_tool(), make_search_lemmas(num_results=5)

    llm_config = build_llm_config()
    ledger = RoutingLedger()
    step_context = StepContext()

    manager, user, groupchat, run_state = build_lean_free_team(
        llm_config,
        tools={"check_lean": check_tool, "search_lemmas": search_tool},
        max_turns=30,
        ledger=ledger,
        step_context=step_context,
    )

    meta = make_trial_meta(
        trial_id="smoke_free", task_id="add_comm", backbone="gpt-4o-mini", testbed="lean"
    )
    writer = TrialLogWriter(LOG_PATH, meta)
    observer = TraceObserver(
        writer, trial_id="smoke_free", ledger=ledger, step_context=step_context
    )
    observer.attach([a for a in groupchat.agents if a.name != "user"])
    observer.record_task(TASK)

    user.initiate_chat(manager, message=TASK, clear_history=True)
    writer.close()
    finalize_run(run_state)

    _, events = read_trial(LOG_PATH)

    print("\n==================== trajectory ====================")
    for e in events:
        marker = ""
        if e.payload.get("handoff_target"):
            marker = f"-> HANDOFF:{e.payload['handoff_target']}"
        elif e.payload.get("tool_request"):
            marker = f"-> TOOL:{e.payload['tool_request']}"
        elif e.payload.get("decision"):
            marker = f"[{e.payload['decision']}]"
        body = (e.payload.get("text", "") or "").replace("\n", " ")[:45]
        et = e.event_type.value
        print(f"  {e.agent_role.value:9s}#{e.seq} {et:17s} {marker:22s} {body!r}")

    order = causal_order(events)
    handoffs = [e for e in events if e.payload.get("handoff_target")]
    tool_reqs = [e for e in events if e.payload.get("tool_request")]

    print("\n==================== checks ====================")
    print(f"  termination reason     : {run_state.reason}")
    print(f"  total turns            : {run_state.turns}")
    print(f"  invalid hand-offs      : {run_state.invalid_handoffs}")
    print(f"  expressed hand-offs    : {len(handoffs)}")
    print(f"  expressed tool requests: {len(tool_reqs)}")
    print(f"  fake check_lean calls  : {len(_FAKE_CALLS)}")
    print(f"  graph is DAG           : {len(order) == len(events)}")


if __name__ == "__main__":
    main()
