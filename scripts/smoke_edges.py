"""Step 2b smoke test: routing-derived caused_by edges on a live run.

Run:
    uv run python scripts/smoke_edges.py

Wires a RoutingLedger through both build_team and the TraceObserver, runs the
toy task, then loads the trial log, builds the graph with the project's own
graph.py, and prints the caused_by chain so you can see real edges produced on
your endpoint (not just the stub-driven unit check).

Two scenarios:
  1. APPROVE path  -- normal Fibonacci task; expect a clean chain
     planner -> engineer -> critic -> executor, each pointing at its cause.
  2. REJECT loop   -- a task whose stated answer is wrong, so the critic
     rejects and the repair loop fires; expect the SECOND engineer event to
     point at the critic's REJECT event (the discriminating edge).

The reject scenario depends on the critic actually rejecting; with a small
backbone it usually does, but if it approves the wrong answer the loop won't
fire (that itself is a finding about critic reliability, not a tracer bug).

Makes real LLM calls; the edge report prints at the end.
"""

from __future__ import annotations

from pathlib import Path

import networkx as nx

from traj_eval.agents import (
    RoutingLedger,
    TraceObserver,
    build_llm_config,
    build_team,
    make_trial_meta,
)
from traj_eval.trace_core.graph import build_graph, causal_order
from traj_eval.trace_core.storage import TrialLogWriter, read_trial

APPROVE_TASK = "Compute the 12th Fibonacci number (with F(1)=F(2)=1)."

# A task that asserts a false answer, to provoke a critic rejection and exercise
# the repair loop. The engineer is told the (wrong) expected value; a correct
# critic rejects, the engineer revises, the critic then approves.
REJECT_TASK = (
    "Compute the 12th Fibonacci number (with F(1)=F(2)=1). "
    "A colleague claims the answer is 143. State whether that is correct and "
    "give the correct value with full working."
)


def _run(task: str, tag: str) -> Path:
    """Run one task with ledger + observer; return the log path."""
    llm_config = build_llm_config()
    ledger = RoutingLedger()
    manager, user, groupchat = build_team(llm_config, max_repairs=2, ledger=ledger)

    log_path = Path(f"runs/smoke_edges_{tag}.jsonl")
    meta = make_trial_meta(trial_id=f"smoke_edges_{tag}", task_id=tag, backbone="gpt-4o-mini")
    writer = TrialLogWriter(log_path, meta)
    observer = TraceObserver(writer, trial_id=f"smoke_edges_{tag}", ledger=ledger)

    role_agents = [a for a in groupchat.agents if a.name != "user"]
    observer.attach(role_agents)

    user.initiate_chat(manager, message=task)
    writer.close()
    return log_path


def _report(log_path: Path, tag: str) -> None:
    meta, events = read_trial(log_path)
    idmap = {e.event_id: f"{e.agent_role.value}#{e.seq}" for e in events}

    print(f"\n==================== {tag}: caused_by chain ====================")
    for e in events:
        parents = [idmap.get(p, p[:8]) for p in e.caused_by]
        text = e.payload.get("text", "").replace("\n", " ")[:40]
        print(f"  {e.agent_role.value:9s}#{e.seq}  caused_by={parents}  | {text!r}")

    g = build_graph(events)
    is_dag = nx.is_directed_acyclic_graph(g)
    print(f"  graph is DAG: {is_dag}")

    order = [f"{e.agent_role.value}#{e.seq}" for e in causal_order(events)]
    print(f"  causal order: {' -> '.join(order)}")

    # If a repair loop happened, surface the discriminating edge.
    engineers = [e for e in events if e.agent_role.value == "engineer"]
    if len(engineers) >= 2:
        second = engineers[1]
        crit_rejects = [
            e for e in events if e.agent_role.value == "critic" and e.event_id in second.caused_by
        ]
        if crit_rejects:
            print(
                f"  >> repair edge: 2nd engineer#{second.seq} points at "
                f"critic#{crit_rejects[0].seq} (the rejection) -- correct"
            )
        else:
            print(
                f"  >> 2nd engineer#{second.seq} caused_by={second.caused_by} "
                f"(no critic parent found)"
            )
    else:
        print("  >> no repair loop this run (critic approved first attempt)")


def main() -> None:
    print("=== Scenario 1: APPROVE path ===")
    p1 = _run(APPROVE_TASK, "approve")
    _report(p1, "approve")

    print("\n=== Scenario 2: REJECT loop ===")
    p2 = _run(REJECT_TASK, "reject")
    _report(p2, "reject")


if __name__ == "__main__":
    main()
