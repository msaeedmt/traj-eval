"""Thin bridge: submission + truth -> vendored evaluator -> AstroCriteria.

The only astro module that imports the vendored Stargazer evaluator. Everything
above it (criteria, anchors, detectors, validator) works on plain dicts and
``AstroCriteria``, so the coupling to upstream code stays at one leaf.

Reuse over reimplementation is not a convenience, it is a correctness
requirement: the forward model (``simulate_rv_keplerian``), the Hungarian
matcher (``match_planets``, weights ``rv_curve=4.0, dlogP=1.0, dlogK=0.5,
de=0.5``, ``max_dist=5``) and the per-instrument MLE gamma fit are precisely
what makes our numbers commensurable with Stargazer's published baseline. A
local reimplementation differing in the fourth decimal place would quietly
destroy that comparability AND the credibility of every anchor built on it.
Those files are vendored verbatim under ``traj_eval/vendor/stargazer`` and
checksum-pinned by ``tests/vendor/test_vendor_integrity.py``.

Submission schema (``params_and_model`` mode). Note the agent does NOT submit
gamma: ``evaluate_submission`` fits one systemic offset per instrument by
weighted MLE itself.

    {
      "planets": [
        {"P_days": float, "m_sin_i_mjup": float, "e": float,
         "inc_rad": float, "Omega_rad": float, "omega_rad": float,
         "l_rad": float},
        ...
      ],
      "noise": {"sigma_jitter_ms": float}          # optional
    }

Only ``P_days`` is strictly required per planet; the rest silently default (see
``evaluator._parse_submission_planets``). Those defaults are a trap -- a planet
submitted without ``l_rad`` gets phase 0, which is exactly the format-fragility
failure mode we intend to DETECT -- so ``validate_submission_shape`` reports
omissions rather than letting them pass unnoticed.
"""

from __future__ import annotations

from typing import Any

from traj_eval.metrics.astro.criteria import AstroCriteria, evaluate_criteria
from traj_eval.vendor.stargazer.config import (
    Observations,
    StarParams,
    SystemConfig,
)
from traj_eval.vendor.stargazer.evaluator import evaluate_submission

# Fields the agent is expected to supply explicitly. Anything omitted is
# defaulted by the evaluator, which turns an omission into a wrong answer rather
# than an error -- so we surface it.
EXPECTED_PLANET_FIELDS = (
    "P_days",
    "m_sin_i_mjup",
    "e",
    "omega_rad",
    "l_rad",
)

# Reward weights do not affect the pass/fail gate (they only scale the scalar
# reward), but evaluate_submission requires them. These are upstream's defaults,
# kept so a logged reward stays comparable if we ever report it.
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
    """Return a list of soft shape problems (empty == fine); raise on hard ones.

    The distinction matters for the taxonomy: a malformed submission the
    evaluator rejects is a format error the agent can see and fix, whereas a
    submission with a silently-defaulted ``l_rad`` scores badly for reasons the
    agent cannot see. The second is the interesting failure, so it is reported
    rather than raised.
    """
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
    """Reconstruct the two dataclasses ``evaluate_submission`` reads.

    Only star mass, the truth planets, and the observation arrays are consumed
    in ``params_and_model`` mode; ``schedule`` is never touched, hence ``None``.
    """
    o = task.observation
    config = SystemConfig(
        star=StarParams(M_star_sun=float(o.star_mass_sun), gamma_ms=0.0),
        planets=list(truth.planets),
        schedule=None,  # unused by evaluate_submission
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
    task: Any,  # AstroTask
    truth: Any,  # AstroTruth
    stargazer_task: Any = None,
) -> tuple[AstroCriteria, dict[str, Any]]:
    """Score one submission, returning (criteria, raw evaluator info).

    Pass ``stargazer_task`` (the parsed ``Task``) when the caller already holds
    it -- the cheaper path inside a trial. Otherwise the minimum the evaluator
    reads is rebuilt from ``AstroTask`` / ``AstroTruth``.
    """
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
    )
    return criteria, info


def submission_from_planets(planets: list[Any], *, jitter_ms: float = 0.0) -> dict[str, Any]:
    """Build a submission dict from ``PlanetParams`` objects.

    Used by the A0 probe (submit the ground truth) and later by anchor code that
    forward-models a hypothesised system through the same path the evaluator
    uses.
    """
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
