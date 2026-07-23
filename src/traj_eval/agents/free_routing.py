"""Free-routing controller for marker- or tool-expressed hand-offs (Step 4d).

Where the stepped controller (controller.py) routes by a fixed workflow, this
controller can let each agent choose who acts next through a text marker or a
registered routing tool. Coordination becomes a measured, fallible decision:
an agent can hand to the wrong role, skip a required tool, or fail a completion
gate. Tool results may also carry an explicitly configured recovery route, so a
bounded intervention remains visible in the same causal trace.

Domain-agnostic by construction. The controller knows only: a ``RoutingConfig``
(which roles exist, each role's allowed hand-off targets and allowed tools, the
entry role, the turn cap), how to read a marker, how to validate the expressed
target against the allowed set, and how to account for termination. It contains
NO Lean. A domain supplies a RoutingConfig and the matching agents/tools; Lean's
config lives in lean_team.py, astro's would live alongside. This is the O1
"framework-agnostic ... domain-adaptable" seam, made explicit.

Termination is always bounded: a run ends with a recorded reason -- ``clean``
(a marker or verified completion tool), ``cap`` (turn budget exhausted),
``stuck`` (invalid routing, exhausted recovery, or repeated no-progress calls),
or ``framework_stop`` (AG2 ended before a controller terminal condition).
A reason-tagged end makes non-termination observable rather than infinite.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from autogen import GroupChat, GroupChatManager, LLMConfig, UserProxyAgent

from traj_eval.agents.markers import VERDICT_APPROVE, parse_handoff
from traj_eval.agents.observer import StepContext
from traj_eval.agents.routing import RoutingLedger
from traj_eval.trace_core.schema import AgentRole


@dataclass(frozen=True)
class RoleSpec:
    """One agent's coordination affordances: who it may hand to, what it may run.

    ``handoff_targets`` and ``tools`` are the ALLOWED sets; an expressed target
    outside them is a coordination error (routed by fallback, logged as invalid).
    ``can_terminate`` marks roles whose terminal marker (e.g. critic APPROVE)
    legitimately ends the run.
    """

    role: AgentRole
    handoff_targets: frozenset[AgentRole] = frozenset()
    tools: frozenset[str] = frozenset()
    can_terminate: bool = False


@dataclass(frozen=True)
class ToolStallHandoff:
    """Request one bounded handoff-summary turn after repeated tool batches."""

    caller: AgentRole
    tool: str
    after_batches: int
    target: AgentRole
    handoff_prompt: str
    required_fields: tuple[str, ...] = ()
    require_failed_compile: bool = False


@dataclass(frozen=True)
class RoutingConfig:
    """The domain's coordination graph: the seam where a domain configures the
    agnostic controller. Lean and astro differ only in this object (plus the
    agents/tools it references), not in the routing logic.
    """

    entry: AgentRole  # who acts first after the task is posted
    roles: dict[AgentRole, RoleSpec] = field(default_factory=dict)
    max_turns: int = 40
    max_consecutive_invalid: int = 3  # consecutive bad hand-offs -> 'stuck'
    max_identical_calls: int = 4  # identical tool submissions in a row -> 'stuck'
    max_failed_compiles: int = 6  # consecutive failed compiles w/ no success -> 'stuck'
    tool_stall_handoffs: tuple[ToolStallHandoff, ...] = ()
    allow_marker_handoffs: bool = True
    allow_terminal_markers: bool = True
    tool_result_routing: bool = False

    def spec(self, role: AgentRole) -> RoleSpec | None:
        return self.roles.get(role)


@dataclass
class _RunState:
    """Mutable bookkeeping for one run."""

    turns: int = 0
    consecutive_invalid: int = 0
    terminated: bool = False
    reason: str | None = None  # clean | cap | stuck | framework_stop
    invalid_handoffs: int = 0  # total coordination errors seen
    # Perseveration bound (4d): the last tool-call code and how many times in a
    # row it has been resubmitted identically. Repeated identical submission is
    # perseveration; we stop the run rather than let it burn the whole budget,
    # and record the count so the offline detector confirms what the bound saw.
    last_call_code: str | None = None
    consecutive_identical_calls: int = 0
    max_identical_calls_seen: int = 0
    # No-progress bound: consecutive failed compiles with no success between
    # them. Unlike the identical-calls bound, this catches "reworded thrashing"
    # -- the agent varying its code cosmetically while never compiling. A
    # successful compile resets it to 0.
    consecutive_failed_compiles: int = 0
    max_failed_compiles_seen: int = 0
    tool_stall_streaks: dict[tuple[AgentRole, str], int] = field(default_factory=dict)
    max_tool_stall_streaks: dict[tuple[AgentRole, str], int] = field(
        default_factory=dict
    )
    tool_stall_handoffs: int = 0
    handoff_prompt_turns: int = 0
    handoff_prompt_failures: int = 0
    pending_handoff: ToolStallHandoff | None = None
    tool_handoffs: int = 0
    forced_recoveries: int = 0
    completion_gate_denials: int = 0
    tool_protocol_errors: int = 0
    controller_fallback_routes: int = 0
    pending_post_tool_target: AgentRole | None = None
    pending_post_tool_reason: str | None = None
    turn_budget: int = 0


def _role_of(name: str) -> AgentRole | None:
    try:
        return AgentRole(name)
    except ValueError:
        return None


def _last_message(groupchat: GroupChat) -> dict[str, Any]:
    return groupchat.messages[-1] if groupchat.messages else {}


def _last_text(groupchat: GroupChat) -> str:
    return _last_message(groupchat).get("content", "") or ""


def _is_native_tool_call(message: dict[str, Any]) -> bool:
    """True if the message is an AG2-native tool call (has ``tool_calls``).

    Registered tools (check_lean, search_lemmas) are invoked through AG2's
    native tool-call protocol -- the LLM emits a structured tool call, NOT a
    text marker. The selector routes such a message to the executor. (An earlier
    design used a ``TOOL:`` text marker for this; that was wrong -- it competed
    with the native mechanism the LLM actually uses. Hand-offs still use a text
    marker because AG2 has no native 'choose next agent' mechanism.)
    """
    return bool(message.get("tool_calls"))


def _called_tools(message: dict[str, Any]) -> frozenset[str | None]:
    return frozenset(
        call.get("function", {}).get("name")
        for call in message.get("tool_calls") or []
    )


def _valid_handoff_summary(text: str, rule: ToolStallHandoff) -> bool:
    """Validate the structured recovery summary promised by the prompt."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    expected_marker = f"HANDOFF: {rule.target.value}"
    if not lines or lines[-1].casefold() != expected_marker.casefold():
        return False
    for field in rule.required_fields:
        if field.endswith(":"):
            if not any(
                line.startswith(field) and line[len(field) :].strip()
                for line in lines
            ):
                return False
        elif field not in lines:
            return False
    return True


def _tool_result_dict(message: dict[str, Any]) -> dict[str, Any] | None:
    """Parse the first dictionary returned by an AG2 tool result."""
    import ast
    import json

    for response in message.get("tool_responses") or []:
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


def _compile_verdict(message: dict[str, Any]) -> bool | None:
    """Read a check_lean compile verdict from an executor result message.

    Returns True/False if this is a check_lean result, or None if it is not a
    compile result at all (e.g. a search_lemmas result, which must NOT count
    toward the no-progress bound). ag2 stringifies the tool's dict with repr(),
    so we parse leniently with ast.literal_eval.
    """
    result = _tool_result_dict(message)
    if result is not None and "compiled" in result:
        return bool(result["compiled"])
    return None


def _is_tool_protocol_error(message: dict[str, Any]) -> bool:
    """Detect executor failures caused by malformed model-emitted tool JSON."""
    text = str(message.get("content") or "")
    text += " " + " ".join(
        str(item.get("content") or "") for item in message.get("tool_responses") or []
    )
    lowered = text.casefold()
    return any(
        marker in lowered
        for marker in (
            "argument must be in json format",
            "failed to parse tool call arguments as json",
            "unterminated string",
        )
    )


def _normalise_call_code(message: dict[str, Any]) -> str | None:
    """Whitespace-normalised concatenation of the tool call(s) arguments.

    Used by the perseveration bound to tell whether this submission repeats the
    previous one. Parses each tool_call's ``arguments`` (clean JSON) and joins
    the values; falls back to the raw arguments string if parsing fails. Mirrors
    the detector's normalisation so the live bound and the offline detector
    agree on what 'identical' means.
    """
    import json as _json

    parts: list[str] = []
    for tc in message.get("tool_calls") or []:
        args = tc.get("function", {}).get("arguments")
        if not args:
            continue
        try:
            parsed = _json.loads(args)
            parts.append(" ".join(str(v) for v in parsed.values()))
        except (ValueError, TypeError, AttributeError):
            parts.append(str(args))
    if not parts:
        return None
    return " ".join(" ".join(parts).split())


def build_free_routing_team(
    llm_config: LLMConfig,
    *,
    config: RoutingConfig,
    agents: dict[AgentRole, Any],
    tools: dict[str, Callable[..., Any]] | None = None,
    ledger: RoutingLedger | None = None,
    step_context: StepContext | None = None,
    post_tool_route: Callable[[AgentRole, frozenset[str]], tuple[AgentRole, str] | None]
    | None = None,
) -> tuple[GroupChatManager, UserProxyAgent, GroupChat, _RunState]:
    """Build a group chat whose next-speaker is chosen by the agents' markers.

    ``agents`` maps each role in ``config`` to its (already-constructed) agent.
    ``tools`` maps tool names to functions; each is registered with every role
    allowed to call it (caller) and a shared mechanical executor (runner).
    Returns (manager, user_proxy, groupchat, run_state); ``run_state`` carries
    the termination reason and coordination-error counts after the run.
    """
    tools = tools or {}
    stall_handoffs = config.tool_stall_handoffs
    seen_stall_keys: set[tuple[AgentRole, str]] = set()
    for stall_handoff in stall_handoffs:
        stall_key = (stall_handoff.caller, stall_handoff.tool)
        if stall_key in seen_stall_keys:
            raise ValueError("tool stall handoff caller/tool pairs must be unique")
        seen_stall_keys.add(stall_key)
        caller_spec = config.spec(stall_handoff.caller)
        if stall_handoff.after_batches < 1:
            raise ValueError("tool stall handoff threshold must be positive")
        if not stall_handoff.handoff_prompt.strip():
            raise ValueError("tool stall handoff prompt must not be blank")
        if any(not field.strip() for field in stall_handoff.required_fields):
            raise ValueError("tool stall handoff required fields must not be blank")
        if caller_spec is None or stall_handoff.tool not in caller_spec.tools:
            raise ValueError("tool stall handoff caller must be allowed to use its tool")
        if stall_handoff.caller not in agents:
            raise ValueError("tool stall handoff caller must have a configured agent")
        if (
            stall_handoff.target not in caller_spec.handoff_targets
            or stall_handoff.target not in agents
        ):
            raise ValueError("tool stall handoff target must be an allowed handoff")
        if (
            stall_handoff.require_failed_compile
            and stall_handoff.after_batches >= config.max_failed_compiles
        ):
            raise ValueError("failed-compile handoff must precede the hard compile limit")

    user = UserProxyAgent(
        name="user",
        human_input_mode="NEVER",
        code_execution_config=False,
        max_consecutive_auto_reply=0,
    )

    # One mechanical executor runs every tool, as in the stepped controller.
    executor = UserProxyAgent(
        name=AgentRole.EXECUTOR.value,
        human_input_mode="NEVER",
        code_execution_config=False,
        max_consecutive_auto_reply=config.max_turns,
    )

    # Register each tool with the roles allowed to call it.
    for tool_name, fn in tools.items():
        executor.register_for_execution(name=tool_name)(fn)
        for role, spec in config.roles.items():
            if tool_name in spec.tools and role in agents:
                agents[role].register_for_llm(
                    name=tool_name,
                    description=fn.__doc__ or tool_name,
                )(fn)

    members = [user, executor, *[agents[r] for r in config.roles if r in agents]]
    state = _RunState(turn_budget=config.max_turns)
    base_system_messages = {
        role: agent.system_message for role, agent in agents.items()
    }

    def _stall_key(rule: ToolStallHandoff) -> tuple[AgentRole, str]:
        return rule.caller, rule.tool

    def _reset_nonmatching_stalls(
        role: AgentRole | None,
        called: frozenset[str | None],
    ) -> None:
        for rule in stall_handoffs:
            if role is not rule.caller or called != frozenset({rule.tool}):
                state.tool_stall_streaks[_stall_key(rule)] = 0

    def _clear_pending_handoff() -> ToolStallHandoff | None:
        pending = state.pending_handoff
        if pending is not None:
            agents[pending.caller].update_system_message(
                base_system_messages[pending.caller]
            )
            state.pending_handoff = None
        return pending

    def _route(agent, parent_role: AgentRole, *, reason: str | None = None):
        # Record the causal edge: the NEXT agent's event will be caused by the
        # PARENT role's most recent event. record_routing expects a LIST of
        # event-ids, not a role -- passing the role here caused it to iterate the
        # enum's string value character-by-character (the ["s","y","s","t","e","m"]
        # bug), corrupting every caused_by edge in the graph.
        if ledger is not None and agent is not None:
            next_role = _role_of(agent.name) or AgentRole.SYSTEM
            cause = ledger.latest_event_id(parent_role)
            ledger.record_routing(next_role, [cause] if cause else [], reason=reason)
        return agent

    def select_next(last_speaker, groupchat: GroupChat):
        state.turns += 1
        if state.turns >= config.max_turns:
            _clear_pending_handoff()
            state.pending_post_tool_target = None
            state.pending_post_tool_reason = None
            state.terminated, state.reason = True, "cap"
            return None

        name = last_speaker.name

        # Entry: the user posts the task -> the configured entry agent.
        if name == "user":
            return _route(agents.get(config.entry), AgentRole.SYSTEM, reason="entry")

        # The executor just ran a tool. Recover the immediately preceding valid
        # caller/tool batch once; duplicate or orphan executor results must not
        # reuse an older caller.
        if name == AgentRole.EXECUTOR.value:
            result_message = _last_message(groupchat)
            caller, caller_message = _last_caller_before_executor(groupchat)
            called = _called_tools(caller_message)
            pending_target = state.pending_post_tool_target
            pending_reason = state.pending_post_tool_reason
            state.pending_post_tool_target = None
            state.pending_post_tool_reason = None

            if caller is None or not called:
                _reset_nonmatching_stalls(None, frozenset())
                _clear_pending_handoff()
                return _invalid(state, config, agents)

            if _is_tool_protocol_error(result_message):
                _clear_pending_handoff()
                state.tool_protocol_errors += 1
                state.terminated, state.reason = True, "stuck"
                return None

            result = _tool_result_dict(result_message)
            verdict = _compile_verdict(result_message)

            # Track compile progress before any typed route returns early.
            if config.max_failed_compiles > 0:
                if verdict is True:
                    state.consecutive_failed_compiles = 0
                elif verdict is False:
                    state.consecutive_failed_compiles += 1
                    state.max_failed_compiles_seen = max(
                        state.max_failed_compiles_seen,
                        state.consecutive_failed_compiles,
                    )
                    if (
                        state.consecutive_failed_compiles
                        >= config.max_failed_compiles
                    ):
                        _clear_pending_handoff()
                        state.terminated, state.reason = True, "stuck"
                        return None

            if config.tool_result_routing:
                terminate_reason = result.get("terminate_reason") if result else None
                if terminate_reason:
                    _clear_pending_handoff()
                    state.terminated, state.reason = True, str(terminate_reason)
                    return None
                if result and result.get("run_complete") is True:
                    _clear_pending_handoff()
                    state.terminated, state.reason = True, "clean"
                    return None

                target_name = result.get("handoff_target") if result else None
                if target_name:
                    target = _role_of(str(target_name))
                    caller_spec = config.spec(caller)
                    if (
                        target is not None
                        and caller_spec is not None
                        and target in caller_spec.handoff_targets
                        and target in agents
                    ):
                        route_kind = str(result.get("route_kind") or "tool_handoff")
                        state.tool_handoffs += 1
                        if route_kind == "failed_compile_recovery":
                            state.forced_recoveries += 1
                        return _route(
                            agents[target], AgentRole.EXECUTOR, reason=route_kind
                        )
                    return _invalid(state, config, agents)

                completion_denied = result is not None and result.get("ok") is False
                if completion_denied:
                    state.completion_gate_denials += 1
                elif pending_target is not None:
                    caller_spec = config.spec(caller)
                    if (
                        caller_spec is not None
                        and pending_target in caller_spec.handoff_targets
                        and pending_target in agents
                    ):
                        state.tool_handoffs += 1
                        state.controller_fallback_routes += 1
                        return _route(
                            agents[pending_target],
                            AgentRole.EXECUTOR,
                            reason=pending_reason or "controller_post_tool_fallback",
                        )
                    return _invalid(state, config, agents)

            # Track compile progress: a check_lean result updates the
            # consecutive-failure counter (a success resets it). search_lemmas
            # results return None here and are ignored. Structured stall rules
            # are setup-specific and run only after typed-result routing.
            _reset_nonmatching_stalls(caller, called)
            completed = bool(result_message.get("tool_responses"))
            for rule in stall_handoffs:
                matches = (
                    completed
                    and caller is rule.caller
                    and called == frozenset({rule.tool})
                    and (not rule.require_failed_compile or verdict is False)
                )
                key = _stall_key(rule)
                if not matches:
                    state.tool_stall_streaks[key] = 0
                    continue
                streak = state.tool_stall_streaks.get(key, 0) + 1
                state.tool_stall_streaks[key] = streak
                state.max_tool_stall_streaks[key] = max(
                    state.max_tool_stall_streaks.get(key, 0),
                    streak,
                )
                if streak >= rule.after_batches:
                    state.tool_stall_streaks[key] = 0
                    state.pending_handoff = rule
                    state.handoff_prompt_turns += 1
                    agents[rule.caller].update_system_message(
                        base_system_messages[rule.caller]
                        + "\n\n--- controller recovery turn ---\n"
                        + rule.handoff_prompt.strip()
                    )
                    return _route(
                        agents[rule.caller],
                        AgentRole.EXECUTOR,
                        reason="stall_handoff_prompt",
                    )
            return (
                _route(agents.get(caller), AgentRole.EXECUTOR, reason="tool_return")
                if caller in agents
                else None
            )

        role = _role_of(name)
        spec = config.spec(role) if role else None
        if spec is None:
            # Unknown speaker; nothing sensible to do.
            state.consecutive_invalid += 1
            return _terminate_if_stuck(state, config)

        text = _last_text(groupchat)

        pending_handoff = state.pending_handoff
        if pending_handoff is not None and role is pending_handoff.caller:
            _clear_pending_handoff()
            marker = parse_handoff(text)
            if (
                _is_native_tool_call(_last_message(groupchat))
                or marker.get("handoff_target") != pending_handoff.target.value
                or not _valid_handoff_summary(text, pending_handoff)
            ):
                state.handoff_prompt_failures += 1
                state.terminated, state.reason = True, "stuck"
                return None
            state.tool_stall_handoffs += 1
            state.consecutive_invalid = 0
            return _route(
                agents[pending_handoff.target],
                role,
                reason="stall_handoff",
            )

        # 1. Terminal marker (e.g. critic APPROVE) from a role allowed to end.
        if (
            config.allow_terminal_markers
            and spec.can_terminate
            and VERDICT_APPROVE in text.upper()
        ):
            state.terminated, state.reason = True, "clean"
            return None

        # 2. Native tool call (AG2 protocol): route to the executor, which runs
        #    it and returns control to this caller. The tool must be one this
        #    role is allowed to call; a disallowed tool is a coordination error.
        last_msg = _last_message(groupchat)
        _reset_nonmatching_stalls(role, _called_tools(last_msg))
        if _is_native_tool_call(last_msg):
            called = _called_tools(last_msg)
            if called and called <= spec.tools:
                state.consecutive_invalid = 0
                # Perseveration bound: if this submission is byte-identical
                # (after whitespace normalisation) to the previous one, count
                # it; past the threshold the agent is stuck resubmitting the
                # same thing, so stop the run as 'stuck' rather than loop to the
                # turn cap. The count is recorded so the offline detector can
                # confirm and characterise the episode.
                code = _normalise_call_code(last_msg)
                if code is not None and code == state.last_call_code:
                    state.consecutive_identical_calls += 1
                else:
                    state.consecutive_identical_calls = 1
                    state.last_call_code = code
                state.max_identical_calls_seen = max(
                    state.max_identical_calls_seen, state.consecutive_identical_calls
                )
                if state.consecutive_identical_calls >= config.max_identical_calls:
                    state.pending_post_tool_target = None
                    state.pending_post_tool_reason = None
                    state.terminated, state.reason = True, "stuck"
                    return None
                if config.tool_result_routing and post_tool_route is not None:
                    fallback = post_tool_route(role, frozenset(called))
                    if fallback is not None:
                        (
                            state.pending_post_tool_target,
                            state.pending_post_tool_reason,
                        ) = fallback
                return _route(executor, role, reason="tool_call")
            return _invalid(state, config, agents)  # called a tool it may not

        # 3. Expressed HANDOFF marker: hand to the named agent (text marker,
        #    since AG2 has no native next-agent mechanism).
        marker = parse_handoff(text) if config.allow_marker_handoffs else {}
        if "handoff_target" in marker:
            target = _role_of(marker["handoff_target"])
            if target is not None and target in spec.handoff_targets and target in agents:
                state.consecutive_invalid = 0
                return _route(agents[target], role, reason="marker_handoff")
            return _invalid(state, config, agents)

        # 4. No tool call and no parseable hand-off: a coordination omission.
        return _invalid(state, config, agents)

    def _last_caller_before_executor(
        groupchat: GroupChat,
    ) -> tuple[AgentRole | None, dict[str, Any]]:
        for msg in reversed(groupchat.messages[:-1]):
            r = _role_of(msg.get("name", ""))
            if r is AgentRole.EXECUTOR:
                return None, {}
            if r is not None:
                return (r, msg) if _is_native_tool_call(msg) else (None, {})
        return None, {}

    # AG2's GroupChat.max_round counts EVERY message (each agent turn, tool
    # call, and tool result), so it advances faster than our per-decision
    # ``state.turns`` (incremented once per select_next call). If the two were
    # equal, AG2 would end the chat on its own counter before our 'cap' branch
    # fired, leaving state.reason = None. We give AG2 generous headroom so OUR
    # cap is the one that trips and records the reason; finalize_run() below is
    # the belt-and-braces backfill for any path that still ends via AG2.
    groupchat = GroupChat(
        agents=members,
        messages=[],
        max_round=config.max_turns * 4,
        speaker_selection_method=select_next,
    )
    manager = GroupChatManager(groupchat=groupchat, llm_config=llm_config)
    return manager, user, groupchat, state


def finalize_run(state: _RunState) -> _RunState:
    """Ensure the run has a recorded termination reason. Call AFTER the chat.

    Keep an explicit selector reason. Otherwise distinguish a real turn-budget
    exhaustion from AG2 ending early without another routed action. The result
    is never None after a completed run.
    """
    if state.reason is None:
        state.terminated = True
        state.reason = (
            "cap"
            if state.turn_budget > 0 and state.turns >= state.turn_budget
            else "framework_stop"
        )
    return state


def _invalid(state: _RunState, config: RoutingConfig, agents: dict):
    """Record a coordination error and apply the fallback (route to entry).

    Fallback keeps the run alive so the trajectory continues to be observed; the
    incremented counters preserve the signal. Too many in a row -> 'stuck'.
    """
    state.invalid_handoffs += 1
    state.consecutive_invalid += 1
    stuck = _terminate_if_stuck(state, config)
    if state.terminated:
        return stuck
    # Fallback: hand to the entry agent so the run can recover.
    return agents.get(config.entry)


def _terminate_if_stuck(state: _RunState, config: RoutingConfig):
    if state.consecutive_invalid >= config.max_consecutive_invalid:
        state.terminated, state.reason = True, "stuck"
        return None
    return None
