from __future__ import annotations

from datetime import UTC, datetime

from traj_eval.metrics.communication import summarize_communication
from traj_eval.trace_core.schema import AgentRole, EventType, TraceEvent


def _event(seq, role, event_type, payload, *, parent=None):
    return TraceEvent(
        event_id=f"e{seq}",
        trial_id="trial",
        seq=seq,
        timestamp=datetime.now(UTC),
        event_type=event_type,
        agent_role=role,
        caused_by=[parent] if parent else [],
        payload=payload,
    )


def _result(seq, compiled, *, parent):
    content = repr({"compiled": compiled, "sorry_free": compiled})
    return _event(
        seq,
        AgentRole.EXECUTOR,
        EventType.EXECUTION_RESULT,
        {"tool_responses": [{"id": f"c{seq}", "content": content}]},
        parent=parent,
    )


def test_linear_trace_has_no_recovery_revision():
    events = [
        _event(0, AgentRole.SYSTEM, EventType.MESSAGE, {"text": "task"}),
        _event(
            1,
            AgentRole.REASONER,
            EventType.MESSAGE,
            {"text": "strategy", "handoff_target": "engineer"},
            parent="e0",
        ),
        _event(
            2,
            AgentRole.ENGINEER,
            EventType.TOOL_CALL,
            {"tool_calls": [{"id": "c3", "name": "check_lean", "arguments": "{}"}]},
            parent="e1",
        ),
        _result(3, True, parent="e2"),
        _event(
            4,
            AgentRole.ENGINEER,
            EventType.MESSAGE,
            {"text": "done", "handoff_target": "critic"},
            parent="e3",
        ),
        _event(
            5,
            AgentRole.CRITIC,
            EventType.MESSAGE,
            {"text": "ok", "decision": "approve"},
            parent="e4",
        ),
    ]

    summary = summarize_communication(events)

    assert summary.engineer_to_reasoner == 0
    assert summary.critic_approvals == 1
    assert summary.critic_rejections == 0
    assert summary.evidence_backed_revisions == 0
    assert summary.revision_followed_by_compile_success is False


def test_failed_compile_then_reasoner_handoff_is_productive_revision_path():
    events = [
        _event(0, AgentRole.SYSTEM, EventType.MESSAGE, {"text": "task"}),
        _event(
            1,
            AgentRole.REASONER,
            EventType.MESSAGE,
            {"text": "strategy", "handoff_target": "engineer"},
            parent="e0",
        ),
        _event(
            2,
            AgentRole.ENGINEER,
            EventType.TOOL_CALL,
            {"tool_calls": [{"id": "c3", "name": "check_lean", "arguments": "{}"}]},
            parent="e1",
        ),
        _result(3, False, parent="e2"),
        _event(
            4,
            AgentRole.ENGINEER,
            EventType.MESSAGE,
            {"text": "revise strategy", "handoff_target": "reasoner"},
            parent="e3",
        ),
        _event(
            5,
            AgentRole.REASONER,
            EventType.MESSAGE,
            {"text": "new strategy", "handoff_target": "engineer"},
            parent="e4",
        ),
        _event(
            6,
            AgentRole.ENGINEER,
            EventType.TOOL_CALL,
            {"tool_calls": [{"id": "c7", "name": "check_lean", "arguments": "{}"}]},
            parent="e5",
        ),
        _result(7, True, parent="e6"),
    ]

    summary = summarize_communication(events)

    assert summary.engineer_to_reasoner == 1
    assert summary.failed_compile_results == 1
    assert summary.evidence_backed_revisions == 1
    assert summary.revision_followed_by_compile_success is True


def test_runtime_fallback_is_not_counted_as_explicit_handoff():
    events = [
        _event(0, AgentRole.SYSTEM, EventType.MESSAGE, {"text": "task"}),
        _event(
            1,
            AgentRole.ENGINEER,
            EventType.MESSAGE,
            {"text": "missing marker"},
            parent="e0",
        ),
        _event(
            2,
            AgentRole.REASONER,
            EventType.MESSAGE,
            {"text": "fallback"},
            parent="e1",
        ),
    ]

    summary = summarize_communication(events)

    assert summary.engineer_to_reasoner == 0
    assert summary.implicit_reasoner_reentries == 1


def test_old_failure_before_success_does_not_back_a_later_replan():
    events = [
        _event(0, AgentRole.SYSTEM, EventType.MESSAGE, {"text": "task"}),
        _event(
            1,
            AgentRole.ENGINEER,
            EventType.TOOL_CALL,
            {"tool_calls": [{"id": "c2", "name": "check_lean", "arguments": "{}"}]},
            parent="e0",
        ),
        _result(2, False, parent="e1"),
        _event(
            3,
            AgentRole.ENGINEER,
            EventType.TOOL_CALL,
            {"tool_calls": [{"id": "c4", "name": "check_lean", "arguments": "{}"}]},
            parent="e2",
        ),
        _result(4, True, parent="e3"),
        _event(
            5,
            AgentRole.ENGINEER,
            EventType.MESSAGE,
            {"text": "strategy question", "handoff_target": "reasoner"},
            parent="e4",
        ),
    ]

    summary = summarize_communication(events)

    assert summary.engineer_to_reasoner == 1
    assert summary.evidence_backed_revisions == 0


def test_critic_reject_and_recheck_are_visible():
    events = [
        _event(0, AgentRole.SYSTEM, EventType.MESSAGE, {"text": "task"}),
        _event(
            1,
            AgentRole.CRITIC,
            EventType.TOOL_CALL,
            {"tool_calls": [{"id": "c2", "name": "check_lean", "arguments": "{}"}]},
            parent="e0",
        ),
        _result(2, True, parent="e1"),
        _event(
            3,
            AgentRole.CRITIC,
            EventType.MESSAGE,
            {"text": "wrong statement", "decision": "reject", "handoff_target": "engineer"},
            parent="e2",
        ),
    ]

    summary = summarize_communication(events)

    assert summary.critic_rechecks == 1
    assert summary.critic_rejections == 1
    assert summary.critic_to_engineer == 1
    assert summary.evidence_backed_revisions == 1
