"""The four-role agents for the multi-agent configuration (Methodology §4.1).

Roles are added one at a time and exercised in the smallest context where each
is actually testable. Step 1a: planner. Step 1b: + engineer.

The role *names* deliberately mirror ``traj_eval.trace_core.schema.AgentRole``
so that when the observer (Step 2) tags events, an agent's name maps onto its
schema role with no translation table. We pin the agent's ``name`` to the
enum's string value for exactly that reason.
"""

from __future__ import annotations

from autogen import ConversableAgent, LLMConfig

from traj_eval.trace_core.schema import AgentRole

PLANNER_SYSTEM_MESSAGE = """\
You are the PLANNER in a multi-agent scientific-reasoning team.

Your one job is to turn the task into a short, ordered plan of steps that other
agents (an engineer, a critic, an executor) will carry out. You decompose and
sequence; you do NOT solve, compute, or write final code yourself.

Rules:
- Output a numbered list of concrete steps, each a single action.
- Keep it to at most 5 steps.
- Do not compute the final answer. If you are tempted to give the answer,
  instead describe the step that would produce it.
- Be explicit about which step verifies the result.
"""


def make_planner(llm_config: LLMConfig) -> ConversableAgent:
    """Create the planner agent.

    ``human_input_mode='NEVER'`` so it runs unattended; the agent name is the
    schema role string, keeping agent identity and trace role aligned.
    """
    return ConversableAgent(
        name=AgentRole.PLANNER.value,
        system_message=PLANNER_SYSTEM_MESSAGE,
        llm_config=llm_config,
        human_input_mode="NEVER",
    )


ENGINEER_SYSTEM_MESSAGE = """\
You are the ENGINEER / FORMALISER in a multi-agent scientific-reasoning team.

You receive a plan from the planner (it arrives as context). Your job is to
carry out that plan and produce a concrete, worked solution to the task.

Rules:
- Follow the plan's steps in order. Show the intermediate work, not just the
  final value, so the critic can check each step.
- For a computation, lay out the values you compute along the way.
- End your reply with a single clearly-marked final line:
      FINAL: <the answer>
- Do not invent a new plan; if the plan is unclear, do your best with it and
  note the ambiguity. Planning is the planner's job, not yours.
"""


def make_engineer(llm_config: LLMConfig) -> ConversableAgent:
    """Create the engineer / formaliser agent.

    Named with the schema role string for trace alignment, same as the planner.
    In Step 1b it consumes the planner's plan via the sequential-chat carryover
    mechanism and produces the worked answer.
    """
    return ConversableAgent(
        name=AgentRole.ENGINEER.value,
        system_message=ENGINEER_SYSTEM_MESSAGE,
        llm_config=llm_config,
        human_input_mode="NEVER",
    )
