"""Keplerian fitting tool: given candidate periods, fit an N-planet model.

Optimises weighted residuals against the VENDORED forward model via
``rv_model.weighted_residuals``, so the objective the agent minimises and the
metrics the grader computes are the same functions. That equality is what makes
the ``fit_rms`` anchor exact: when the agent reports an RMS, we can recompute
what its parameters really imply without any implementation gap to explain away.

Design choices that matter to the measurement
---------------------------------------------
**Periods stay near the guess.** The optimiser may move each period only within
``period_tolerance_frac`` (default 20%). This is not a numerical convenience --
it is what preserves alias convergence as an observable phenomenon. An alias is
typically at P/2, 2P, or a 1-day beat period, all far outside 20%; so a fit
seeded on an alias converges on the alias and fails, exactly as it should. An
unbounded optimiser would quietly slide from a wrong peak to the right one and
delete the failure mode this project exists to detect. Refinement within the
periodogram peak still works, since the peak is far narrower than 20%.

**Offsets are profiled out, not fitted.** ``evaluate_submission`` fits one
systemic velocity per instrument by weighted MLE and ignores any gamma in the
submission, so we solve them analytically at every objective evaluation. Fewer
free parameters, better conditioning, and identical to what the grader will do.

**Parameterisation.** log P (scale-free), log K (amplitude is positive and spans
orders of magnitude), and h = sqrt(e) cos w, k = sqrt(e) sin w. The h/k pair
removes the e -> 0 degeneracy where omega becomes unidentifiable and the
optimiser stalls on a ridge. K is converted to m sin i on output by inverting
the grader's own relation.

**Determinism.** Same arguments in, same fit out: the multi-start seeds come
from a fixed sequence, never from an unseeded RNG. The trace is only gradable if
tool verdicts are reproducible -- the same property the Lean compiler tool is
built around.

The returned ``ok`` means THE OPTIMISER CONVERGED, not that the fit is good. The
no-progress bound in the controller counts ``ok: false``, and what should trip it
is a fitter that cannot produce a usable answer at all -- repeated thrashing --
not a converged fit that happens to be wrong. Judging fit quality is the
evaluator's job, and the agent gets the numbers to judge it too.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.optimize import least_squares

from traj_eval.tools.rv_model import (
    MAX_ECC,
    fit_quality,
    make_residual_fn,
    mass_from_semi_amplitude,
    planets_to_submission_dicts,
    semi_amplitude_from_mass,
    to_planet_params,
)

PARAMS_PER_PLANET = 5  # log P, log K, h, k, l_rad
DEFAULT_PERIOD_TOLERANCE_FRAC = 0.20
DEFAULT_MAX_STARTS = 12
MAX_PLANETS = 6
# Per-start evaluation cap. With sane tolerances a fit converges in far fewer;
# the cap only bounds pathological starts.
MAX_NFEV = 600
_SQRT_MAX_ECC = math.sqrt(MAX_ECC)

# Eccentricity and phase seeds. Two eccentricities (near-circular and moderate)
# and four phases spread over the circle: enough to escape the common local
# minima without making the start count explode with planet number.
_ECC_SEEDS = (0.01, 0.25)
_PHASE_SEEDS = (0.0, 0.5 * math.pi, math.pi, 1.5 * math.pi)


class RvFitError(ValueError):
    """The fit request itself is malformed (bad periods, too many planets)."""


def _unpack(theta: np.ndarray, n_planets: int) -> list[dict[str, float]]:
    """Optimiser vector -> submission-shaped planet dicts."""
    planets: list[dict[str, float]] = []
    for i in range(n_planets):
        log_p, log_k, h, k, lam = theta[i * PARAMS_PER_PLANET : (i + 1) * PARAMS_PER_PLANET]
        e = float(np.clip(h * h + k * k, 0.0, MAX_ECC))
        omega = float(math.atan2(k, h)) % (2.0 * math.pi)
        planets.append(
            {
                "P_days": float(math.exp(log_p)),
                "K_ms": float(math.exp(log_k)),
                "e": e,
                "omega_rad": omega,
                "l_rad": float(lam) % (2.0 * math.pi),
            }
        )
    return planets


def _to_planet_dicts(raw: list[dict[str, float]], star_mass_sun: float) -> list[dict[str, float]]:
    """Convert the optimiser's K parameterisation into the submission schema."""
    return [
        {
            "P_days": p["P_days"],
            "m_sin_i_mjup": mass_from_semi_amplitude(p["K_ms"], p["P_days"], p["e"], star_mass_sun),
            "e": p["e"],
            "inc_rad": 0.0,
            "Omega_rad": 0.0,
            "omega_rad": p["omega_rad"],
            "l_rad": p["l_rad"],
        }
        for p in raw
    ]


def _seed_vectors(
    period_guesses: list[float],
    k_guess: float,
    max_starts: int,
) -> list[np.ndarray]:
    """Deterministic multi-start seeds, most promising first.

    Start 0 is always near-circular at phase 0 -- the seed most fits converge
    from. Later seeds vary eccentricity and phase in a fixed order, so the set
    is reproducible and truncating at ``max_starts`` keeps the best candidates.
    """
    n = len(period_guesses)
    seeds: list[np.ndarray] = []
    log_k = math.log(max(k_guess, 1e-3))
    for ecc in _ECC_SEEDS:
        for phase in _PHASE_SEEDS:
            theta = np.empty(n * PARAMS_PER_PLANET, dtype=float)
            for i, period in enumerate(period_guesses):
                # Offset each planet's phase seed so a multi-planet start does
                # not put every planet at the same orbital phase.
                lam = (phase + i * 0.5 * math.pi) % (2.0 * math.pi)
                theta[i * PARAMS_PER_PLANET : (i + 1) * PARAMS_PER_PLANET] = (
                    math.log(period),
                    log_k,
                    math.sqrt(ecc),  # h with omega = 0
                    0.0,  # k
                    lam,
                )
            seeds.append(theta)
            if len(seeds) >= max_starts:
                return seeds
    return seeds


def _bounds(
    period_guesses: list[float],
    tolerance_frac: float,
    k_max: float,
) -> tuple[np.ndarray, np.ndarray]:
    n = len(period_guesses)
    lo = np.empty(n * PARAMS_PER_PLANET, dtype=float)
    hi = np.empty(n * PARAMS_PER_PLANET, dtype=float)
    for i, period in enumerate(period_guesses):
        s = slice(i * PARAMS_PER_PLANET, (i + 1) * PARAMS_PER_PLANET)
        lo[s] = (
            math.log(period * (1.0 - tolerance_frac)),
            math.log(1e-3),
            -_SQRT_MAX_ECC,
            -_SQRT_MAX_ECC,
            -4.0 * math.pi,
        )
        hi[s] = (
            math.log(period * (1.0 + tolerance_frac)),
            math.log(max(k_max, 1e-2)),
            _SQRT_MAX_ECC,
            _SQRT_MAX_ECC,
            4.0 * math.pi,
        )
    return lo, hi


class RvFit:
    """Keplerian fitting tool bound to one task's observations.

    Holds only the agent-visible ``AstroTask``; no ground truth is reachable
    from here.
    """

    def __init__(self, task: Any) -> None:
        obs = task.observation
        self.task_id = str(task.task_id)
        self.times = np.asarray(obs.times_days, dtype=float)
        self.rvs = np.asarray(obs.rvs_ms, dtype=float)
        self.sigmas = np.asarray(obs.sigmas_ms, dtype=float)
        self.instruments = np.asarray(obs.instruments)
        self.star_mass_sun = float(obs.star_mass_sun)
        self.baseline_days = float(obs.baseline_days)
        self._rv_scale = float(np.std(self.rvs)) if self.rvs.size else 1.0

    def _residual_fn(self, n_planets: int, sigma_jitter_ms: float):
        """Objective closure with instrument bookkeeping hoisted out of the loop."""
        base = make_residual_fn(
            times_days=self.times,
            rvs_ms=self.rvs,
            sigmas_ms=self.sigmas,
            instruments=self.instruments,
            star_mass_sun=self.star_mass_sun,
            sigma_jitter_ms=sigma_jitter_ms,
        )

        def residuals(theta: np.ndarray) -> np.ndarray:
            raw = _unpack(theta, n_planets)
            return base(to_planet_params(_to_planet_dicts(raw, self.star_mass_sun)))

        return residuals

    def fit(
        self,
        period_guesses: list[float],
        *,
        sigma_jitter_ms: float = 0.0,
        period_tolerance_frac: float = DEFAULT_PERIOD_TOLERANCE_FRAC,
        max_starts: int = DEFAULT_MAX_STARTS,
    ) -> dict[str, Any]:
        """Fit one planet per entry in ``period_guesses``."""
        guesses = self._validate(period_guesses)
        n = len(guesses)
        residual_fn = self._residual_fn(n, sigma_jitter_ms)
        lo, hi = _bounds(guesses, period_tolerance_frac, k_max=100.0 * max(self._rv_scale, 1e-2))
        seeds = _seed_vectors(guesses, k_guess=max(self._rv_scale, 1e-2), max_starts=max_starts)

        best_theta: np.ndarray | None = None
        best_cost = math.inf
        n_converged = 0
        for theta0 in seeds:
            try:
                result = least_squares(
                    residual_fn,
                    np.clip(theta0, lo, hi),
                    bounds=(lo, hi),
                    method="trf",
                    max_nfev=MAX_NFEV,
                    xtol=1e-10,
                    ftol=1e-10,
                    gtol=1e-10,
                    x_scale="jac",
                )
            except (ValueError, FloatingPointError):
                # A seed can land somewhere the forward model rejects; skip it
                # rather than failing the whole fit, and report how many worked.
                continue
            if result.success:
                n_converged += 1
            if np.isfinite(result.cost) and result.cost < best_cost:
                best_cost, best_theta = float(result.cost), result.x

        if best_theta is None:
            return {
                "ok": False,
                "task_id": self.task_id,
                "error": "no start converged to a finite solution",
                "n_starts_tried": len(seeds),
                "n_planets_requested": n,
                "period_guesses_days": guesses,
            }

        planet_dicts = _to_planet_dicts(_unpack(best_theta, n), self.star_mass_sun)
        planets = to_planet_params(planet_dicts)
        quality = fit_quality(
            planets,
            times_days=self.times,
            rvs_ms=self.rvs,
            sigmas_ms=self.sigmas,
            instruments=self.instruments,
            star_mass_sun=self.star_mass_sun,
            sigma_jitter_ms=sigma_jitter_ms,
        )
        submission_planets = planets_to_submission_dicts(planets)
        return {
            "ok": True,
            "task_id": self.task_id,
            "planets": submission_planets,
            "semi_amplitudes_ms": [
                semi_amplitude_from_mass(p["m_sin_i_mjup"], p["P_days"], p["e"], self.star_mass_sun)
                for p in submission_planets
            ],
            "period_guesses_days": guesses,
            "period_bound_frac": float(period_tolerance_frac),
            "n_starts_tried": len(seeds),
            "n_starts_converged": n_converged,
            "sigma_jitter_ms": float(sigma_jitter_ms),
            **quality,
            "notes": (
                "Periods were constrained to within "
                f"{period_tolerance_frac:.0%} of the supplied guesses, so a guess on a "
                "spurious periodogram peak will not drift onto a different period. "
                "l_rad is the mean longitude at the FIRST observation epoch "
                "(times_days[0]); submit it on that convention. Systemic offsets are "
                "fitted per instrument and must not be included in the submission. "
                "rms_ms and delta_bic_per_point are computed the same way the final "
                "evaluation computes them."
            ),
        }

    def _validate(self, period_guesses: list[float]) -> list[float]:
        if not isinstance(period_guesses, list | tuple) or not period_guesses:
            raise RvFitError("period_guesses must be a non-empty list of periods in days")
        if len(period_guesses) > MAX_PLANETS:
            raise RvFitError(f"at most {MAX_PLANETS} planets may be fitted at once")
        out: list[float] = []
        for raw in period_guesses:
            try:
                period = float(raw)
            except (TypeError, ValueError) as exc:
                raise RvFitError(f"period guess {raw!r} is not a number") from exc
            if not math.isfinite(period) or period <= 0.0:
                raise RvFitError(f"period guess {period} must be a positive finite number")
            # Two guesses at effectively the same period make the model
            # degenerate: the optimiser can trade amplitude between them freely.
            if any(abs(period - kept) <= 0.01 * min(period, kept) for kept in out):
                raise RvFitError(
                    f"period guess {period:.4g} d duplicates another guess; "
                    "distinct planets need distinct periods"
                )
            out.append(period)
        return out

    def as_tool(self):
        """Return the closure to register with AG2."""

        def rv_fit(
            period_guesses: list[float],
            sigma_jitter_ms: float = 0.0,
        ) -> dict[str, Any]:
            """Fit a multi-planet Keplerian model at the given candidate periods.

            Fits one planet per period supplied, with per-instrument systemic
            velocities solved automatically. Returns the fitted orbital
            parameters plus the fit-quality numbers used in the final evaluation
            (rms_ms, delta_bic_per_point). Each period is refined only within
            20% of the value you supply, so choose your candidate periods
            deliberately.

            Args:
                period_guesses: candidate orbital periods in days, one per
                    planet. Must be distinct.
                sigma_jitter_ms: extra white noise in m/s to add in quadrature
                    to the reported uncertainties, if you believe the star is
                    jittery.
            """
            try:
                return self.fit(period_guesses, sigma_jitter_ms=sigma_jitter_ms)
            except RvFitError as exc:
                return {"ok": False, "task_id": self.task_id, "error": str(exc)}

        return rv_fit
