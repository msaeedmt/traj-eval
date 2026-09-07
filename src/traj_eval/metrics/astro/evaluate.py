"""Thin bridge: submission + truth -> vendored evaluator -> AstroCriteria."""

from __future__ import annotations

from typing import Any

from traj_eval.metrics.astro.criteria import AstroCriteria, evaluate_criteria
from traj_eval.vendor.stargazer.config import Observations, StarParams, SystemConfig
from traj_eval.vendor.stargazer.evaluator import evaluate_submission

EXPECTED_PLANET_FIELDS = ("P_days", "m_sin_i_mjup", "e", "omega_rad", "l_rad")
DEFAULT_REWARD_WEIGHTS: dict[str, float] = {
    "likelihood": 1.0,
    "delta_bic": 0.3,
    "neg_rms": 0.1,
    "match": 1.0,
    "count": 0.2,
}


class SubmissionShapeError(ValueError):
    """The submission is not a shape the evaluator can score."""


def validate_submission_shape(submission: Any) -> list[str]:
    if not isinstance(submission, dict):
        raise SubmissionShapeError(f"submission must be a dict, got {type(submission).__name__}")
    planets = submission.get("planets")
    if planets is None:
        raise SubmissionShapeError("submission must include 'planets'")
    if not isinstance(planets, list):
        raise SubmissionShapeError("'planets' must be a list of dicts")
    problems: list[str] = []
    for i, planet in enumerate(planets):
        if not isinstance(planet, dict):
            raise SubmissionShapeError(f"planets[{i}] must be a dict")
        if "P_days" not in planet:
            raise SubmissionShapeError(f"planets[{i}] must include 'P_days'")
        for key in EXPECTED_PLANET_FIELDS:
            if key not in planet:
                problems.append(f"planets[{i}] omits {key!r} (evaluator will default it)")
    return problems


def _rebuild_config_and_obs(task: Any, truth: Any) -> tuple[SystemConfig, Observations]:
    o = task.observation
    config = SystemConfig(
        star=StarParams(M_star_sun=float(o.star_mass_sun), gamma_ms=0.0),
        planets=list(truth.planets),
        schedule=None,
    )
    obs = Observations(
        times_days=list(o.times_days),
        rvs_ms=list(o.rvs_ms),
        sigmas_ms=list(o.sigmas_ms),
        instruments=list(o.instruments),
    )
    return config, obs


def score_submission(
    submission: dict[str, Any],
    *,
    task: Any,
    truth: Any,
    stargazer_task: Any = None,
    min_match_score: float | None = None,
) -> tuple[AstroCriteria, dict[str, Any]]:
    validate_submission_shape(submission)
    if stargazer_task is not None:
        config, obs = stargazer_task.config, stargazer_task.observations
    else:
        config, obs = _rebuild_config_and_obs(task, truth)
    _reward, info = evaluate_submission(
        config=config,
        obs=obs,
        submission=submission,
        truth_planets=list(truth.planets),
        reward_weights=DEFAULT_REWARD_WEIGHTS,
        mode="params_and_model",
    )
    criteria = evaluate_criteria(
        info,
        median_sigma_ms=task.observation.median_sigma_ms,
        hints=task.observation.hints,
        min_match_score=min_match_score,
    )
    return criteria, info


def submission_from_planets(planets: list[Any], *, jitter_ms: float = 0.0) -> dict[str, Any]:
    return {
        "planets": [
            {
                "P_days": float(p.P_days),
                "m_sin_i_mjup": float(p.m_sin_i_mjup),
                "e": float(p.e),
                "inc_rad": float(p.inc_rad),
                "Omega_rad": float(p.Omega_rad),
                "omega_rad": float(p.omega_rad),
                "l_rad": float(p.l_rad),
            }
            for p in planets
        ],
        "noise": {"sigma_jitter_ms": float(jitter_ms)},
    }
