"""Free-routing controller: agent-chosen hand-offs (Step 4d).

Where the stepped controller (controller.py) routes by a fixed workflow, this
controller lets each agent CHOOSE who acts next via a marker in its message
(``HANDOFF: <role>`` / ``TOOL: <tool>``). Coordination becomes a measured,
fallible decision: an agent can hand to the wrong role, skip a required tool, or
nobody can advance -- and each of those is a recorded event, which is the point
(the study measures multi-agent coordination, not just task success).

Domain-agnostic by construction. The controller knows only: a ``RoutingConfig``
(which roles exist, each role's allowed hand-off targets and allowed tools, the
entry role, the turn cap), how to read a marker, how to validate the expressed
target against the allowed set, and how to account for termination. It contains
NO Lean. A domain supplies a RoutingConfig and the matching agents/tools; Lean's
config lives in lean_team.py, astro's would live alongside. This is the O1
"framework-agnostic ... domain-adaptable" seam, made explicit.

Termination is always bounded: a run ends with a recorded reason -- ``clean``
(an agent emitted the terminal marker), ``cap`` (turn budget exhausted), or
``stuck`` (too many consecutive malformed/disallowed hand-offs). A bounded,
reason-tagged end means non-termination is itself observable data (coordination
collapse), never an infinite loop.
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

    def spec(self, role: AgentRole) -> RoleSpec | None:
        return self.roles.get(role)


@dataclass
class _RunState:
    """Mutable bookkeeping for one run."""

    turns: int = 0
    consecutive_invalid: int = 0
    terminated: bool = False
    reason: str | None = None  # 'clean' | 'cap' | 'stuck'
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


def _compile_verdict(message: dict[str, Any]) -> bool | None:
    """Read a check_lean compile verdict from an executor result message.

    Returns True/False if this is a check_lean result, or None if it is not a
    compile result at all (e.g. a search_lemmas result, which must NOT count
    toward the no-progress bound). ag2 stringifies the tool's dict with repr(),
    so we parse leniently with ast.literal_eval.
    """
    import ast

    responses = message.get("tool_responses") or []
    for r in responses:
        content = r.get("content")
        if not content:
            continue
        try:
            d = ast.literal_eval(content)
        except (ValueError, SyntaxError):
            continue
        if isinstance(d, dict) and "compiled" in d:
            return bool(d["compiled"])
    return None


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
) -> tuple[GroupChatManager, UserProxyAgent, GroupChat, _RunState]:
    """Build a group chat whose next-speaker is chosen by the agents' markers.

    ``agents`` maps each role in ``config`` to its (already-constructed) agent.
    ``tools`` maps tool names to functions; each is registered with every role
    allowed to call it (caller) and a shared mechanical executor (runner).
    Returns (manager, user_proxy, groupchat, run_state); ``run_state`` carries
    the termination reason and coordination-error counts after the run.
    """
    tools = tools or {}
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
    state = _RunState()

    def _route(agent, parent_role: AgentRole):
        # Record the causal edge: the NEXT agent's event will be caused by the
        # PARENT role's most recent event. record_routing expects a LIST of
        # event-ids, not a role -- passing the role here caused it to iterate the
        # enum's string value character-by-character (the ["s","y","s","t","e","m"]
        # bug), corrupting every caused_by edge in the graph.
        if ledger is not None and agent is not None:
            next_role = _role_of(agent.name) or AgentRole.SYSTEM
            cause = ledger.latest_event_id(parent_role)
            ledger.record_routing(next_role, [cause] if cause else [])
        return agent

    def select_next(last_speaker, groupchat: GroupChat):
        state.turns += 1
        if state.turns >= config.max_turns:
            state.terminated, state.reason = True, "cap"
            return None

        name = last_speaker.name

        # Entry: the user posts the task -> the configured entry agent.
        if name == "user":
            return _route(agents.get(config.entry), AgentRole.SYSTEM)

        # The executor just ran a tool -> control returns to whoever called it.
        # The caller is the last non-executor agent; recover it from the ledger
        # if present, else from the message before the tool result.
        if name == AgentRole.EXECUTOR.value:
            # Track compile progress: a check_lean result updates the
            # consecutive-failure counter (a success resets it). search_lemmas
            # results return None here and are ignored. Past the threshold the
            # agent is thrashing without ever compiling -- stop as 'stuck'.
            verdict = _compile_verdict(_last_message(groupchat))
            if verdict is True:
                state.consecutive_failed_compiles = 0
            elif verdict is False:
                state.consecutive_failed_compiles += 1
                state.max_failed_compiles_seen = max(
                    state.max_failed_compiles_seen, state.consecutive_failed_compiles
                )
                if state.consecutive_failed_compiles >= config.max_failed_compiles:
                    state.terminated, state.reason = True, "stuck"
                    return None
            caller = _last_caller_before_executor(groupchat)
            return _route(agents.get(caller), AgentRole.EXECUTOR) if caller else None

        role = _role_of(name)
        spec = config.spec(role) if role else None
        if spec is None:
            # Unknown speaker; nothing sensible to do.
            state.consecutive_invalid += 1
            return _terminate_if_stuck(state, config)

        text = _last_text(groupchat)

        # 1. Terminal marker (e.g. critic APPROVE) from a role allowed to end.
        if spec.can_terminate and VERDICT_APPROVE in text.upper():
            state.terminated, state.reason = True, "clean"
            return None

        # 2. Native tool call (AG2 protocol): route to the executor, which runs
        #    it and returns control to this caller. The tool must be one this
        #    role is allowed to call; a disallowed tool is a coordination error.
        last_msg = _last_message(groupchat)
        if _is_native_tool_call(last_msg):
            called = {tc.get("function", {}).get("name") for tc in last_msg.get("tool_calls") or []}
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
                    state.terminated, state.reason = True, "stuck"
                    return None
                return _route(executor, role)
            return _invalid(state, config, agents)  # called a tool it may not

        # 3. Expressed HANDOFF marker: hand to the named agent (text marker,
        #    since AG2 has no native next-agent mechanism).
        marker = parse_handoff(text)
        if "handoff_target" in marker:
            target = _role_of(marker["handoff_target"])
            if target is not None and target in spec.handoff_targets and target in agents:
                state.consecutive_invalid = 0
                return _route(agents[target], role)
            return _invalid(state, config, agents)

        # 4. No tool call and no parseable hand-off: a coordination omission.
        return _invalid(state, config, agents)

    def _last_caller_before_executor(groupchat: GroupChat) -> AgentRole | None:
        for msg in reversed(groupchat.messages[:-1]):
            r = _role_of(msg.get("name", ""))
            if r is not None and r is not AgentRole.EXECUTOR:
                return r
        return None

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

    If our selector set a reason (clean / cap / stuck), keep it. If the chat
    ended without our selector setting one -- the only remaining way out is
    AG2's own max_round limit -- record it as 'cap'. Guarantees ``reason`` is
    never None after a completed run, so 'how did this end' is always answerable.
    """
    if state.reason is None:
        state.terminated, state.reason = True, "cap"
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
