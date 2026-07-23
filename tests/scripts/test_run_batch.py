"""Tests for the batch runner's outcome classification (pure logic). The live
run loop needs an LLM + kernel and is not exercised here; the classification
and import-error detection are.
"""

from __future__ import annotations

from dataclasses import dataclass
from inspect import signature
from types import SimpleNamespace

import pytest
import scripts.run_batch as run_batch_module
from scripts.run_batch import (
    TrialOutcome,
    _assert_summary_paths_available,
    _assert_trace_path_available,
    _build_run_summary,
    _configure_console,
    _explore_trace,
    _explore_traces,
    _recorded_termination,
    _report,
    _resolve_worker_thinking,
    _summary_stem,
    _task_prompt,
    _trace_is_analyzable,
    _trace_is_valid,
    _trace_path,
    _trial_config,
    _trial_key,
    _write_summary,
    run_one_trial,
)

from traj_eval.agents import lean_team, make_trial_meta
from traj_eval.agents.lean_team import (
    RECOVERY_TRIANGLE_NO_RETRIEVAL_V1,
    RECOVERY_TRIANGLE_STALL_HANDOFF_V1,
    RECOVERY_TRIANGLE_V1,
    TOOL_ROUTED_SUBGOALS_V1,
)
from traj_eval.dataset.loader import ProblemRecord
from traj_eval.metrics.communication import CommunicationSummary
from traj_eval.metrics.lean.outcomes import classify_outcome, looks_like_import_error
from traj_eval.trace_core.schema import AgentRole
from traj_eval.trace_core.storage import TrialLogWriter, read_trial


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


def test_trace_is_valid_accepts_terminal_trace(tmp_path):
    from traj_eval.agents.observer import TraceObserver

    path = tmp_path / "trial.jsonl"
    meta = make_trial_meta(trial_id="trial", task_id="task", backbone="test", testbed="lean")
    with TrialLogWriter(path, meta) as writer:
        observer = TraceObserver(writer, trial_id="trial")
        observer.record_termination("framework_stop", turns=0)

    assert _trace_is_valid(path) is True


def test_trace_is_valid_rejects_parseable_interrupted_trace(tmp_path):
    path = tmp_path / "trial.jsonl"
    meta = make_trial_meta(trial_id="trial", task_id="task", backbone="test", testbed="lean")
    with TrialLogWriter(path, meta):
        pass

    assert _trace_is_valid(path) is False


def test_trace_is_valid_requires_termination_to_be_the_final_event(tmp_path):
    from datetime import UTC, datetime

    from traj_eval.agents.observer import TraceObserver
    from traj_eval.trace_core.schema import AgentRole, EventType, TraceEvent

    path = tmp_path / "trial.jsonl"
    meta = make_trial_meta(
        trial_id="trial",
        task_id="task",
        backbone="test",
        testbed="lean",
        config={"setup": RECOVERY_TRIANGLE_V1},
    )
    with TrialLogWriter(path, meta) as writer:
        observer = TraceObserver(writer, trial_id="trial")
        observer.record_termination("framework_stop", turns=0)
        writer.append(
            TraceEvent(
                event_id="after-terminal",
                trial_id="trial",
                seq=1,
                timestamp=datetime.now(UTC),
                event_type=EventType.MESSAGE,
                agent_role=AgentRole.SYSTEM,
                payload={"text": "must invalidate completion"},
            )
        )

    assert _trace_is_valid(path) is False


def test_trace_is_valid_rejects_trial_or_setup_identity_mismatch(tmp_path):
    from traj_eval.agents.observer import TraceObserver

    path = tmp_path / "trial.jsonl"
    meta = make_trial_meta(
        trial_id="task_t0",
        task_id="task",
        backbone="test",
        testbed="lean",
        config={"setup": RECOVERY_TRIANGLE_V1},
    )
    with TrialLogWriter(path, meta) as writer:
        observer = TraceObserver(writer, trial_id="task_t0")
        observer.record_termination("framework_stop", turns=0)

    assert _trace_is_valid(
        path,
        expected_trial_id="task_t0",
        expected_setup=RECOVERY_TRIANGLE_V1,
    )
    assert not _trace_is_valid(
        path,
        expected_trial_id="wrong_t0",
        expected_setup=RECOVERY_TRIANGLE_V1,
    )
    assert not _trace_is_valid(
        path,
        expected_trial_id="task_t0",
        expected_setup=TOOL_ROUTED_SUBGOALS_V1,
    )


def test_trace_is_valid_rejects_event_trial_identity_mismatch(tmp_path):
    from datetime import UTC, datetime

    from traj_eval.trace_core.schema import EventType, TraceEvent

    path = tmp_path / "task_t0.jsonl"
    meta = make_trial_meta(
        trial_id="task_t0",
        task_id="task",
        backbone="test",
        testbed="lean",
        config={"setup": RECOVERY_TRIANGLE_V1},
    )
    with TrialLogWriter(path, meta) as writer:
        writer.append(
            TraceEvent(
                event_id="terminal",
                trial_id="wrong_t0",
                seq=0,
                timestamp=datetime.now(UTC),
                event_type=EventType.MESSAGE,
                agent_role=AgentRole.SYSTEM,
                payload={
                    "phase": "termination",
                    "termination_reason": "framework_stop",
                },
            )
        )

    assert not _trace_is_valid(
        path,
        expected_trial_id="task_t0",
        expected_setup=RECOVERY_TRIANGLE_V1,
        expected_task_id="task",
    )


def test_legacy_v1_trace_is_analyzable_but_never_resumable(tmp_path):
    from datetime import UTC, datetime

    from traj_eval.trace_core.schema import EventType, TraceEvent

    path = tmp_path / "task_t0.jsonl"
    meta = make_trial_meta(
        trial_id="task_t0",
        task_id="task",
        backbone="qwen",
        testbed="lean",
    )
    with TrialLogWriter(path, meta) as writer:
        writer.append(
            TraceEvent(
                event_id="legacy-event",
                trial_id="task_t0",
                seq=0,
                timestamp=datetime.now(UTC),
                event_type=EventType.MESSAGE,
                agent_role=AgentRole.REASONER,
                payload={"text": "historical trace without a terminal record"},
            )
        )

    assert not _trace_is_valid(
        path,
        expected_trial_id="task_t0",
        expected_setup=RECOVERY_TRIANGLE_V1,
        expected_task_id="task",
    )
    assert _trace_is_analyzable(
        path,
        expected_trial_id="task_t0",
        expected_setup=RECOVERY_TRIANGLE_V1,
        expected_task_id="task",
    )
    assert not _trace_is_analyzable(
        path,
        expected_trial_id="task_t0",
        expected_setup=TOOL_ROUTED_SUBGOALS_V1,
        expected_task_id="task",
    )


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
    with pytest.raises(ValueError, match="unsupported worker thinking mode"):
        _resolve_worker_thinking("anything", "invalid")


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


def test_trace_exploration_uses_the_setup_specific_trace_path(tmp_path):
    from traj_eval.agents.observer import TraceObserver

    record = ProblemRecord(
        id="LeanCat002",
        source="LeanCat",
        difficulty="easy",
        informal="An informal theorem.",
        statement="theorem task : True := by trivial",
        context="",
    )
    setup = RECOVERY_TRIANGLE_NO_RETRIEVAL_V1
    trial_id = _trial_key(record.id, 0, setup)
    path = _trace_path(tmp_path, record.id, 0, setup)
    meta = make_trial_meta(
        trial_id=trial_id,
        task_id=record.id,
        backbone="test",
        testbed="lean",
        config={"setup": setup},
    )
    with TrialLogWriter(path, meta) as writer:
        observer = TraceObserver(writer, trial_id=trial_id)
        observer.record_termination("framework_stop", turns=0)

    explored = _explore_traces(tmp_path, [record], 1, setup)

    assert [item["path"] for item in explored] == [path.name]
    assert explored[0]["trial_id"] == trial_id


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

    analysis_dir = tmp_path / "analysis"
    docs_dir = tmp_path / "docs"
    _write_summary(analysis_dir, docs_dir, summary)
    assert (analysis_dir / "summary.json").is_file()
    assert not (analysis_dir / "summary.md").exists()
    assert "O3" in (docs_dir / "summary.md").read_text(encoding="utf-8")
    assert not (docs_dir / "summary.json").exists()


def test_summary_outputs_are_write_once_and_preflight_all_targets(tmp_path):
    summary = _build_run_summary(
        [],
        expected_trials=0,
        setup=TOOL_ROUTED_SUBGOALS_V1,
        model="qwen",
        errors=[],
    )
    analysis_dir = tmp_path / "analysis"
    docs_dir = tmp_path / "docs"
    collision = docs_dir / "summary.md"
    collision.parent.mkdir(parents=True)
    collision.write_text("preserve", encoding="utf-8")

    with pytest.raises(FileExistsError, match="derived evidence"):
        _assert_summary_paths_available(
            analysis_dir,
            docs_dir,
            TOOL_ROUTED_SUBGOALS_V1,
        )
    with pytest.raises(FileExistsError, match="derived evidence"):
        _write_summary(analysis_dir, docs_dir, summary)

    assert collision.read_text(encoding="utf-8") == "preserve"
    assert not (analysis_dir / "summary.json").exists()


def test_run_summary_is_incomplete_when_expected_trials_are_missing():
    summary = _build_run_summary(
        [],
        expected_trials=1,
        setup=RECOVERY_TRIANGLE_V1,
        model="qwen",
    )

    assert summary["completed_trials"] == 0
    assert summary["provider_status"] == "incomplete"


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


def test_no_retrieval_changes_only_search_result():
    calls: list[str] = []

    def check_lean(code: str) -> str:
        return code

    def search_lemmas(query: str) -> str:
        """Search Mathlib for candidate declarations."""
        calls.append(query)
        return f"found: {query}"

    tools = {"check_lean": check_lean, "search_lemmas": search_lemmas}
    grounded = lean_team._tools_for_setup(tools, RECOVERY_TRIANGLE_V1)
    ablated = lean_team._tools_for_setup(
        tools, RECOVERY_TRIANGLE_NO_RETRIEVAL_V1
    )

    assert grounded is tools
    assert set(ablated) == set(grounded)
    assert ablated["check_lean"] is grounded["check_lean"]
    assert ablated["search_lemmas"].__name__ == search_lemmas.__name__
    assert signature(ablated["search_lemmas"]) == signature(search_lemmas)
    assert ablated["search_lemmas"].__doc__ == search_lemmas.__doc__
    assert grounded["search_lemmas"]("monic composition") == "found: monic composition"
    assert (
        ablated["search_lemmas"]("monic composition")
        == lean_team.RETRIEVAL_DISABLED_RESULT
    )
    assert calls == ["monic composition"]


def test_retrieval_metadata_is_matched_except_condition_labels():
    grounded = _trial_config(RECOVERY_TRIANGLE_V1)
    ablated = _trial_config(RECOVERY_TRIANGLE_NO_RETRIEVAL_V1)

    assert grounded["retrieval_condition"] == "enabled"
    assert ablated == grounded | {
        "setup": RECOVERY_TRIANGLE_NO_RETRIEVAL_V1,
        "retrieval_condition": "disabled",
    }


def test_trial_artifact_naming_suffixes_only_retrieval_and_stall_arms(tmp_path):
    baseline_key = _trial_key("LeanCat002", 0, RECOVERY_TRIANGLE_V1)
    tool_key = _trial_key("LeanCat002", 0, TOOL_ROUTED_SUBGOALS_V1)
    ablation_key = _trial_key(
        "LeanCat002", 0, RECOVERY_TRIANGLE_NO_RETRIEVAL_V1
    )
    stall_key = _trial_key(
        "LeanCat002", 0, RECOVERY_TRIANGLE_STALL_HANDOFF_V1
    )

    assert baseline_key == "LeanCat002_t0"
    assert tool_key == "LeanCat002_t0"
    assert ablation_key == (
        "LeanCat002_t0__recovery_triangle_no_retrieval_v1"
    )
    assert stall_key == "LeanCat002_t0__recovery_triangle_stall_handoff_v1"
    assert _trace_path(tmp_path, "LeanCat002", 0, RECOVERY_TRIANGLE_V1) == (
        tmp_path / "LeanCat002_t0.jsonl"
    )
    assert _trace_path(
        tmp_path, "LeanCat002", 0, TOOL_ROUTED_SUBGOALS_V1
    ) == (tmp_path / "LeanCat002_t0.jsonl")
    assert _trace_path(
        tmp_path, "LeanCat002", 0, RECOVERY_TRIANGLE_NO_RETRIEVAL_V1
    ) == tmp_path / "LeanCat002_t0__recovery_triangle_no_retrieval_v1.jsonl"
    assert _trace_path(
        tmp_path, "LeanCat002", 0, RECOVERY_TRIANGLE_STALL_HANDOFF_V1
    ) == tmp_path / "LeanCat002_t0__recovery_triangle_stall_handoff_v1.jsonl"
    assert _summary_stem(RECOVERY_TRIANGLE_V1) == "summary"
    assert _summary_stem(TOOL_ROUTED_SUBGOALS_V1) == "summary"
    assert _summary_stem(RECOVERY_TRIANGLE_NO_RETRIEVAL_V1) == (
        "summary__recovery_triangle_no_retrieval_v1"
    )
    assert _summary_stem(RECOVERY_TRIANGLE_STALL_HANDOFF_V1) == (
        "summary__recovery_triangle_stall_handoff_v1"
    )


def test_existing_unsuffixed_sibling_arm_is_never_overwritten(tmp_path):
    from traj_eval.agents.observer import TraceObserver

    path = _trace_path(tmp_path, "task", 0, TOOL_ROUTED_SUBGOALS_V1)
    meta = make_trial_meta(
        trial_id="task_t0",
        task_id="task",
        backbone="qwen",
        testbed="lean",
        config={"setup": TOOL_ROUTED_SUBGOALS_V1},
    )
    with TrialLogWriter(path, meta) as writer:
        observer = TraceObserver(writer, trial_id="task_t0")
        observer.record_termination("clean", turns=1)
    original = path.read_bytes()

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        _assert_trace_path_available(
            path,
            trial_id="task_t0",
            setup=RECOVERY_TRIANGLE_V1,
        )

    assert path.read_bytes() == original


def test_trial_config_records_typed_and_stall_runtime_controls():
    role_budgets = {
        AgentRole.REASONER: 100,
        AgentRole.ENGINEER: 200,
        AgentRole.CRITIC: 300,
    }
    typed = _trial_config(
        TOOL_ROUTED_SUBGOALS_V1,
        tools={"plan_subgoal", "check_lean", "finish_run"},
        max_turns=17,
        max_engineer_failures=4,
        max_forced_replans=1,
        outer_orchestrator="personal_experiment",
        worker_model="qwen-test",
        role_budgets=role_budgets,
        enable_thinking=False,
        min_subgoals=4,
    )
    stall = _trial_config(RECOVERY_TRIANGLE_STALL_HANDOFF_V1)

    assert typed["routing_policy"] == "tool_routed_subgoal_dag"
    assert typed["tools"] == ["check_lean", "finish_run", "plan_subgoal"]
    assert typed["max_turns"] == 17
    assert typed["role_max_tokens"] == {
        "reasoner": 100,
        "engineer": 200,
        "critic": 300,
    }
    assert typed["worker_enable_thinking"] is False
    assert typed["min_subgoals"] == 4
    assert stall["stall_handoff_thresholds"] == {
        "reasoner_search_batches": 2,
        "engineer_failed_compiles": 2,
    }


def test_run_one_trial_wires_role_budgets_thinking_and_metadata(
    tmp_path, monkeypatch
):
    config_calls: list[dict] = []
    captured_team: dict = {}

    def fake_build_llm_config(**kwargs):
        config_calls.append(kwargs)
        return {"config_call": len(config_calls), **kwargs}

    class FakeUser:
        def initiate_chat(self, manager, *, message, clear_history):
            assert manager == "manager"
            assert message
            assert clear_history is True

    run_state = SimpleNamespace(
        turns=1,
        turn_budget=20,
        terminated=True,
        reason="clean",
        invalid_handoffs=0,
        max_identical_calls_seen=0,
        max_failed_compiles_seen=0,
        tool_stall_handoffs=0,
        handoff_prompt_turns=0,
        handoff_prompt_failures=0,
        max_tool_stall_streaks={},
        tool_handoffs=0,
        forced_recoveries=0,
        completion_gate_denials=0,
        tool_protocol_errors=0,
        controller_fallback_routes=0,
    )

    def fake_build_team(llm_config, **kwargs):
        captured_team["manager_config"] = llm_config
        captured_team.update(kwargs)
        return (
            "manager",
            FakeUser(),
            SimpleNamespace(agents=[]),
            run_state,
        )

    def fake_check_lean(code: str) -> str:
        return code

    class FakeCompiler:
        def as_tool(self):
            return fake_check_lean

    def fake_search_factory(*, num_results):
        assert num_results == 5

        def search_lemmas(query: str) -> str:
            return query

        return search_lemmas

    sentinel = object()
    monkeypatch.setattr(run_batch_module, "build_llm_config", fake_build_llm_config)
    monkeypatch.setattr(run_batch_module, "build_lean_free_team", fake_build_team)
    monkeypatch.setattr(run_batch_module, "_score_trace", lambda *args, **kwargs: sentinel)
    import traj_eval.tools.lean_search as lean_search

    monkeypatch.setattr(lean_search, "make_search_lemmas", fake_search_factory)

    record = ProblemRecord(
        id="task",
        source="FATE-M",
        difficulty="easy",
        informal="An informal theorem.",
        statement="theorem task : True := by trivial",
        context="",
    )
    outcome = run_one_trial(
        record,
        0,
        FakeCompiler(),
        output_dir=tmp_path,
        setup=RECOVERY_TRIANGLE_V1,
        worker_model="openai/Qwen-test",
        reasoner_max_tokens=111,
        engineer_max_tokens=222,
        critic_max_tokens=333,
        worker_thinking="auto",
    )

    assert outcome is sentinel
    assert [call["max_tokens"] for call in config_calls] == [111, 222, 333, 111]
    assert all(call["enable_thinking"] is False for call in config_calls)
    assert captured_team["manager_config"] == config_calls[-1] | {"config_call": 4}
    assert {
        role: config["max_tokens"]
        for role, config in captured_team["role_llm_configs"].items()
    } == {
        AgentRole.REASONER: 111,
        AgentRole.ENGINEER: 222,
        AgentRole.CRITIC: 333,
    }

    meta, events = read_trial(
        _trace_path(tmp_path, "task", 0, RECOVERY_TRIANGLE_V1)
    )
    assert meta.trial_id == "task_t0"
    assert all(event.trial_id == meta.trial_id for event in events)
    assert meta.config["role_max_tokens"] == {
        "reasoner": 111,
        "engineer": 222,
        "critic": 333,
    }
    assert meta.config["worker_enable_thinking"] is False


def test_no_retrieval_summary_does_not_overwrite_baseline(tmp_path):
    baseline = _build_run_summary(
        [], expected_trials=0, setup=RECOVERY_TRIANGLE_V1, model="probe"
    )
    ablation = _build_run_summary(
        [],
        expected_trials=0,
        setup=RECOVERY_TRIANGLE_NO_RETRIEVAL_V1,
        model="probe",
    )

    analysis_dir = tmp_path / "analysis"
    docs_dir = tmp_path / "docs"
    _write_summary(analysis_dir, docs_dir, baseline)
    _write_summary(analysis_dir, docs_dir, ablation)

    assert (analysis_dir / "summary.json").is_file()
    assert (docs_dir / "summary.md").is_file()
    assert (
        analysis_dir / "summary__recovery_triangle_no_retrieval_v1.json"
    ).is_file()
    assert (
        docs_dir / "summary__recovery_triangle_no_retrieval_v1.md"
    ).is_file()


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
