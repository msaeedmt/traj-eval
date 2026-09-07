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

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from autogen import GroupChat, GroupChatManager, LLMConfig, UserProxyAgent, register_function

from traj_eval.agents.markers import VERDICT_APPROVE, parse_handoff
from traj_eval.agents.observer import StepContext
from traj_eval.agents.routing import RoutingLedger
from traj_eval.trace_core.schema import AgentRole

ProgressVerdictFn = Callable[[dict[str, Any]], bool | None]


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
    max_identical_calls: int = 4  # repeated tool submissions in a row -> 'stuck'
    # How far back a repeat is recognised. With 1 this bound sees only calls
    # identical to the IMMEDIATELY previous one, which misses cycles: on
    # seed13_diff10_t0 the planner issued 11 rv_periodogram calls with 3 distinct
    # argument sets, cycling 0.5-10 -> 10-100 -> 100-429.8 four times over and
    # receiving byte-identical results each time. No two CONSECUTIVE calls were
    # ever the same, so the bound never fired; the idle bound could not see it
    # either (these are tool calls) and the no-progress bound ignores
    # rv_periodogram by design. 8 covers every cycle length the roles can
    # plausibly produce while staying far below the number of genuinely distinct
    # calls a healthy trial makes.
    call_history_window: int = 8
    max_no_progress: int = 6  # consecutive unsuccessful verifier calls -> 'stuck'
    # Consecutive agent messages that call no tool and reach no verdict ->
    # 'stuck_idle'. The other two bounds both key on TOOL CALLS, so a team that
    # stops calling tools entirely is invisible to them: on seed22_diff4_t0 the
    # run ended with 21 consecutive messages and no tool call, stopped only by
    # the turn cap, with 4 of 5 submissions unused.
    #
    # 6 is set from data, not guessed. Over 145 completed trials no SUCCESSFUL
    # run ever exceeded 4 consecutive idle messages (median 1), while failures
    # reached 27 (median 6). Thresholds of 3 and 4 would have cut 3 and 1
    # successful trials respectively -- converting successes into recorded
    # failures and corrupting the failure statistics this project measures. 5 is
    # the first safe value; 6 leaves a two-message margin against a larger
    # sample, at a cost of about 2 percentage points of savings.
    #
    # Set to None to disable, which is worth doing on a small subset so that
    # full coordination collapse can still be observed rather than truncated.
    max_idle_messages: int | None = 6
    # Tools whose successful call means the team produced a scorable answer.
    # Domain-specific, so the agnostic controller is told rather than guessing:
    # astro sets {"rv_submit"}; Lean leaves it empty because its terminal act is
    # the APPROVE marker, not a tool call, and an empty set disables the bound.
    submission_tools: frozenset[str] = frozenset()
    # Fraction of max_turns after which a run that has never submitted is
    # stopped as 'stuck_no_submission'.
    #
    # This is the one pathology the other bounds structurally cannot see. On
    # seed13_diff10 a team ran the full 60 turns making only novel, well-formed,
    # successful tool calls -- no idling, no repeats, no cycles, no errors -- and
    # never submitted once, because the planner and engineer captured the loop
    # and the critic, the only role holding rv_submit, was never handed control.
    # Every bound passed; the work looked maximally productive and converged on
    # nothing.
    #
    # A fraction rather than a turn count because max_turns varies by tier
    # (30 / 50 / 90), so a fixed number would be wrong for all of them. Once a
    # submission exists the bound can never fire again: this is about never
    # reaching the goal at all, not about submitting slowly.
    submission_deadline_frac: float | None = 0.5
    progress_verdict: ProgressVerdictFn | None = None

    def spec(self, role: AgentRole) -> RoleSpec | None:
        return self.roles.get(role)

    def read_progress(self, message: dict[str, Any]) -> bool | None:
        verdict = self.progress_verdict or _LEAN_PROGRESS_VERDICT
        return verdict(message)


@dataclass
class _RunState:
    """Mutable bookkeeping for one run."""

    turns: int = 0
    consecutive_invalid: int = 0
    terminated: bool = False
    reason: str | None = None
    # 'clean' | 'cap' | 'stuck' | 'stuck_cycle' | 'stuck_idle'
    # | 'stuck_tool_error' | 'stuck_no_submission'
    invalid_handoffs: int = 0  # total coordination errors seen
    # Perseveration bound (4d): the last tool-call code and how many times in a
    # row it has been resubmitted identically. Repeated identical submission is
    # perseveration; we stop the run rather than let it burn the whole budget,
    # and record the count so the offline detector confirms what the bound saw.
    last_call_code: str | None = None
    # The last ``call_history_window`` distinct-position call signatures. A
    # repeat is a call whose signature is anywhere in here, not merely equal to
    # the previous one -- which is what lets the bound see cycles.
    recent_call_codes: deque[str] = field(default_factory=deque)
    consecutive_identical_calls: int = 0
    max_identical_calls_seen: int = 0
    # Set when a repeat matched a NON-adjacent earlier call, i.e. the team is
    # cycling rather than repeating one call. Reported as a distinct termination
    # reason so the two pathologies stay separable in analysis.
    saw_cycle: bool = False
    # The TIGHTEST loop observed: the smallest gap between a call and its most
    # recent earlier occurrence. Smallest rather than largest because a team
    # going A B C B C A is really stuck in the B-C pair; reporting 5 (the A-to-A
    # gap) would describe the outer wrapper rather than the loop it is caught in.
    cycle_period: int = 0
    # No-progress bound: consecutive failed compiles with no success between
    # them. Unlike the identical-calls bound, this catches "reworded thrashing"
    # -- the agent varying its code cosmetically while never compiling. A
    # successful compile resets it to 0.
    consecutive_no_progress: int = 0
    max_no_progress_seen: int = 0
    # Idle bound: consecutive agent messages that call no tool and reach no
    # verdict. Reset by either. Healthy runs interleave at 1 -- an agent
    # reasons, hands off, the next one calls a tool -- so a long run means work
    # is circulating while nothing is being done.
    consecutive_idle_messages: int = 0
    max_idle_messages_seen: int = 0
    # Consecutive executor results that were errors rather than answers. Tracked
    # so a run killed by repeated tool errors is never recorded as
    # perseveration: on seed13_diff10 a planner used the wrong field name, got
    # the single word "Error: 'P_days'" four times, and was stopped by the
    # repeat bound -- but it was not being stubborn, it had been given nothing
    # to act on. Attributing that to the agent would corrupt the taxonomy.
    consecutive_tool_errors: int = 0
    max_tool_errors_seen: int = 0
    # Calls to a configured submission tool. Counted at the CALL, not the
    # result: a submission the evaluator rejects is still an attempt at the
    # goal, and this bound is about never attempting.
    n_submission_calls: int = 0


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


def make_key_progress_verdict(key: str) -> ProgressVerdictFn:
    """Build a progress verdict reading one boolean key off a tool result."""
    import ast

    def _verdict(message: dict[str, Any]) -> bool | None:
        for r in message.get("tool_responses") or []:
            content = r.get("content")
            if not content:
                continue
            try:
                d = ast.literal_eval(content)
            except (ValueError, SyntaxError):
                continue
            if isinstance(d, dict) and key in d:
                return bool(d[key])
        return None

    return _verdict


_LEAN_PROGRESS_VERDICT: ProgressVerdictFn = make_key_progress_verdict("compiled")


def _looks_like_tool_error(message: dict[str, Any]) -> bool:
    """Did the executor return an error rather than an answer?

    Two shapes count. ag2 stringifies an uncaught exception as ``Error: ...``,
    and a tool that validates its own input returns a dict carrying an
    ``error`` key. Both mean the call produced no information the agent can use.
    """
    import ast

    for response in message.get("tool_responses") or []:
        content = response.get("content")
        if not content:
            continue
        text = str(content).strip()
        if text.startswith("Error:") or text.startswith("Error "):
            return True
        try:
            parsed = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            continue
        if isinstance(parsed, dict) and parsed.get("error"):
            return True
    return False


def _normalise_call_code(message: dict[str, Any]) -> str | None:
    """Whitespace-normalised signature of the tool call(s): NAME plus arguments.

    The tool NAME is part of the signature: without it, two different actions
    that happen to take the same payload are indistinguishable, which in the
    astro testbed is the normal workflow rather than a pathology.
    """
    import json as _json

    parts: list[str] = []
    for tc in message.get("tool_calls") or []:
        function = tc.get("function", {}) or {}
        args = function.get("arguments")
        if not args:
            continue
        name = str(function.get("name") or "?")
        try:
            parsed = _json.loads(args)
            payload = " ".join(str(v) for v in parsed.values())
        except (ValueError, TypeError, AttributeError):
            payload = str(args)
        parts.append(f"{name}({payload})")
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
        for role, spec in config.roles.items():
            if tool_name in spec.tools and role in agents:
                register_function(
                    fn,
                    caller=agents[role],
                    executor=executor,
                    name=tool_name,
                    description=fn.__doc__ or tool_name,
                )

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

        # Never-submitted bound. Only meaningful once a domain has named its
        # submission tools; without that the set is empty and this is inert.
        if (
            config.submission_tools
            and config.submission_deadline_frac is not None
            and state.n_submission_calls == 0
            and state.turns >= config.submission_deadline_frac * config.max_turns
        ):
            state.terminated, state.reason = True, "stuck_no_submission"
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
            if _looks_like_tool_error(_last_message(groupchat)):
                state.consecutive_tool_errors += 1
                state.max_tool_errors_seen = max(
                    state.max_tool_errors_seen, state.consecutive_tool_errors
                )
            else:
                state.consecutive_tool_errors = 0
            verdict = config.read_progress(_last_message(groupchat))
            if verdict is True:
                state.consecutive_no_progress = 0
            elif verdict is False:
                state.consecutive_no_progress += 1
                state.max_no_progress_seen = max(
                    state.max_no_progress_seen, state.consecutive_no_progress
                )
                if state.consecutive_no_progress >= config.max_no_progress:
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
            state.consecutive_idle_messages = 0
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
                # The team is doing work again.
                state.consecutive_idle_messages = 0
                if called & config.submission_tools:
                    state.n_submission_calls += 1
                # Perseveration bound: if this submission is byte-identical
                # (after whitespace normalisation) to the previous one, count
                # it; past the threshold the agent is stuck resubmitting the
                # same thing, so stop the run as 'stuck' rather than loop to the
                # turn cap. The count is recorded so the offline detector can
                # confirm and characterise the episode.
                code = _normalise_call_code(last_msg)
                if code is not None and code in state.recent_call_codes:
                    state.consecutive_identical_calls += 1
                    # Distance back to the match is the cycle period: 1 means the
                    # team repeated the immediately previous call, >1 means it is
                    # going round a loop.
                    history = list(state.recent_call_codes)
                    # Distance back to the MOST RECENT match, not the first:
                    # the nearest occurrence is the loop the team is actually in.
                    period = len(history) - max(i for i, c in enumerate(history) if c == code)
                    if period > 1:
                        state.saw_cycle = True
                        state.cycle_period = (
                            period if state.cycle_period == 0 else min(state.cycle_period, period)
                        )
                else:
                    state.consecutive_identical_calls = 1
                state.last_call_code = code
                if code is not None:
                    state.recent_call_codes.append(code)
                    while len(state.recent_call_codes) > max(config.call_history_window, 1):
                        state.recent_call_codes.popleft()
                state.max_identical_calls_seen = max(
                    state.max_identical_calls_seen, state.consecutive_identical_calls
                )
                if state.consecutive_identical_calls >= config.max_identical_calls:
                    state.terminated = True
                    # Repeating a call that keeps erroring is a tool-usability
                    # failure, not perseveration; keep them separable.
                    if state.consecutive_tool_errors >= config.max_identical_calls - 1:
                        state.reason = "stuck_tool_error"
                    else:
                        state.reason = "stuck_cycle" if state.saw_cycle else "stuck"
                    return None
                return _route(executor, role)
            return _invalid(state, config, agents)  # called a tool it may not

        # This message called no tool and ended nothing, so it is idle. Count
        # it BEFORE routing the hand-off: a stalled team hands off perfectly
        # well, which is exactly why the hand-off itself is not evidence of
        # progress. Terminating with its own reason keeps a detected stall
        # distinguishable from budget exhaustion in every downstream analysis.
        state.consecutive_idle_messages += 1
        state.max_idle_messages_seen = max(
            state.max_idle_messages_seen, state.consecutive_idle_messages
        )
        if (
            config.max_idle_messages is not None
            and state.consecutive_idle_messages >= config.max_idle_messages
        ):
            state.terminated, state.reason = True, "stuck_idle"
            return None

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
