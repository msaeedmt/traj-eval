"""Tests for the period-selection anchor. Pure arithmetic: no evaluator, no LLM.

The tolerance tests use the real numbers from development traces, because the
first version of the tolerance calculation produced FALSE VIOLATIONS ON SOLVED
TRIALS -- the failure mode that would most quietly corrupt the metric.
"""

from __future__ import annotations

import pytest

from traj_eval.anchors.astro.period_selection import (
    MAX_RELATIVE_TOLERANCE,
    MIN_RELATIVE_TOLERANCE,
    PeriodLabel,
    classify_period,
    relative_tolerance,
    run_period_anchor,
)
from traj_eval.metrics.astro.artifacts import AstroTrialArtifacts, FitRecord, Handoff


def _classify(period, truths, baseline, window=None, fap=None):
    return classify_period(
        period,
        true_periods=truths,
        baseline_days=baseline,
        window_peaks_days=window or [],
        fap_at_selection=fap,
    )


# --------------------------------------------------------------------------
# tolerance
# --------------------------------------------------------------------------


def test_tolerance_scales_with_period_and_baseline() -> None:
    """Resolution is P / (oversample * baseline): worse for long P, short baseline."""
    tight = relative_tolerance(10.0, baseline_days=1000.0)
    loose = relative_tolerance(10.0, baseline_days=20.0)
    assert tight < loose
    assert relative_tolerance(5.0, 100.0) < relative_tolerance(50.0, 100.0)


def test_tolerance_is_clamped() -> None:
    assert relative_tolerance(1.0, baseline_days=1e6) == MIN_RELATIVE_TOLERANCE
    assert relative_tolerance(1000.0, baseline_days=1.0) == MAX_RELATIVE_TOLERANCE
    assert relative_tolerance(10.0, baseline_days=0.0) == MAX_RELATIVE_TOLERANCE


@pytest.mark.parametrize(
    ("chosen", "truths", "baseline"),
    [
        # seed1108_diff2: the periodogram peak was one grid step off the truth.
        (5.1869, [5.283], 15.02),
        # seed210_diff2: 3.95% off against a ~4% resolution -- the case that a
        # one-grid-step tolerance rejected on a trial that SOLVED the task.
        (20.8233, [16.0, 21.68], 54.1),
        (15.9260, [16.0, 21.68], 54.1),
    ],
)
def test_grid_quantisation_is_not_a_violation(chosen, truths, baseline) -> None:
    verdict = _classify(chosen, truths, baseline)
    assert verdict.label is PeriodLabel.TRUE, verdict.detail
    assert not verdict.is_violation


# --------------------------------------------------------------------------
# classification
# --------------------------------------------------------------------------


def test_a_true_period_passes() -> None:
    verdict = _classify(10.53, [10.53], 20.78)
    assert verdict.label is PeriodLabel.TRUE
    assert verdict.nearest_true_days == 10.53
    assert verdict.relative_error == pytest.approx(0.0)


@pytest.mark.parametrize("factor", [0.5, 2.0])
def test_harmonics_are_labelled(factor: float) -> None:
    verdict = _classify(10.53 * factor, [10.53], 20.78)
    assert verdict.label is PeriodLabel.HARMONIC
    assert verdict.is_violation


def test_a_one_day_beat_alias_is_labelled() -> None:
    beat = 1.0 / (1.0 / 10.53 + 1.0)
    assert _classify(beat, [10.53], 20.78).label is PeriodLabel.BEAT


def test_a_window_peak_is_labelled() -> None:
    """A period from WHEN the telescope looked, not from the star."""
    verdict = _classify(2.1443, [10.53], 20.78, window=[2.1443, 16.0, 0.6933])
    assert verdict.label is PeriodLabel.WINDOW


def test_noise_is_spurious() -> None:
    """The seed53_diff5 case: a peak matching nothing at all."""
    verdict = _classify(2.70, [10.53], 20.78, window=[2.1443, 16.0], fap=0.295)
    assert verdict.label is PeriodLabel.SPURIOUS
    assert verdict.fap_at_selection == 0.295
    assert verdict.nearest_true_days == 10.53


def test_the_classes_stay_disjoint_at_the_widest_tolerance() -> None:
    """A harmonic is 50-100% away, so no plausible tolerance can absorb it."""
    truths = [10.53]
    assert _classify(10.53, truths, 5.0).label is PeriodLabel.TRUE
    assert _classify(5.265, truths, 5.0).label is PeriodLabel.HARMONIC
    assert _classify(21.06, truths, 5.0).label is PeriodLabel.HARMONIC


def test_true_wins_over_a_coincident_alias() -> None:
    """When a period is both a true period and an alias of another, TRUE wins."""
    verdict = _classify(10.0, [10.0, 20.0], 200.0)
    assert verdict.label is PeriodLabel.TRUE


def test_anchor_check_renders_for_the_schema() -> None:
    check = _classify(2.70, [10.53], 20.78).to_anchor_check()
    assert check.name == "period_selection"
    assert check.status.value == "violation"
    assert check.observed == 2.70


# --------------------------------------------------------------------------
# whole-trial
# --------------------------------------------------------------------------


def _task_truth(truths, baseline=20.78):
    import types

    obs = types.SimpleNamespace(baseline_days=baseline)
    return (
        types.SimpleNamespace(task_id="t", observation=obs),
        types.SimpleNamespace(task_id="t", periods_days=truths),
    )


def test_first_violation_is_attributed_to_the_deciding_agent() -> None:
    """The engineer runs the fit, but the planner chose the periods.

    Collapsing the two would credit every period error to the engineer and make
    Expected Result 2 untestable.
    """
    task, truth = _task_truth([10.53])
    artifacts = AstroTrialArtifacts(
        trial_id="t",
        task_id="t",
        fits=[
            FitRecord(
                seq=4,
                role="engineer",
                period_guesses=[10.4, 2.7],
                sigma_jitter_ms=0.0,
                ok=True,
                planets=[],
            )
        ],
        handoffs=[Handoff(seq=3, from_role="planner", to_role="engineer")],
    )
    report = run_period_anchor(artifacts, task=task, truth=truth)
    assert report.first_violation_seq == 4
    assert report.first_violation_role == "engineer"
    assert report.first_violation_origin_role == "planner"


def test_a_clean_trial_has_no_violations() -> None:
    task, truth = _task_truth([16.0, 21.68], baseline=54.1)
    artifacts = AstroTrialArtifacts(
        trial_id="t",
        task_id="t",
        fits=[
            FitRecord(
                seq=12,
                role="engineer",
                period_guesses=[20.767, 15.926],
                sigma_jitter_ms=0.0,
                ok=True,
                planets=[],
            )
        ],
    )
    report = run_period_anchor(artifacts, task=task, truth=truth)
    assert report.n_violations == 0
    assert report.violation_rate == 0.0
    assert report.first_violation is None
    assert report.ever_found_all_true


def test_missed_true_periods_are_reported() -> None:
    """Distinguishes 'chose wrong' from 'never looked'."""
    task, truth = _task_truth([11.2, 57.9], baseline=400.0)
    artifacts = AstroTrialArtifacts(
        trial_id="t",
        task_id="t",
        fits=[
            FitRecord(
                seq=4,
                role="engineer",
                period_guesses=[11.2],
                sigma_jitter_ms=0.0,
                ok=True,
                planets=[],
            )
        ],
    )
    report = run_period_anchor(artifacts, task=task, truth=truth)
    assert report.missed_true_periods == [57.9]
    assert not report.ever_found_all_true


def test_alias_and_spurious_are_distinguished() -> None:
    """Different diagnoses: subtle physics versus misreading significance."""
    task, truth = _task_truth([10.53])
    aliasing = AstroTrialArtifacts(
        trial_id="t",
        task_id="t",
        fits=[
            FitRecord(
                seq=4,
                role="engineer",
                period_guesses=[5.265],
                sigma_jitter_ms=0.0,
                ok=True,
                planets=[],
            )
        ],
    )
    noise = AstroTrialArtifacts(
        trial_id="t",
        task_id="t",
        fits=[
            FitRecord(
                seq=4,
                role="engineer",
                period_guesses=[2.7],
                sigma_jitter_ms=0.0,
                ok=True,
                planets=[],
            )
        ],
    )
    a = run_period_anchor(aliasing, task=task, truth=truth)
    b = run_period_anchor(noise, task=task, truth=truth)
    assert a.chased_alias and not a.chased_spurious
    assert b.chased_spurious and not b.chased_alias


def test_label_counts_and_worst_fap() -> None:
    task, truth = _task_truth([10.53])
    artifacts = AstroTrialArtifacts(
        trial_id="t",
        task_id="t",
        fits=[
            FitRecord(
                seq=4,
                role="engineer",
                period_guesses=[10.4, 2.7, 4.77],
                sigma_jitter_ms=0.0,
                ok=True,
                planets=[],
            )
        ],
    )
    report = run_period_anchor(artifacts, task=task, truth=truth)
    counts = report.label_counts()
    assert counts["true"] == 1
    assert counts["spurious"] == 2
    assert report.n_checked == 3
    assert report.violation_rate == pytest.approx(2 / 3)


def test_non_finite_guesses_are_skipped() -> None:
    task, truth = _task_truth([10.53])
    artifacts = AstroTrialArtifacts(
        trial_id="t",
        task_id="t",
        fits=[
            FitRecord(
                seq=4,
                role="engineer",
                period_guesses=[10.53, float("nan"), -1.0, 0.0],
                sigma_jitter_ms=0.0,
                ok=True,
                planets=[],
            )
        ],
    )
    assert run_period_anchor(artifacts, task=task, truth=truth).n_checked == 1
