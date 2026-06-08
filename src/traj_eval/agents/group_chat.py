"""Four-role group chat with a deterministic workflow loop (Methodology §4.1).

This is the Step 1d substrate: planner, engineer, critic, executor wired into an
AG2 GroupChat whose speaker selection is a *deterministic* function encoding the
scientific workflow:

    planner -> engineer -> critic
        critic APPROVE -> executor -> END
        critic REJECT  -> engineer (repair loop, up to max_repairs)

We use a callable speaker_selection_method rather than AG2's LLM-based 'auto'
selection on purpose: the speaker sequence is part of the trajectory the
observer (O1) will trace, so it must be a known function, not a model guess.
The repair edge (critic REJECT -> engineer) is the genuine loop; hitting
max_repairs is the operational signal behind the perseveration detector (O2).

Execution is simulated on toy tasks (no sandbox yet); a real executor is a
later step.
"""

from __future__ import annotations

from autogen import GroupChat, GroupChatManager, LLMConfig, UserProxyAgent

from traj_eval.agents.roles import (
    make_critic,
    make_engineer,
    make_executor,
    make_planner,
)
from traj_eval.trace_core.schema import AgentRole

# Markers the role prompts agree to emit; read here to drive the loop.
_VERDICT_APPROVE = "VERDICT: APPROVE"
_VERDICT_REJECT = "VERDICT: REJECT"


def _last_content(groupchat: GroupChat) -> str:
    """Text of the most recent message, or empty string if none."""
    if not groupchat.messages:
        return ""
    return groupchat.messages[-1].get("content", "") or ""


def build_team(
    llm_config: LLMConfig,
    *,
    max_repairs: int = 2,
    max_round: int = 20,
) -> tuple[GroupChatManager, UserProxyAgent, GroupChat]:
    """Build the four-role group chat and its manager.

    Returns (manager, user_proxy, groupchat). Start a run with
    ``user_proxy.initiate_chat(manager, message=task)``.

    ``max_repairs`` caps the critic-reject -> engineer loop; once exceeded the
    run terminates even without approval (a perseveration outcome).
    """
    planner = make_planner(llm_config)
    engineer = make_engineer(llm_config)
    critic = make_critic(llm_config)
    executor = make_executor(llm_config)

    user = UserProxyAgent(
        name="user",
        human_input_mode="NEVER",
        code_execution_config=False,
        max_consecutive_auto_reply=0,
    )

    agents = [user, planner, engineer, critic, executor]

    # Mutable counter closed over by the selector. A list so the closure can
    # mutate it without `nonlocal` gymnastics across calls.
    repair_count = {"n": 0}

    def select_next(last_speaker, groupchat: GroupChat):
        """Deterministic workflow transitions. Returns the next agent or None.

        None terminates the chat. The order of checks is the workflow:
        user -> planner -> engineer -> critic -> {executor | engineer}.
        """
        name = last_speaker.name

        if name == "user":
            return planner
        if name == AgentRole.PLANNER.value:
            return engineer
        if name == AgentRole.ENGINEER.value:
            return critic
        if name == AgentRole.CRITIC.value:
            content = _last_content(groupchat).upper()
            if _VERDICT_APPROVE in content:
                return executor
            if _VERDICT_REJECT in content:
                if repair_count["n"] < max_repairs:
                    repair_count["n"] += 1
                    return engineer  # repair loop
                return None  # gave up after max_repairs (perseveration)
            # Malformed verdict: stop rather than guess.
            return None
        if name == AgentRole.EXECUTOR.value:
            return None  # executor is terminal on success
        return None

    groupchat = GroupChat(
        agents=agents,
        messages=[],
        max_round=max_round,
        speaker_selection_method=select_next,
    )

    manager = GroupChatManager(
        groupchat=groupchat,
        llm_config=llm_config,
    )

    return manager, user, groupchat
