"""Step 1c smoke test: planner -> engineer -> critic (terminal judge).

Run:
    uv run python scripts/smoke_review.py                # honest run -> APPROVE
    uv run python scripts/smoke_review.py --inject-error # planted wrong answer -> REJECT

Extends the 1b sequential chain by one chat: the engineer's worked solution is
carried over to the critic, who issues a single approve/reject verdict and the
chain stops (terminal). No revision loop yet -- that arrives in 1d with the
executor/repairer.

The --inject-error flag replaces the engineer's solution with a deliberately
wrong one (FINAL: 143) so you can confirm the critic actually *judges* rather
than rubber-stamping. This makes real LLM calls; eyeball the output.

Success:
  * honest run  -> critic ends with `VERDICT: APPROVE`
  * injected run -> critic ends with `VERDICT: REJECT - <reason>` and the
    reason points at the wrong arithmetic, not something spurious.
"""

from __future__ import annotations

import argparse

from autogen import UserProxyAgent

from traj_eval.agents import (
    build_llm_config,
    make_critic,
    make_engineer,
    make_planner,
)

TOY_TASK = "Compute the 12th Fibonacci number (with F(1)=F(2)=1)."

# A plausible-looking but WRONG worked solution, used only with --inject-error.
# The error is in the last step (89 + 55 = 143 instead of 144); everything
# before it is correct, so a rubber-stamping critic would miss it.
WRONG_SOLUTION = """\
Working through the recurrence with F(1)=F(2)=1:
- F(3)=2, F(4)=3, F(5)=5, F(6)=8, F(7)=13, F(8)=21, F(9)=34, F(10)=55, F(11)=89
- F(12) = F(11) + F(10) = 89 + 55 = 143
FINAL: 143
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--inject-error",
        action="store_true",
        help="Feed the critic a planted wrong solution to test rejection.",
    )
    args = parser.parse_args()

    llm_config = build_llm_config()
    planner = make_planner(llm_config)
    engineer = make_engineer(llm_config)
    critic = make_critic(llm_config)

    driver = UserProxyAgent(
        name="user",
        human_input_mode="NEVER",
        code_execution_config=False,
        max_consecutive_auto_reply=0,
    )

    if args.inject_error:
        # Skip the real engineer; hand the critic a known-wrong solution so the
        # test exercises the critic's judgment in isolation.
        review_message = (
            "Review the following solution to the task "
            f"'{TOY_TASK}'. Decide if it is correct.\n\n{WRONG_SOLUTION}"
        )
        results = driver.initiate_chats(
            [
                {
                    "recipient": critic,
                    "message": review_message,
                    "max_turns": 1,
                    "summary_method": "last_msg",
                },
            ]
        )
    else:
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
                        "Here is the task and the planner's plan (in the "
                        f"context). Carry out the plan to solve: {TOY_TASK}"
                    ),
                    "max_turns": 1,
                    "summary_method": "last_msg",
                },
                {
                    "recipient": critic,
                    "message": (
                        "Review the engineer's solution (in the context) to the "
                        f"task '{TOY_TASK}' and issue a verdict."
                    ),
                    "max_turns": 1,
                    "summary_method": "last_msg",
                },
            ]
        )

    print("\n==================== VERDICT (last chat summary) ====================")
    print(results[-1].summary)


if __name__ == "__main__":
    main()
