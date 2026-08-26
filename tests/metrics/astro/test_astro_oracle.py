"""Tests for the counterfactual oracle. Uses the vendored evaluator (numpy/scipy only).

The oracle is the astro replacement for Lean's independent re-verification, which
cannot transfer: ``rv_submit`` and any offline re-scoring call the same
``evaluate_submission``, so re-checking a submission is a tautology. Instead we
score systems the team could have submitted from its own fits and did not.
"""

from __future__ import annotations

import types

import numpy as np
import pytest

from traj_eval.metrics.astro.artifacts import (
    AstroTrialArtifacts,
    FitRecord,
    SubmissionRecord,
)
from traj_eval.metrics.astro.oracle import run_oracle
from traj_eval.vendor.stargazer.config import PlanetParams
from traj_eval.vendor.stargazer.forward_keplerian import simulate_rv_keplerian


def _task_and_truth(planets, *, n=46, span=20.8, noise=2.14, mstar=1.13, seed=53):
    rng = np.random.default_rng(seed)
    times = np.sort(rng.uniform(0.0, span, n))
    sigmas = np.full(n, noise)
    rvs = simulate_rv_keplerian(planets, times, mstar, gamma_ms=-0.5)
    rvs = rvs + rng.normal(0.0, noise, n)
    obs = types.SimpleNamespace(
        times_days=times.tolist(),
        rvs_ms=rvs.tolist(),
        sigmas_ms=sigmas.tolist(),
        instruments=["instA"] * n,
        star_mass_sun=mstar,
        median_sigma_ms=noise,
        hints={},
        n_obs=n,
        baseline_days=float(times.max() - times.min()),
    )
    task = types.SimpleNamespace(
        task_id="fixture", kind="synthetic", observation=obs, max_submissions=5
    )
    truth = types.SimpleNamespace(
        task_id="fixture", planets=list(planets), star_mass_sun=mstar, meta={}
    )
    return task, truth


def _pd(P, m, e, w, l):  # noqa: E741 - l_rad is the field name
    return {
        "P_days": P,
        "m_sin_i_mjup": m,
        "e": e,
        "inc_rad": 0.0,
        "Omega_rad": 0.0,
        "omega_rad": w,
        "l_rad": l,
    }


TRUE_PLANET = PlanetParams(
    P_days=10.53,
    m_sin_i_mjup=0.74,
    e=0.017,
    inc_rad=0.0,
    Omega_rad=0.0,
    omega_rad=1.85,
    l_rad=3.36,
)
GOOD = _pd(10.534, 0.7377, 0.0166, 1.8488, 3.3636)
SPURIOUS = _pd(2.4104, 0.00806, 0.95, 0.3726, 0.8602)
THIRD = _pd(4.3585, 0.0829, 0.8854, 6.2379, 2.5218)


@pytest.fixture(scope="module")
def single_planet_task():
    return _task_and_truth([TRUE_PLANET])


def test_oracle_finds_the_passing_subset_the_team_discarded(single_planet_task) -> None:
    """The motivating real failure: one true planet fitted alongside a spurious one.

    The team submitted both, failed on count, escalated to three, and failed
    worse -- while the subset {10.53 d} was in hand from the first fit onward.
    """
    task, truth = single_planet_task
    artifacts = AstroTrialArtifacts(
        trial_id="t",
        task_id="fixture",
        fits=[
            FitRecord(
                seq=4,
                role="engineer",
                period_guesses=[10.4, 2.7],
                sigma_jitter_ms=2.14,
                ok=True,
                planets=[SPURIOUS, GOOD],
                rms_ms=2.27,
            ),
            FitRecord(
                seq=11,
                role="engineer",
                period_guesses=[2.68, 10.53, 4.77],
                sigma_jitter_ms=2.14,
                ok=True,
                planets=[SPURIOUS, THIRD, GOOD],
                rms_ms=1.97,
            ),
        ],
        submissions=[
            SubmissionRecord(
                seq=7,
                role="critic",
                index=1,
                planets=[SPURIOUS, GOOD],
                accepted=True,
                solved=False,
                criteria={
                    "ok_delta_bic": True,
                    "ok_rms": True,
                    "ok_match": False,
                    "ok_count": False,
                },
                failed_criteria=["ok_match", "ok_count"],
            ),
        ],
    )
    report = run_oracle(artifacts, task=task, truth=truth)

    assert report.reachable_solved
    assert not report.submitted_solved
    assert report.had_it_and_lost_it
    # Available from the FIRST fit, which is where localisation should point.
    assert report.first_solved_seq == 4
    assert report.best_reachable is not None
    assert report.best_reachable.periods == pytest.approx([10.534], rel=1e-6)


def test_the_gap_is_exactly_the_count_penalty(single_planet_task) -> None:
    """Separating 'wrong orbits' from 'wrong count' is what made the case legible.

    components['match'] already folds in -0.25*|dn|, so a submission with correct
    orbits but one planet too many looks far worse on match than its orbital
    recovery warrants.
    """
    task, truth = single_planet_task
    artifacts = AstroTrialArtifacts(
        trial_id="t",
        task_id="fixture",
        fits=[
            FitRecord(
                seq=4,
                role="engineer",
                period_guesses=[10.4, 2.7],
                sigma_jitter_ms=0.0,
                ok=True,
                planets=[SPURIOUS, GOOD],
            )
        ],
        submissions=[
            SubmissionRecord(
                seq=7, role="critic", index=1, planets=[SPURIOUS, GOOD], accepted=True, solved=False
            )
        ],
    )
    report = run_oracle(artifacts, task=task, truth=truth)
    assert report.match_gap == pytest.approx(0.25, abs=1e-6)
    submitted = report.best_submitted
    assert submitted is not None
    # Add the penalty back: the orbits themselves were fine all along.
    assert submitted.match_without_count_penalty == pytest.approx(
        report.best_reachable.criteria.match_score, abs=1e-6
    )


def test_no_false_positive_when_the_team_submitted_its_best(single_planet_task) -> None:
    task, truth = single_planet_task
    artifacts = AstroTrialArtifacts(
        trial_id="t",
        task_id="fixture",
        fits=[
            FitRecord(
                seq=4,
                role="engineer",
                period_guesses=[10.53],
                sigma_jitter_ms=0.0,
                ok=True,
                planets=[GOOD],
            )
        ],
        submissions=[
            SubmissionRecord(
                seq=7, role="critic", index=1, planets=[GOOD], accepted=True, solved=True
            )
        ],
    )
    report = run_oracle(artifacts, task=task, truth=truth)
    assert report.reachable_solved and report.submitted_solved
    assert not report.had_it_and_lost_it
    assert report.match_gap == pytest.approx(0.0, abs=1e-9)


def test_unfittable_trial_yields_no_reachable_solution(single_planet_task) -> None:
    """When nothing the team fitted works, the failure is FITTING, not selection."""
    task, truth = single_planet_task
    wrong = _pd(3.3, 0.1, 0.0, 0.0, 0.0)
    artifacts = AstroTrialArtifacts(
        trial_id="t",
        task_id="fixture",
        fits=[
            FitRecord(
                seq=4,
                role="engineer",
                period_guesses=[3.3],
                sigma_jitter_ms=0.0,
                ok=True,
                planets=[wrong],
            )
        ],
        submissions=[
            SubmissionRecord(
                seq=7, role="critic", index=1, planets=[wrong], accepted=True, solved=False
            )
        ],
    )
    report = run_oracle(artifacts, task=task, truth=truth)
    assert not report.reachable_solved
    assert not report.had_it_and_lost_it
    assert report.first_solved_seq is None


def test_enumeration_covers_every_non_empty_subset(single_planet_task) -> None:
    task, truth = single_planet_task
    artifacts = AstroTrialArtifacts(
        trial_id="t",
        task_id="fixture",
        fits=[
            FitRecord(
                seq=4,
                role="engineer",
                period_guesses=[],
                sigma_jitter_ms=0.0,
                ok=True,
                planets=[SPURIOUS, THIRD, GOOD],
            )
        ],
    )
    report = run_oracle(artifacts, task=task, truth=truth)
    assert report.n_candidates == 7  # 2**3 - 1
    assert not report.errors


def test_failed_fits_contribute_no_candidates(single_planet_task) -> None:
    task, truth = single_planet_task
    artifacts = AstroTrialArtifacts(
        trial_id="t",
        task_id="fixture",
        fits=[
            FitRecord(
                seq=4,
                role="engineer",
                period_guesses=[10.5],
                sigma_jitter_ms=0.0,
                ok=False,
                planets=[],
                error="no convergence",
            )
        ],
    )
    report = run_oracle(artifacts, task=task, truth=truth)
    assert report.n_candidates == 0
    assert report.best_reachable is None
    assert not report.had_it_and_lost_it
