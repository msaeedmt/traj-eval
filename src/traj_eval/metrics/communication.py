"""Communication metrics for free-routing trajectories.

These metrics distinguish an agent's explicit handoff from a controller
fallback. A revision is evidence-backed only when its causal ancestry contains
a failed compiler result, or when a critic explicitly rejects a proof.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass

import networkx as nx

from traj_eval.trace_core.graph import build_graph
from traj_eval.trace_core.schema import AgentRole, EventType, TraceEvent


@dataclass(frozen=True)
class CommunicationSummary:
    explicit_handoffs: int
    reasoner_to_engineer: int
    engineer_to_reasoner: int
    engineer_to_critic: int
    critic_to_engineer: int
    implicit_reasoner_reentries: int
    failed_compile_results: int
    successful_compile_results: int
    critic_rechecks: int
    critic_approvals: int
    critic_rejections: int
    evidence_backed_revisions: int
    revision_followed_by_compile_success: bool
    graph_longest_path: int
    graph_dead_end_fraction: float
    tool_handoffs: int = 0
    forced_recoveries: int = 0
    strategy_revisions: int = 0
    subgoals_defined: int = 0
    subgoals_accepted: int = 0
    subgoals_rejected: int = 0
    critic_gate_denials: int = 0
    verified_completion: bool = False


def _result_dict(event: TraceEvent) -> dict | None:
    if event.event_type is not EventType.EXECUTION_RESULT:
        return None
    for response in event.payload.get("tool_responses") or []:
        content = response.get("content")
        if not content:
            continue
        try:
            parsed = ast.literal_eval(content)
        except (ValueError, SyntaxError):
            try:
                parsed = json.loads(content)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _compile_verdict(event: TraceEvent) -> bool | None:
    parsed = _result_dict(event)
    if parsed is not None and isinstance(parsed.get("compiled"), bool):
        return parsed["compiled"]
    return None


def _calls_check_lean(event: TraceEvent) -> bool:
    return any(
        call.get("name") in {"check_lean", "review_lean"}
        for call in event.payload.get("tool_calls") or []
    )


def _tool_arguments(call: dict) -> dict:
    try:
        parsed = json.loads(call.get("arguments") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def summarize_communication(events: list[TraceEvent]) -> CommunicationSummary:
    """Summarize explicit recovery behavior and its causal compiler evidence."""
    ordered = sorted(events, key=lambda event: event.seq)
    graph = build_graph(ordered)

    handoffs: dict[tuple[AgentRole, str], int] = {
        (event.agent_role, event.payload.get("handoff_target")): 0
        for event in ordered
        if event.payload.get("handoff_target")
    }
    for event in ordered:
        target = event.payload.get("handoff_target")
        if target:
            handoffs[(event.agent_role, target)] = handoffs.get((event.agent_role, target), 0) + 1

    tool_handoff_events: list[tuple[TraceEvent, str]] = []
    for event in ordered:
        if event.event_type is not EventType.TOOL_CALL:
            continue
        for call in event.payload.get("tool_calls") or []:
            if call.get("name") != "route_next_agent":
                continue
            target = str(_tool_arguments(call).get("target") or "").lower()
            if target:
                handoffs[(event.agent_role, target)] = handoffs.get(
                    (event.agent_role, target), 0
                ) + 1
                tool_handoff_events.append((event, target))

    results = {
        event.event_id: parsed
        for event in ordered
        if (parsed := _result_dict(event)) is not None
    }
    forced_ids = {
        event_id
        for event_id, parsed in results.items()
        if parsed.get("route_kind") == "failed_compile_recovery"
    }

    compile_verdicts = {
        event.event_id: verdict
        for event in ordered
        if (verdict := _compile_verdict(event)) is not None
    }
    failed_ids = {event_id for event_id, verdict in compile_verdicts.items() if not verdict}
    successful_ids = {event_id for event_id, verdict in compile_verdicts.items() if verdict}
    by_id = {event.event_id: event for event in ordered}

    revision_ids: list[str] = []
    for event in ordered:
        target = event.payload.get("handoff_target")
        engineer_replan = (
            event.agent_role is AgentRole.ENGINEER and target == AgentRole.REASONER.value
        )
        critic_reject = (
            event.agent_role is AgentRole.CRITIC
            and target == AgentRole.ENGINEER.value
            and event.payload.get("decision") == "reject"
        )
        if engineer_replan:
            ancestors = nx.ancestors(graph, event.event_id)
            compile_ancestors = ancestors & compile_verdicts.keys()
            latest_compile = max(
                compile_ancestors, key=lambda event_id: by_id[event_id].seq, default=None
            )
            if latest_compile is not None and compile_verdicts[latest_compile] is False:
                revision_ids.append(event.event_id)
        elif critic_reject:
            revision_ids.append(event.event_id)

    for event, target in tool_handoff_events:
        if event.agent_role is AgentRole.ENGINEER and target == AgentRole.REASONER.value:
            ancestors = nx.ancestors(graph, event.event_id)
            failed_ancestors = ancestors & failed_ids
            if failed_ancestors:
                revision_ids.append(event.event_id)
        elif event.agent_role is AgentRole.CRITIC and target == AgentRole.ENGINEER.value:
            ancestors = nx.ancestors(graph, event.event_id)
            if any(results.get(event_id, {}).get("decision") == "reject" for event_id in ancestors):
                revision_ids.append(event.event_id)
    revision_ids.extend(sorted(forced_ids))

    revision_followed_by_success = any(
        successful_ids & nx.descendants(graph, event_id) for event_id in revision_ids
    )

    messages = [
        event
        for event in ordered
        if event.event_type is EventType.MESSAGE and event.agent_role is not AgentRole.SYSTEM
    ]
    implicit_reasoner_reentries = sum(
        1
        for previous, current in zip(messages, messages[1:])
        if previous.agent_role is AgentRole.ENGINEER
        and current.agent_role is AgentRole.REASONER
        and previous.payload.get("handoff_target") != AgentRole.REASONER.value
    )

    longest_path = nx.dag_longest_path_length(graph) if nx.is_directed_acyclic_graph(graph) else 0
    dead_ends = sum(1 for node in graph if graph.out_degree(node) == 0)
    dead_end_fraction = dead_ends / len(graph) if graph else 0.0

    return CommunicationSummary(
        explicit_handoffs=sum(handoffs.values()),
        reasoner_to_engineer=handoffs.get(
            (AgentRole.REASONER, AgentRole.ENGINEER.value), 0
        ),
        engineer_to_reasoner=handoffs.get(
            (AgentRole.ENGINEER, AgentRole.REASONER.value), 0
        ),
        engineer_to_critic=handoffs.get(
            (AgentRole.ENGINEER, AgentRole.CRITIC.value), 0
        ),
        critic_to_engineer=handoffs.get(
            (AgentRole.CRITIC, AgentRole.ENGINEER.value), 0
        ),
        implicit_reasoner_reentries=implicit_reasoner_reentries,
        failed_compile_results=len(failed_ids),
        successful_compile_results=len(successful_ids),
        critic_rechecks=sum(
            1
            for event in ordered
            if event.agent_role is AgentRole.CRITIC and _calls_check_lean(event)
        ),
        critic_approvals=sum(
            1
            for event in ordered
            if event.agent_role is AgentRole.CRITIC
            and event.payload.get("decision") == "approve"
        )
        + sum(1 for parsed in results.values() if parsed.get("run_complete") is True),
        critic_rejections=sum(
            1
            for event in ordered
            if event.agent_role is AgentRole.CRITIC
            and event.payload.get("decision") == "reject"
        )
        + sum(1 for parsed in results.values() if parsed.get("decision") == "reject"),
        evidence_backed_revisions=len(revision_ids),
        revision_followed_by_compile_success=revision_followed_by_success,
        graph_longest_path=longest_path,
        graph_dead_end_fraction=dead_end_fraction,
        tool_handoffs=len(tool_handoff_events),
        forced_recoveries=len(forced_ids),
        strategy_revisions=sum(
            1 for parsed in results.values() if parsed.get("revised") is True
        ),
        subgoals_defined=sum(
            1 for parsed in results.values() if parsed.get("created") is True
        ),
        subgoals_accepted=sum(
            1
            for parsed in results.values()
            if parsed.get("decision") == "accept" and parsed.get("accepted") is True
        ),
        subgoals_rejected=sum(
            1 for parsed in results.values() if parsed.get("decision") == "reject"
        ),
        critic_gate_denials=sum(
            1
            for parsed in results.values()
            if parsed.get("ok") is False
            and any(
                word in str(parsed.get("error", "")).lower()
                for word in ("critic", "candidate", "subgoals", "final evidence")
            )
        ),
        verified_completion=any(
            parsed.get("run_complete") is True for parsed in results.values()
        ),
    )
