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
from functools import wraps
from typing import Any

from autogen import GroupChatManager, LLMConfig, UserProxyAgent

from traj_eval.agents.free_routing import (
    RoleSpec,
    RoutingConfig,
    ToolStallHandoff,
    build_free_routing_team,
)
from traj_eval.agents.observer import StepContext
from traj_eval.agents.roles import make_critic_free, make_engineer_free, make_reasoner
from traj_eval.agents.routing import RoutingLedger
from traj_eval.trace_core.schema import AgentRole

RECOVERY_TRIANGLE_V1 = "recovery_triangle_v1"
RECOVERY_TRIANGLE_NO_RETRIEVAL_V1 = "recovery_triangle_no_retrieval_v1"
RECOVERY_TRIANGLE_STALL_HANDOFF_V1 = "recovery_triangle_stall_handoff_v1"
RETRIEVAL_DISABLED_RESULT = (
    "search_lemmas unavailable (retrieval disabled by matched ablation); "
    "proceed without retrieval."
)
SUPPORTED_LEAN_SETUPS = (
    RECOVERY_TRIANGLE_V1,
    RECOVERY_TRIANGLE_NO_RETRIEVAL_V1,
    RECOVERY_TRIANGLE_STALL_HANDOFF_V1,
)

REASONER_STUCK_HANDOFF_PROMPT = """\
Retrieval is now exhausted for this attempt. Do not call another tool.
Write a compact handoff for the Engineer using exactly these field labels:
RECOVERY_KIND: reasoner_search_stall
STRATEGY: <the proposed mathematical strategy>
RETRIEVED_LEMMAS: <useful lemma names already retrieved>
UNRESOLVED_FORMALISATION: <the exact unresolved question>
NEXT_LEAN_STEP: <the first concrete Lean step the Engineer should try>
End with exactly `HANDOFF: engineer`.
"""
REASONER_STUCK_HANDOFF_FIELDS = (
    "RECOVERY_KIND: reasoner_search_stall",
    "STRATEGY:",
    "RETRIEVED_LEMMAS:",
    "UNRESOLVED_FORMALISATION:",
    "NEXT_LEAN_STEP:",
)

ENGINEER_STUCK_HANDOFF_PROMPT = """\
Local compilation repair is now exhausted for this attempt. Do not call another tool.
Write a compact handoff for the Reasoner using exactly these field labels:
RECOVERY_KIND: engineer_compile_stall
PROOF_ATTEMPT: <the proof shape attempted>
COMPILER_EVIDENCE: <the exact latest compiler error or unsolved goal>
WHY_STRATEGY_REVIEW: <why another local edit is unlikely to work>
STRATEGIC_QUESTION: <the lemma or interpretation decision to reconsider>
End with exactly `HANDOFF: reasoner`.
"""
ENGINEER_STUCK_HANDOFF_FIELDS = (
    "RECOVERY_KIND: engineer_compile_stall",
    "PROOF_ATTEMPT:",
    "COMPILER_EVIDENCE:",
    "WHY_STRATEGY_REVIEW:",
    "STRATEGIC_QUESTION:",
)


def _stall_handoffs(
    reasoner_after: int | None,
    engineer_after: int | None,
) -> tuple[ToolStallHandoff, ...]:
    rules: list[ToolStallHandoff] = []
    if reasoner_after is not None:
        rules.append(
            ToolStallHandoff(
                caller=AgentRole.REASONER,
                tool="search_lemmas",
                after_batches=reasoner_after,
                target=AgentRole.ENGINEER,
                handoff_prompt=REASONER_STUCK_HANDOFF_PROMPT,
                required_fields=REASONER_STUCK_HANDOFF_FIELDS,
            )
        )
    if engineer_after is not None:
        rules.append(
            ToolStallHandoff(
                caller=AgentRole.ENGINEER,
                tool="check_lean",
                after_batches=engineer_after,
                target=AgentRole.REASONER,
                handoff_prompt=ENGINEER_STUCK_HANDOFF_PROMPT,
                required_fields=ENGINEER_STUCK_HANDOFF_FIELDS,
                require_failed_compile=True,
            )
        )
    return tuple(rules)


def _tools_for_setup(
    tools: dict[str, Callable[..., Any]], setup: str
) -> dict[str, Callable[..., Any]]:
    """Apply only the named setup's retrieval intervention."""
    if setup != RECOVERY_TRIANGLE_NO_RETRIEVAL_V1 or "search_lemmas" not in tools:
        return tools

    search_lemmas = tools["search_lemmas"]

    @wraps(search_lemmas)
    def retrieval_disabled(query: str) -> str:
        _ = query
        return RETRIEVAL_DISABLED_RESULT

    conditioned_tools = dict(tools)
    conditioned_tools["search_lemmas"] = retrieval_disabled
    return conditioned_tools


def lean_routing_config(
    *,
    max_turns: int = 40,
    reasoner_search_handoff_after: int | None = None,
    engineer_failed_compile_handoff_after: int | None = None,
) -> RoutingConfig:
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
        tool_stall_handoffs=_stall_handoffs(
            reasoner_search_handoff_after,
            engineer_failed_compile_handoff_after,
        ),
    )


def build_lean_free_team(
    llm_config: LLMConfig,
    *,
    tools: dict[str, Callable[..., Any]],
    setup: str = RECOVERY_TRIANGLE_V1,
    max_turns: int = 40,
    reasoner_search_handoff_after: int | None = None,
    engineer_failed_compile_handoff_after: int | None = None,
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

    if setup == RECOVERY_TRIANGLE_STALL_HANDOFF_V1:
        if reasoner_search_handoff_after is None:
            reasoner_search_handoff_after = 2
        if engineer_failed_compile_handoff_after is None:
            engineer_failed_compile_handoff_after = 2

    config = lean_routing_config(
        max_turns=max_turns,
        reasoner_search_handoff_after=reasoner_search_handoff_after,
        engineer_failed_compile_handoff_after=(
            engineer_failed_compile_handoff_after
        ),
    )
    agents = {
        AgentRole.REASONER: make_reasoner(llm_config),
        AgentRole.ENGINEER: make_engineer_free(llm_config),
        AgentRole.CRITIC: make_critic_free(llm_config),
    }
    return build_free_routing_team(
        llm_config,
        config=config,
        agents=agents,
        tools=_tools_for_setup(tools, setup),
        ledger=ledger,
        step_context=step_context,
    )
