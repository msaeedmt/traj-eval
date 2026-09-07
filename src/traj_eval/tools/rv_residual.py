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

Like ``rv_periodogram``, this tool deliberately omits an ``ok`` key -- including
on the error path. Inspecting residuals is exploration, not a verification
attempt, so it must not count toward the controller's no-progress bound, and a
malformed call is still not an attempt at anything.

The scatter is reported in units of the reported uncertainties as well as m/s,
because the evaluator's RMS criterion is ``rms <= 1.5 * median sigma`` -- a
residual scatter of 3 m/s means nothing until you know whether sigma is 0.5 or 5.

Input validation
----------------
Earlier this tool did no validation: it called ``float(p["P_days"])`` directly,
so a planet dict with the wrong field name raised a bare ``KeyError`` that ag2
surfaced to the agent as the single word ``Error: 'P_days'``. On seed13_diff10 a
planner passed ``period_days`` -- a plausible guess, since the tool's docstring
named no fields -- received that message four times, learned nothing from it, and
was killed by the repeat bound.

That is a tool defect being recorded as agent perseveration, which corrupts the
failure taxonomy: the agent was not being stubborn, it was given nothing to act
on. So the tool now validates its input and returns an error that names the
offending field, lists the expected ones, and recognises common wrong names --
and the docstring lists the fields so the schema the model sees is explicit.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from traj_eval.tools.rv_model import fit_quality, full_model, to_planet_params
from traj_eval.tools.rv_periodogram import DEFAULT_MIN_PERIOD_DAYS, RvPeriodogram

# The evaluator's own RMS gate: rms <= RMS_FACTOR * median sigma.
RMS_FACTOR = 1.5

# The submission schema. Only P_days is strictly required -- the rest default,
# exactly as in the evaluator -- but all are named here so the error message and
# the tool docstring can state them.
REQUIRED_PLANET_FIELDS = ("P_days",)
OPTIONAL_PLANET_FIELDS = ("m_sin_i_mjup", "e", "inc_rad", "Omega_rad", "omega_rad", "l_rad")
ALL_PLANET_FIELDS = REQUIRED_PLANET_FIELDS + OPTIONAL_PLANET_FIELDS

# Plausible wrong names, mapped to the right one. An agent that guesses a
# reasonable synonym should be told the actual name rather than left to guess
# again; every entry here was either observed in a trace or is an obvious
# near-miss for one that was.
FIELD_ALIASES = {
    "period_days": "P_days",
    "period": "P_days",
    "p_days": "P_days",
    "P": "P_days",
    "mass": "m_sin_i_mjup",
    "m_sin_i": "m_sin_i_mjup",
    "msini": "m_sin_i_mjup",
    "mass_mjup": "m_sin_i_mjup",
    "ecc": "e",
    "eccentricity": "e",
    "omega": "omega_rad",
    "arg_periastron": "omega_rad",
    "l": "l_rad",
    "lambda": "l_rad",
    "mean_longitude": "l_rad",
    "inc": "inc_rad",
    "inclination": "inc_rad",
}


class PlanetShapeError(ValueError):
    """A planets argument the tool cannot use, with an actionable message."""


def validate_planets(planets: Any) -> list[dict[str, Any]]:
    """Check the planets argument, raising a message the agent can act on.

    Returns the list unchanged when it is usable. The messages name the offending
    index and field and, where the agent used a recognisable synonym, the correct
    name -- because an error an agent cannot act on produces a repeat, not a fix.
    """
    if planets is None:
        return []
    if not isinstance(planets, list):
        raise PlanetShapeError(
            f"'planets' must be a list of planet dicts, got {type(planets).__name__}. "
            f"Pass the 'planets' list from rv_fit unchanged, or [] for the raw data."
        )
    for i, planet in enumerate(planets):
        if not isinstance(planet, dict):
            raise PlanetShapeError(
                f"planets[{i}] must be a dict with fields {list(ALL_PLANET_FIELDS)}, "
                f"got {type(planet).__name__}."
            )
        for required in REQUIRED_PLANET_FIELDS:
            if required in planet:
                continue
            alias = next((k for k in planet if FIELD_ALIASES.get(k) == required), None)
            hint = (
                f" You passed {alias!r}; the field is {required!r}."
                if alias
                else f" Got keys {sorted(planet)}."
            )
            raise PlanetShapeError(
                f"planets[{i}] is missing {required!r}.{hint} "
                f"Expected fields: {list(ALL_PLANET_FIELDS)} "
                f"(only {list(REQUIRED_PLANET_FIELDS)} required)."
            )
        for key, value in planet.items():
            if key in ALL_PLANET_FIELDS and not isinstance(value, int | float):
                raise PlanetShapeError(
                    f"planets[{i}][{key!r}] must be a number, got " f"{type(value).__name__}."
                )
    return planets


def _shape_error_payload(exc: PlanetShapeError, task_id: str) -> dict[str, Any]:
    """The error dict handed back to the agent.

    Deliberately carries NO ``ok`` key: a malformed exploratory call is still not
    a verification attempt, so it must not count toward the no-progress bound.
    """
    return {
        "task_id": task_id,
        "error": str(exc),
        "expected_fields": list(ALL_PLANET_FIELDS),
        "required_fields": list(REQUIRED_PLANET_FIELDS),
        "hint": (
            "Pass the 'planets' list returned by rv_fit unchanged. To analyse the "
            "raw data with no planets removed, pass [] or omit the argument."
        ),
    }


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
        """Residuals after removing ``planets`` (empty list = the raw data).

        Raises ``PlanetShapeError`` on a malformed argument; the tool closure
        converts that into a structured error rather than letting it escape as a
        bare exception.
        """
        planet_list = to_planet_params(validate_planets(planets) or [])
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
                planets: the planets to remove, as returned by rv_fit. Each is a
                    dict with the field P_days (required) and optionally
                    m_sin_i_mjup, e, inc_rad, Omega_rad, omega_rad, l_rad. Use
                    these exact names. Pass [] or omit to analyse the raw data.
                sigma_jitter_ms: extra white noise in m/s to add in quadrature
                    to the reported uncertainties.
                top_k: how many residual periodogram peaks to return.
            """
            try:
                return self.analyse(planets, sigma_jitter_ms=sigma_jitter_ms, top_k=top_k)
            except PlanetShapeError as exc:
                return _shape_error_payload(exc, self.task_id)
            except (KeyError, TypeError, ValueError) as exc:
                # Anything the validator did not anticipate still reaches the
                # agent as a readable message rather than a bare exception.
                return _shape_error_payload(
                    PlanetShapeError(
                        f"could not use the supplied planets: " f"{type(exc).__name__}: {exc}"
                    ),
                    self.task_id,
                )

        return rv_residual
