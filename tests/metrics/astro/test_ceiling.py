"""Tests for the match ceiling. Uses the vendored evaluator; no LLM, no network.

The ceiling exists because ``ok_match`` is not always satisfiable: with finite
data the maximum-likelihood parameters differ from the true ones, and the
displacement can exceed the 0.80 threshold. These tests pin both directions --
a clean task must be solvable, and a noise-limited one must not.
"""

from __future__ import annotations

import types

import numpy as np
import pytest

from traj_eval.metrics.astro.ceiling import (
    MatchCeiling,
    compute_ceiling,
    load_ceilings,
    save_ceilings,
)
from traj_eval.vendor.stargazer.config import PlanetParams
from traj_eval.vendor.stargazer.forward_keplerian import simulate_rv_keplerian


def make_task(planets, *, n_obs=120, span=400.0, noise=0.5, seed=7, mstar=1.0, difficulty=4):
    """A task whose data was generated from ``planets`` plus white noise."""
    rng = np.random.default_rng(seed)
    times = np.sort(rng.uniform(0.0, span, n_obs))
    sigmas = np.full(n_obs, noise)
    rvs = simulate_rv_keplerian(planets, times, mstar, gamma_ms=5.0)
    rvs = rvs + rng.normal(0.0, noise, n_obs)
    obs = types.SimpleNamespace(
        times_days=times.tolist(),
        rvs_ms=rvs.tolist(),
        sigmas_ms=sigmas.tolist(),
        instruments=["instA"] * n_obs,
        star_mass_sun=mstar,
        median_sigma_ms=float(np.median(sigmas)),
        hints={},
        n_obs=n_obs,
        baseline_days=float(times.max() - times.min()),
    )
    task = types.SimpleNamespace(
        task_id="fixture",
        kind="synthetic",
        difficulty=difficulty,
        tier="medium",
        observation=obs,
        max_submissions=5,
    )
    truth = types.SimpleNamespace(
        task_id="fixture",
        planets=list(planets),
        star_mass_sun=mstar,
        meta={},
        periods_days=[p.P_days for p in planets],
    )
    return task, truth


# The full sweep uses 48 starts; tests use far fewer, since the seed ordering
# puts the most productive starts first and these fixtures are easy to fit.
TEST_STARTS = 8


def planet(period, mass=0.8, ecc=0.1, omega=1.0, lam=2.0):
    return PlanetParams(
        P_days=period,
        m_sin_i_mjup=mass,
        e=ecc,
        inc_rad=0.0,
        Omega_rad=0.0,
        omega_rad=omega,
        l_rad=lam,
    )


def test_a_well_constrained_task_is_solvable() -> None:
    """Plenty of data, low noise, many cycles: the ML fit should land on truth."""
    task, truth = make_task([planet(11.2)], n_obs=200, span=600.0, noise=0.3)
    ceiling = compute_ceiling(task, truth, max_starts=TEST_STARTS)
    assert ceiling.ceiling_match is not None
    assert ceiling.ceiling_match > 0.9
    assert ceiling.ceiling_solved
    assert ceiling.solvable


def test_a_noise_limited_task_is_not_solvable() -> None:
    """Few points, high noise, barely two cycles: the ML peak leaves the truth.

    This is the seed22_diff4 situation, reproduced from scratch: the best fit
    explains the data better than the true planet does, and still cannot clear
    the match threshold.
    """
    task, truth = make_task(
        [planet(3.1, mass=0.2, ecc=0.19)], n_obs=30, span=6.0, noise=8.0, seed=3
    )
    ceiling = compute_ceiling(task, truth, max_starts=TEST_STARTS)
    assert ceiling.ceiling_match is not None
    assert not ceiling.ceiling_solved
    assert ceiling.ceiling_match < ceiling.threshold
    # The diagnostic that makes it legible: maximising likelihood moves AWAY
    # from the parameters being scored.
    assert ceiling.outfits_truth


def test_truth_always_scores_one() -> None:
    """A sanity anchor: the truth matches itself, whatever the ceiling is."""
    task, truth = make_task([planet(11.2)])
    ceiling = compute_ceiling(task, truth, max_starts=TEST_STARTS)
    assert ceiling.truth_match == pytest.approx(1.0, abs=1e-6)


def test_ceiling_is_at_most_the_truth_score() -> None:
    """The ML fit cannot beat the truth on match; only on likelihood."""
    task, truth = make_task([planet(11.2)])
    ceiling = compute_ceiling(task, truth, max_starts=TEST_STARTS)
    assert ceiling.ceiling_match <= ceiling.truth_match + 1e-9


def test_ml_fit_is_at_least_as_good_as_truth_on_rms() -> None:
    """If it were not, the optimiser failed to find the optimum."""
    task, truth = make_task([planet(11.2)], n_obs=80, noise=1.5)
    ceiling = compute_ceiling(task, truth, max_starts=TEST_STARTS)
    assert ceiling.ceiling_rms_ms <= ceiling.truth_rms_ms + 1e-6


def test_multi_planet_ceiling_recovers_both_periods() -> None:
    task, truth = make_task(
        [planet(11.2), planet(57.9, mass=1.4, ecc=0.22)], n_obs=90, span=400.0, noise=0.4
    )
    ceiling = compute_ceiling(task, truth, max_starts=12)
    assert len(ceiling.ceiling_periods_days) == 2
    for got, want in zip(ceiling.ceiling_periods_days, sorted(truth.periods_days), strict=True):
        assert got == pytest.approx(want, rel=0.02)


def test_deficit_is_zero_when_the_team_hits_the_ceiling() -> None:
    """A team at the ceiling did everything a fitter could; the rest is threshold."""
    task, truth = make_task([planet(11.2)])
    ceiling = compute_ceiling(task, truth, max_starts=TEST_STARTS)
    assert ceiling.deficit_for(ceiling.ceiling_match) == pytest.approx(0.0, abs=1e-12)
    assert ceiling.deficit_for(None) is None


def test_deficit_is_positive_when_the_team_underperforms() -> None:
    task, truth = make_task([planet(11.2)])
    ceiling = compute_ceiling(task, truth, max_starts=TEST_STARTS)
    assert ceiling.deficit_for(ceiling.ceiling_match - 0.2) == pytest.approx(0.2, abs=1e-9)


def test_a_task_with_no_planets_reports_an_error_not_a_crash() -> None:
    task, truth = make_task([planet(11.2)])
    empty = types.SimpleNamespace(
        task_id="fixture", planets=[], star_mass_sun=1.0, meta={}, periods_days=[]
    )
    ceiling = compute_ceiling(task, empty, max_starts=TEST_STARTS)
    assert ceiling.ceiling_match is None
    assert not ceiling.ceiling_solved
    assert ceiling.error


def test_cache_round_trips(tmp_path) -> None:
    task, truth = make_task([planet(11.2)])
    ceiling = compute_ceiling(task, truth, max_starts=TEST_STARTS)
    path = tmp_path / "ceilings.json"
    save_ceilings([ceiling], path)
    loaded = load_ceilings(path)
    assert set(loaded) == {"fixture"}
    assert isinstance(loaded["fixture"], MatchCeiling)
    assert loaded["fixture"].ceiling_match == pytest.approx(ceiling.ceiling_match)


def test_missing_cache_is_empty_not_an_error(tmp_path) -> None:
    """Analysis must still run on a checkout without the cache."""
    assert load_ceilings(tmp_path / "nope.json") == {}


# --------------------------------------------------------------------------
# configurable match threshold
# --------------------------------------------------------------------------


def test_tolerance_multiplier_maps_to_the_equivalent_threshold() -> None:
    """d is linear in the weights, so widening tolerances m-fold == threshold**m."""
    from traj_eval.metrics.astro.criteria import (
        DEFAULT_MIN_MATCH_SCORE,
        threshold_for_tolerance,
    )

    assert threshold_for_tolerance(1.0) == pytest.approx(DEFAULT_MIN_MATCH_SCORE)
    assert threshold_for_tolerance(2.0) == pytest.approx(0.64)
    assert threshold_for_tolerance(3.0) == pytest.approx(0.512)
    # Looser tolerance must never tighten the gate.
    assert threshold_for_tolerance(4.0) < threshold_for_tolerance(2.0)
    with pytest.raises(ValueError):
        threshold_for_tolerance(0.0)


def test_relaxing_the_threshold_can_make_a_task_reachable() -> None:
    """The whole point of the knob: a task below 0.80 may clear a lower gate."""
    task, truth = make_task(
        [planet(3.1, mass=0.2, ecc=0.19)], n_obs=30, span=6.0, noise=8.0, seed=3
    )
    strict = compute_ceiling(task, truth, max_starts=TEST_STARTS)
    relaxed = compute_ceiling(task, truth, max_starts=TEST_STARTS, min_match_score=0.4)
    # Same fit, same score: only the verdict moves.
    assert relaxed.ceiling_match == pytest.approx(strict.ceiling_match)
    assert strict.threshold == 0.8
    assert relaxed.threshold == 0.4
    assert not strict.ceiling_solved
    assert relaxed.ceiling_solved


def test_the_explicit_threshold_overrides_a_task_hint() -> None:
    """An experiment-level gate must apply everywhere, including hinted tasks.

    Otherwise a relaxed run would silently keep the strict gate on exactly the
    tasks that carry their own threshold.
    """
    from traj_eval.metrics.astro.criteria import evaluate_criteria

    info = {
        "residuals": {"rms": 1.0},
        "components": {"delta_bic": 10.0, "match": 0.55, "count": 0.0},
    }
    hinted = evaluate_criteria(info, median_sigma_ms=1.0, hints={"target_match_score": 0.9})
    assert not hinted.ok_match
    overridden = evaluate_criteria(
        info, median_sigma_ms=1.0, hints={"target_match_score": 0.9}, min_match_score=0.5
    )
    assert overridden.ok_match
    assert overridden.min_match_score == 0.5
