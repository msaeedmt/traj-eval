from __future__ import annotations

import json
import os

import pytest

pytest.importorskip("autogen", reason="agents extra (ag2) not installed")

from scripts.run_routing_ablation import (
    DEFAULT_TASKS,
    PROJECT_CONTRACT_FILES,
    PROVIDER_MAX_RETRIES,
    RETRIEVAL_ONLY_STREAK_EVALUATION,
    TrialOutcome,
    _read_smoke_result,
    _refuse_existing,
    _score_trace,
    _trace_is_valid,
    _trial_config,
    _trial_meta,
    balanced_schedule,
    build_preplanned_comparison,
    preflight_new_run,
    read_provider_env,
    run_trial_with_one_infrastructure_retry,
    task_prompt,
    verify_lean_project_contract,
    wilson_interval,
    write_summaries,
)

from traj_eval.agents.lean_routing_ablation import RoutingArm
from traj_eval.agents.observer import TraceObserver, make_trial_meta
from traj_eval.dataset.loader import ProblemRecord
from traj_eval.trace_core.storage import TrialLogWriter


def _record() -> ProblemRecord:
    return ProblemRecord(
        id="easy_fatem_test",
        source="FATE-M",
        difficulty="easy",
        imports=["Mathlib.Data.Nat.Basic"],
        statement="theorem sample (a b : Nat) : a + b = b + a",
        context="variable (a b : Nat)",
        informal="Addition is commutative.",
        module="Sample",
        source_id="test",
        path=None,
    )


def _outcome(arm: RoutingArm, task: str, trial: int, solved: bool) -> TrialOutcome:
    return TrialOutcome(
        arm=arm.value,
        task_id=task,
        trial=trial,
        trace="trace.jsonl",
        attempt=0,
        outcome="solved" if solved else "unsolved",
        termination="clean" if solved else "cap",
        worker_turns=1,
        controller_turns=0,
        total_model_calls=1,
        elapsed_seconds=1.0,
        n_tool_calls=1,
        perseverated=False,
        retrieval_only_streak=0,
        max_retrieval_only_streak_seen=0,
        reasoner_stuck_to_engineer=0,
        engineer_stuck_to_reasoner=0,
        engineer_local_retries=0,
        communication={},
        validation={},
    )


def test_schedule_is_complete_balanced_and_rotated():
    arms = tuple(RoutingArm)
    schedule = balanced_schedule(DEFAULT_TASKS, arms, 20)

    assert len(schedule) == 160
    assert len(set(schedule)) == 160
    for arm in arms:
        for task in DEFAULT_TASKS:
            assert sum(item[1:] == (task, arm) for item in schedule) == 20
    assert schedule[0][2] is RoutingArm.LEGACY_DETERMINISTIC
    assert schedule[8][2] is RoutingArm.UPSTREAM_FREE


def test_160_slot_preflight_refuses_collision_before_any_run(tmp_path):
    arms = tuple(RoutingArm)
    schedule = balanced_schedule(DEFAULT_TASKS, arms, 20)
    raw_dir = tmp_path / "raw"
    analysis_dir = tmp_path / "analysis"
    docs_dir = tmp_path / "docs"
    collision = (
        raw_dir
        / RoutingArm.CENTRAL_TOTAL_CALL_MATCHED.value
        / "easy_fatem_020_t19.jsonl"
    )
    collision.parent.mkdir(parents=True)
    collision.write_text("preserve", encoding="utf-8")

    with pytest.raises(FileExistsError, match="1 artifact collision") as error:
        preflight_new_run(raw_dir, analysis_dir, docs_dir, schedule, arms)

    assert str(collision.resolve()) in str(error.value)
    assert collision.read_text(encoding="utf-8") == "preserve"


@pytest.mark.skipif(os.name != "nt", reason="Windows path identity is case-insensitive")
def test_preflight_refuses_case_only_run_root_collision(tmp_path):
    with pytest.raises(ValueError, match="run roots must resolve to distinct paths"):
        preflight_new_run(
            tmp_path / "Raw",
            tmp_path / "raw",
            tmp_path / "docs",
            [],
            (),
        )


def test_wilson_interval_handles_zero_and_full_success():
    zero = wilson_interval(0, 20)
    full = wilson_interval(20, 20)

    assert zero[0] == 0.0 and 0.0 < zero[1] < 0.2
    assert 0.8 < full[0] < 1.0 and full[1] == 1.0


def test_cost_effective_requires_total_call_matched_to_beat_upstream():
    outcomes = [
        _outcome(RoutingArm.UPSTREAM_FREE, "task", 0, False),
        _outcome(RoutingArm.UPSTREAM_FREE, "task", 1, True),
        _outcome(RoutingArm.LEGACY_DETERMINISTIC, "task", 0, False),
        _outcome(RoutingArm.LEGACY_DETERMINISTIC, "task", 1, False),
        _outcome(RoutingArm.CENTRAL_WORKER_MATCHED, "task", 0, True),
        _outcome(RoutingArm.CENTRAL_WORKER_MATCHED, "task", 1, True),
        _outcome(RoutingArm.CENTRAL_TOTAL_CALL_MATCHED, "task", 0, True),
        _outcome(RoutingArm.CENTRAL_TOTAL_CALL_MATCHED, "task", 1, True),
    ]

    comparison = build_preplanned_comparison(outcomes)

    assert comparison["central_routing_cost_effective"] is True
    key = "central_total_call_matched_vs_upstream_free"
    assert comparison["comparisons"][key]["paired_rate_delta"] == 0.5


def test_worker_matched_gain_alone_is_not_called_cost_effective():
    outcomes = [
        _outcome(RoutingArm.UPSTREAM_FREE, "task", 0, False),
        _outcome(RoutingArm.CENTRAL_WORKER_MATCHED, "task", 0, True),
        _outcome(RoutingArm.CENTRAL_TOTAL_CALL_MATCHED, "task", 0, False),
    ]

    assert build_preplanned_comparison(outcomes)["central_routing_cost_effective"] is False


def test_summary_preflight_refuses_all_writes_on_any_collision(tmp_path):
    raw_dir = tmp_path / "raw"
    analysis_dir = tmp_path / "analysis"
    docs_dir = tmp_path / "docs"
    collision = docs_dir / "COMPARISON.md"
    collision.parent.mkdir(parents=True)
    collision.write_text("preserve me", encoding="utf-8")

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        write_summaries(
            raw_dir,
            analysis_dir,
            docs_dir,
            [],
            (RoutingArm.LEGACY_DETERMINISTIC,),
            expected_per_arm=0,
            model="qwen",
        )

    assert collision.read_text(encoding="utf-8") == "preserve me"
    assert not (analysis_dir / "legacy_deterministic" / "summary.json").exists()


def test_summary_outputs_use_raw_analysis_and_docs_roots(tmp_path):
    raw_dir = tmp_path / "raw"
    analysis_dir = tmp_path / "analysis"
    docs_dir = tmp_path / "docs"

    write_summaries(
        raw_dir,
        analysis_dir,
        docs_dir,
        [],
        (RoutingArm.LEGACY_DETERMINISTIC,),
        expected_per_arm=0,
        model="qwen",
    )

    assert (raw_dir / "run_manifest.json").is_file()
    assert (analysis_dir / "legacy_deterministic" / "summary.json").is_file()
    assert (analysis_dir / "metrics.json").is_file()
    assert (docs_dir / "legacy_deterministic" / "RESULTS.md").is_file()
    assert (docs_dir / "COMPARISON.md").is_file()
    assert not (raw_dir / "analysis").exists()
    assert not (raw_dir / "legacy_deterministic" / "summary.json").exists()


def test_task_prompt_is_routing_neutral_and_imports_mathlib():
    prompt = task_prompt(_record())

    assert "import Mathlib" in prompt
    assert "central" not in prompt.lower()
    assert "free routing" not in prompt.lower()
    assert "deterministic" not in prompt.lower()


def test_v4_trial_metadata_discloses_disabled_provider_retries():
    config = _trial_config(
        RoutingArm.LEGACY_DETERMINISTIC,
        model="qwen",
        max_worker_turns=200,
        max_total_model_calls=200,
        contract_hashes={"lean-toolchain": "hash"},
    )

    assert PROVIDER_MAX_RETRIES == 0
    assert config["provider_max_retries"] == 0
    assert config["retrieval_only_streak_limit"] == 8
    assert (
        config["retrieval_only_streak_evaluation"]
        == RETRIEVAL_ONLY_STREAK_EVALUATION
    )


def test_refuse_existing_never_overwrites(tmp_path):
    target = tmp_path / "trace.jsonl"
    target.write_text("evidence", encoding="utf-8")

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        _refuse_existing(target)
    assert target.read_text(encoding="utf-8") == "evidence"


def test_resumable_trace_requires_explicit_terminal_event(tmp_path):
    partial = tmp_path / "partial.jsonl"
    complete = tmp_path / "complete.jsonl"
    legacy = tmp_path / "legacy.jsonl"
    meta = make_trial_meta(
        "trial",
        task_id="task",
        backbone="model",
        testbed="lean",
        grounding=True,
        config={
            "retrieval_only_streak_limit": 8,
            "retrieval_only_streak_evaluation": RETRIEVAL_ONLY_STREAK_EVALUATION,
        },
    )
    writer = TrialLogWriter(partial, meta)
    writer.close()
    assert _trace_is_valid(partial) is False

    writer = TrialLogWriter(complete, meta)
    observer = TraceObserver(writer, trial_id="trial")
    observer.record_termination("cap")
    writer.close()
    assert _trace_is_valid(complete) is True

    writer = TrialLogWriter(
        legacy,
        make_trial_meta(
            "legacy",
            task_id="task",
            backbone="model",
            testbed="lean",
            grounding=True,
        ),
    )
    observer = TraceObserver(writer, trial_id="legacy")
    observer.record_termination("cap")
    writer.close()
    assert _trace_is_valid(legacy) is False


@pytest.mark.parametrize(
    "mismatch",
    (
        "task_id",
        "trial_id",
        "architecture",
        "backbone",
        "config_arm",
        "config_model",
        "max_worker_turns",
        "max_total_model_calls",
        "worker_max_tokens",
        "controller_max_tokens",
        "provider_max_retries",
        "retrieval_only_streak_limit",
        "retrieval_only_streak_evaluation",
        "lean_project_contract",
    ),
)
def test_resume_rejects_mismatched_trial_contract_without_writing(tmp_path, mismatch):
    record = _record()
    arm = RoutingArm.CENTRAL_TOTAL_CALL_MATCHED
    contract_hashes = {"lean-toolchain": "expected-hash"}
    actual = _trial_meta(
        record,
        3,
        arm,
        model="qwen",
        max_worker_turns=200,
        max_total_model_calls=200,
        contract_hashes=contract_hashes,
    ).model_copy(deep=True)
    if mismatch == "task_id":
        actual.task_id = "other-task"
    elif mismatch == "trial_id":
        actual.trial_id = actual.trial_id.replace("_t03", "_t04")
    elif mismatch == "architecture":
        actual.architecture = "lean_routing_upstream_free"
    elif mismatch == "backbone":
        actual.backbone = "other-model"
    elif mismatch == "config_arm":
        actual.config["arm"] = RoutingArm.UPSTREAM_FREE.value
    elif mismatch == "config_model":
        actual.config["model"] = "other-model"
    elif mismatch == "lean_project_contract":
        actual.config[mismatch] = {"lean-toolchain": "other-hash"}
    elif mismatch == "retrieval_only_streak_evaluation":
        actual.config[mismatch] = "other-phase"
    else:
        actual.config[mismatch] = int(actual.config[mismatch]) + 1

    path = tmp_path / "trace.jsonl"
    writer = TrialLogWriter(path, actual)
    TraceObserver(writer, trial_id=actual.trial_id).record_termination("cap")
    writer.close()
    original = path.read_bytes()

    with pytest.raises(FileExistsError, match="not safely resumable"):
        run_trial_with_one_infrastructure_retry(
            record,
            3,
            arm,
            path=path,
            resume=True,
            compiler=object(),
            model="qwen",
            provider={
                "OPENAI_API_KEY": "unused",
                "OPENAI_BASE_URL": "https://unused.invalid/v1",
            },
            max_worker_turns=200,
            max_total_model_calls=200,
            timeout_seconds=1.0,
            contract_hashes=contract_hashes,
        )

    assert path.read_bytes() == original
    assert not path.with_name("trace_retry1.jsonl").exists()


def test_scored_and_persisted_trace_path_is_portable(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    arm = RoutingArm.LEGACY_DETERMINISTIC
    path = tmp_path / "raw" / arm.value / "easy_fatem_test_t00.jsonl"
    meta = make_trial_meta(
        "trial",
        task_id="easy_fatem_test",
        backbone="qwen",
        testbed="lean",
        grounding=True,
        config={
            "retrieval_only_streak_limit": 8,
            "retrieval_only_streak_evaluation": RETRIEVAL_ONLY_STREAK_EVALUATION,
        },
    )
    writer = TrialLogWriter(path, meta)
    TraceObserver(writer, trial_id="trial").record_termination("cap")
    writer.close()

    outcome = _score_trace(_record(), arm, 0, object(), path)
    assert outcome.trace == f"raw/{arm.value}/easy_fatem_test_t00.jsonl"

    write_summaries(
        tmp_path / "raw",
        tmp_path / "analysis",
        tmp_path / "docs",
        [outcome],
        (arm,),
        expected_per_arm=1,
        model="qwen",
    )
    summary = json.loads(
        (tmp_path / "analysis" / arm.value / "summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["trials"][0]["trace"] == outcome.trace
    assert not os.path.isabs(summary["trials"][0]["trace"])


def test_provider_file_is_read_without_mutating_process_route(monkeypatch, tmp_path):
    provider = tmp_path / "provider.env"
    provider.write_text(
        "OPENAI_BASE_URL=https://qwen.invalid/v1\nOPENAI_API_KEY=file-key\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_BASE_URL", "https://stale.invalid/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "stale-key")

    values = read_provider_env(provider)

    assert values == {
        "OPENAI_BASE_URL": "https://qwen.invalid/v1",
        "OPENAI_API_KEY": "file-key",
    }
    assert os.environ["OPENAI_BASE_URL"] == "https://stale.invalid/v1"
    assert os.environ["OPENAI_API_KEY"] == "stale-key"


def test_preserved_failed_smoke_result_is_read_without_reinterpretation(tmp_path):
    result = tmp_path / "probe.json"
    result.write_text('{"passed": false, "score_reason": "invalid"}', encoding="utf-8")

    assert _read_smoke_result(result)["passed"] is False


def test_preserved_smoke_result_requires_exact_resume_contract(tmp_path):
    result = tmp_path / "probe.json"
    result.write_text(
        '{"schema":"han_controller_stuck_smoke_v4","model":"old","passed":true}',
        encoding="utf-8",
    )
    original = result.read_bytes()

    with pytest.raises(RuntimeError, match="incompatible preserved smoke contract"):
        _read_smoke_result(
            result,
            expected_contract={
                "schema": "han_controller_stuck_smoke_v4",
                "model": "new",
            },
        )

    assert result.read_bytes() == original


def test_malformed_preserved_smoke_result_blocks_resume(tmp_path):
    malformed = tmp_path / "probe.json"
    malformed.write_text('{"score_reason": "missing pass field"}', encoding="utf-8")

    with pytest.raises(RuntimeError, match="preserved smoke schema"):
        _read_smoke_result(malformed)


def test_lean_project_contract_requires_matching_hashes_and_lake(tmp_path):
    dataset = tmp_path / "dataset"
    runtime = tmp_path / "runtime"
    dataset.mkdir()
    runtime.mkdir()
    (runtime / ".lake").mkdir()
    for name in PROJECT_CONTRACT_FILES:
        (dataset / name).write_text(json.dumps({"name": name}), encoding="utf-8")
        (runtime / name).write_text(json.dumps({"name": name}), encoding="utf-8")

    hashes = verify_lean_project_contract(dataset, runtime)
    assert set(hashes) == set(PROJECT_CONTRACT_FILES)

    (runtime / "lakefile.lean").write_text("changed", encoding="utf-8")
    with pytest.raises(RuntimeError, match="lakefile.lean"):
        verify_lean_project_contract(dataset, runtime)
