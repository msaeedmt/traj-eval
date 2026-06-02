"""Framework-agnostic trace event schema (O1).

This module is the single source of truth for what a trajectory looks like.
Every observer, regardless of substrate (AG2, Lean, ...), emits objects that
validate against these models. The JSON Schema is exported from here so that
non-Python tooling can validate against the identical contract.

Design rules (keep these stable — changing them invalidates logged trials):
  * Every event has a globally unique `event_id` and a `trial_id`.
  * Causal structure is expressed by `caused_by`: a list of parent event_ids.
    The directed interaction graph G is built from these edges.
  * `anchor` is a slot populated by domain-specific anchor logic *after*
    logging; the observer itself never fills it (separation of concerns).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

SCHEMA_VERSION = "0.1.0"


class AgentRole(StrEnum):
    """Fixed four-role decomposition from the proposal (Methodology §4.1)."""

    PLANNER = "planner"
    ENGINEER = "engineer"  # engineer / formaliser
    CRITIC = "critic"  # critic / reviewer
    EXECUTOR = "executor"  # executor / repairer
    SYSTEM = "system"  # orchestrator / environment, not an agent


class EventType(StrEnum):
    """The event kinds the non-invasive observer records (Methodology §4.2)."""

    MESSAGE = "message"
    TOOL_CALL = "tool_call"
    CODE_EVENT = "code_event"
    RETRY = "retry"
    EXECUTION_RESULT = "execution_result"
    CONFIDENCE_REPORT = "confidence_report"  # numeric confidence at termination


class AnchorStatus(StrEnum):
    PASS = "pass"
    VIOLATION = "violation"
    NOT_APPLICABLE = "n/a"


class AnchorCheck(BaseModel):
    """Result of a domain-specific anchor check attached to an event.

    Domain-adaptable: Lean reads correctness from the proof state; astro
    recomputes intermediate quantities from the Stargazer forward model.
    The schema only cares that a check has a status and is identifiable.
    """

    name: str = Field(..., description="e.g. 'periodogram_peak', 'subgoal_discharge'")
    status: AnchorStatus
    expected: Any | None = None
    observed: Any | None = None
    detail: str | None = None


class TraceEvent(BaseModel):
    """A single node in the directed interaction graph G."""

    schema_version: str = SCHEMA_VERSION
    event_id: str = Field(..., description="Globally unique within a trial")
    trial_id: str
    seq: int = Field(..., description="Monotonic order within the trial")
    timestamp: datetime

    event_type: EventType
    agent_role: AgentRole

    caused_by: list[str] = Field(
        default_factory=list,
        description="Parent event_ids; defines edges of G",
    )

    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Type-specific content (message text, tool name/args, code, stdout, ...)",
    )

    # Populated post-hoc by anchor logic, never by the observer itself.
    anchor: AnchorCheck | None = None


class TrialMeta(BaseModel):
    """One header record per trial, written before the event stream."""

    trial_id: str
    schema_version: str = SCHEMA_VERSION
    testbed: str = Field(..., description="'lean' or 'astro'")
    task_id: str
    architecture: str = Field(..., description="e.g. 'react_single', 'four_role_multi'")
    backbone: str = Field(..., description="model identifier")
    grounding: bool = Field(..., description="Mathlib / CAMB docs toggled on?")
    stress_level: int = 0
    started_at: datetime
    config: dict[str, Any] = Field(default_factory=dict)
