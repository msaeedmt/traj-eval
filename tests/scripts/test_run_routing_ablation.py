from __future__ import annotations

import json
import os

import pytest

pytest.importorskip("autogen", reason="agents extra (ag2) not installed")

from scripts.run_routing_ablation import (
    DEFAULT_TASKS,
    PROJECT_CONTRACT_FILES,
    PROVIDER_MAX_RETRIES,
    _read_smoke_result,
    _refuse_existing,
    _trace_is_valid,
    _trial_config,
    balanced_schedule,
    build_preplanned_comparison,
    preflight_new_run,
    read_provider_env,
    task_prompt,
    verify_lean_project_contract,
    wilson_interval,
    write_summaries,
)
from scripts.run_routing_ablation import TrialOutcome
from traj_eval.agents.observer import TraceObserver, make_trial_meta
from traj_eval.agents.lean_routing_ablation import RoutingArm
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
    collision = (
        tmp_path
        / RoutingArm.CENTRAL_TOTAL_CALL_MATCHED.value
        / "easy_fatem_020_t19.jsonl"
    )
    collision.parent.mkdir(parents=True)
    collision.write_text("preserve", encoding="utf-8")

    with pytest.raises(FileExistsError, match="1 artifact collision") as error:
        preflight_new_run(tmp_path, schedule, arms)

    assert str(collision.resolve()) in str(error.value)
    assert collision.read_text(encoding="utf-8") == "preserve"


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
    collision = tmp_path / "analysis" / "COMPARISON.md"
    collision.parent.mkdir(parents=True)
    collision.write_text("preserve me", encoding="utf-8")

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        write_summaries(
            tmp_path,
            [],
            (RoutingArm.LEGACY_DETERMINISTIC,),
            expected_per_arm=0,
            model="qwen",
        )

    assert collision.read_text(encoding="utf-8") == "preserve me"
    assert not (tmp_path / "legacy_deterministic" / "summary.json").exists()


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


def test_refuse_existing_never_overwrites(tmp_path):
    target = tmp_path / "trace.jsonl"
    target.write_text("evidence", encoding="utf-8")

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        _refuse_existing(target)
    assert target.read_text(encoding="utf-8") == "evidence"


def test_resumable_trace_requires_explicit_terminal_event(tmp_path):
    partial = tmp_path / "partial.jsonl"
    complete = tmp_path / "complete.jsonl"
    meta = make_trial_meta(
        "trial", task_id="task", backbone="model", testbed="lean", grounding=True
    )
    writer = TrialLogWriter(partial, meta)
    writer.close()
    assert _trace_is_valid(partial) is False

    writer = TrialLogWriter(complete, meta)
    observer = TraceObserver(writer, trial_id="trial")
    observer.record_termination("cap")
    writer.close()
    assert _trace_is_valid(complete) is True


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
