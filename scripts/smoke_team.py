"""Step 1d smoke test: full four-role team with the workflow loop.

Run:
    uv run python scripts/smoke_team.py

Runs planner -> engineer -> critic -> executor on the toy task, with the
deterministic speaker-selection loop. On a correct solution the critic should
APPROVE and the executor should confirm, terminating cleanly. If the critic
rejects, the engineer revises and the critic re-checks, up to max_repairs.

Makes real LLM calls; eyeball the transcript.

Success:
  * the four roles speak in workflow order (planner, engineer, critic, executor);
  * the run terminates on its own (not by hitting max_round);
  * the executor ends with `EXECUTION: OK - 144`.
"""

from __future__ import annotations

from traj_eval.agents import build_llm_config, build_team

TOY_TASK = "Compute the 12th Fibonacci number (with F(1)=F(2)=1)."


def main() -> None:
    llm_config = build_llm_config()
    manager, user, groupchat = build_team(llm_config, max_repairs=2)

    user.initiate_chat(manager, message=TOY_TASK)

    print("\n==================== SPEAKER ORDER ====================")
    order = [m.get("name", "?") for m in groupchat.messages]
    print(" -> ".join(order))


if __name__ == "__main__":
    main()
