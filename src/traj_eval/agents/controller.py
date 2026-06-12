"""Per-step controller (Phase 3, Step 3b).

Replaces the single-pass flow (planner -> engineer -> critic -> executor) with a
controller that walks the planner's structured plan one sub-task at a time:

    planner -> engineer(step 0) -> engineer(step 1) -> ... -> engineer(step N-1) -> END

The executor is intentionally absent from this flow (kept as a role/factory for
later reuse, but not wired here). The critic is added per-step in 3b's successor
(3c); 3b is engineer-only per step, to isolate "does the controller walk the
plan and materialise one engineer event per step" before adding the gate.

How a sub-task reaches the engineer: AG2 chooses *who* speaks, not *what* they
are told. So an ``update_agent_state`` hook on the engineer rewrites its system
message to focus on the current sub-task immediately before each of its turns.
The controller owns ``current_step``; the hook reads it.

The plan is parsed from the planner's own message on the first transition, so
the controller depends only on the planner emitting <step> tags (Step 3a).
"""

from __future__ import annotations

from autogen import GroupChat, GroupChatManager, LLMConfig, UserProxyAgent

from traj_eval.agents.plan import Plan, parse_plan
from traj_eval.agents.roles import ENGINEER_SYSTEM_MESSAGE, make_engineer, make_planner
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


class _StepState:
    """Controller state shared between the selector and the engineer hook."""

    def __init__(self) -> None:
        self.plan: Plan | None = None
        self.current_step: int = 0


def build_stepped_team(
    llm_config: LLMConfig,
    *,
    max_round: int = 40,
    ledger: RoutingLedger | None = None,
) -> tuple[GroupChatManager, UserProxyAgent, GroupChat]:
    """Build a per-step team: planner then engineer once per plan sub-task.

    Returns (manager, user_proxy, groupchat). Start with
    ``user_proxy.initiate_chat(manager, message=task)``.

    The plan is parsed from the planner's first message. If it has N steps, the
    engineer speaks N times, once per step, each time focused on that sub-task.
    """
    planner = make_planner(llm_config)
    engineer = make_engineer(llm_config)

    user = UserProxyAgent(
        name="user",
        human_input_mode="NEVER",
        code_execution_config=False,
        max_consecutive_auto_reply=0,
    )

    agents = [user, planner, engineer]
    state = _StepState()

    def _focus_engineer_on_step() -> None:
        """update_agent_state hook: point the engineer at the current sub-task."""
        if state.plan is None:
            return
        idx = state.current_step
        if idx >= len(state.plan):
            return
        engineer.update_system_message(
            _STEP_INSTRUCTION.format(
                idx=idx + 1,
                total=len(state.plan),
                subtask=state.plan[idx],
                base=ENGINEER_SYSTEM_MESSAGE,
            )
        )

    engineer.register_hook("update_agent_state", lambda *a, **k: _focus_engineer_on_step())

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
            # Parse the plan from the planner's message; start at step 0.
            state.plan = parse_plan(_last_content(groupchat))
            state.current_step = 0
            return _route_to(engineer, AgentRole.PLANNER)

        if name == AgentRole.ENGINEER.value:
            # Engineer just finished the current step; advance.
            state.current_step += 1
            if state.plan is not None and state.current_step < len(state.plan):
                # Next step is caused by the previous engineer step (the chain
                # of work); single-parent, same as 2b.
                return _route_to(engineer, AgentRole.ENGINEER)
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
