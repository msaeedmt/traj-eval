"""Per-step controller (Phase 3, Steps 3b-3c).

Replaces the single-pass flow with a controller that walks the planner's
structured plan one sub-task at a time, gating each step through a critic:

    planner
      -> [ engineer(step i) -> critic(step i)
             APPROVE -> advance to step i+1
             REJECT  -> engineer(step i) again, up to max_repairs (step-local) ]
      -> END after the last step is approved (or its repair budget is spent)

The executor is intentionally absent (kept as a role/factory for later reuse).
The critic here is a *performance aid* for the engineer, not an anchor oracle;
anchor validation is a separate, later layer (Lean kernel / forward model).

How a sub-task reaches the engineer and critic: AG2 chooses *who* speaks, not
*what* they are told. So ``update_agent_state`` hooks on the engineer and the
critic rewrite their system messages to focus on the current sub-task right
before each of their turns. The controller owns ``current_step`` and a
per-step ``repairs`` counter that RESETS when advancing (perseveration is
per-step, not global).

Edges are single-parent (Step 2b rule): a step's re-attempt is caused by that
step's critic rejection. The engineer self-edge (revision also depending on its
own prior attempt) is deferred to a later step.
"""

from __future__ import annotations

from autogen import GroupChat, GroupChatManager, LLMConfig, UserProxyAgent

from traj_eval.agents.markers import VERDICT_REJECT
from traj_eval.agents.plan import Plan, parse_plan
from traj_eval.agents.roles import (
    CRITIC_SYSTEM_MESSAGE,
    ENGINEER_SYSTEM_MESSAGE,
    make_critic,
    make_engineer,
    make_planner,
)
from traj_eval.agents.routing import RoutingLedger
from traj_eval.trace_core.schema import AgentRole


def _role_for_agent(agent) -> AgentRole:
    try:
        return AgentRole(agent.name)
    except ValueError:
        return AgentRole.SYSTEM


def _last_content(groupchat: GroupChat) -> str:
    if not groupchat.messages:
        return ""
    return groupchat.messages[-1].get("content", "") or ""


# Engineer instruction for one sub-task. The base engineer prompt is appended so
# its FINAL-marker convention and "show your work" rules still apply.
_STEP_INSTRUCTION = """\
You are working on ONE sub-task of a larger plan, not the whole task.

Current sub-task (step {idx} of {total}):
{subtask}

Do only this sub-task. Show your work. If this is the final step, end with the
FINAL: marker as usual; otherwise end your message with the result of this
sub-task so the next step can build on it.

--- base engineer instructions ---
{base}
"""

# Critic instruction for one sub-task: judge the engineer's step against THIS
# sub-task, not the whole task. The base critic prompt is appended so its
# correctness-only, VERDICT-marker rules still apply.
_CRITIC_STEP_INSTRUCTION = """\
You are reviewing ONE sub-task of a larger plan, not the whole task.

Current sub-task (step {idx} of {total}):
{subtask}

Judge ONLY whether the engineer correctly completed THIS sub-task. Do not
penalise the engineer for not having done later steps.

--- base critic instructions ---
{base}
"""


class _StepState:
    """Controller state shared between the selector and the focus hooks."""

    def __init__(self) -> None:
        self.plan: Plan | None = None
        self.current_step: int = 0
        self.repairs: int = 0  # repairs used on the CURRENT step; resets on advance


def build_stepped_team(
    llm_config: LLMConfig,
    *,
    max_repairs: int = 2,
    max_round: int = 60,
    ledger: RoutingLedger | None = None,
) -> tuple[GroupChatManager, UserProxyAgent, GroupChat]:
    """Build a per-step team: planner, then engineer->critic per plan sub-task.

    Returns (manager, user_proxy, groupchat). Start with
    ``user_proxy.initiate_chat(manager, message=task)``.

    Each step runs engineer -> critic; APPROVE advances, REJECT re-runs the
    engineer on the same step up to ``max_repairs`` (counted per step). If the
    repair budget is spent without approval, the controller advances anyway
    (a per-step perseveration outcome) rather than stalling.
    """
    planner = make_planner(llm_config)
    engineer = make_engineer(llm_config)
    critic = make_critic(llm_config)

    user = UserProxyAgent(
        name="user",
        human_input_mode="NEVER",
        code_execution_config=False,
        max_consecutive_auto_reply=0,
    )

    agents = [user, planner, engineer, critic]
    state = _StepState()

    def _focus_engineer() -> None:
        if state.plan is None or state.current_step >= len(state.plan):
            return
        engineer.update_system_message(
            _STEP_INSTRUCTION.format(
                idx=state.current_step + 1,
                total=len(state.plan),
                subtask=state.plan[state.current_step],
                base=ENGINEER_SYSTEM_MESSAGE,
            )
        )

    def _focus_critic() -> None:
        if state.plan is None or state.current_step >= len(state.plan):
            return
        critic.update_system_message(
            _CRITIC_STEP_INSTRUCTION.format(
                idx=state.current_step + 1,
                total=len(state.plan),
                subtask=state.plan[state.current_step],
                base=CRITIC_SYSTEM_MESSAGE,
            )
        )

    engineer.register_hook("update_agent_state", lambda *a, **k: _focus_engineer())
    critic.register_hook("update_agent_state", lambda *a, **k: _focus_critic())

    def _route_to(next_agent, cause_role: AgentRole):
        if ledger is not None:
            cause = ledger.latest_event_id(cause_role)
            ledger.record_routing(_role_for_agent(next_agent), [cause] if cause else [])
        return next_agent

    def select_next(last_speaker, groupchat: GroupChat):
        name = last_speaker.name

        if name == "user":
            return _route_to(planner, AgentRole.SYSTEM)

        if name == AgentRole.PLANNER.value:
            state.plan = parse_plan(_last_content(groupchat))
            state.current_step = 0
            state.repairs = 0
            return _route_to(engineer, AgentRole.PLANNER)

        if name == AgentRole.ENGINEER.value:
            # Engineer finished (an attempt at) the current step; critic reviews.
            return _route_to(critic, AgentRole.ENGINEER)

        if name == AgentRole.CRITIC.value:
            content = _last_content(groupchat).upper()
            rejected = VERDICT_REJECT in content

            if rejected and state.repairs < max_repairs:
                # Step-local repair: re-run the engineer on the SAME step.
                state.repairs += 1
                return _route_to(engineer, AgentRole.CRITIC)

            # Approved, or repair budget spent, or malformed verdict: advance.
            state.current_step += 1
            state.repairs = 0  # reset per-step budget
            if state.plan is not None and state.current_step < len(state.plan):
                # Next step's engineer is caused by this critic's verdict (the
                # event that triggered the advance). Single-parent (2b rule).
                return _route_to(engineer, AgentRole.CRITIC)
            return None  # all steps done

        return None

    groupchat = GroupChat(
        agents=agents,
        messages=[],
        max_round=max_round,
        speaker_selection_method=select_next,
    )
    manager = GroupChatManager(groupchat=groupchat, llm_config=llm_config)
    return manager, user, groupchat
