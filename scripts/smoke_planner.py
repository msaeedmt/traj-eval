"""Step 1a smoke test: does the planner spin up and reply in-role?

Run:
    uv run python scripts/smoke_planner.py

Expects OPENAI_API_KEY (and optionally OPENAI_BASE_URL, TRAJ_EVAL_MODEL) in the
environment. This makes a real LLM call. It is NOT a pytest unit test — it hits
a live endpoint and is meant to be eyeballed: confirm the planner returns a
numbered plan and does NOT just hand back the final number.
"""

from __future__ import annotations

from autogen import UserProxyAgent

from traj_eval.agents import build_llm_config, make_planner

TOY_TASK = "Compute the 12th Fibonacci number (with F(1)=F(2)=1)."


def main() -> None:
    llm_config = build_llm_config()
    planner = make_planner(llm_config)

    # Minimal driver: sends the task, takes exactly one planner reply, stops.
    # No code execution, no LLM on this side — it only relays the task.
    user = UserProxyAgent(
        name="user",
        human_input_mode="NEVER",
        code_execution_config=False,
        max_consecutive_auto_reply=0,
    )

    user.initiate_chat(
        recipient=planner,
        message=TOY_TASK,
        max_turns=1,
    )


if __name__ == "__main__":
    main()
