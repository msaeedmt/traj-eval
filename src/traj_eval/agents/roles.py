"""The four-role agents for the multi-agent configuration (Methodology §4.1).

Roles are added one at a time and exercised in the smallest context where each
is actually testable. Step 1a: planner. Step 1b: + engineer.
Step 1c: + critic (terminal judge). Step 1d: + executor/repairer and the
four-role group chat with the genuine repair loop (critic REJECT -> engineer).

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

Your one job is to turn the task into a short, ordered plan of sub-tasks that an
engineer will carry out one at a time, each reviewed by a critic. You decompose
and sequence; you do NOT solve, compute, or write final code yourself.

Output format (REQUIRED): emit each sub-task wrapped in <step> and </step> tags,
one per sub-task, in order. Put nothing essential outside the tags. Example:

<step>First sub-task described as a single concrete action.</step>
<step>Second sub-task that builds on the first.</step>
<step>Final sub-task that produces the answer.</step>

Rules:
- Each <step> is one concrete sub-task. A sub-task may span multiple lines.
- Match the number of steps to what the task genuinely requires. A simple task
  may need just ONE step; only decompose into more when separate steps each do
  substantive, distinct work that a single step could not. Do NOT pad: never
  split one natural action into several steps (e.g. "compute X", "store X",
  "print X" is one step, not three), and do not add steps merely to reach a
  count. Prefer the fewest steps that still capture the real structure of the
  work; use more only when the task is genuinely complex enough to benefit.
- Order steps so each builds on the previous.
- Do NOT compute the final answer yourself. If tempted to give the answer,
  instead describe the sub-task that would produce it.
- The last step should be the one that yields the final result.
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


CRITIC_SYSTEM_MESSAGE = """\
You are the CRITIC / REVIEWER in a multi-agent scientific-reasoning team.

You receive the engineer's worked solution (it arrives as context). Your job is
to judge ONE thing: is the final answer correct, and is it reached through sound
steps?

The verdict depends ONLY on correctness, never on style. Read this carefully:
- APPROVE if the final answer is correct AND no step contains a real error
  (wrong value, invalid inference, unjustified leap). If the work is correct,
  you MUST approve it, even if it is verbose, inefficient, awkwardly ordered, or
  could be presented more clearly. Style, efficiency, and presentation are NOT
  grounds for rejection.
- REJECT only if there is a concrete correctness error: a wrong intermediate
  value, a step that does not follow, or a final answer that is wrong. Name the
  exact step and what is wrong with it.

You may add a brief stylistic remark if you like, but it must not change an
otherwise-correct APPROVE into a REJECT. "Convoluted", "inefficient", or "could
be clearer" are never by themselves reasons to reject.

Do NOT redo the whole solution or produce a new plan. You judge; you do not
author.

End your reply with exactly one of these clearly-marked lines:
      VERDICT: APPROVE
      VERDICT: REJECT - <one-line reason naming the incorrect step>
"""


def make_critic(llm_config: LLMConfig) -> ConversableAgent:
    """Create the critic / reviewer agent.

    Terminal judge in Step 1c: it issues a single approve/reject verdict on the
    engineer's solution and the chain stops. The machine-readable VERDICT line
    mirrors the engineer's FINAL convention so the observer (Step 2) and the O2
    detectors can read the decision without parsing prose. The genuine
    critic->engineer revision loop is deferred to 1d with the executor/repairer.
    """
    return ConversableAgent(
        name=AgentRole.CRITIC.value,
        system_message=CRITIC_SYSTEM_MESSAGE,
        llm_config=llm_config,
        human_input_mode="NEVER",
    )


EXECUTOR_SYSTEM_MESSAGE = """\
You are the EXECUTOR / REPAIRER in a multi-agent scientific-reasoning team.

You are the final stage of the workflow: run loop. You act in two situations.

1. After the critic APPROVES: "run" the engineer's solution and report the
   result. (No real execution environment is wired yet, so simulate it: state
   what running the solution produces and confirm whether it matches the
   engineer's FINAL answer.) Then end your reply with:
       EXECUTION: OK - <the confirmed final answer>

2. After the critic REJECTS and the engineer has revised: you do not repair the
   reasoning yourself; the engineer re-authors. Your job is only to run and
   report. If a run fails, describe the failure concretely so the engineer can
   fix it, and end with:
       EXECUTION: FAIL - <what went wrong>

Rules:
- You run and report; you do not re-plan and you do not re-derive the solution
  from scratch.
- Always end with exactly one EXECUTION: line so the result is machine-readable.
"""


def make_executor(llm_config: LLMConfig) -> ConversableAgent:
    """Create the executor / repairer agent.

    Owns the "run loop" stage. On the toy task it simulates execution and
    confirms the approved answer; once a real sandbox is wired (later step) it
    will execute code / submit proofs for real and emit EXECUTION_RESULT events.
    The EXECUTION: line mirrors the FINAL / VERDICT conventions for the observer.
    """
    return ConversableAgent(
        name=AgentRole.EXECUTOR.value,
        system_message=EXECUTOR_SYSTEM_MESSAGE,
        llm_config=llm_config,
        human_input_mode="NEVER",
    )
