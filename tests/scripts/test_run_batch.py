"""Tests for the batch runner's outcome classification (pure logic). The live
run loop needs an LLM + kernel and is not exercised here; the classification
and import-error detection are.
"""

from __future__ import annotations

from dataclasses import dataclass

from traj_eval.agents import make_trial_meta
from scripts.run_batch import _classify, _looks_like_import_error, _trace_is_valid
from traj_eval.trace_core.storage import TrialLogWriter


@dataclass
class _FakeMetrics:
    final_proof_compiles: bool | None = None
    final_proof_sorry_free: bool | None = None
    statement_preserved: bool | None = None
    axiom_clean: bool | None = None
    silent_failure: bool | None = None


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
    assert _classify([], m, None) == "solved"


def test_silent_failure_classified():
    m = _FakeMetrics(silent_failure=True)
    assert _classify([], m, None) == "silent_failure"


def test_unsolved_when_incomplete():
    m = _FakeMetrics(final_proof_compiles=False)
    assert _classify([], m, None) == "unsolved"


def test_import_error_takes_precedence():
    # even if metrics would say unsolved, an import error in the trace wins
    ev = _make_result_event("{'compiled': False, 'errors': [{'data': 'unknown constant Foo'}]}")
    m = _FakeMetrics(final_proof_compiles=False)
    assert _classify([ev], m, None) == "import_error"


def test_import_error_detection_positive():
    ev = _make_result_event("{'compiled': False, 'summary': 'unknown module Mathlib.Foo.Bar'}")
    assert _looks_like_import_error([ev]) is True


def test_import_error_detection_ignores_ordinary_failure():
    # a normal proof error (unsolved goals) is NOT an import error
    ev = _make_result_event("{'compiled': False, 'errors': [{'data': 'unsolved goals'}]}")
    assert _looks_like_import_error([ev]) is False


def test_import_error_detection_ignores_success():
    ev = _make_result_event("{'compiled': True, 'sorry_free': True}")
    assert _looks_like_import_error([ev]) is False


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
