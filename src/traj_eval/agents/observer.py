"""Non-invasive trace observer for the AG2 substrate (O1, Step 2a).

Hooks the agents' outgoing-message path and emits one schema-valid TraceEvent
per message into a TrialLogWriter. It is a passive listener: it never sends a
message, never changes a reply, never appears in speaker selection. The hook
returns every message exactly as received, so attaching the observer cannot
change what the team does (the non-invasiveness property O1 depends on).

Step 2a scope: MESSAGE events only. No causal edges yet (`caused_by` is left
empty; the routing-derived edge rule is Step 2b) and no anchors (filled
post-hoc by domain logic, never here).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from autogen import Agent, ConversableAgent

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
    ):
        self._writer = writer
        self._trial_id = trial_id
        self._seq = 0
        # Optional bridge to the speaker-selection function. When present, the
        # observer reads routing-derived parents for each event and reports each
        # emit back so later edges can point at it (Step 2b).
        self._ledger = ledger

    def _next_seq(self) -> int:
        s = self._seq
        self._seq += 1
        return s

    def _record_message(
        self,
        sender: ConversableAgent,
        message: dict[str, Any] | str,
        recipient: Agent,
        silent: bool,
    ) -> dict[str, Any] | str:
        """The hook. Emits a TraceEvent, then returns the message UNCHANGED."""
        role = _role_for(sender.name)

        # Routing-derived parents, if a ledger is wired. Empty otherwise (the
        # pure 2a behaviour). take_pending consumes the decision exactly once.
        caused_by = self._ledger.take_pending(role) if self._ledger else []

        event_id = str(uuid.uuid4())
        event = TraceEvent(
            event_id=event_id,
            trial_id=self._trial_id,
            seq=self._next_seq(),
            timestamp=datetime.now(UTC),
            event_type=EventType.MESSAGE,
            agent_role=role,
            caused_by=caused_by,
            payload={
                "sender": sender.name,
                "recipient": getattr(recipient, "name", str(recipient)),
                "text": _message_text(message),
            },
        )
        self._writer.append(event)

        # Let later routing decisions point at this event.
        if self._ledger is not None:
            self._ledger.record_emit(role, event_id)

        return message  # non-invasive: return exactly what we received

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
