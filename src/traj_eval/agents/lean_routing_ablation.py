"""Matched Lean routing policies for the private Han V4 ablation study.

The workers, tools, prompts, safety guards, and Lean validation boundary are
shared.  Only speaker selection and model-call budget accounting differ.
"""

from __future__ import annotations

import ast
import json
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from autogen import (
    ConversableAgent,
    GroupChat,
    GroupChatManager,
    LLMConfig,
    UserProxyAgent,
    register_function,
)

from traj_eval.agents.markers import VERDICT_APPROVE, VERDICT_REJECT, parse_handoff
from traj_eval.agents.observer import StepContext
from traj_eval.agents.routing import RoutingLedger
from traj_eval.trace_core.schema import AgentRole


class RoutingArm(StrEnum):
    LEGACY_DETERMINISTIC = "legacy_deterministic"
    UPSTREAM_FREE = "upstream_free"
    CENTRAL_WORKER_MATCHED = "central_worker_matched"
    CENTRAL_TOTAL_CALL_MATCHED = "central_total_call_matched"


CENTRAL_ARMS = {
    RoutingArm.CENTRAL_WORKER_MATCHED,
    RoutingArm.CENTRAL_TOTAL_CALL_MATCHED,
}

HANDOFF_TARGETS: dict[AgentRole, frozenset[AgentRole]] = {
    AgentRole.REASONER: frozenset({AgentRole.ENGINEER}),
    AgentRole.ENGINEER: frozenset({AgentRole.REASONER, AgentRole.CRITIC}),
    AgentRole.CRITIC: frozenset({AgentRole.ENGINEER}),
}

TOOL_PERMISSIONS: dict[AgentRole, frozenset[str]] = {
    AgentRole.REASONER: frozenset({"search_lemmas"}),
    AgentRole.ENGINEER: frozenset(
        {"check_lean", "search_lemmas", "try_tactic", "show_goals"}
    ),
    AgentRole.CRITIC: frozenset({"check_lean"}),
}

COMMON_REASONER_PROMPT = """\
You are the REASONER in a Lean theorem-proving team. Give a concise informal
strategy and name likely Mathlib lemmas. You may use search_lemmas to resolve a
specific library uncertainty. Do not write Lean code. When compiler evidence
returns to you, revise the strategy instead of repeating it.
"""

COMMON_ENGINEER_PROMPT = """\
You are the ENGINEER / FORMALISER in a Lean theorem-proving team. Turn the
reasoner's strategy into an exact Lean 4 proof of the requested statement.

Tools:
- search_lemmas(query): semantic Mathlib retrieval.
- show_goals(code): inspect hypotheses and targets at tactic-mode sorry holes.
- try_tactic(code): run exact? or apply? at a concrete goal.
- check_lean(code): kernel-backed verification of complete Lean source.

Work incrementally. Use show_goals and try_tactic only to resolve concrete
formal goals, and always finish with check_lean. Never weaken the theorem and
never use sorry, admit, or a new axiom in a submitted proof. Do not claim that
a proof is ready for review unless check_lean accepted that exact proof.
"""

COMMON_CRITIC_PROMPT = """\
You are the CRITIC / FAITHFULNESS REVIEWER in a Lean theorem-proving team.
Check that the engineer's exact proof matches the requested statement, contains
no sorry/admit/new axiom, and has real check_lean evidence. You may call
check_lean yourself. Approve only a faithful kernel-accepted proof; otherwise
give one concrete correction.
"""

_FREE_SUFFIXES = {
    AgentRole.REASONER: """
Routing contract: when not calling a tool, end with exactly
`HANDOFF: engineer`.
""",
    AgentRole.ENGINEER: """
Routing contract: when not calling a tool, end with exactly one of
`HANDOFF: critic` or `HANDOFF: reasoner`.
""",
    AgentRole.CRITIC: """
Routing contract: when not calling a tool, end with exactly one of
`VERDICT: APPROVE` or `HANDOFF: engineer`.
""",
}

_DETERMINISTIC_SUFFIX = """
Routing contract: the host selects the next role deterministically. Do not emit
HANDOFF markers. The Critic must end a non-tool response with exactly
`VERDICT: APPROVE` or `VERDICT: REJECT - <concrete reason>`.
"""

_CENTRAL_SUFFIX = """
Routing contract: a separate controller selects the next role. Do not emit
HANDOFF markers. The Critic must end a non-tool response with exactly
`VERDICT: APPROVE` or `VERDICT: REJECT - <concrete reason>`.
"""

CONTROLLER_PROMPT = """\
You are a routing-only controller for a Lean theorem-proving team. You do not
solve mathematics, write Lean, call tools, or judge success. Select exactly one
next worker from reasoner, engineer, or critic using the visible conversation
and Lean tool results.

Recover from lack of progress using these operational rules:
- If the reasoner repeats retrieval or an unchanged strategy, route to engineer
  so a concrete Lean attempt exposes the real goal or compiler obstruction.
- If the engineer has a new, local syntax/elaboration repair to try, keep the
  engineer working.
- If the engineer repeats a failed proof shape, compiler failure, missing-lemma
  search, or explicitly lacks a viable strategy, route back to reasoner.
- Route to critic only when the engineer presents an exact candidate with
  successful check_lean evidence.

Do not call a worker stuck after one ordinary failure. Base a stuck-recovery
route on visible repetition, unchanged evidence, or an explicit strategic
block. Your output is only a routing decision, never a mathematical verdict.

Allowed handoff graph:
- reasoner -> engineer
- engineer -> reasoner or critic
- critic -> engineer
After a tool result, the tool caller itself is also allowed so it can interpret
the result.

Return one JSON object and nothing else:
{"next_role":"reasoner|engineer|critic","reason":"short routing reason"}

OUTPUT FORMAT IS A HARD RUNTIME CONSTRAINT. The first character must be `{`
and the last character must be `}`. Do not use Markdown or a ```json fence.
"""


@dataclass(frozen=True)
class ControllerStuckProbe:
    """Pre-registered transcript and required route for a controller smoke."""

    name: str
    transcript: tuple[dict[str, str], ...]
    allowed_roles: frozenset[AgentRole]
    expected_role: AgentRole
    live_smoke: bool


CONTROLLER_STUCK_PROBES = (
    ControllerStuckProbe(
        name="reasoner_retrieval_loop",
        transcript=(
            {
                "name": "reasoner",
                "content": "I need a commutativity lemma; search_lemmas Nat addition.",
            },
            {
                "name": "executor",
                "content": "Search results include Nat.add_comm.",
            },
            {
                "name": "reasoner",
                "content": "I still need a commutativity lemma; search_lemmas Nat addition.",
            },
            {
                "name": "executor",
                "content": "Search results again include Nat.add_comm.",
            },
        ),
        allowed_roles=frozenset({AgentRole.REASONER, AgentRole.ENGINEER}),
        expected_role=AgentRole.ENGINEER,
        live_smoke=True,
    ),
    ControllerStuckProbe(
        name="engineer_strategic_failure_loop",
        transcript=(
            {
                "name": "engineer",
                "content": "Candidate A uses the same rewrite sequence.",
            },
            {
                "name": "executor",
                "content": "check_lean: compiled=false; unsolved goals remain.",
            },
            {
                "name": "engineer",
                "content": "The same proof shape still fails; I lack a viable lemma strategy.",
            },
            {
                "name": "executor",
                "content": "check_lean: compiled=false; the same goal remains.",
            },
        ),
        allowed_roles=frozenset(
            {AgentRole.REASONER, AgentRole.ENGINEER, AgentRole.CRITIC}
        ),
        expected_role=AgentRole.REASONER,
        live_smoke=True,
    ),
    ControllerStuckProbe(
        name="engineer_local_repair",
        transcript=(
            {
                "name": "engineer",
                "content": "The proof strategy is viable; this candidate has a local syntax error.",
            },
            {
                "name": "executor",
                "content": "check_lean: compiled=false; unexpected token ')' at line 4.",
            },
        ),
        allowed_roles=frozenset(
            {AgentRole.REASONER, AgentRole.ENGINEER, AgentRole.CRITIC}
        ),
        expected_role=AgentRole.ENGINEER,
        live_smoke=False,
    ),
)


@dataclass
class RoutingRunState:
    arm: RoutingArm
    max_worker_turns: int
    max_total_model_calls: int | None
    worker_turns: int = 0
    controller_turns: int = 0
    invalid_routes: int = 0
    consecutive_invalid: int = 0
    terminated: bool = False
    reason: str | None = None
    last_worker_role: AgentRole | None = None
    after_tool_result: bool = False
    budget_exhausted: bool = False
    last_call_code: str | None = None
    consecutive_identical_calls: int = 0
    max_identical_calls_seen: int = 0
    consecutive_failed_compiles: int = 0
    max_failed_compiles_seen: int = 0
    last_tool_names: frozenset[str] = frozenset()
    last_compile_verdict: bool | None = None
    reasoner_stuck_to_engineer: int = 0
    engineer_stuck_to_reasoner: int = 0
    engineer_local_retries: int = 0

    @property
    def total_model_calls(self) -> int:
        return self.worker_turns + self.controller_turns


def worker_prompts(arm: RoutingArm) -> dict[AgentRole, str]:
    """Return prompts whose mathematical content is common across all arms."""
    if arm is RoutingArm.UPSTREAM_FREE:
        suffixes = _FREE_SUFFIXES
    elif arm is RoutingArm.LEGACY_DETERMINISTIC:
        suffixes = {role: _DETERMINISTIC_SUFFIX for role in HANDOFF_TARGETS}
    else:
        suffixes = {role: _CENTRAL_SUFFIX for role in HANDOFF_TARGETS}
    return {
        AgentRole.REASONER: COMMON_REASONER_PROMPT + suffixes[AgentRole.REASONER],
        AgentRole.ENGINEER: COMMON_ENGINEER_PROMPT + suffixes[AgentRole.ENGINEER],
        AgentRole.CRITIC: COMMON_CRITIC_PROMPT + suffixes[AgentRole.CRITIC],
    }


def parse_controller_decision(
    message: dict[str, Any], allowed: frozenset[AgentRole]
) -> tuple[AgentRole, str] | None:
    """Validate the controller's strict routing-only JSON contract."""
    if message.get("tool_calls"):
        return None
    content = message.get("content", "") or ""
    try:
        payload = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict) or set(payload) != {"next_role", "reason"}:
        return None
    if not isinstance(payload["reason"], str) or not payload["reason"].strip():
        return None
    if len(payload["reason"]) > 300:
        return None
    try:
        role = AgentRole(payload["next_role"])
    except (ValueError, TypeError):
        return None
    if role not in allowed:
        return None
    return role, payload["reason"].strip()


def evaluate_controller_stuck_probe(
    probe: ControllerStuckProbe, message: dict[str, Any]
) -> tuple[bool, str]:
    """Score a live controller response without post-hoc interpretation."""
    decision = parse_controller_decision(message, probe.allowed_roles)
    if decision is None:
        return False, "invalid_controller_output"
    role, _ = decision
    if role is not probe.expected_role:
        return False, f"wrong_route:{role.value}"
    return True, "expected_route"


def _last_message(groupchat: GroupChat) -> dict[str, Any]:
    return groupchat.messages[-1] if groupchat.messages else {}


def _is_tool_call(message: dict[str, Any]) -> bool:
    return bool(message.get("tool_calls"))


def _called_tools(message: dict[str, Any]) -> set[str]:
    return {
        call.get("function", {}).get("name")
        for call in message.get("tool_calls") or []
        if call.get("function", {}).get("name")
    }


def _normalise_call(message: dict[str, Any]) -> str | None:
    parts: list[str] = []
    for call in message.get("tool_calls") or []:
        arguments = call.get("function", {}).get("arguments")
        if not arguments:
            continue
        try:
            parsed = json.loads(arguments)
            parts.append(" ".join(str(value) for value in parsed.values()))
        except (ValueError, TypeError, AttributeError):
            parts.append(str(arguments))
    if not parts:
        return None
    return " ".join(" ".join(parts).split())


def _compile_verdict(message: dict[str, Any]) -> bool | None:
    for response in message.get("tool_responses") or []:
        content = response.get("content")
        if not content:
            continue
        try:
            payload = ast.literal_eval(content)
        except (ValueError, SyntaxError):
            continue
        if isinstance(payload, dict) and "compiled" in payload:
            return bool(payload["compiled"])
    return None


def _fallback_role(state: RoutingRunState) -> AgentRole:
    role = state.last_worker_role
    if role is None:
        return AgentRole.REASONER
    if state.after_tool_result:
        return role
    if role is AgentRole.REASONER:
        return AgentRole.ENGINEER
    if role is AgentRole.ENGINEER:
        return AgentRole.CRITIC
    return AgentRole.ENGINEER


def _allowed_controller_roles(state: RoutingRunState) -> frozenset[AgentRole]:
    role = state.last_worker_role
    if role is None:
        return frozenset({AgentRole.REASONER})
    allowed = set(HANDOFF_TARGETS[role])
    if state.after_tool_result:
        allowed.add(role)
    return frozenset(allowed)


def _mark_invalid(state: RoutingRunState) -> bool:
    state.invalid_routes += 1
    state.consecutive_invalid += 1
    if state.consecutive_invalid >= 3:
        state.terminated = True
        state.reason = "stuck"
        return True
    return False


def _update_tool_guards(state: RoutingRunState, message: dict[str, Any]) -> bool:
    verdict = _compile_verdict(message)
    state.last_compile_verdict = verdict
    if verdict is True:
        state.consecutive_failed_compiles = 0
    elif verdict is False:
        state.consecutive_failed_compiles += 1
        state.max_failed_compiles_seen = max(
            state.max_failed_compiles_seen, state.consecutive_failed_compiles
        )
        if state.consecutive_failed_compiles >= 6:
            state.terminated = True
            state.reason = "stuck"
            return False
    return True


def _record_controller_recovery(
    state: RoutingRunState, selected: AgentRole
) -> None:
    """Count only pre-registered, evidence-backed stuck-recovery routes."""
    if (
        state.last_worker_role is AgentRole.REASONER
        and state.after_tool_result
        and state.last_tool_names == frozenset({"search_lemmas"})
        and state.consecutive_identical_calls >= 2
        and selected is AgentRole.ENGINEER
    ):
        state.reasoner_stuck_to_engineer += 1
    elif (
        state.last_worker_role is AgentRole.ENGINEER
        and state.after_tool_result
        and state.last_compile_verdict is False
        and state.consecutive_failed_compiles >= 2
        and selected is AgentRole.REASONER
    ):
        state.engineer_stuck_to_reasoner += 1
    elif (
        state.last_worker_role is AgentRole.ENGINEER
        and state.after_tool_result
        and state.last_compile_verdict is False
        and selected is AgentRole.ENGINEER
    ):
        state.engineer_local_retries += 1


def build_routing_ablation_team(
    worker_llm_config: LLMConfig,
    *,
    arm: RoutingArm,
    tools: dict[str, Callable[..., Any]],
    max_worker_turns: int = 200,
    max_total_model_calls: int = 200,
    controller_llm_config: LLMConfig | None = None,
    ledger: RoutingLedger | None = None,
    step_context: StepContext | None = None,
) -> tuple[GroupChatManager, UserProxyAgent, GroupChat, RoutingRunState]:
    """Build one matched routing arm around the common Lean workers."""
    if max_worker_turns < 1 or max_total_model_calls < 1:
        raise ValueError("model-call budgets must be positive")
    if arm in CENTRAL_ARMS and controller_llm_config is None:
        raise ValueError("central routing arms require controller_llm_config")

    prompts = worker_prompts(arm)
    workers = {
        role: ConversableAgent(
            name=role.value,
            system_message=prompt,
            llm_config=worker_llm_config,
            human_input_mode="NEVER",
        )
        for role, prompt in prompts.items()
    }
    user = UserProxyAgent(
        name="user",
        human_input_mode="NEVER",
        code_execution_config=False,
        max_consecutive_auto_reply=0,
    )
    executor = UserProxyAgent(
        name=AgentRole.EXECUTOR.value,
        human_input_mode="NEVER",
        code_execution_config=False,
        max_consecutive_auto_reply=max_worker_turns,
    )
    controller = None
    if arm in CENTRAL_ARMS:
        controller = ConversableAgent(
            name=AgentRole.SYSTEM.value,
            system_message=CONTROLLER_PROMPT,
            llm_config=controller_llm_config,
            human_input_mode="NEVER",
        )

    for tool_name, function in tools.items():
        callers = [
            workers[role]
            for role, allowed in TOOL_PERMISSIONS.items()
            if tool_name in allowed
        ]
        if not callers:
            continue
        register_function(
            function,
            caller=callers[0],
            executor=executor,
            name=tool_name,
            description=function.__doc__ or tool_name,
        )
        for caller in callers[1:]:
            caller.register_for_llm(
                name=tool_name,
                description=function.__doc__ or tool_name,
            )(function)

    members = [user, executor, *workers.values()]
    if controller is not None:
        members.append(controller)
    state = RoutingRunState(
        arm=arm,
        max_worker_turns=max_worker_turns,
        max_total_model_calls=(
            max_total_model_calls
            if arm is RoutingArm.CENTRAL_TOTAL_CALL_MATCHED
            else None
        ),
    )

    def route(agent, parent_role: AgentRole):
        if ledger is not None and agent is not None:
            try:
                next_role = AgentRole(agent.name)
            except ValueError:
                next_role = AgentRole.SYSTEM
            cause = ledger.latest_event_id(parent_role)
            ledger.record_routing(next_role, [cause] if cause else [])
        return agent

    def stop(reason: str):
        state.terminated = True
        state.reason = reason
        return None

    def selector(last_speaker, groupchat: GroupChat):
        message = _last_message(groupchat)
        name = last_speaker.name

        if name == "user":
            state.after_tool_result = False
            if controller is not None:
                return route(controller, AgentRole.SYSTEM)
            return route(workers[AgentRole.REASONER], AgentRole.SYSTEM)

        if controller is not None and last_speaker is controller:
            state.controller_turns += 1
            if (
                state.max_total_model_calls is not None
                and state.total_model_calls >= state.max_total_model_calls
            ):
                return stop("cap")
            allowed = _allowed_controller_roles(state)
            decision = parse_controller_decision(message, allowed)
            if decision is None:
                if _mark_invalid(state):
                    return None
                selected = _fallback_role(state)
            else:
                selected, _ = decision
                state.consecutive_invalid = 0
            _record_controller_recovery(state, selected)
            state.after_tool_result = False
            return route(workers[selected], AgentRole.SYSTEM)

        if name == AgentRole.EXECUTOR.value:
            if not _update_tool_guards(state, message):
                return None
            if state.budget_exhausted:
                return stop("cap")
            state.after_tool_result = True
            if controller is not None:
                return route(controller, AgentRole.EXECUTOR)
            if state.last_worker_role is None:
                return stop("stuck")
            return route(workers[state.last_worker_role], AgentRole.EXECUTOR)

        try:
            role = AgentRole(name)
        except ValueError:
            return stop("stuck")
        if role not in workers:
            return stop("stuck")

        state.last_worker_role = role
        state.after_tool_result = False
        state.worker_turns += 1
        state.budget_exhausted = state.worker_turns >= state.max_worker_turns
        if (
            state.max_total_model_calls is not None
            and state.total_model_calls >= state.max_total_model_calls
        ):
            state.budget_exhausted = True

        text = message.get("content", "") or ""
        if role is AgentRole.CRITIC and VERDICT_APPROVE in text.upper():
            return stop("clean")

        if _is_tool_call(message):
            called = _called_tools(message)
            state.last_tool_names = frozenset(called)
            if not called or not called <= TOOL_PERMISSIONS[role]:
                return stop("stuck") if _mark_invalid(state) else route(
                    workers[AgentRole.REASONER], role
                )
            state.consecutive_invalid = 0
            code = _normalise_call(message)
            if code is not None and code == state.last_call_code:
                state.consecutive_identical_calls += 1
            else:
                state.last_call_code = code
                state.consecutive_identical_calls = 1
            state.max_identical_calls_seen = max(
                state.max_identical_calls_seen, state.consecutive_identical_calls
            )
            if state.consecutive_identical_calls >= 4:
                return stop("stuck")
            return route(executor, role)

        if state.budget_exhausted:
            return stop("cap")

        if arm is RoutingArm.LEGACY_DETERMINISTIC:
            if role is AgentRole.REASONER:
                return route(workers[AgentRole.ENGINEER], role)
            if role is AgentRole.ENGINEER:
                return route(workers[AgentRole.CRITIC], role)
            if VERDICT_REJECT in text.upper():
                return route(workers[AgentRole.ENGINEER], role)
            return stop("stuck")

        if arm is RoutingArm.UPSTREAM_FREE:
            marker = parse_handoff(text)
            target = None
            if "handoff_target" in marker:
                try:
                    target = AgentRole(marker["handoff_target"])
                except ValueError:
                    target = None
            if target in HANDOFF_TARGETS[role]:
                state.consecutive_invalid = 0
                return route(workers[target], role)
            if _mark_invalid(state):
                return None
            return route(workers[AgentRole.REASONER], role)

        return route(controller, role)

    groupchat = GroupChat(
        agents=members,
        messages=[],
        max_round=max_worker_turns * 8 + 50,
        speaker_selection_method=selector,
    )
    manager = GroupChatManager(groupchat=groupchat, llm_config=worker_llm_config)
    return manager, user, groupchat, state


def finalize_routing_ablation(state: RoutingRunState) -> RoutingRunState:
    """Backfill a reason if AG2 stops outside the experiment selector."""
    if state.reason is None:
        state.terminated = True
        state.reason = "framework_stop"
    return state
