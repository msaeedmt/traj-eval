"""Lean instantiation of the free-routing controller (Step 4d).

This is the DOMAIN-CONFIG seam: it supplies a RoutingConfig and the matching
agents for theorem proving, configuring the agnostic free_routing controller.
Astro would provide a parallel module; the controller itself is untouched.

The coordination triangle (from the design discussion):

    reasoner --HANDOFF--> engineer
    engineer --TOOL: check_lean--> (executor) --> engineer
    engineer --HANDOFF--> {critic, reasoner}
    critic   --TOOL: check_lean--> (executor) --> critic
    critic   --HANDOFF--> engineer   |   VERDICT: APPROVE (terminate)

Each role's allowed targets/tools are the ALLOWED sets; the gap between allowed
and what an agent actually expresses is the coordination signal the run records.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from autogen import GroupChatManager, LLMConfig, UserProxyAgent

from traj_eval.agents.free_routing import RoleSpec, RoutingConfig, build_free_routing_team
from traj_eval.agents.observer import StepContext
from traj_eval.agents.roles import make_critic_free, make_engineer_free, make_reasoner
from traj_eval.agents.routing import RoutingLedger
from traj_eval.trace_core.schema import AgentRole


def lean_routing_config(*, max_turns: int = 40) -> RoutingConfig:
    """The reasoner -> engineer <-> critic coordination graph for Lean."""
    return RoutingConfig(
        entry=AgentRole.REASONER,
        roles={
            AgentRole.REASONER: RoleSpec(
                role=AgentRole.REASONER,
                handoff_targets=frozenset({AgentRole.ENGINEER}),
                tools=frozenset({"search_lemmas"}),  # retrieval added later
            ),
            AgentRole.ENGINEER: RoleSpec(
                role=AgentRole.ENGINEER,
                handoff_targets=frozenset({AgentRole.CRITIC, AgentRole.REASONER}),
                tools=frozenset({"check_lean", "search_lemmas", "try_tactic", "show_goals"}),
            ),
            AgentRole.CRITIC: RoleSpec(
                role=AgentRole.CRITIC,
                handoff_targets=frozenset({AgentRole.ENGINEER}),
                tools=frozenset({"check_lean"}),
                can_terminate=True,
            ),
        },
        max_turns=max_turns,
    )


def build_lean_free_team(
    llm_config: LLMConfig,
    *,
    tools: dict[str, Callable[..., Any]],
    max_turns: int = 40,
    ledger: RoutingLedger | None = None,
    step_context: StepContext | None = None,
) -> tuple[GroupChatManager, UserProxyAgent, Any, Any]:
    """Build the Lean reasoner/engineer/critic free-routing team.

    ``tools`` maps tool names (e.g. "check_lean", "search_lemmas") to functions.
    Only the tools named in the config's RoleSpecs are registered; passing extra
    tools is harmless, and omitting one a role lists just means that role's
    requests for it will be (correctly) unroutable -- itself an observable
    coordination outcome.
    """
    config = lean_routing_config(max_turns=max_turns)
    agents = {
        AgentRole.REASONER: make_reasoner(llm_config),
        AgentRole.ENGINEER: make_engineer_free(llm_config),
        AgentRole.CRITIC: make_critic_free(llm_config),
    }
    return build_free_routing_team(
        llm_config,
        config=config,
        agents=agents,
        tools=tools,
        ledger=ledger,
        step_context=step_context,
    )
