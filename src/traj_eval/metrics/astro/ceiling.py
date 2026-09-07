"""The match ceiling: the best score a maximum-likelihood fitter could achieve.

Why this exists
---------------
Stargazer's ``ok_match`` criterion asks whether the submitted orbits correspond
to the true system, with a threshold of 0.80. It is not always satisfiable.

With finite data, the parameters that best explain the observations are not
exactly the true parameters -- noise displaces the likelihood peak. On
seed22_diff4 (53 points, sigma 3.14 m/s, only 2.6 orbital cycles observed) an
exhaustive search finds the global maximum-likelihood solution at P = 3.1011 d
against a true period of 3.1170 d, and that solution fits the data BETTER than
the truth does (RMS 4.034 versus 4.409). Its match score is 0.774. The threshold
is 0.80. No fitting procedure can pass that task: the only way to score higher
would be to fit worse.

Without knowing which tasks are like that, every aggregate conflates two very
different things -- agents reasoning badly, and tasks that cannot be passed. The
ceiling separates them:

    ceiling >= 0.80  ->  solvable; a failure is attributable to the agents
    ceiling <  0.80  ->  unsolvable; exclude it, or report it separately
    match_deficit    ->  ceiling minus what the team achieved, i.e. the part of
                         the shortfall that really is the team's

Why this does NOT reuse rv_fit
------------------------------
The ceiling has to be an INDEPENDENT reference. If it were computed with the same
optimiser the agents call, any limitation of that optimiser would appear as a
property of the benchmark, and a task the agents could not fit would look
unsolvable rather than hard. So this module carries its own multi-start
least-squares fit and depends only on the vendored evaluator and forward model --
the same physics the grader uses, reached by a different route.

It also deliberately does NOT constrain periods to +-20% the way ``rv_fit`` does.
That bound exists to keep alias convergence observable during a trial; here we
want the genuine optimum, so the search is seeded near the true periods and
allowed to settle wherever the likelihood takes it.

What "ceiling" means precisely
------------------------------
The match score of the maximum-likelihood solution AT THE TRUE PLANET COUNT.

Not "the best possible submission" -- that is trivially the truth itself, scoring
1.0, which no fitter would ever return because it fits the data worse. The
question a ceiling has to answer is: *if an agent identified the right number of
planets and fitted them perfectly, would it pass?* Hence maximum likelihood, at
the right count, scored for match.

Cost: seconds per task, no LLM, no network. Run once, cache, reuse.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import least_squares

from traj_eval.metrics.astro.criteria import DEFAULT_MIN_MATCH_SCORE
from traj_eval.metrics.astro.evaluate import score_submission
from traj_eval.vendor.stargazer.config import PlanetParams
from traj_eval.vendor.stargazer.forward_keplerian import simulate_rv_keplerian
from traj_eval.vendor.stargazer.utils_units import semi_amplitude_ms

CEILINGS_FILENAME = "ceilings.json"

# The forward model clips eccentricity here; staying inside keeps the optimiser
# from exploring parameters the evaluator would silently alter.
MAX_ECC = 0.95
_SQRT_MAX_ECC = math.sqrt(MAX_ECC)

# Multi-start seeds. The search is seeded AROUND the true periods rather than
# blind across the whole range: we are asking what a fitter that already found
# the right periods could achieve, not whether the periods are findable (that is
# the period-selection anchor's question).
#
# The FIRST seed is the truth itself. That is the canonical start for this
# problem -- relaxing from the true parameters lands on the likelihood optimum in
# truth's own basin -- and omitting it produced badly wrong ceilings: on two
# tasks whose true eccentricity fell outside the grid below, the search settled
# in a poor basin and reported ceilings of 0.579 for systems that real trials
# scored 0.981 and 0.845 on. A ceiling that trials beat is worse than no ceiling,
# because it silently converts agent successes into "impossible" tasks.
PERIOD_SEED_OFFSETS = (0.97, 1.0, 1.03)
ECC_SEEDS = (0.02, 0.25, 0.55, 0.80)
PHASE_SEEDS = (0.0, 0.5 * math.pi, math.pi, 1.5 * math.pi)

# Periods may settle this far from their seed. Wide enough for the likelihood
# peak (observed displacements are well under 1%), narrow enough that a planet
# cannot wander onto a neighbour's period and produce a degenerate fit.
PERIOD_BOUND_FRAC = 0.15

MAX_STARTS = 48
MAX_NFEV = 1500


@dataclass(frozen=True)
class MatchCeiling:
    """The best a maximum-likelihood fitter could do on one task."""

    task_id: str
    kind: str
    difficulty: int
    tier: str
    n_truth_planets: int
    ceiling_match: float | None
    ceiling_solved: bool
    threshold: float
    ceiling_rms_ms: float | None
    truth_rms_ms: float | None
    truth_match: float | None
    ceiling_periods_days: list[float]
    truth_periods_days: list[float]
    n_starts: int
    error: str | None = None

    @property
    def solvable(self) -> bool:
        """Can any maximum-likelihood fit clear the match threshold?"""
        return self.ceiling_solved

    @property
    def outfits_truth(self) -> bool | None:
        """Does the ML solution explain the data better than the truth does?

        When true, the benchmark is asking for parameters the data does not
        support: any fitter that maximises likelihood moves AWAY from the answer
        being scored. This is the diagnostic that makes an unsolvable task
        legible rather than merely disappointing.
        """
        if self.ceiling_rms_ms is None or self.truth_rms_ms is None:
            return None
        return self.ceiling_rms_ms < self.truth_rms_ms

    def deficit_for(self, achieved_match: float | None) -> float | None:
        """Ceiling minus achieved: the part of the shortfall that is the team's."""
        if achieved_match is None or self.ceiling_match is None:
            return None
        return self.ceiling_match - achieved_match


def _weighted_rms(rvs, model, sigmas, instruments) -> float:
    """RMS after removing the MLE systemic offset per instrument, as the grader does."""
    resid = rvs - model
    weights = 1.0 / (sigmas**2 + 1e-12)
    for label in np.unique(instruments):
        mask = instruments == label
        offset = float(np.sum(weights[mask] * resid[mask]) / np.sum(weights[mask]))
        resid[mask] -= offset
    return float(np.sqrt(np.mean(resid**2)))


def _planets_from_theta(theta: np.ndarray, n: int, star_mass: float) -> list[PlanetParams]:
    planets: list[PlanetParams] = []
    for i in range(n):
        log_p, log_k, h, k, lam = theta[i * 5 : (i + 1) * 5]
        e = float(np.clip(h * h + k * k, 0.0, MAX_ECC))
        omega = float(math.atan2(k, h)) % (2.0 * math.pi)
        period = math.exp(log_p)
        semi_amplitude = math.exp(log_k)
        mass = (
            semi_amplitude
            * math.sqrt(max(1.0 - e * e, 1e-12))
            * (star_mass ** (2.0 / 3.0))
            * ((period / 365.25) ** (1.0 / 3.0))
            / 28.4329
        )
        planets.append(
            PlanetParams(
                P_days=period,
                m_sin_i_mjup=mass,
                e=e,
                inc_rad=0.0,
                Omega_rad=0.0,
                omega_rad=omega,
                l_rad=float(lam) % (2.0 * math.pi),
            )
        )
    return planets


def _truth_seed(truth_planets: list[Any], star_mass: float) -> np.ndarray:
    """The true parameters, in optimiser coordinates.

    Relaxing from here finds the likelihood optimum in truth's own basin, which
    is exactly the quantity a ceiling should report.
    """
    theta = np.empty(len(truth_planets) * 5, dtype=float)
    for i, p in enumerate(sorted(truth_planets, key=lambda q: q.P_days)):
        e = float(np.clip(p.e, 0.0, MAX_ECC))
        semi_amplitude = semi_amplitude_ms(
            float(p.m_sin_i_mjup), float(p.P_days), e, float(star_mass)
        )
        theta[i * 5 : (i + 1) * 5] = (
            math.log(float(p.P_days)),
            math.log(max(abs(semi_amplitude), 1e-3)),
            math.sqrt(e) * math.cos(float(p.omega_rad)),
            math.sqrt(e) * math.sin(float(p.omega_rad)),
            float(p.l_rad),
        )
    return theta


def _seeds(
    true_periods: list[float],
    k_guess: float,
    max_starts: int,
    truth_seed: np.ndarray | None = None,
) -> list[np.ndarray]:
    """Deterministic multi-start seeds, the truth first, then a grid around it.

    Ordered so the most productive starts come first, which makes truncation at
    ``max_starts`` keep the best candidates.
    """
    n = len(true_periods)
    log_k = math.log(max(k_guess, 1e-3))
    seeds: list[np.ndarray] = []
    if truth_seed is not None:
        seeds.append(truth_seed)
    for ecc in ECC_SEEDS:
        for phase in PHASE_SEEDS:
            for offset in PERIOD_SEED_OFFSETS:
                theta = np.empty(n * 5, dtype=float)
                for i, period in enumerate(true_periods):
                    theta[i * 5 : (i + 1) * 5] = (
                        math.log(period * offset),
                        log_k,
                        math.sqrt(ecc),
                        0.0,
                        (phase + i * 0.5 * math.pi) % (2.0 * math.pi),
                    )
                seeds.append(theta)
                if len(seeds) >= max_starts:
                    return seeds
    return seeds


def compute_ceiling(
    task: Any,
    truth: Any,
    *,
    stargazer_task: Any = None,
    max_starts: int = MAX_STARTS,
    min_match_score: float | None = None,
) -> MatchCeiling:
    """Find the maximum-likelihood fit at the true planet count and score it.

    ``max_starts`` trades thoroughness for speed. The default is sized for a
    one-off sweep over the whole bank; tests lower it, since the seed ordering
    puts the most productive starts first.
    """
    obs = task.observation
    times = np.asarray(obs.times_days, dtype=float)
    rvs = np.asarray(obs.rvs_ms, dtype=float)
    sigmas = np.asarray(obs.sigmas_ms, dtype=float)
    instruments = np.asarray(obs.instruments)
    star_mass = float(obs.star_mass_sun)
    true_periods = [float(p) for p in truth.periods_days]
    n = len(true_periods)

    common = {
        "task_id": str(task.task_id),
        "kind": str(task.kind),
        "difficulty": int(task.difficulty),
        "tier": str(task.tier),
        "n_truth_planets": n,
        "threshold": float(
            min_match_score if min_match_score is not None else DEFAULT_MIN_MATCH_SCORE
        ),
        "truth_periods_days": true_periods,
    }

    if n == 0:
        return MatchCeiling(
            ceiling_match=None,
            ceiling_solved=False,
            ceiling_rms_ms=None,
            truth_rms_ms=None,
            truth_match=None,
            ceiling_periods_days=[],
            n_starts=0,
            error="task has no truth planets",
            **common,
        )

    # Truth's own fit quality, for the "does ML out-fit truth" diagnostic.
    truth_model = simulate_rv_keplerian(list(truth.planets), times, star_mass, gamma_ms=0.0)
    truth_rms = _weighted_rms(rvs, truth_model, sigmas, instruments)
    truth_sub = {
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
            for p in truth.planets
        ]
    }
    truth_criteria, _ = score_submission(
        truth_sub,
        task=task,
        truth=truth,
        stargazer_task=stargazer_task,
        min_match_score=min_match_score,
    )

    inv_sigma = 1.0 / np.sqrt(sigmas**2 + 1e-12)
    weights = 1.0 / (sigmas**2 + 1e-12)
    masks = [
        (
            instruments == label,
            weights[instruments == label],
            float(np.sum(weights[instruments == label])),
        )
        for label in np.unique(instruments)
    ]

    def residuals(theta: np.ndarray) -> np.ndarray:
        planets = _planets_from_theta(theta, n, star_mass)
        signal = simulate_rv_keplerian(planets, times, star_mass, gamma_ms=0.0)
        resid = rvs - signal
        for mask, w_masked, w_sum in masks:
            resid[mask] -= float(np.sum(w_masked * resid[mask]) / w_sum)
        return resid * inv_sigma

    rv_scale = float(np.std(rvs)) if rvs.size else 1.0
    lo = np.empty(n * 5)
    hi = np.empty(n * 5)
    for i, period in enumerate(true_periods):
        lo[i * 5 : (i + 1) * 5] = (
            math.log(period * (1.0 - PERIOD_BOUND_FRAC)),
            math.log(1e-3),
            -_SQRT_MAX_ECC,
            -_SQRT_MAX_ECC,
            -4.0 * math.pi,
        )
        hi[i * 5 : (i + 1) * 5] = (
            math.log(period * (1.0 + PERIOD_BOUND_FRAC)),
            math.log(max(100.0 * rv_scale, 1e-2)),
            _SQRT_MAX_ECC,
            _SQRT_MAX_ECC,
            4.0 * math.pi,
        )

    best_theta: np.ndarray | None = None
    best_cost = math.inf
    seeds = _seeds(
        true_periods,
        max(rv_scale, 1e-2),
        max_starts,
        truth_seed=np.clip(_truth_seed(list(truth.planets), star_mass), lo, hi),
    )
    for theta0 in seeds:
        try:
            result = least_squares(
                residuals,
                np.clip(theta0, lo, hi),
                bounds=(lo, hi),
                method="trf",
                max_nfev=MAX_NFEV,
                xtol=1e-12,
                ftol=1e-12,
                gtol=1e-12,
                x_scale="jac",
            )
        except (ValueError, FloatingPointError):
            continue
        if np.isfinite(result.cost) and result.cost < best_cost:
            best_cost, best_theta = float(result.cost), result.x

    if best_theta is None:
        return MatchCeiling(
            ceiling_match=None,
            ceiling_solved=False,
            ceiling_rms_ms=None,
            truth_rms_ms=truth_rms,
            truth_match=truth_criteria.match_score,
            ceiling_periods_days=[],
            n_starts=len(seeds),
            error="no start converged",
            **common,
        )

    planets = _planets_from_theta(best_theta, n, star_mass)
    submission = {
        "planets": [
            {
                "P_days": float(p.P_days),
                "m_sin_i_mjup": float(p.m_sin_i_mjup),
                "e": float(p.e),
                "inc_rad": 0.0,
                "Omega_rad": 0.0,
                "omega_rad": float(p.omega_rad),
                "l_rad": float(p.l_rad),
            }
            for p in sorted(planets, key=lambda q: q.P_days)
        ]
    }
    criteria, _ = score_submission(
        submission,
        task=task,
        truth=truth,
        stargazer_task=stargazer_task,
        min_match_score=min_match_score,
    )
    model = simulate_rv_keplerian(planets, times, star_mass, gamma_ms=0.0)

    return MatchCeiling(
        ceiling_match=criteria.match_score,
        # Solvability is about the MATCH criterion specifically. The other three
        # are not in question here: a maximum-likelihood fit at the right count
        # passes delta-BIC and RMS essentially by construction, and the count is
        # correct by assumption.
        ceiling_solved=bool(
            criteria.match_score is not None and criteria.match_score >= criteria.min_match_score
        ),
        ceiling_rms_ms=_weighted_rms(rvs, model, sigmas, instruments),
        truth_rms_ms=truth_rms,
        truth_match=truth_criteria.match_score,
        ceiling_periods_days=[float(p["P_days"]) for p in submission["planets"]],
        n_starts=len(seeds),
        **common,
    )


# --------------------------------------------------------------------------
# cache
# --------------------------------------------------------------------------


def ceilings_path(dataset_root: Path | str) -> Path:
    return Path(dataset_root) / CEILINGS_FILENAME


def save_ceilings(ceilings: list[MatchCeiling], path: Path | str) -> None:
    payload = {c.task_id: asdict(c) for c in ceilings}
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def load_ceilings(path: Path | str) -> dict[str, MatchCeiling]:
    """Load the cache, or return {} when it has not been computed yet.

    Callers treat an empty result as "ceilings unknown" and fall back to
    unconditioned reporting, so nothing breaks on a checkout without the cache.
    """
    path = Path(path)
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {task_id: MatchCeiling(**fields) for task_id, fields in raw.items()}
