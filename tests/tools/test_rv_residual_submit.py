"""Tests for the residual tool and the submission tool."""

from __future__ import annotations

import math

import pytest

from traj_eval.tools.rv_fit import RvFit
from traj_eval.tools.rv_residual import RvResidual
from traj_eval.tools.rv_submit import RvSubmit

# --------------------------------------------------------------------------
# rv_residual
# --------------------------------------------------------------------------


def test_escalation_reveals_the_second_planet(two_planet_task) -> None:
    """The subtract-and-look-again loop must actually work.

    This is the whole mechanism by which multi-planet systems get found: remove
    the strong planet, and the weaker one should become the top residual peak.
    """
    task, _ = two_planet_task
    residual = RvResidual(task)
    fitter = RvFit(task)

    raw = residual.analyse([])
    assert not raw["rms_within_threshold"]
    assert raw["residual_periodogram"]["peaks"][0]["period_days"] == pytest.approx(57.9, rel=0.05)

    one_removed = residual.analyse(fitter.fit([57.9])["planets"])
    assert one_removed["residual_rms_ms"] < raw["residual_rms_ms"]
    assert not one_removed["rms_within_threshold"]
    surviving = one_removed["residual_periodogram"]["peaks"][0]["period_days"]
    assert surviving == pytest.approx(11.2, rel=0.05), "the missed planet must be findable"

    both_removed = residual.analyse(fitter.fit([11.2, 57.9])["planets"])
    assert both_removed["residual_rms_ms"] < one_removed["residual_rms_ms"]
    assert both_removed["rms_within_threshold"], "the full model should clear the RMS gate"


def test_scatter_is_reported_against_the_graders_threshold(two_planet_task) -> None:
    """3 m/s means nothing until you know whether sigma is 0.5 or 5."""
    task, _ = two_planet_task
    result = RvResidual(task).analyse([])
    expected = 1.5 * task.observation.median_sigma_ms
    assert result["rms_threshold_ms"] == pytest.approx(expected)
    assert result["residual_rms_in_sigma"] == pytest.approx(
        result["residual_rms_ms"] / task.observation.median_sigma_ms
    )
    assert result["rms_within_threshold"] is (result["residual_rms_ms"] <= expected)


def test_residual_result_carries_no_ok_key(two_planet_task) -> None:
    """Inspecting residuals is exploration, not a verification attempt."""
    task, _ = two_planet_task
    assert "ok" not in RvResidual(task).analyse([])


def test_per_instrument_breakdown(two_planet_task) -> None:
    task, _ = two_planet_task
    result = RvResidual(task).analyse([])
    assert set(result["per_instrument"]) == {"instA"}
    assert result["per_instrument"]["instA"]["n_points"] == task.observation.n_obs


def test_omitting_planets_analyses_the_raw_data(two_planet_task) -> None:
    task, _ = two_planet_task
    tool = RvResidual(task).as_tool()
    assert tool()["n_planets_removed"] == 0
    assert tool(planets=[])["residual_rms_ms"] == pytest.approx(tool()["residual_rms_ms"])


# --------------------------------------------------------------------------
# rv_submit
# --------------------------------------------------------------------------


def test_a_correct_fit_solves_the_task(two_planet_task, two_planet_correct_fit) -> None:
    task, truth = two_planet_task
    planets = two_planet_correct_fit["planets"]
    result = RvSubmit(task=task, truth=truth).submit({"planets": planets})
    assert result["ok"] and result["solved"]
    assert result["failed_criteria"] == []
    assert all(result["criteria"].values())


def test_phase_convention_error_fails_match_and_is_explained(
    two_planet_task, two_planet_correct_fit
) -> None:
    """Format fragility: right science, wrong epoch convention.

    The guidance must point at l_rad, because this failure is indistinguishable
    from a scientific error unless the agent is told where to look.
    """
    task, truth = two_planet_task
    planets = two_planet_correct_fit["planets"]
    broken = [dict(p, l_rad=(p["l_rad"] + math.pi) % (2.0 * math.pi)) for p in planets]

    submitter = RvSubmit(task=task, truth=truth)
    good = submitter.submit({"planets": planets})
    bad = submitter.submit({"planets": broken})

    assert good["solved"] and not bad["solved"]
    assert "ok_match" in bad["failed_criteria"]
    assert bad["measured"]["rms_ms"] > good["measured"]["rms_ms"]
    assert any("l_rad" in line for line in bad["guidance"])


def test_omitted_fields_produce_shape_warnings(two_planet_task) -> None:
    """A defaulted l_rad scores badly for a reason the agent cannot otherwise see."""
    task, truth = two_planet_task
    result = RvSubmit(task=task, truth=truth).submit({"planets": [{"P_days": 11.2}]})
    assert result["ok"]
    assert any("l_rad" in w for w in result["shape_warnings"])


def test_budget_is_enforced_at_the_tier_limit(two_planet_task, two_planet_correct_fit) -> None:
    task, truth = two_planet_task  # easy tier -> 3 attempts
    planets = two_planet_correct_fit["planets"]
    submitter = RvSubmit(task=task, truth=truth)
    assert submitter.max_attempts == 3

    for expected_remaining in (2, 1, 0):
        out = submitter.submit({"planets": planets})
        assert out["ok"]
        assert out["attempts_remaining"] == expected_remaining

    exhausted = submitter.submit({"planets": planets})
    assert exhausted["ok"] is False
    assert "budget" in exhausted["error"]
    assert submitter.n_attempts == 3


def test_best_of_episode_remembers_a_solved_attempt(
    two_planet_task, two_planet_correct_fit
) -> None:
    """Stargazer scores the best submission, not the last one."""
    task, truth = two_planet_task
    planets = two_planet_correct_fit["planets"]
    submitter = RvSubmit(task=task, truth=truth)
    submitter.submit({"planets": planets})
    submitter.submit(
        {
            "planets": [
                {"P_days": 3.3, "m_sin_i_mjup": 0.1, "e": 0.0, "omega_rad": 0.0, "l_rad": 0.0}
            ]
        }
    )
    assert [a.criteria.solved for a in submitter.attempts] == [True, False]
    assert submitter.solved is True


@pytest.mark.parametrize(
    "submission",
    [
        {"planets": [{"m_sin_i_mjup": 1.0}]},  # no P_days
        {"planets": "nonsense"},
        {"planets": None},
        {"planets": [42]},
        "not a dict",
    ],
)
def test_malformed_submissions_never_consume_scoring_budget(two_planet_task, submission) -> None:
    """Format errors must not cost a scientific attempt.

    A typo costing a scoring attempt would conflate format fragility with
    scientific failure -- the two things the taxonomy needs to keep apart.
    """
    task, truth = two_planet_task
    submitter = RvSubmit(task=task, truth=truth)
    result = submitter.submit(submission)
    assert result["ok"] is False
    assert result["attempts_used"] == 0
    assert submitter.attempts_remaining == 3
    assert submitter.n_invalid == 1


def test_malformed_submissions_are_capped(two_planet_task) -> None:
    """Uncapped format retries would burn the token budget instead."""
    task, truth = two_planet_task
    submitter = RvSubmit(task=task, truth=truth, max_invalid=2)
    for _ in range(2):
        submitter.submit({"planets": None})
    final = submitter.submit({"planets": None})
    assert final["invalid_attempts_remaining"] == 0
    assert submitter.attempts_remaining == 3  # still untouched


def test_result_never_leaks_the_truth(two_planet_task) -> None:
    """The only tool holding AstroTruth must not echo it back.

    A leaked planet count or period would let an agent 'solve' the task by
    reading the feedback, and nothing downstream could detect that afterwards.
    """
    task, truth = two_planet_task
    result = RvSubmit(task=task, truth=truth).submit(
        {
            "planets": [
                {"P_days": 3.3, "m_sin_i_mjup": 0.1, "e": 0.0, "omega_rad": 0.0, "l_rad": 0.0}
            ]
        }
    )
    blob = repr(result)
    for planet in truth.planets:
        assert f"{planet.P_days:.6g}" not in blob
    # The count is revealed only as a pass/fail bit, never as a number.
    assert "n_planets_truth" not in result
    assert result["n_planets_submitted"] == 1
