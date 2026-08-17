"""Tests for the periodogram tool and the shared RV numerics."""

from __future__ import annotations

import numpy as np
import pytest

from traj_eval.tools.rv_model import (
    fit_quality,
    mass_from_semi_amplitude,
    planets_to_submission_dicts,
    semi_amplitude_from_mass,
    to_planet_params,
)
from traj_eval.tools.rv_periodogram import (
    RvPeriodogram,
    alias_family,
    find_peaks,
    frequency_grid,
    gls_power,
)

from .conftest import ONE_PLANET, make_task


def test_recovers_the_injected_period(one_planet_task) -> None:
    task, _ = one_planet_task
    result = RvPeriodogram(task).compute(min_period_days=1.0, top_k=3)
    best = result["peaks"][0]["period_days"]
    assert abs(best - 12.345) / 12.345 < 0.01, f"recovered {best}"
    assert result["peaks"][0]["power"] > 0.5


def test_power_is_bounded_and_constant_data_has_none(one_planet_task) -> None:
    task, _ = one_planet_task
    times = np.asarray(task.observation.times_days)
    sigmas = np.asarray(task.observation.sigmas_ms)
    freqs = frequency_grid(times, min_period_days=1.0)

    power = gls_power(times, np.asarray(task.observation.rvs_ms), sigmas, freqs)
    assert power.min() >= 0.0 and power.max() <= 1.0
    flat = gls_power(times, np.full(times.size, 7.0), sigmas, freqs)
    assert flat.max() < 1e-9


def test_peaks_are_distinct_in_period(one_planet_task) -> None:
    """Without thinning, top-k would return one peak's shoulders as three planets."""
    task, _ = one_planet_task
    peaks = RvPeriodogram(task).compute(min_period_days=1.0, top_k=5)["peaks"]
    periods = [p["period_days"] for p in peaks]
    for i, a in enumerate(periods):
        for b in periods[i + 1 :]:
            assert abs(a - b) > 0.05 * min(a, b), f"{a} and {b} are the same peak"


def test_peak_ranking_is_monotonic_in_power(one_planet_task) -> None:
    task, _ = one_planet_task
    peaks = RvPeriodogram(task).compute(min_period_days=1.0, top_k=4)["peaks"]
    powers = [p["power"] for p in peaks]
    assert powers == sorted(powers, reverse=True)
    assert [p["rank"] for p in peaks] == list(range(1, len(peaks) + 1))


def test_result_carries_no_ok_key(one_planet_task) -> None:
    """Exploration must read as 'not a verification step' to the controller.

    If this dict carried ``ok``, running a periodogram would count toward the
    no-progress bound and exploration would be scored as thrashing.
    """
    task, _ = one_planet_task
    assert "ok" not in RvPeriodogram(task).compute()


def test_grid_stops_at_twice_the_baseline(one_planet_task) -> None:
    """Beyond ~2x baseline a period is unconstrained -- power there is a trend."""
    task, _ = one_planet_task
    result = RvPeriodogram(task).compute(min_period_days=1.0)
    longest = result["searched_period_range_days"][1]
    assert longest <= 2.0 * task.observation.baseline_days * 1.001


def test_grid_rejects_inverted_period_range(one_planet_task) -> None:
    task, _ = one_planet_task
    with pytest.raises(ValueError):
        frequency_grid(
            np.asarray(task.observation.times_days),
            min_period_days=100.0,
            max_period_days=10.0,
        )


def test_alias_family_contains_the_usual_suspects() -> None:
    family = alias_family(11.2, baseline_days=400.0)
    assert family["half"] == pytest.approx(5.6)
    assert family["double"] == pytest.approx(22.4)
    # 1/(1/11.2 + 1) ~ 0.918 d: the nightly-cadence beat period.
    assert family["beat_1d_plus"] == pytest.approx(1.0 / (1.0 / 11.2 + 1.0))
    assert family["baseline"] == pytest.approx(400.0)


def test_find_peaks_handles_tiny_arrays() -> None:
    periods = np.array([1.0, 2.0])
    power = np.array([0.1, 0.9])
    assert find_peaks(periods, power, top_k=2)


def test_semi_amplitude_round_trip() -> None:
    """K -> mass -> K must be exact, since the fitter works in K and submits mass."""
    for period, ecc in ((12.345, 0.12), (278.0, 0.4), (2.5, 0.0)):
        k = semi_amplitude_from_mass(0.7, period, ecc, 1.1)
        mass = mass_from_semi_amplitude(k, period, ecc, 1.1)
        assert mass == pytest.approx(0.7, rel=1e-9)


def test_mass_from_semi_amplitude_rejects_bad_period() -> None:
    with pytest.raises(ValueError):
        mass_from_semi_amplitude(10.0, 0.0, 0.1, 1.0)


def test_fit_quality_on_truth_recovers_noise_and_offset(one_planet_task) -> None:
    task, truth = one_planet_task
    obs = task.observation
    quality = fit_quality(
        truth.planets,
        times_days=np.asarray(obs.times_days),
        rvs_ms=np.asarray(obs.rvs_ms),
        sigmas_ms=np.asarray(obs.sigmas_ms),
        instruments=np.asarray(obs.instruments),
        star_mass_sun=obs.star_mass_sun,
    )
    # Scatter near the injected noise, model beats a flat line, offset recovered.
    assert 1.0 < quality["rms_ms"] < 2.0
    assert quality["delta_bic_per_point"] > 0.0
    assert quality["gamma_per_instrument_ms"]["instA"] == pytest.approx(20.0, abs=1.0)
    # 5 orbital params per planet + 1 offset per instrument, the grader's count.
    assert quality["k_params"] == 6


def test_fit_quality_counts_one_offset_per_instrument() -> None:
    task, truth = make_task(
        ONE_PLANET,
        n_obs=100,
        instruments=["instA"] * 50 + ["instB"] * 50,
    )
    obs = task.observation
    quality = fit_quality(
        truth.planets,
        times_days=np.asarray(obs.times_days),
        rvs_ms=np.asarray(obs.rvs_ms),
        sigmas_ms=np.asarray(obs.sigmas_ms),
        instruments=np.asarray(obs.instruments),
        star_mass_sun=obs.star_mass_sun,
    )
    assert set(quality["gamma_per_instrument_ms"]) == {"instA", "instB"}
    assert quality["k_params"] == 5 + 2


def test_submission_dicts_are_sorted_by_period() -> None:
    """Stable ordering is what lets the perseveration detector spot a repeat."""
    planets = to_planet_params(
        [
            {"P_days": 57.9, "m_sin_i_mjup": 1.4, "e": 0.2, "omega_rad": 1.0, "l_rad": 2.0},
            {"P_days": 11.2, "m_sin_i_mjup": 0.5, "e": 0.0, "omega_rad": 0.5, "l_rad": 1.0},
        ]
    )
    out = planets_to_submission_dicts(planets)
    assert [p["P_days"] for p in out] == [11.2, 57.9]
    assert set(out[0]) == {
        "P_days",
        "m_sin_i_mjup",
        "e",
        "inc_rad",
        "Omega_rad",
        "omega_rad",
        "l_rad",
    }
