"""Tests for the trace core: schema, storage round-trip, causal localisation."""

from __future__ import annotations

from datetime import UTC, datetime

from traj_eval.trace_core.graph import first_violation
from traj_eval.trace_core.schema import (
    AgentRole,
    AnchorCheck,
    AnchorStatus,
    EventType,
    TraceEvent,
    TrialMeta,
)
from traj_eval.trace_core.storage import TrialLogWriter, read_trial


def _event(seq: int, eid: str, parents: list[str], violation: bool = False) -> TraceEvent:
    return TraceEvent(
        event_id=eid,
        trial_id="t1",
        seq=seq,
        timestamp=datetime.now(UTC),
        event_type=EventType.MESSAGE,
        agent_role=AgentRole.PLANNER,
        caused_by=parents,
        anchor=(AnchorCheck(name="x", status=AnchorStatus.VIOLATION) if violation else None),
    )


def test_schema_roundtrip():
    ev = _event(0, "e0", [])
    assert TraceEvent.model_validate(ev.model_dump(mode="json")) == ev


def test_storage_roundtrip(tmp_path):
    meta = TrialMeta(
        trial_id="t1",
        testbed="lean",
        task_id="fate_001",
        architecture="react_single",
        backbone="dummy",
        grounding=False,
        started_at=datetime.now(UTC),
    )
    events = [_event(0, "e0", []), _event(1, "e1", ["e0"])]
    path = tmp_path / "t1.jsonl"
    with TrialLogWriter(path, meta) as w:
        for e in events:
            w.append(e)

    rmeta, revents = read_trial(path)
    assert rmeta.task_id == "fate_001"
    assert [e.event_id for e in revents] == ["e0", "e1"]


def test_first_violation_follows_causal_order():
    events = [
        _event(0, "e0", []),
        _event(1, "e1", ["e0"], violation=True),
        _event(2, "e2", ["e1"], violation=True),
    ]
    fv = first_violation(events)
    assert fv is not None and fv.event_id == "e1"


def test_no_violation_returns_none():
    assert first_violation([_event(0, "e0", [])]) is None
