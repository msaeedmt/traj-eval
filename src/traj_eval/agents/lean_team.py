"""Lean instantiations of the free-routing controller (Step 4d).

This is the DOMAIN-CONFIG seam: it supplies a RoutingConfig and the matching
agents for theorem proving, configuring the agnostic free_routing controller.
Astro would provide a parallel module; the controller itself is untouched.

The historical setup uses marker hand-offs. The focused subgoal setup replaces
those markers with typed tools, a bounded dependency graph, forced recovery
after repeated proof failures, and verifier-backed critic acceptance. Both use
the same domain-agnostic controller and remain separately named in TrialMeta.

Historical coordination triangle:

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
from traj_eval.agents.roles import (
    make_critic_free,
    make_critic_subgoals,
    make_engineer_free,
    make_engineer_subgoals,
    make_reasoner,
    make_reasoner_subgoals,
)
from traj_eval.agents.routing import RoutingLedger
from traj_eval.trace_core.schema import AgentRole

RECOVERY_TRIANGLE_V1 = "recovery_triangle_v1"
TOOL_ROUTED_SUBGOALS_V1 = "tool_routed_subgoals_v1"
SUPPORTED_LEAN_SETUPS = (RECOVERY_TRIANGLE_V1, TOOL_ROUTED_SUBGOALS_V1)


def lean_routing_config(
    *, max_turns: int = 40, setup: str = RECOVERY_TRIANGLE_V1
) -> RoutingConfig:
    """The reasoner -> engineer <-> critic coordination graph for Lean."""
    if setup == TOOL_ROUTED_SUBGOALS_V1:
        return RoutingConfig(
            entry=AgentRole.REASONER,
            roles={
                AgentRole.REASONER: RoleSpec(
                    role=AgentRole.REASONER,
                    handoff_targets=frozenset({AgentRole.ENGINEER}),
                    tools=frozenset(
                        {
                            "plan_subgoal",
                            "read_subgoals",
                            "search_lemmas",
                            "route_next_agent",
                        }
                    ),
                ),
                AgentRole.ENGINEER: RoleSpec(
                    role=AgentRole.ENGINEER,
                    handoff_targets=frozenset({AgentRole.CRITIC, AgentRole.REASONER}),
                    tools=frozenset(
                        {
                            "check_lean",
                            "read_subgoals",
                            "search_lemmas",
                            "submit_subgoal",
                            "route_next_agent",
                        }
                    ),
                ),
                AgentRole.CRITIC: RoleSpec(
                    role=AgentRole.CRITIC,
                    handoff_targets=frozenset({AgentRole.ENGINEER, AgentRole.REASONER}),
                    tools=frozenset(
                        {
                            "review_lean",
                            "read_candidate",
                            "read_subgoals",
                            "review_subgoal",
                            "route_next_agent",
                            "finish_run",
                        }
                    ),
                    can_terminate=True,
                ),
            },
            max_turns=max_turns,
            max_failed_compiles=0,
            allow_marker_handoffs=False,
            allow_terminal_markers=False,
            tool_result_routing=True,
        )
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
                tools=frozenset({"check_lean", "search_lemmas"}),
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
    setup: str = RECOVERY_TRIANGLE_V1,
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
    if setup not in SUPPORTED_LEAN_SETUPS:
        raise ValueError(f"Unsupported Lean team setup: {setup}")

    config = lean_routing_config(max_turns=max_turns, setup=setup)
    if setup == TOOL_ROUTED_SUBGOALS_V1:
        agents = {
            AgentRole.REASONER: make_reasoner_subgoals(llm_config),
            AgentRole.ENGINEER: make_engineer_subgoals(llm_config),
            AgentRole.CRITIC: make_critic_subgoals(llm_config),
        }
    else:
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
