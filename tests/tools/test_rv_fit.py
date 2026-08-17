"""Tests for the Keplerian fitting tool.

The parameter-recovery tests confirm the fitter agrees with the vendored forward
model. The alias tests confirm something more important: that the fitter does NOT
rescue an agent from a bad period choice, because alias convergence is a failure
mode this project exists to observe, and an unbounded optimiser would silently
delete it.
"""

from __future__ import annotations

import math

import pytest

from traj_eval.tools.rv_fit import (
    DEFAULT_PERIOD_TOLERANCE_FRAC as TOL,
)
from traj_eval.tools.rv_fit import (
    MAX_PLANETS,
    RvFit,
    RvFitError,
)


def test_recovers_a_single_planet(one_planet_task) -> None:
    task, _ = one_planet_task
    result = RvFit(task).fit([12.36])
    assert result["ok"]
    planet = result["planets"][0]
    assert planet["P_days"] == pytest.approx(12.345, abs=0.02)
    assert planet["m_sin_i_mjup"] == pytest.approx(0.6, abs=0.08)
    assert planet["e"] == pytest.approx(0.12, abs=0.10)
    assert planet["l_rad"] == pytest.approx(2.0, abs=0.2)
    assert result["rms_ms"] < 1.8
    assert result["delta_bic_per_point"] > 0.0


def test_recovers_two_planets(two_planet_correct_fit) -> None:
    result = two_planet_correct_fit
    assert result["ok"]
    periods = [p["P_days"] for p in result["planets"]]
    assert periods[0] == pytest.approx(11.2, abs=0.05)
    assert periods[1] == pytest.approx(57.9, abs=0.4)
    assert result["rms_ms"] < 1.9


def test_planets_are_returned_sorted_by_period(two_planet_task) -> None:
    task, _ = two_planet_task
    result = RvFit(task).fit([58.5, 11.3])  # deliberately out of order
    periods = [p["P_days"] for p in result["planets"]]
    assert periods == sorted(periods)


@pytest.mark.parametrize("factor", [0.5, 2.0])
def test_harmonic_alias_does_not_drift_to_the_truth(
    two_planet_task, two_planet_correct_fit, factor: float
) -> None:
    """A fit seeded on P/2 or 2P must stay there and score worse.

    If the optimiser could escape to the true period, an agent that picked the
    wrong periodogram peak would be silently rescued and alias convergence would
    become unobservable.
    """
    task, _ = two_planet_task
    correct = two_planet_correct_fit
    seed = 11.2 * factor
    aliased = RvFit(task).fit([seed])
    got = aliased["planets"][0]["P_days"]

    assert seed * (1 - TOL) <= got <= seed * (1 + TOL), "fit left its declared bound"
    assert abs(got - 11.2) > 1.0, "fitter escaped to the true period"
    assert aliased["rms_ms"] > correct["rms_ms"]


def test_one_day_beat_alias_does_not_drift(two_planet_task, two_planet_correct_fit) -> None:
    task, _ = two_planet_task
    correct = two_planet_correct_fit
    beat = 1.0 / (1.0 / 11.2 + 1.0)
    aliased = RvFit(task).fit([beat])
    got = aliased["planets"][0]["P_days"]
    assert beat * (1 - TOL) <= got <= beat * (1 + TOL)
    assert aliased["rms_ms"] > correct["rms_ms"]


def test_declared_bound_is_reported_to_the_agent(two_planet_task) -> None:
    """The agent must be told its period will not be moved far, or the constraint
    is a trap rather than a tool contract."""
    task, _ = two_planet_task
    result = RvFit(task).fit([11.2])
    assert result["period_bound_frac"] == pytest.approx(TOL)
    assert "20%" in result["notes"]
    assert "times_days[0]" in result["notes"]


def test_fit_is_deterministic(two_planet_task, two_planet_correct_fit) -> None:
    """Trace gradability depends on identical input giving identical output.

    Compared against the session-cached fit, so this costs one fit rather than
    two: the point is reproducibility across separate RvFit instances, which a
    fresh fit with identical arguments demonstrates.
    """
    task, _ = two_planet_task
    repeat = RvFit(task).fit([11.2, 57.9])
    assert repeat["planets"] == two_planet_correct_fit["planets"]
    assert repeat["rms_ms"] == two_planet_correct_fit["rms_ms"]
    assert repeat["n_starts_converged"] == two_planet_correct_fit["n_starts_converged"]


def test_ok_means_converged_not_good(two_planet_task) -> None:
    """A converged fit on a wrong period is still ok=True.

    ok drives the controller's no-progress bound, which should catch a fitter
    that cannot produce an answer -- not one that produces a bad answer. Judging
    quality is the evaluator's job.
    """
    task, _ = two_planet_task
    result = RvFit(task).fit([3.3])  # nothing there
    assert result["ok"] is True
    assert result["rms_ms"] > 5.0


def test_reports_start_counts(two_planet_task) -> None:
    task, _ = two_planet_task
    result = RvFit(task).fit([11.2])
    assert result["n_starts_tried"] >= 1
    assert 0 < result["n_starts_converged"] <= result["n_starts_tried"]


@pytest.mark.parametrize(
    ("guesses", "fragment"),
    [
        ([], "non-empty"),
        ([11.2, 11.25], "duplicates"),
        ([-3.0], "positive finite"),
        ([0.0], "positive finite"),
        ([float("nan")], "positive finite"),
        ([float("inf")], "positive finite"),
        (["abc"], "not a number"),
        ([float(i + 1) for i in range(MAX_PLANETS + 1)], "at most"),
    ],
)
def test_invalid_requests_are_rejected(two_planet_task, guesses, fragment: str) -> None:
    task, _ = two_planet_task
    with pytest.raises(RvFitError, match=fragment):
        RvFit(task).fit(guesses)


def test_tool_wrapper_returns_ok_false_instead_of_raising(two_planet_task) -> None:
    """An exception out of a tool is an AG2 crash; ok=False is a fixable message."""
    task, _ = two_planet_task
    out = RvFit(task).as_tool()([11.2, 11.25])
    assert out["ok"] is False
    assert "duplicates" in out["error"]


def test_eccentricity_stays_inside_the_graders_clip(two_planet_correct_fit) -> None:
    """The forward model clips e at 0.95; a fit outside it would be silently altered."""
    result = two_planet_correct_fit
    for planet in result["planets"]:
        assert 0.0 <= planet["e"] <= 0.95


def test_angles_are_wrapped_into_range(two_planet_task) -> None:
    task, _ = two_planet_task
    result = RvFit(task).fit([11.2])
    planet = result["planets"][0]
    assert 0.0 <= planet["l_rad"] < 2.0 * math.pi
    assert 0.0 <= planet["omega_rad"] < 2.0 * math.pi
