"""Step 1b smoke test: planner -> engineer hand-off.

Run:
    uv run python scripts/smoke_handoff.py

Uses AG2's sequential-chat pattern: a driver runs two chained chats. The first
produces the plan (planner); the second carries that plan over as context to
the engineer, who works it through to a final answer. We use the carryover
mechanism so the engineer literally receives the planner's output as context.

This makes real LLM calls and is meant to be eyeballed, not asserted in pytest.
Success: the planner emits a plan (no final number), and the engineer then
works it through and ends with `FINAL: 144`.
"""

from __future__ import annotations

from autogen import UserProxyAgent

from traj_eval.agents import build_llm_config, make_engineer, make_planner

TOY_TASK = "Compute the 12th Fibonacci number (with F(1)=F(2)=1)."


def main() -> None:
    llm_config = build_llm_config()
    planner = make_planner(llm_config)
    engineer = make_engineer(llm_config)

    # Driver relays the task and chains the two chats. It runs no LLM itself.
    driver = UserProxyAgent(
        name="user",
        human_input_mode="NEVER",
        code_execution_config=False,
        max_consecutive_auto_reply=0,
    )

    # Sequential chats: the summary of chat 1 (the plan) is carried over into
    # chat 2 as context for the engineer. max_turns=1 each => one reply apiece,
    # no back-and-forth yet (that arrives once the critic exists in 1c).
    results = driver.initiate_chats(
        [
            {
                "recipient": planner,
                "message": TOY_TASK,
                "max_turns": 1,
                "summary_method": "last_msg",
            },
            {
                "recipient": engineer,
                "message": (
                    "Here is the task and the planner's plan (in the context). "
                    f"Carry out the plan to solve: {TOY_TASK}"
                ),
                "max_turns": 1,
                "summary_method": "last_msg",
            },
        ]
    )

    print("\n==================== SUMMARIES ====================")
    for i, r in enumerate(results):
        print(f"\n--- chat {i} summary ---\n{r.summary}")


if __name__ == "__main__":
    main()
