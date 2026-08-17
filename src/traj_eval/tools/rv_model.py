"""Shared RV numerics for the astro tools: one model, one set of metrics.

Every astro tool that evaluates a planetary system goes through this module, and
this module goes through the VENDORED Stargazer functions -- ``simulate_rv_keplerian``
for the forward model, and ``loglike_white_jitter`` / ``best_constant_fit`` /
``bic_from_ll`` / ``summarize_residuals`` for the metrics.

Why that matters more than it looks
-----------------------------------
The anchors are the research contribution, and an anchor asserts things like
*"the agent reported RMS 1.08, but its own parameters really imply 7.71"*. The
word "really" has to mean exactly what the grader means, or the anchor stops
measuring the agent's error and starts measuring the disagreement between two
implementations of the same equations. Since ``rv_fit`` optimises against this
module and the grader scores against the same functions, the agent's claimed fit
quality and the evaluated fit quality are the same quantity computed twice --
so any gap between them is genuinely the agent's.

It also removes a whole class of phantom bug. The reference epoch is
``times_days[0]`` (not zero, not the midpoint) and the phase convention is
``l_rad = omega + M0`` with ``Omega_rad = 0``; a tool that got either subtly
wrong would still produce plausible fits, and we would spend days deciding
whether an anchor violation was real.

Per-instrument offsets are NOT free parameters
----------------------------------------------
``evaluate_submission`` fits one systemic velocity per instrument by weighted
MLE and does not read any gamma from the submission. We mirror that here
(``mle_offsets``), which means the fitter profiles them out analytically at
every objective evaluation instead of handing them to the optimiser. That is
both faster and exactly what the grader will do afterwards.

BIC parameter count is the grader's: ``5 * n_planets + n_instruments``.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from traj_eval.vendor.stargazer.config import PlanetParams
from traj_eval.vendor.stargazer.evaluator import (
    best_constant_fit,
    bic_from_ll,
    loglike_white_jitter,
    summarize_residuals,
)
from traj_eval.vendor.stargazer.forward_keplerian import simulate_rv_keplerian
from traj_eval.vendor.stargazer.utils_units import semi_amplitude_ms

# The grader clips eccentricity here in the forward model; staying inside it
# keeps the fitter from exploring parameters the evaluator would silently alter.
MAX_ECC = 0.95

# Orbital parameters per planet, as counted for BIC by the evaluator.
PARAMS_PER_PLANET = 5


def mass_from_semi_amplitude(K_ms: float, P_days: float, e: float, M_star_sun: float) -> float:
    """Invert ``semi_amplitude_ms``: m sin i [M_Jup] from K [m/s].

    The fitter works in K because it is the linear, well-scaled amplitude of the
    signal; the submission schema wants a mass. Inverting the grader's own
    relation (rather than a textbook restatement of it) keeps the round trip
    exact.
    """
    if P_days <= 0.0:
        raise ValueError(f"P_days must be > 0, got {P_days}")
    e = float(np.clip(e, 0.0, 0.999999))
    P_years = P_days / 365.25
    return (
        abs(float(K_ms))
        * math.sqrt(1.0 - e * e)
        * (float(M_star_sun) ** (2.0 / 3.0))
        * (P_years ** (1.0 / 3.0))
        / 28.4329
    )


def semi_amplitude_from_mass(
    m_sin_i_mjup: float, P_days: float, e: float, M_star_sun: float
) -> float:
    """K [m/s] from m sin i [M_Jup] -- the grader's relation, re-exported."""
    return float(semi_amplitude_ms(float(m_sin_i_mjup), float(P_days), float(e), float(M_star_sun)))


def to_planet_params(planets: list[dict[str, Any]]) -> list[PlanetParams]:
    """Turn submission-shaped planet dicts into vendored ``PlanetParams``.

    Defaults mirror the evaluator's own parsing so that a dict which round-trips
    through here scores identically to one handed straight to
    ``evaluate_submission``. ``inc_rad`` is ignored by the forward model and
    ``Omega_rad`` is 0 under RV-only semantics.
    """
    out: list[PlanetParams] = []
    for p in planets:
        out.append(
            PlanetParams(
                P_days=float(p["P_days"]),
                m_sin_i_mjup=float(p.get("m_sin_i_mjup", 0.0)),
                e=float(np.clip(float(p.get("e", 0.0)), 0.0, MAX_ECC)),
                inc_rad=float(p.get("inc_rad", 0.0)),
                Omega_rad=float(p.get("Omega_rad", 0.0)),
                omega_rad=float(p.get("omega_rad", 0.0)),
                l_rad=float(p.get("l_rad", 0.0)),
            )
        )
    return out


def planet_signal(
    planets: list[PlanetParams],
    times_days: np.ndarray,
    star_mass_sun: float,
) -> np.ndarray:
    """The planetary RV signal with zero systemic offset.

    Offsets are added afterwards per instrument, exactly as the evaluator does.
    """
    if not planets:
        return np.zeros(np.asarray(times_days).shape, dtype=float)
    return simulate_rv_keplerian(
        planets, np.asarray(times_days, dtype=float), float(star_mass_sun), gamma_ms=0.0
    )


def mle_offsets(
    rvs_ms: np.ndarray,
    signal_ms: np.ndarray,
    sigmas_ms: np.ndarray,
    instruments: np.ndarray,
    sigma_jitter_ms: float = 0.0,
) -> dict[str, float]:
    """Weighted-MLE systemic offset per instrument (the evaluator's formula)."""
    var = sigmas_ms**2 + float(sigma_jitter_ms) ** 2 + 1e-12
    weights = 1.0 / var
    offsets: dict[str, float] = {}
    for inst in np.unique(instruments):
        mask = instruments == inst
        offsets[str(inst)] = float(
            np.sum(weights[mask] * (rvs_ms[mask] - signal_ms[mask])) / np.sum(weights[mask])
        )
    return offsets


def full_model(
    planets: list[PlanetParams],
    times_days: np.ndarray,
    rvs_ms: np.ndarray,
    sigmas_ms: np.ndarray,
    instruments: np.ndarray,
    star_mass_sun: float,
    sigma_jitter_ms: float = 0.0,
) -> tuple[np.ndarray, dict[str, float]]:
    """Planetary signal plus fitted per-instrument offsets. Returns (model, offsets)."""
    signal = planet_signal(planets, times_days, star_mass_sun)
    offsets = mle_offsets(rvs_ms, signal, sigmas_ms, instruments, sigma_jitter_ms)
    model = signal.copy()
    for inst, gamma in offsets.items():
        model[instruments == inst] += gamma
    return model, offsets


def fit_quality(
    planets: list[PlanetParams],
    *,
    times_days: np.ndarray,
    rvs_ms: np.ndarray,
    sigmas_ms: np.ndarray,
    instruments: np.ndarray,
    star_mass_sun: float,
    sigma_jitter_ms: float = 0.0,
) -> dict[str, Any]:
    """Every fit-quality number the four criteria depend on, grader-computed.

    ``delta_bic_per_point`` is the quantity the ``ok_delta_bic`` criterion tests
    (strictly > 0), and ``rms_ms`` the one ``ok_rms`` tests against
    ``1.5 * median sigma``. Reporting them here means the agent sees the same
    numbers it will be judged on -- which is the point: a divergence between
    them then indicates a real mistake (usually a phase or epoch convention
    error at submission time), not a difference of formula.
    """
    times_days = np.asarray(times_days, dtype=float)
    rvs_ms = np.asarray(rvs_ms, dtype=float)
    sigmas_ms = np.asarray(sigmas_ms, dtype=float)
    instruments = np.asarray(instruments)

    model, offsets = full_model(
        planets, times_days, rvs_ms, sigmas_ms, instruments, star_mass_sun, sigma_jitter_ms
    )
    n = int(rvs_ms.size)
    n_inst = int(np.unique(instruments).size)
    ll = loglike_white_jitter(rvs_ms, model, sigmas_ms, float(sigma_jitter_ms))
    k = len(planets) * PARAMS_PER_PLANET + n_inst
    bic = bic_from_ll(ll, k_params=k, n_points=n)
    null = best_constant_fit(rvs_ms, sigmas_ms, instruments=instruments)
    delta_bic = float(null["bic"]) - float(bic)
    resid = summarize_residuals(rvs_ms, model)

    return {
        "n_planets": len(planets),
        "rms_ms": float(resid["rms"]),
        "mae_ms": float(resid["mae"]),
        "log_likelihood": float(ll),
        "bic": float(bic),
        "bic_null": float(null["bic"]),
        "delta_bic": float(delta_bic),
        "delta_bic_per_point": float(delta_bic / n) if n else 0.0,
        "k_params": int(k),
        "gamma_per_instrument_ms": {key: float(v) for key, v in offsets.items()},
        "chi2_reduced": float(
            np.sum(((rvs_ms - model) ** 2) / (sigmas_ms**2 + float(sigma_jitter_ms) ** 2 + 1e-12))
            / max(n - k, 1)
        ),
    }


def weighted_residuals(
    planets: list[PlanetParams],
    *,
    times_days: np.ndarray,
    rvs_ms: np.ndarray,
    sigmas_ms: np.ndarray,
    instruments: np.ndarray,
    star_mass_sun: float,
    sigma_jitter_ms: float = 0.0,
) -> np.ndarray:
    """(data - model) / sigma, the vector ``least_squares`` minimises."""
    model, _ = full_model(
        planets, times_days, rvs_ms, sigmas_ms, instruments, star_mass_sun, sigma_jitter_ms
    )
    var = sigmas_ms**2 + float(sigma_jitter_ms) ** 2 + 1e-12
    return (rvs_ms - model) / np.sqrt(var)


def make_residual_fn(
    *,
    times_days: np.ndarray,
    rvs_ms: np.ndarray,
    sigmas_ms: np.ndarray,
    instruments: np.ndarray,
    star_mass_sun: float,
    sigma_jitter_ms: float = 0.0,
):
    """Build a fast weighted-residual function for repeated optimiser calls.

    Identical arithmetic to ``weighted_residuals``, but the per-instrument masks
    and inverse-variance weights are computed ONCE instead of on every objective
    evaluation. ``np.unique`` over a string array inside the inner loop dominated
    the fit cost: a least-squares fit makes thousands of evaluations, and each
    was re-deriving the instrument partition from scratch.

    The forward model is still the vendored ``simulate_rv_keplerian`` -- only the
    bookkeeping around it is hoisted, so the objective the fitter minimises stays
    exactly the quantity the grader will recompute.
    """
    times = np.asarray(times_days, dtype=float)
    rvs = np.asarray(rvs_ms, dtype=float)
    sigmas = np.asarray(sigmas_ms, dtype=float)
    inst = np.asarray(instruments)
    star_mass = float(star_mass_sun)

    var = sigmas**2 + float(sigma_jitter_ms) ** 2 + 1e-12
    inv_sigma = 1.0 / np.sqrt(var)
    weights = 1.0 / var
    # Precomputed partition: (mask, weights[mask], sum weights[mask]) per instrument.
    masks = [
        (inst == label, weights[inst == label], float(np.sum(weights[inst == label])))
        for label in np.unique(inst)
    ]

    def residuals(planets: list[PlanetParams]) -> np.ndarray:
        signal = (
            simulate_rv_keplerian(planets, times, star_mass, gamma_ms=0.0)
            if planets
            else np.zeros(times.shape, dtype=float)
        )
        resid = rvs - signal
        for mask, w_masked, w_sum in masks:
            resid[mask] -= float(np.sum(w_masked * resid[mask]) / w_sum)
        return resid * inv_sigma

    return residuals


def planets_to_submission_dicts(planets: list[PlanetParams]) -> list[dict[str, float]]:
    """Serialise fitted planets into the submission schema, longest period last.

    Sorted by period so that repeated fits of the same system produce the same
    ordering -- which is what lets the perseveration detector recognise "the
    same wrong answer submitted again" instead of being fooled by a permutation.
    """
    ordered = sorted(planets, key=lambda p: float(p.P_days))
    return [
        {
            "P_days": float(p.P_days),
            "m_sin_i_mjup": float(p.m_sin_i_mjup),
            "e": float(p.e),
            "inc_rad": float(p.inc_rad),
            "Omega_rad": float(p.Omega_rad),
            "omega_rad": float(p.omega_rad),
            "l_rad": float(p.l_rad),
        }
        for p in ordered
    ]
