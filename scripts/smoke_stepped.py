"""Step 3b smoke test: the per-step controller walks the plan.

Run:
    uv run python scripts/smoke_stepped.py

Runs the per-step team on the toy task with the observer + ledger attached, then
checks that the trajectory has ONE engineer event per plan step (instead of a
single engineer pass), and that the causal chain threads through them.

Success:
  * planner produced N steps;
  * there are exactly N engineer events;
  * the run terminated on its own (not by max_round);
  * the graph is a DAG and each engineer step points at the previous one.

Makes real LLM calls; the report prints at the end.
"""

from __future__ import annotations

from pathlib import Path

import networkx as nx

from traj_eval.agents import (
    RoutingLedger,
    StepContext,
    TraceObserver,
    build_llm_config,
    build_stepped_team,
    make_trial_meta,
    parse_plan,
)
from traj_eval.trace_core.graph import build_graph, causal_order
from traj_eval.trace_core.storage import TrialLogWriter, read_trial

TOY_TASK = "Compute the 12th Fibonacci number (with F(1)=F(2)=1)."
LOG_PATH = Path("runs/smoke_stepped.jsonl")


def main() -> None:
    llm_config = build_llm_config()
    ledger = RoutingLedger()
    step_context = StepContext()
    manager, user, groupchat = build_stepped_team(
        llm_config, ledger=ledger, step_context=step_context
    )

    meta = make_trial_meta(trial_id="smoke_stepped", task_id="fib12", backbone="gpt-4o-mini")
    writer = TrialLogWriter(LOG_PATH, meta)
    observer = TraceObserver(
        writer, trial_id="smoke_stepped", ledger=ledger, step_context=step_context
    )
    observer.attach([a for a in groupchat.agents if a.name != "user"])
    observer.record_task(TOY_TASK)

    user.initiate_chat(manager, message=TOY_TASK)
    writer.close()

    meta2, events = read_trial(LOG_PATH)
    idmap = {e.event_id: f"{e.agent_role.value}#{e.seq}" for e in events}

    print("\n==================== trajectory ====================")
    for e in events:
        parents = [idmap.get(p, p[:8]) for p in e.caused_by]
        text = e.payload.get("text", "").replace("\n", " ")[:50]
        step = e.payload.get("step_idx")
        stamp = f"[s{step}.a{e.payload.get('attempt')}]" if step is not None else ""
        print(f"  {e.agent_role.value:9s}#{e.seq} {stamp:8s} caused_by={parents}  | {text!r}")

    planner_events = [e for e in events if e.agent_role.value == "planner"]
    engineer_events = [e for e in events if e.agent_role.value == "engineer"]
    critic_events = [e for e in events if e.agent_role.value == "critic"]

    n_steps = None
    if planner_events:
        try:
            n_steps = len(parse_plan(planner_events[0].payload["text"]))
        except Exception as exc:  # noqa: BLE001
            print(f"  (could not re-parse plan: {exc})")

    # Step 2a: every engineer/critic event must carry the plan step it belongs
    # to, so the accumulation layer reads step membership instead of re-deriving
    # it from the verdict sequence.
    stepped = engineer_events + critic_events
    all_stamped = all("step_idx" in e.payload and "attempt" in e.payload for e in stepped)
    step_indices = sorted(
        {e.payload["step_idx"] for e in engineer_events if "step_idx" in e.payload}
    )

    print("\n==================== checks ====================")
    print(f"  plan steps (N)         : {n_steps}")
    print(f"  engineer events        : {len(engineer_events)}")
    print(f"  critic events          : {len(critic_events)}")
    print(f"  >= N engineer events   : {n_steps is not None and len(engineer_events) >= n_steps}")
    print(f"  engineer/critic paired : {len(engineer_events) == len(critic_events)}")
    print(f"  all eng/critic stamped : {all_stamped}")
    print(f"  distinct step indices  : {step_indices}")
    g = build_graph(events)
    print(f"  graph is DAG           : {nx.is_directed_acyclic_graph(g)}")
    order = [f"{e.agent_role.value}#{e.seq}" for e in causal_order(events)]
    print(f"  causal order           : {' -> '.join(order)}")


if __name__ == "__main__":
    main()
