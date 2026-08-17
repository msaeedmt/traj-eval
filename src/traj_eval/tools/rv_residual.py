"""Residual tool: what is left after a fit, and is another planet hiding in it.

Subtract the fitted planets from the data and look at the remainder. If it is
consistent with noise, the model is complete; if a coherent period survives,
there is a planet still to find. This iterative subtract-and-look-again loop is
the entire mechanism by which multi-planet systems get discovered, so without
this tool an agent has no principled way to decide how many planets to fit.

Why this tool matters to the measurement
----------------------------------------
The decision *"the leftovers look like noise, I'll stop here"* is where count
failures are born, and it is exactly the sort of decision that is invisible in a
final answer but checkable in a trajectory. Every call here is an anchor site:
we can independently recompute whether real signal remained at the moment the
agent chose to stop escalating, which is what turns "the agent under-counted
planets" from a post-hoc observation into an attributable event.

Like ``rv_periodogram``, this tool deliberately omits an ``ok`` key: inspecting
residuals is exploration, not a verification attempt, so it must not count
toward the controller's no-progress bound.

The scatter is reported in units of the reported uncertainties as well as m/s,
because the evaluator's RMS criterion is ``rms <= 1.5 * median sigma`` -- a
residual scatter of 3 m/s means nothing until you know whether sigma is 0.5 or 5.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from traj_eval.tools.rv_model import fit_quality, full_model, to_planet_params
from traj_eval.tools.rv_periodogram import DEFAULT_MIN_PERIOD_DAYS, RvPeriodogram

# The evaluator's own RMS gate: rms <= RMS_FACTOR * median sigma.
RMS_FACTOR = 1.5


class RvResidual:
    """Residual analysis bound to one task's observations. No ground truth."""

    def __init__(self, task: Any) -> None:
        obs = task.observation
        self.task_id = str(task.task_id)
        self.times = np.asarray(obs.times_days, dtype=float)
        self.rvs = np.asarray(obs.rvs_ms, dtype=float)
        self.sigmas = np.asarray(obs.sigmas_ms, dtype=float)
        self.instruments = np.asarray(obs.instruments)
        self.star_mass_sun = float(obs.star_mass_sun)
        self.median_sigma_ms = float(obs.median_sigma_ms)
        self._periodogram = RvPeriodogram(task)

    def analyse(
        self,
        planets: list[dict[str, Any]] | None = None,
        *,
        sigma_jitter_ms: float = 0.0,
        min_period_days: float = DEFAULT_MIN_PERIOD_DAYS,
        max_period_days: float | None = None,
        top_k: int = 3,
    ) -> dict[str, Any]:
        """Residuals after removing ``planets`` (empty list = the raw data)."""
        planet_list = to_planet_params(planets or [])
        model, offsets = full_model(
            planet_list,
            self.times,
            self.rvs,
            self.sigmas,
            self.instruments,
            self.star_mass_sun,
            sigma_jitter_ms,
        )
        resid = self.rvs - model
        rms = float(np.sqrt(np.mean(resid**2))) if resid.size else 0.0
        rms_threshold = RMS_FACTOR * self.median_sigma_ms

        # Periodogram OF THE RESIDUALS: the same machinery as rv_periodogram, so
        # peak finding, thinning and the alias family stay one implementation.
        residual_pgram = self._periodogram.compute(
            values_ms=resid,
            min_period_days=min_period_days,
            max_period_days=max_period_days,
            top_k=top_k,
        )

        quality = fit_quality(
            planet_list,
            times_days=self.times,
            rvs_ms=self.rvs,
            sigmas_ms=self.sigmas,
            instruments=self.instruments,
            star_mass_sun=self.star_mass_sun,
            sigma_jitter_ms=sigma_jitter_ms,
        )

        per_instrument = {}
        for inst in np.unique(self.instruments):
            mask = self.instruments == inst
            per_instrument[str(inst)] = {
                "n_points": int(mask.sum()),
                "rms_ms": float(np.sqrt(np.mean(resid[mask] ** 2))),
                "median_sigma_ms": float(np.median(self.sigmas[mask])),
            }

        return {
            "task_id": self.task_id,
            "n_planets_removed": len(planet_list),
            "residual_rms_ms": rms,
            "residual_rms_in_sigma": float(rms / self.median_sigma_ms)
            if self.median_sigma_ms > 0
            else float("nan"),
            "rms_threshold_ms": float(rms_threshold),
            "rms_within_threshold": bool(rms <= rms_threshold),
            "residual_max_abs_ms": float(np.max(np.abs(resid))) if resid.size else 0.0,
            "gamma_per_instrument_ms": offsets,
            "per_instrument": per_instrument,
            "delta_bic_per_point": quality["delta_bic_per_point"],
            "chi2_reduced": quality["chi2_reduced"],
            "residual_periodogram": {
                "peaks": residual_pgram["peaks"],
                "spectral_window_peaks_days": residual_pgram["spectral_window_peaks_days"],
                "searched_period_range_days": residual_pgram["searched_period_range_days"],
            },
            "notes": (
                "residual_rms_in_sigma is the scatter in units of the median reported "
                f"uncertainty; the final evaluation requires it below {RMS_FACTOR}. "
                "A surviving periodogram peak may be a further planet, or an alias of "
                "one already removed, or a property of the observing cadence -- compare "
                "against spectral_window_peaks_days and the alias_family_days of the "
                "planets you have already fitted."
            ),
        }

    def as_tool(self):
        """Return the closure to register with AG2."""

        def rv_residual(
            planets: list[dict[str, Any]] | None = None,
            sigma_jitter_ms: float = 0.0,
            top_k: int = 3,
        ) -> dict[str, Any]:
            """Inspect what is left after removing a set of fitted planets.

            Returns the residual scatter (in m/s and in units of the reported
            uncertainties, with the threshold the final evaluation applies) and a
            periodogram of the residuals. Use it to decide whether your model is
            complete or another planet remains.

            Args:
                planets: the planets to remove, as returned by rv_fit. Pass an
                    empty list or omit to analyse the raw data.
                sigma_jitter_ms: extra white noise in m/s to add in quadrature
                    to the reported uncertainties.
                top_k: how many residual periodogram peaks to return.
            """
            return self.analyse(planets, sigma_jitter_ms=sigma_jitter_ms, top_k=top_k)

        return rv_residual
