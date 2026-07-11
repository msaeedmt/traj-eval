"""Tests for the batch runner's outcome classification (pure logic). The live
run loop needs an LLM + kernel and is not exercised here; the classification
and import-error detection are.
"""

from __future__ import annotations

from dataclasses import dataclass

from traj_eval.agents import make_trial_meta
from traj_eval.agents.lean_team import TOOL_ROUTED_SUBGOALS_V1
from scripts.run_batch import (
    TrialOutcome,
    _build_run_summary,
    _configure_console,
    _explore_trace,
    _report,
    _recorded_termination,
    _resolve_worker_thinking,
    _task_prompt,
    _trace_is_valid,
    _write_summary,
)
from traj_eval.dataset.loader import ProblemRecord
from traj_eval.metrics.communication import CommunicationSummary
from traj_eval.metrics.lean.outcomes import classify_outcome, looks_like_import_error
from traj_eval.trace_core.storage import TrialLogWriter


@dataclass
class _FakeMetrics:
    final_proof_compiles: bool | None = None
    final_proof_sorry_free: bool | None = None
    statement_preserved: bool | None = None
    axiom_clean: bool | None = None
    silent_failure: bool | None = None
    has_submission: bool | None = True


@dataclass
class _FakeEvent:
    event_type: object
    payload: dict


def _make_result_event(text):
    from traj_eval.trace_core.schema import EventType

    return _FakeEvent(EventType.EXECUTION_RESULT, {"text": text})


def test_solved_when_all_group_b_true():
    m = _FakeMetrics(
        final_proof_compiles=True,
        final_proof_sorry_free=True,
        statement_preserved=True,
        axiom_clean=True,
        silent_failure=False,
    )
    assert classify_outcome([], m) == "solved"


def test_silent_failure_classified():
    m = _FakeMetrics(
        final_proof_compiles=False,
        final_proof_sorry_free=True,
        statement_preserved=False,
        axiom_clean=True,
        silent_failure=True,
    )
    assert classify_outcome([], m) == "silent_failure"


def test_unsolved_when_incomplete():
    m = _FakeMetrics(
        final_proof_compiles=False,
        final_proof_sorry_free=True,
        statement_preserved=None,
        axiom_clean=None,
        silent_failure=None,
    )
    assert classify_outcome([], m) == "unsolved"


def test_validation_unknown_when_posthoc_verdict_is_indeterminate():
    m = _FakeMetrics(
        final_proof_compiles=None,
        final_proof_sorry_free=None,
        statement_preserved=None,
        axiom_clean=None,
        silent_failure=None,
        has_submission=True,
    )
    assert classify_outcome([], m) == "validation_unknown"


def test_import_error_takes_precedence():
    # even if metrics would say unsolved, an import error in the trace wins
    ev = _make_result_event("{'compiled': False, 'errors': [{'data': 'unknown module Foo'}]}")
    ev.payload["phase"] = "infrastructure_error"
    m = _FakeMetrics(final_proof_compiles=False)
    assert classify_outcome([ev], m) == "import_error"


def test_solved_final_proof_takes_precedence_over_earlier_import_error():
    ev = _make_result_event("{'compiled': False, 'errors': [{'data': 'unknown constant Foo'}]}")
    m = _FakeMetrics(
        final_proof_compiles=True,
        final_proof_sorry_free=True,
        statement_preserved=True,
        axiom_clean=True,
        silent_failure=False,
    )
    assert classify_outcome([ev], m) == "solved"


def test_import_error_detection_positive():
    ev = _make_result_event("{'compiled': False, 'summary': 'unknown module Mathlib.Foo.Bar'}")
    ev.payload["phase"] = "infrastructure_error"
    assert looks_like_import_error([ev]) is True


def test_hallucinated_import_is_engineer_failure_not_infrastructure():
    ev = _make_result_event("{'compiled': False, 'summary': 'unknown module Imaginary.Foo'}")
    assert looks_like_import_error([ev]) is False
    assert classify_outcome([ev], _FakeMetrics(final_proof_compiles=False)) == "unsolved"


def test_import_error_detection_ignores_ordinary_failure():
    # a normal proof error (unsolved goals) is NOT an import error
    ev = _make_result_event("{'compiled': False, 'errors': [{'data': 'unsolved goals'}]}")
    assert looks_like_import_error([ev]) is False


def test_import_error_detection_ignores_unknown_api_symbols():
    for diagnostic in ("unknown constant Foo", "unknown identifier bar", "unknown namespace Baz"):
        ev = _make_result_event(
            "{'compiled': False, 'errors': [{'data': '" + diagnostic + "'}]}"
        )
        assert looks_like_import_error([ev]) is False


def test_import_error_detection_ignores_success():
    ev = _make_result_event("{'compiled': True, 'sorry_free': True}")
    assert looks_like_import_error([ev]) is False


def test_trace_is_valid_accepts_readable_trace(tmp_path):
    path = tmp_path / "trial.jsonl"
    meta = make_trial_meta(trial_id="trial", task_id="task", backbone="test", testbed="lean")
    with TrialLogWriter(path, meta):
        pass

    assert _trace_is_valid(path) is True


def test_trace_is_valid_rejects_missing_empty_and_invalid(tmp_path):
    missing = tmp_path / "missing.jsonl"
    empty = tmp_path / "empty.jsonl"
    invalid = tmp_path / "invalid.jsonl"
    empty.write_text("")
    invalid.write_text("not json\n")

    assert _trace_is_valid(missing) is False
    assert _trace_is_valid(empty) is False
    assert _trace_is_valid(invalid) is False


def test_recorded_termination_prefers_explicit_terminal_event():
    events = [
        _FakeEvent(object(), {"text": "work"}),
        _FakeEvent(
            object(),
            {"phase": "termination", "termination_reason": "framework_stop"},
        ),
    ]

    assert _recorded_termination(events) == "framework_stop"
    assert _recorded_termination(events[:1]) == "offline_rescore"


def test_worker_thinking_auto_disables_qwen_only():
    assert _resolve_worker_thinking("openai/Qwen3.5-27B.gguf", "auto") is False
    assert _resolve_worker_thinking("gpt-4o-mini", "auto") is None
    assert _resolve_worker_thinking("anything", "enabled") is True
    assert _resolve_worker_thinking("anything", "disabled") is False


def test_trace_exploration_reads_controller_plan_and_graph(tmp_path):
    path = tmp_path / "task_t0.jsonl"
    meta = make_trial_meta(trial_id="task_t0", task_id="task", backbone="qwen", testbed="lean")
    with TrialLogWriter(path, meta) as writer:
        from datetime import UTC, datetime

        from traj_eval.trace_core.schema import AgentRole, EventType, TraceEvent

        writer.append(
            TraceEvent(
                event_id="plan",
                trial_id="task_t0",
                seq=0,
                timestamp=datetime.now(UTC),
                event_type=EventType.MESSAGE,
                agent_role=AgentRole.SYSTEM,
                payload={
                    "phase": "controller_plan",
                    "plan": {
                        "owner_role": "reasoner",
                        "history": [{"version": 1}],
                        "final_state": {
                            "version": 1,
                            "plan_ready": True,
                            "nodes": [{"id": "goal", "status": "active"}],
                        },
                    },
                },
            )
        )

    explored = _explore_trace(path)

    assert explored["graph"] == {"nodes": 1, "edges": 0, "roots": 1, "leaves": 1}
    assert explored["controller_plan"]["present"] is True
    assert explored["controller_plan"]["history_length"] == 1


def _communication(
    *,
    failed=0,
    revisions=0,
    recovered=False,
    approvals=0,
    handed_off=True,
    tool_handoffs=0,
    forced_recoveries=0,
    strategy_revisions=0,
    subgoals_accepted=0,
    verified_completion=False,
):
    return CommunicationSummary(
        explicit_handoffs=2 if handed_off else 0,
        reasoner_to_engineer=1 if handed_off else 0,
        engineer_to_reasoner=revisions,
        engineer_to_critic=1 if handed_off else 0,
        critic_to_engineer=0,
        implicit_reasoner_reentries=0,
        failed_compile_results=failed,
        successful_compile_results=int(recovered),
        critic_rechecks=0,
        critic_approvals=approvals,
        critic_rejections=0,
        evidence_backed_revisions=revisions,
        revision_followed_by_compile_success=recovered,
        graph_longest_path=4,
        graph_dead_end_fraction=0.2,
        tool_handoffs=tool_handoffs,
        forced_recoveries=forced_recoveries,
        strategy_revisions=strategy_revisions,
        subgoals_accepted=subgoals_accepted,
        verified_completion=verified_completion,
    )


def test_run_summary_uses_recovery_decision_gate(tmp_path):
    outcome = TrialOutcome(
        task_id="task",
        difficulty="easy",
        trial=0,
        outcome="solved",
        termination="clean",
        n_tool_calls=2,
        perseverated=False,
        communication=_communication(failed=1, revisions=1, recovered=True),
    )
    summary = _build_run_summary(
        [outcome], expected_trials=1, setup="recovery_triangle_v1", model="qwen"
    )

    assert summary["decision"] == "scale_recovery_triangle_to_10_trials"
    assert summary["communication"]["productive_recovery_trials"] == 1

    _write_summary(tmp_path, summary)
    assert (tmp_path / "summary.json").is_file()
    assert "O3" in (tmp_path / "summary.md").read_text(encoding="utf-8")


def test_run_summary_counts_reasoner_stall_and_critic_masking():
    outcomes = [
        TrialOutcome(
            task_id="stalled",
            difficulty="easy",
            trial=0,
            outcome="unsolved",
            termination="max_turns",
            n_tool_calls=10,
            perseverated=True,
            communication=_communication(handed_off=False),
        ),
        TrialOutcome(
            task_id="masked",
            difficulty="easy",
            trial=0,
            outcome="silent_failure",
            termination="critic_approved",
            n_tool_calls=2,
            perseverated=False,
            communication=_communication(approvals=1),
        ),
    ]

    summary = _build_run_summary(
        outcomes, expected_trials=2, setup="recovery_triangle_v1", model="qwen"
    )

    assert summary["communication"]["reasoner_stall_trials"] == 1
    assert summary["communication"]["critic_masking_trials"] == 1


def test_task_prompt_allows_evidence_backed_free_routing():
    record = ProblemRecord(
        id="task",
        source="FATE-M",
        difficulty="easy",
        informal="An informal theorem.",
        statement="theorem task : True := by trivial",
        context="",
    )

    prompt = _task_prompt(record)

    assert "Each role chooses its next allowed action" in prompt
    assert "extra communication is not itself success" in prompt


def test_tool_subgoal_prompt_requires_typed_routing():
    record = ProblemRecord(
        id="task",
        source="FATE-M",
        difficulty="easy",
        informal="An informal theorem.",
        statement="theorem task : True := by trivial",
        context="",
    )

    prompt = _task_prompt(record, setup=TOOL_ROUTED_SUBGOALS_V1)

    assert "typed subgoal tools" in prompt
    assert "two work subgoals plus one final integration subgoal" in prompt
    assert "sequential dependencies" in prompt
    assert "Do not use HANDOFF or VERDICT" in prompt


def test_tool_subgoal_summary_reports_feasibility_not_o3():
    outcome = TrialOutcome(
        task_id="task",
        difficulty="easy",
        trial=0,
        outcome="solved",
        termination="clean",
        n_tool_calls=12,
        perseverated=False,
        communication=_communication(
            tool_handoffs=4,
            subgoals_accepted=3,
            verified_completion=True,
        ),
    )

    summary = _build_run_summary(
        [outcome],
        expected_trials=1,
        setup=TOOL_ROUTED_SUBGOALS_V1,
        model="qwen",
    )

    assert summary["decision"] == "feasibility_demonstrated_no_o3_claim"
    assert summary["proposal_status"]["O3"] == "not claimed from this feasibility pilot"


def test_tool_subgoal_summary_does_not_reward_silent_completion():
    outcome = TrialOutcome(
        task_id="task",
        difficulty="easy",
        trial=0,
        outcome="silent_failure",
        termination="clean",
        n_tool_calls=12,
        perseverated=False,
        communication=_communication(
            tool_handoffs=4,
            subgoals_accepted=3,
            verified_completion=True,
            approvals=1,
        ),
    )

    summary = _build_run_summary(
        [outcome],
        expected_trials=1,
        setup=TOOL_ROUTED_SUBGOALS_V1,
        model="qwen",
    )

    assert summary["decision"] == "final_faithfulness_gate_required"
    assert summary["communication"]["critic_masking_trials"] == 1


def test_report_preserves_summary_mapping(capsys):
    outcome = TrialOutcome(
        task_id="task",
        difficulty="easy",
        trial=0,
        outcome="solved",
        termination="clean",
        n_tool_calls=1,
        perseverated=False,
        communication=_communication(),
    )
    summary = _build_run_summary(
        [outcome], expected_trials=1, setup="recovery_triangle_v1", model="qwen"
    )

    _report([outcome], summary)

    assert "decision:" in capsys.readouterr().out


def test_configure_console_accepts_test_capture_streams():
    _configure_console()
