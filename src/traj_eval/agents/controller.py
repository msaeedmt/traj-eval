"""Per-step controller (Phase 3, Steps 3b-3c; Phase 4, Step 4d).

Replaces the single-pass flow with a controller that walks the planner's
structured plan one sub-task at a time, gating each step through a critic:

    planner
      -> [ engineer(step i)
             -> [ tool call? -> executor runs it -> engineer reacts ]*  (4d)
             -> critic(step i)
                  APPROVE -> advance to step i+1
                  REJECT  -> engineer(step i) again, up to max_repairs ]
      -> END after the last step is approved (or its repair budget is spent)

In-loop compiler (Step 4d, opt-in via ``lean_tool``): the engineer is given a
deterministic checker as an AG2 tool (``register_function`` with the engineer
as caller and a mechanical ``executor`` proxy as runner -- this restores the
proposal's executor role, now as plumbing rather than a reasoning agent). When
the engineer suggests a call, the selector routes to the executor, then back to
the engineer to react to the result; this engineer<->executor loop is bounded
per step by ``max_tool_calls`` so it cannot spin. Only when the engineer
returns a plain (non-tool) message does the critic review. With no ``lean_tool``
the executor is absent and behaviour is identical to Steps 3b-3c.

Note the compiler is now IN the loop (agents use it to solve the task); it is
no longer an independent anchor oracle. Correctness ground truth moves to an
offline validator over the final trace (Phase 4 metrics), not this loop.

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

from collections.abc import Callable
from typing import Any

from autogen import (
    GroupChat,
    GroupChatManager,
    LLMConfig,
    UserProxyAgent,
    register_function,
)

from traj_eval.agents.markers import VERDICT_REJECT
from traj_eval.agents.observer import StepContext
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


def _last_message(groupchat: GroupChat) -> dict[str, Any]:
    if not groupchat.messages:
        return {}
    return groupchat.messages[-1]


def _last_content(groupchat: GroupChat) -> str:
    return _last_message(groupchat).get("content", "") or ""


def _is_tool_call(message: dict[str, Any]) -> bool:
    """True if the engineer's last message suggested a tool call.

    Same shape the observer classifies as TOOL_CALL (Step 4c); checked here so
    the selector can route a suggested call to the executor instead of the
    critic. Reading the message, not the role, keeps the two in lockstep.
    """
    return bool(message.get("tool_calls"))


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
        self.tool_calls: int = 0  # tool calls used on the CURRENT step; resets on advance


def build_stepped_team(
    llm_config: LLMConfig,
    *,
    max_repairs: int = 2,
    max_round: int = 60,
    ledger: RoutingLedger | None = None,
    step_context: StepContext | None = None,
    lean_tool: Callable[..., Any] | None = None,
    tool_name: str = "check_lean",
    tool_description: str = (
        "Type-check Lean 4 source and report compile status, errors, and remaining sorries."
    ),
    max_tool_calls: int = 4,
) -> tuple[GroupChatManager, UserProxyAgent, GroupChat]:
    """Build a per-step team: planner, then engineer->critic per plan sub-task.

    Returns (manager, user_proxy, groupchat). Start with
    ``user_proxy.initiate_chat(manager, message=task)``.

    Each step runs engineer -> critic; APPROVE advances, REJECT re-runs the
    engineer on the same step up to ``max_repairs`` (counted per step). If the
    repair budget is spent without approval, the controller advances anyway
    (a per-step perseveration outcome) rather than stalling.

    If ``lean_tool`` is given, it is registered as an AG2 tool the engineer can
    call (Step 4d); a mechanical ``executor`` proxy runs it. When the engineer
    suggests a call the selector routes engineer->executor->engineer, bounded by
    ``max_tool_calls`` per step, before the critic ever reviews. With no
    ``lean_tool`` the executor is absent and the flow is exactly Steps 3b-3c.
    The tool must be deterministic (same code in, same verdict out).

    If a ``step_context`` is passed, the controller mirrors its private
    ``(current_step, repairs)`` onto it whenever they change, so an observer
    sharing that same context can stamp each engineer/critic/tool event with the
    plan step it belongs to (Step 2a/4c). The internal ``_StepState`` stays the
    sole driver of control flow; the context is a read-only mirror for the
    trace, never consulted by the selector.
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

    # In-loop compiler (Step 4d): restore the executor, but as a non-LLM runner
    # for the tool, not a reasoning role. register_function makes the engineer
    # the caller (its LLM can suggest the call) and the executor the runner.
    executor: UserProxyAgent | None = None
    if lean_tool is not None:
        executor = UserProxyAgent(
            name=AgentRole.EXECUTOR.value,
            human_input_mode="NEVER",
            code_execution_config=False,
            # The executor must be allowed to auto-reply: running the tool and
            # returning its result IS an auto-reply. With 0 it is selected but
            # declines to act, and the run terminates. The selector still gates
            # how often it speaks (per-step max_tool_calls), so a generous cap
            # here does not let it run away.
            max_consecutive_auto_reply=max_tool_calls + 1,
        )
        register_function(
            lean_tool,
            caller=engineer,
            executor=executor,
            name=tool_name,
            description=tool_description,
        )
        agents.append(executor)

    state = _StepState()

    def _sync() -> None:
        """Mirror the controller's step pointer onto the shared trace context.

        Called after every mutation of ``current_step``/``repairs`` so the
        observer reads the same step the selector is acting on. No-op when no
        context is wired (pure control-flow behaviour, unchanged).
        """
        if step_context is not None:
            step_context.step_idx = state.current_step
            step_context.attempt = state.repairs

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
            state.tool_calls = 0
            _sync()
            return _route_to(engineer, AgentRole.PLANNER)

        if name == AgentRole.ENGINEER.value:
            last = _last_message(groupchat)
            # 4d: if the engineer suggested a compiler call and the per-step
            # tool budget remains, route to the executor to run it. The executor
            # speaks the result, then we route back here. Budget guards the
            # engineer<->executor loop so it cannot spin within a step.
            if executor is not None and _is_tool_call(last) and state.tool_calls < max_tool_calls:
                state.tool_calls += 1
                return _route_to(executor, AgentRole.ENGINEER)
            # Plain message (or budget spent): the step attempt is done; review.
            return _route_to(critic, AgentRole.ENGINEER)

        if executor is not None and name == AgentRole.EXECUTOR.value:
            # Tool result delivered; the engineer reacts to it (continue the
            # within-step loop or finalise the attempt). Caused by the executor.
            return _route_to(engineer, AgentRole.EXECUTOR)

        if name == AgentRole.CRITIC.value:
            content = _last_content(groupchat).upper()
            rejected = VERDICT_REJECT in content

            if rejected and state.repairs < max_repairs:
                # Step-local repair: re-run the engineer on the SAME step.
                state.repairs += 1
                state.tool_calls = 0  # fresh tool budget for the new attempt
                _sync()
                return _route_to(engineer, AgentRole.CRITIC)

            # Approved, or repair budget spent, or malformed verdict: advance.
            state.current_step += 1
            state.repairs = 0  # reset per-step budget
            state.tool_calls = 0  # reset per-step tool budget
            _sync()
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
