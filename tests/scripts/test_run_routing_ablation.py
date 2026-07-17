from __future__ import annotations

import json
import os

import pytest

pytest.importorskip("autogen", reason="agents extra (ag2) not installed")

from scripts.run_routing_ablation import (
    DEFAULT_TASKS,
    PROJECT_CONTRACT_FILES,
    _refuse_existing,
    _trace_is_valid,
    balanced_schedule,
    load_provider_env,
    task_prompt,
    verify_lean_project_contract,
)
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


def test_task_prompt_is_routing_neutral_and_imports_mathlib():
    prompt = task_prompt(_record())

    assert "import Mathlib" in prompt
    assert "central" not in prompt.lower()
    assert "free routing" not in prompt.lower()
    assert "deterministic" not in prompt.lower()


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


def test_explicit_provider_file_overrides_stale_process_route(monkeypatch, tmp_path):
    provider = tmp_path / "provider.env"
    provider.write_text(
        "OPENAI_BASE_URL=https://qwen.invalid/v1\nOPENAI_API_KEY=file-key\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_BASE_URL", "https://stale.invalid/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "stale-key")

    load_provider_env(provider)

    assert os.environ["OPENAI_BASE_URL"] == "https://qwen.invalid/v1"
    assert os.environ["OPENAI_API_KEY"] == "file-key"


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
