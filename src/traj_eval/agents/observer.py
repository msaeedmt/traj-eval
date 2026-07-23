"""Non-invasive trace observer for the AG2 substrate (O1, Step 2a).

Hooks the agents' outgoing-message path and emits one schema-valid TraceEvent
per message into a TrialLogWriter. It is a passive listener: it never sends a
message, never changes a reply, never appears in speaker selection. The hook
returns every message exactly as received, so attaching the observer cannot
change what the team does (the non-invasiveness property O1 depends on).

Step 2a scope: MESSAGE events only. No causal edges yet (`caused_by` is left
empty; the routing-derived edge rule is Step 2b) and no anchors (filled
post-hoc by domain logic, never here).

Step-index stamping (Phase 3): the per-step controller knows which plan step
an engineer/critic turn belongs to, but that knowledge lives only in the
selector closure -- it never reaches the logged event. Rather than have the
anchor layer re-derive step boundaries by replaying critic verdicts (which
would duplicate the controller's advance state machine in a second place and
silently mis-attribute steps whenever the two drift), the controller stamps the
truth at the source via a shared ``StepContext``. The observer reads it when
emitting an engineer/critic event, so the trace is self-describing: an event
carries its own ``step_idx``/``attempt`` the way it already carries
``has_final``. This mirrors how the RoutingLedger bridges selector and observer
for causal edges -- same one-writer/one-reader shape, different field.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from autogen import Agent, ConversableAgent

from traj_eval.agents.markers import parse_decision, parse_handoff
from traj_eval.agents.routing import RoutingLedger
from traj_eval.trace_core.schema import (
    AgentRole,
    EventType,
    TraceEvent,
    TrialMeta,
)
from traj_eval.trace_core.storage import TrialLogWriter


def _role_for(agent_name: str) -> AgentRole:
    """Map an AG2 agent name to a schema role.

    Agent names were pinned to AgentRole values in the role factories, so the
    four roles map directly. Anything else (the user proxy, the group-chat
    manager) is orchestration, not an agent role -> SYSTEM.
    """
    try:
        return AgentRole(agent_name)
    except ValueError:
        return AgentRole.SYSTEM


def _message_text(message: dict[str, Any] | str) -> str:
    """Extract the text content from an AG2 message (dict or str)."""
    if isinstance(message, dict):
        return message.get("content", "") or ""
    return message or ""


def _classify(message: dict[str, Any] | str) -> EventType:
    """Decide the event kind from the message shape (Step 4c).

    AG2 carries tool interactions as ordinary messages on the same outgoing
    path, distinguishable only by their shape: a caller's suggestion has a
    ``tool_calls`` list; an executor's result has ``role == "tool"`` (and a
    ``tool_responses`` list). Everything else is a plain MESSAGE. These two
    shapes were confirmed against ag2 0.13 directly, not assumed -- the same
    probe verified both pass through ``process_message_before_send``, which is
    why the observer can classify them here rather than needing a second hook.
    """
    if isinstance(message, dict):
        if message.get("tool_calls"):
            return EventType.TOOL_CALL
        if message.get("role") == "tool" or message.get("tool_responses"):
            return EventType.EXECUTION_RESULT
    return EventType.MESSAGE


def _tool_call_payload(message: dict[str, Any]) -> dict[str, Any]:
    """Structured payload for a TOOL_CALL: one row per suggested call.

    Keeps the raw argument string rather than parsing it -- the argument is the
    proof code the agent wants checked, and re-serialising risks changing it.
    The downstream metric ('was the submitted proof the thing last compiled?')
    needs the bytes as sent.
    """
    calls = []
    for tc in message.get("tool_calls") or []:
        fn = tc.get("function", {})
        calls.append(
            {
                "id": tc.get("id"),
                "name": fn.get("name"),
                "arguments": fn.get("arguments"),
            }
        )
    return {"tool_calls": calls}


def _tool_result_payload(message: dict[str, Any]) -> dict[str, Any]:
    """Structured payload for an EXECUTION_RESULT: the tool's returned text.

    AG2 puts the result under ``tool_responses`` (a list keyed by call id) and
    mirrors it into ``content``; we record both so the result can be tied back
    to its TOOL_CALL by id and read as plain text without re-parsing.
    """
    responses = []
    for tr in message.get("tool_responses") or []:
        responses.append(
            {
                "id": tr.get("tool_call_id"),
                "content": tr.get("content"),
            }
        )
    return {"tool_responses": responses, "text": _message_text(message)}


class StepContext:
    """Shared step pointer the controller writes and the observer reads.

    One instance per stepped trial. The controller updates ``step_idx`` and
    ``attempt`` as it advances the plan / consumes the repair budget; the
    observer reads them when stamping an engineer or critic event. Kept as a
    mutable object (not a value passed through the hook) for the same reason as
    the RoutingLedger: AG2 owns the hook signature, so selector and observer
    must share state through a side channel, not arguments.

    ``step_idx`` is 0-based and stays at its last value once the plan is
    exhausted; ``attempt`` is 0 for the first engineer try on a step and
    increments per step-local repair, resetting when the step advances. A turn
    that is not part of a plan step (planner, the opening task) leaves both at
    their defaults and is simply not stamped by the observer.
    """

    def __init__(self) -> None:
        self.step_idx: int = 0
        self.attempt: int = 0


class TraceObserver:
    """Attaches to agents and records their outgoing messages as TraceEvents.

    Usage:
        observer = TraceObserver(writer, trial_id="...")
        observer.attach([planner, engineer, critic, executor, user])
        ... run the chat ...
        writer.close()
    """

    def __init__(
        self,
        writer: TrialLogWriter,
        *,
        trial_id: str,
        ledger: RoutingLedger | None = None,
        step_context: StepContext | None = None,
    ):
        self._writer = writer
        self._trial_id = trial_id
        self._seq = 0
        self._last_event_id: str | None = None
        # Optional bridge to the speaker-selection function. When present, the
        # observer reads routing-derived parents for each event and reports each
        # emit back so later edges can point at it (Step 2b).
        self._ledger = ledger
        # Optional bridge to the per-step controller. When present, engineer and
        # critic events are stamped with the plan step they belong to (Step 2a).
        self._step_context = step_context

    def _next_seq(self) -> int:
        s = self._seq
        self._seq += 1
        return s

    def record_task(self, text: str) -> str:
        """Emit the opening task message as a SYSTEM event, before the chat runs.

        Call this once, before ``initiate_chat``, so it takes seq=0 and the
        planner's first message (seq=1) can point at it instead of being an
        artificial root. The event reports itself to the ledger as the SYSTEM
        role's latest, so the existing ``user -> planner`` transition (routed
        with cause_role=SYSTEM in build_team) attributes the planner to it with
        no selector change. Returns the task event_id.
        """
        event_id = str(uuid.uuid4())
        event = TraceEvent(
            event_id=event_id,
            trial_id=self._trial_id,
            seq=self._next_seq(),
            timestamp=datetime.now(UTC),
            event_type=EventType.MESSAGE,
            agent_role=AgentRole.SYSTEM,
            caused_by=[],  # the task is the genuine root of the trajectory
            payload={
                "sender": "user",
                "recipient": "chat_manager",
                "text": text,
            },
        )
        self._writer.append(event)
        self._last_event_id = event_id
        if self._ledger is not None:
            self._ledger.record_emit(AgentRole.SYSTEM, event_id)
        return event_id

    def _record_message(
        self,
        sender: ConversableAgent,
        message: dict[str, Any] | str,
        recipient: Agent,
        silent: bool,
    ) -> dict[str, Any] | str:
        """The hook. Emits a TraceEvent, then returns the message UNCHANGED."""
        role = _role_for(sender.name)
        event_type = _classify(message)

        # Routing-derived parents, if a ledger is wired. Empty otherwise (the
        # pure 2a behaviour). take_pending consumes the decision exactly once.
        caused_by = self._ledger.take_pending(role) if self._ledger else []
        route_reason = self._ledger.take_pending_reason(role) if self._ledger else None

        # Common payload: who/whom, plus the type-specific body below.
        payload: dict[str, Any] = {
            "sender": sender.name,
            "recipient": getattr(recipient, "name", str(recipient)),
        }
        if route_reason:
            payload["route_reason"] = route_reason

        # Type-specific body (Step 4c). Tool messages travel the same path as
        # plain messages and are told apart only by shape, so the payload shape
        # follows the classified type rather than the role.
        if event_type is EventType.TOOL_CALL:
            payload.update(_tool_call_payload(message))  # type: ignore[arg-type]
        elif event_type is EventType.EXECUTION_RESULT:
            payload.update(_tool_result_payload(message))  # type: ignore[arg-type]
        else:
            text = _message_text(message)
            payload["text"] = text
            # Minimal marker parsing: stamp the decision (approve/reject) or
            # has_final flag as structured fields (Step 2c). Only meaningful for
            # plain messages; tool events carry no verdict.
            payload.update(parse_decision(role, text))
            # Stamp the expressed coordination marker (4d free-routing): which
            # agent this one chose to hand to, or which tool it requested. We
            # record only what was EXPRESSED here -- judging whether the target
            # was allowed needs the RoutingConfig, which is the controller's /
            # metrics layer's concern, not the observer's. Keeping validity out
            # of the observer keeps it agnostic and config-free.
            payload.update(parse_handoff(text))

        # Stamp the plan step this turn belongs to, if a stepped controller is
        # driving (Step 2a), extended in 4c to tool events as well: a compiler
        # call and its result belong to the same step as the engineer turn that
        # issued them, so they must carry the same stamp for per-step
        # accumulation and the "did this step verify its proof" metric. The
        # executor speaks the result, so stamp ENGINEER/CRITIC *and* the tool
        # event types regardless of the speaking role.
        is_tool_event = event_type in (EventType.TOOL_CALL, EventType.EXECUTION_RESULT)
        if self._step_context is not None and (
            role in (AgentRole.ENGINEER, AgentRole.CRITIC) or is_tool_event
        ):
            payload["step_idx"] = self._step_context.step_idx
            payload["attempt"] = self._step_context.attempt

        event_id = str(uuid.uuid4())
        event = TraceEvent(
            event_id=event_id,
            trial_id=self._trial_id,
            seq=self._next_seq(),
            timestamp=datetime.now(UTC),
            event_type=event_type,
            agent_role=role,
            caused_by=caused_by,
            payload=payload,
        )
        self._writer.append(event)
        self._last_event_id = event_id

        # Let later routing decisions point at this event.
        if self._ledger is not None:
            self._ledger.record_emit(role, event_id)

        return message  # non-invasive: return exactly what we received

    def record_termination(self, reason: str, **details: Any) -> str:
        """Append an explicit terminal node after the chat stops."""
        event_id = str(uuid.uuid4())
        event = TraceEvent(
            event_id=event_id,
            trial_id=self._trial_id,
            seq=self._next_seq(),
            timestamp=datetime.now(UTC),
            event_type=EventType.MESSAGE,
            agent_role=AgentRole.SYSTEM,
            caused_by=[self._last_event_id] if self._last_event_id else [],
            payload={
                "phase": "termination",
                "termination_reason": reason,
                **details,
            },
        )
        self._writer.append(event)
        self._last_event_id = event_id
        if self._ledger is not None:
            self._ledger.record_emit(AgentRole.SYSTEM, event_id)
        return event_id

    def record_controller_plan(self, plan: dict[str, Any]) -> str:
        """Persist the controller's final plan view as a causal trace event."""
        event_id = str(uuid.uuid4())
        event = TraceEvent(
            event_id=event_id,
            trial_id=self._trial_id,
            seq=self._next_seq(),
            timestamp=datetime.now(UTC),
            event_type=EventType.MESSAGE,
            agent_role=AgentRole.SYSTEM,
            caused_by=[self._last_event_id] if self._last_event_id else [],
            payload={"phase": "controller_plan", "plan": plan},
        )
        self._writer.append(event)
        self._last_event_id = event_id
        if self._ledger is not None:
            self._ledger.record_emit(AgentRole.SYSTEM, event_id)
        return event_id

    def record_infrastructure_error(self, error: BaseException) -> str:
        """Persist a provider/runtime failure separately from agent behavior."""
        event_id = str(uuid.uuid4())
        event = TraceEvent(
            event_id=event_id,
            trial_id=self._trial_id,
            seq=self._next_seq(),
            timestamp=datetime.now(UTC),
            event_type=EventType.EXECUTION_RESULT,
            agent_role=AgentRole.SYSTEM,
            caused_by=[self._last_event_id] if self._last_event_id else [],
            payload={
                "phase": "infrastructure_error",
                "error_type": type(error).__name__,
                "message": str(error)[:1000],
            },
        )
        self._writer.append(event)
        self._last_event_id = event_id
        if self._ledger is not None:
            self._ledger.record_emit(AgentRole.SYSTEM, event_id)
        return event_id

    def attach(self, agents: list[ConversableAgent]) -> None:
        """Register the message hook on every agent."""
        for agent in agents:
            agent.register_hook("process_message_before_send", self._record_message)


def make_trial_meta(
    trial_id: str,
    *,
    task_id: str,
    backbone: str,
    testbed: str = "toy",
    architecture: str = "four_role_multi",
    grounding: bool = False,
    stress_level: int = 0,
    config: dict[str, Any] | None = None,
) -> TrialMeta:
    """Build the per-trial header record written before the event stream."""
    return TrialMeta(
        trial_id=trial_id,
        testbed=testbed,
        task_id=task_id,
        architecture=architecture,
        backbone=backbone,
        grounding=grounding,
        stress_level=stress_level,
        started_at=datetime.now(UTC),
        config=config or {},
    )
