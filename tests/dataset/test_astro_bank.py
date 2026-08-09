"""Tests for the rv_semantics gate. No rebound, no task bank, no network.

The gate exists because an unprepared task does not fail loudly -- it scores
subtly wrong. The ground truth would not reach match 1.0, and every anchor built
on the forward model would inherit that offset. So these tests check the loader
REFUSES rather than proceeds.
"""

from __future__ import annotations

import pytest

from traj_eval.dataset.astro_bank import (
    ACCEPTED_RV_SEMANTICS,
    AstroDatasetError,
    assert_prepared,
    is_prepared,
    rv_semantics,
)


class _FakeTask:
    """Minimal stand-in: the gate only ever reads ``task_id`` and ``meta``."""

    def __init__(self, meta):
        self.task_id = "seed22_diff4"
        self.meta = meta


@pytest.mark.parametrize("semantics", sorted(ACCEPTED_RV_SEMANTICS))
def test_accepted_semantics_pass(semantics: str) -> None:
    task = _FakeTask({"rv_semantics": semantics})
    assert rv_semantics(task) == semantics
    assert is_prepared(task)
    assert_prepared(task)  # must not raise


@pytest.mark.parametrize(
    "meta",
    [
        {},  # raw upstream file, key absent
        {"rv_semantics": None},
        {"rv_semantics": "rebound"},  # N-body signal, never converted
        {"rv_semantics": "nbody"},
        {"rv_only_compat_applied": True},  # flag set but label missing
        None,  # meta not a dict at all
    ],
)
def test_unprepared_tasks_are_refused(meta) -> None:
    task = _FakeTask(meta)
    assert not is_prepared(task)
    with pytest.raises(AstroDatasetError) as exc:
        assert_prepared(task)
    # The message must name the fix, not just the symptom.
    assert "prepare_astro_dataset" in str(exc.value)


def test_error_message_includes_task_id_and_path() -> None:
    from pathlib import Path

    task = _FakeTask({"rv_semantics": "rebound"})
    with pytest.raises(AstroDatasetError) as exc:
        assert_prepared(task, path=Path("dataset/Astro/synthetic/seed22_diff4.json"))
    message = str(exc.value)
    assert "seed22_diff4" in message
    assert "dataset/Astro/synthetic" in message


def test_rv_semantics_accepts_a_bare_meta_dict() -> None:
    assert rv_semantics({"rv_semantics": "rv_only"}) == "rv_only"
    assert rv_semantics({}) is None
    assert rv_semantics("not a dict") is None
