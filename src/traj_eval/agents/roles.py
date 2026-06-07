"""The four-role agents for the multi-agent configuration (Methodology §4.1).

Roles are added one at a time and exercised in the smallest context where each
is actually testable. Step 1a: planner only.

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
