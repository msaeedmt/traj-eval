"""Synthetic RV tasks with known truth, for testing the astro tools.

Built locally rather than loaded from ``dataset/Astro/`` so these tests run in a
bare checkout with no prepared task bank -- the same reason the criteria tests
avoid importing anything heavy. The data is generated through the VENDORED
forward model, so a tool that recovers the injected parameters is agreeing with
the same physics the evaluator will use.
"""

from __future__ import annotations

import types
from typing import Any

import numpy as np
import pytest

from traj_eval.tools.rv_model import planet_signal, to_planet_params

TIER_BUDGETS = {"easy": 3, "medium": 5, "hard": 10}


def make_task(
    planet_specs: list[dict[str, float]],
    *,
    n_obs: int = 140,
    span_days: float = 400.0,
    noise_ms: float = 1.5,
    seed: int = 5,
    star_mass_sun: float = 1.0,
    gamma_ms: float = 20.0,
    tier: str = "medium",
    instruments: list[str] | None = None,
) -> tuple[Any, Any]:
    """Return (AstroTask-like, AstroTruth-like) for an injected planetary system.

    Duck-typed stand-ins rather than the real dataclasses: the tools only read
    ``task.observation.*`` and ``truth.planets``, so this keeps the tool tests
    independent of the dataset layer.
    """
    rng = np.random.default_rng(seed)
    planets = to_planet_params(planet_specs)
    times = np.sort(rng.uniform(0.0, span_days, n_obs))
    sigmas = np.full(n_obs, noise_ms)
    inst = instruments if instruments is not None else ["instA"] * n_obs
    rvs = planet_signal(planets, times, star_mass_sun) + gamma_ms
    rvs = rvs + rng.normal(0.0, noise_ms, n_obs)

    observation = types.SimpleNamespace(
        times_days=times.tolist(),
        rvs_ms=rvs.tolist(),
        sigmas_ms=sigmas.tolist(),
        instruments=list(inst),
        star_mass_sun=float(star_mass_sun),
        n_obs=n_obs,
        baseline_days=float(times.max() - times.min()),
        median_sigma_ms=float(np.median(sigmas)),
        instrument_labels=sorted(set(inst)),
        task_description=None,
        hints={},
        reference=None,
    )
    task = types.SimpleNamespace(
        task_id="synthetic_fixture",
        kind="synthetic",
        difficulty=4,
        tier=tier,
        observation=observation,
        max_submissions=TIER_BUDGETS[tier],
    )
    truth = types.SimpleNamespace(
        task_id="synthetic_fixture",
        planets=planets,
        star_mass_sun=float(star_mass_sun),
        difficulty_details={},
        meta={},
    )
    return task, truth


ONE_PLANET = [{"P_days": 12.345, "m_sin_i_mjup": 0.6, "e": 0.12, "omega_rad": 1.0, "l_rad": 2.0}]
TWO_PLANETS = [
    {"P_days": 11.2, "m_sin_i_mjup": 0.5, "e": 0.05, "omega_rad": 0.7, "l_rad": 1.2},
    {"P_days": 57.9, "m_sin_i_mjup": 1.4, "e": 0.22, "omega_rad": 2.4, "l_rad": 4.8},
]


# Session-scoped: building a task is pure, and a Keplerian fit costs seconds --
# re-fitting the same injected system in a dozen tests would dominate the suite.
# Anything with mutable state (RvSubmit's attempt budget) is deliberately NOT
# cached here; those tests construct their own.


@pytest.fixture(scope="session")
def one_planet_task():
    return make_task(ONE_PLANET, n_obs=110, span_days=300.0, seed=3)


@pytest.fixture(scope="session")
def two_planet_task():
    return make_task(TWO_PLANETS, n_obs=110, tier="easy")


@pytest.fixture(scope="session")
def two_planet_correct_fit(two_planet_task):
    """The correct two-planet fit, computed once and shared.

    Used as the reference every alias and format-fragility test compares against.
    """
    from traj_eval.tools.rv_fit import RvFit

    task, _ = two_planet_task
    return RvFit(task).fit([11.2, 57.9])
