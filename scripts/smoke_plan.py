"""Step 3a smoke test: planner emits a parseable structured plan.

Run:
    uv run python scripts/smoke_plan.py

Runs the real planner on the toy task and confirms its output parses into an
ordered list of sub-tasks via parse_plan. No controller yet -- this only checks
that we can reliably get a step list out of the planner.

Makes one real LLM call. Success: parse_plan returns >= 2 steps, each a
non-empty sub-task string.
"""

from __future__ import annotations

from autogen import UserProxyAgent

from traj_eval.agents import build_llm_config, make_planner, parse_plan
from traj_eval.agents.plan import PlanParseError

TOY_TASK = "Compute the 12th Fibonacci number (with F(1)=F(2)=1)."


def main() -> None:
    llm_config = build_llm_config()
    planner = make_planner(llm_config)

    driver = UserProxyAgent(
        name="user",
        human_input_mode="NEVER",
        code_execution_config=False,
        max_consecutive_auto_reply=0,
    )

    result = driver.initiate_chat(
        recipient=planner,
        message=TOY_TASK,
        max_turns=1,
        summary_method="last_msg",
    )

    planner_text = result.summary

    print("\n==================== RAW PLANNER OUTPUT ====================")
    print(planner_text)

    print("\n==================== PARSED PLAN ====================")
    try:
        plan = parse_plan(planner_text)
    except PlanParseError as e:
        print(f"PARSE FAILED: {e}")
        return

    print(f"parsed {len(plan)} steps:")
    for i, step in enumerate(plan.steps):
        print(f"  [{i}] {step}")

    print("\nchecks:")
    print(f"  >= 2 steps          : {len(plan) >= 2}")
    print(f"  all non-empty       : {all(s.strip() for s in plan.steps)}")
    print(f"  no answer leaked(144): {'144' not in planner_text}")


if __name__ == "__main__":
    main()
