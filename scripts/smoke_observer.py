"""Step 2a smoke test: attach the observer to the four-role team.

Run:
    uv run python scripts/smoke_observer.py

Runs the toy task twice on the same team setup:
  1. WITHOUT the observer  -> record the speaker order and final answer;
  2. WITH the observer      -> record the same, plus write a trial log.

Then it checks the two properties that make Step 2a meaningful:
  * NON-INVASIVENESS: the speaker order is identical with and without the
    observer. (The observer must not change what the team does.)
  * LOG COMPLETENESS: the written log reloads via read_trial, every record is
    schema-valid, seq is contiguous from 0, and there is one MESSAGE event per
    agent message observed.

No causal edges are checked here -- caused_by is empty by design until 2b.
Makes real LLM calls; the verification is printed at the end.
"""

from __future__ import annotations

from pathlib import Path

from traj_eval.agents import (
    TraceObserver,
    build_llm_config,
    build_team,
    make_trial_meta,
)
from traj_eval.trace_core.storage import TrialLogWriter, read_trial

TOY_TASK = "Compute the 12th Fibonacci number (with F(1)=F(2)=1)."
LOG_PATH = Path("runs/smoke_observer_trial.jsonl")


def _run(observer_attached: bool) -> list[str]:
    """Run the toy task once; return the speaker order. Writes a log iff
    observer_attached."""
    llm_config = build_llm_config()
    manager, user, groupchat = build_team(llm_config, max_repairs=2)

    writer = None
    if observer_attached:
        meta = make_trial_meta(
            trial_id="smoke_observer_trial",
            task_id="fib12",
            backbone="gpt-4o-mini",
        )
        writer = TrialLogWriter(LOG_PATH, meta)
        observer = TraceObserver(writer, trial_id="smoke_observer_trial")
        # Attach to the four role agents (the user proxy's opening message is
        # orchestration; role-agent messages are the 2a scope).
        role_agents = [a for a in groupchat.agents if a.name != "user"]
        observer.attach(role_agents)

    user.initiate_chat(manager, message=TOY_TASK)

    if writer is not None:
        writer.close()

    return [m.get("name", "?") for m in groupchat.messages]


def main() -> None:
    print("=== Run 1: WITHOUT observer ===")
    order_plain = _run(observer_attached=False)

    print("\n=== Run 2: WITH observer ===")
    order_observed = _run(observer_attached=True)

    print("\n==================== VERIFICATION ====================")

    # 1. Non-invasiveness: same speaker order both runs.
    # (Role-agent subsequence, since the observer only watches role agents.)
    roles_plain = [n for n in order_plain if n != "user"]
    roles_observed = [n for n in order_observed if n != "user"]
    invasive_ok = roles_plain == roles_observed
    print(f"non-invasive (same speaker order): {invasive_ok}")
    print(f"  without: {roles_plain}")
    print(f"  with   : {roles_observed}")

    # 2. Log completeness + validity: reload and check.
    meta, events = read_trial(LOG_PATH)
    seqs = [e.seq for e in events]
    seq_contiguous = seqs == list(range(len(events)))
    all_messages = all(e.event_type.value == "message" for e in events)
    print(f"log reloads & validates: True ({len(events)} events)")
    print(f"  seq contiguous from 0 : {seq_contiguous}  ({seqs})")
    print(f"  all MESSAGE events    : {all_messages}")
    print(f"  trial_id matches meta : {all(e.trial_id == meta.trial_id for e in events)}")
    print(f"  caused_by empty (2a)  : {all(e.caused_by == [] for e in events)}")

    # Number of observed events should equal number of role-agent messages.
    n_role_msgs = len(roles_observed)
    print(
        f"  events == role msgs   : {len(events) == n_role_msgs} ({len(events)} vs {n_role_msgs})"
    )

    print("\nRoles captured (in seq order):")
    for e in events:
        print(f"  [{e.seq}] {e.agent_role.value:9s} -> {e.payload.get('recipient', '?')}")


if __name__ == "__main__":
    main()
