"""Periodogram tool: which periods are present in the RV data.

Implements the generalised Lomb-Scargle (Zechmeister & Kurster 2009, A&A 496,
577), i.e. Lomb-Scargle with per-point weights and a floating mean. Plain
Lomb-Scargle assumes the mean is known and all points equally good; RV data has
heteroscedastic errors and an unknown systemic velocity, so the plain version
biases both the power and the peak location. Implemented here in ~40 lines of
numpy rather than pulled from astropy, to avoid adding a dependency for one
function.

What this tool must NOT do
--------------------------
It reports; it does not interpret. Every real period also produces spurious
peaks -- at the sampling frequency's beat periods (typically near 1 day for
nightly observations), at harmonics P/2 and 2P, and at the observing baseline.
Mistaking one for a planet is *alias convergence*, the most-documented failure
in Stargazer, and it is one of the failure modes this project exists to detect.
So the tool returns the peaks, the spectral window, and the arithmetic alias
family, and stops. Whether the agent reasons correctly about them is the
measurement, and pre-digesting it into "warning: peak 2 is probably an alias"
would delete the phenomenon we are trying to observe.

Returning the spectral window is not a hint, it is standard practice: no
astronomer reads an RV periodogram without it, and withholding it would make the
task harder than the science, not more faithful to it.

Note this tool deliberately omits an ``ok`` key. The no-progress bound counts
verifier rejections, and a periodogram is exploration, not an attempt -- so its
result must read as "not a verification step" (see
``free_routing.make_key_progress_verdict``). Only ``rv_fit`` and the submission
tool report ``ok``.
"""

from __future__ import annotations

from typing import Any

import numpy as np

# Frequency-grid defaults. OVERSAMPLE controls how finely the grid resolves each
# independent frequency (1/baseline); 10 is the usual compromise between peak
# localisation and cost.
OVERSAMPLE = 10.0
DEFAULT_MIN_PERIOD_DAYS = 0.5
# Beyond ~2x the baseline a "period" is unconstrained -- the data cannot see a
# full cycle, so power there reflects a trend, not a detection.
BASELINE_PERIOD_FACTOR = 2.0
MAX_GRID_POINTS = 200_000
_CHUNK = 2048


def gls_power(
    times_days: np.ndarray,
    rvs_ms: np.ndarray,
    sigmas_ms: np.ndarray,
    frequencies: np.ndarray,
) -> np.ndarray:
    """Generalised Lomb-Scargle normalised power in [0, 1], per frequency.

    Vectorised over frequencies in chunks to bound peak memory at large grids.
    Follows Zechmeister & Kurster (2009) eqs. 5-15 with weights w_i proportional
    to 1/sigma_i^2, normalised to sum to one.
    """
    t = np.asarray(times_days, dtype=float)
    y = np.asarray(rvs_ms, dtype=float)
    dy = np.asarray(sigmas_ms, dtype=float)
    freqs = np.asarray(frequencies, dtype=float)

    w = 1.0 / (dy**2 + 1e-12)
    w = w / np.sum(w)
    Y = float(np.sum(w * y))
    YY = float(np.sum(w * y * y)) - Y * Y
    if YY <= 0.0:  # constant data: no power anywhere
        return np.zeros(freqs.shape, dtype=float)

    power = np.empty(freqs.shape, dtype=float)
    for start in range(0, freqs.size, _CHUNK):
        block = freqs[start : start + _CHUNK]
        phase = 2.0 * np.pi * block[:, None] * t[None, :]
        cos_t, sin_t = np.cos(phase), np.sin(phase)

        C = cos_t @ w
        S = sin_t @ w
        YC = (cos_t @ (w * y)) - Y * C
        YS = (sin_t @ (w * y)) - Y * S
        CC = (cos_t**2 @ w) - C * C
        SS = (sin_t**2 @ w) - S * S
        CS = ((cos_t * sin_t) @ w) - C * S

        D = CC * SS - CS * CS
        with np.errstate(divide="ignore", invalid="ignore"):
            p = (SS * YC**2 + CC * YS**2 - 2.0 * CS * YC * YS) / (YY * D)
        power[start : start + block.size] = np.where(np.isfinite(p) & (D > 0), p, 0.0)

    return np.clip(power, 0.0, 1.0)


def spectral_window_power(times_days: np.ndarray, frequencies: np.ndarray) -> np.ndarray:
    """Normalised spectral window |sum exp(-2 pi i f t)|^2 / N^2, per frequency.

    Peaks here are properties of WHEN the star was observed, not of the star. A
    periodogram peak coinciding with a window peak is the classic alias trap.
    """
    t = np.asarray(times_days, dtype=float)
    freqs = np.asarray(frequencies, dtype=float)
    n = t.size
    out = np.empty(freqs.shape, dtype=float)
    for start in range(0, freqs.size, _CHUNK):
        block = freqs[start : start + _CHUNK]
        phase = 2.0 * np.pi * block[:, None] * t[None, :]
        real = np.cos(phase).sum(axis=1)
        imag = np.sin(phase).sum(axis=1)
        out[start : start + block.size] = (real**2 + imag**2) / (n * n)
    return out


def frequency_grid(
    times_days: np.ndarray,
    *,
    min_period_days: float = DEFAULT_MIN_PERIOD_DAYS,
    max_period_days: float | None = None,
    oversample: float = OVERSAMPLE,
) -> np.ndarray:
    """Uniform-in-frequency grid spanning the periods the data can constrain."""
    t = np.asarray(times_days, dtype=float)
    baseline = float(t.max() - t.min()) if t.size > 1 else 1.0
    if max_period_days is None:
        max_period_days = BASELINE_PERIOD_FACTOR * baseline
    f_min = 1.0 / float(max_period_days)
    f_max = 1.0 / float(min_period_days)
    if f_max <= f_min:
        raise ValueError("min_period_days must be shorter than max_period_days")
    df = 1.0 / (oversample * baseline) if baseline > 0 else (f_max - f_min) / 1000.0
    n = int(min(np.ceil((f_max - f_min) / df) + 1, MAX_GRID_POINTS))
    return np.linspace(f_min, f_max, max(n, 2))


def _false_alarm_probability(power: float, n_points: int, n_independent: float) -> float:
    """Approximate FAP for a GLS peak (Horne & Baliunas style, Baluev-adjacent).

    Analytic and approximate, and labelled as such where the agent sees it:
    correlated stellar activity makes the true FAP worse than this. It is here
    to give the agent a sense of scale, not a decision rule -- the actual
    detection gate is the evaluator's delta-BIC criterion.
    """
    if n_points <= 3:
        return 1.0
    p = float(np.clip(power, 0.0, 1.0 - 1e-15))
    single = (1.0 - p) ** ((n_points - 3) / 2.0)
    return float(np.clip(1.0 - (1.0 - single) ** max(n_independent, 1.0), 0.0, 1.0))


def find_peaks(
    periods_days: np.ndarray,
    power: np.ndarray,
    *,
    top_k: int,
    min_separation_frac: float = 0.05,
) -> list[int]:
    """Indices of the top local maxima, thinned so peaks are distinct in period.

    Without the separation filter the top-k would be several grid points on the
    shoulders of a single peak, which would let the agent "find three planets"
    that are one planet sampled thrice.
    """
    if power.size < 3:
        return list(np.argsort(power)[::-1][:top_k])
    is_local_max = np.zeros(power.shape, dtype=bool)
    is_local_max[1:-1] = (power[1:-1] >= power[:-2]) & (power[1:-1] >= power[2:])
    candidates = np.flatnonzero(is_local_max)
    candidates = candidates[np.argsort(power[candidates])[::-1]]

    chosen: list[int] = []
    for idx in candidates:
        period = periods_days[idx]
        if all(
            abs(period - periods_days[j]) > min_separation_frac * min(period, periods_days[j])
            for j in chosen
        ):
            chosen.append(int(idx))
        if len(chosen) >= top_k:
            break
    return chosen


def alias_family(period_days: float, baseline_days: float) -> dict[str, float]:
    """The arithmetic relatives of a period that commonly masquerade as planets.

    Beat periods against a 1-day sampling rhythm (nightly cadence), the first
    harmonic and subharmonic, and the baseline itself. Pure arithmetic, no
    judgement -- the same list the alias-convergence detector will later use to
    decide whether a claimed period is a relative of a true one.
    """
    P = float(period_days)
    out: dict[str, float] = {"half": P / 2.0, "double": P * 2.0}
    f = 1.0 / P
    for label, beat_f in (("beat_1d_minus", f - 1.0), ("beat_1d_plus", f + 1.0)):
        if abs(beat_f) > 1e-9:
            candidate = abs(1.0 / beat_f)
            if candidate <= BASELINE_PERIOD_FACTOR * baseline_days:
                out[label] = candidate
    out["baseline"] = float(baseline_days)
    return out


class RvPeriodogram:
    """Periodogram tool bound to one task's observations.

    Holds only the agent-visible ``AstroTask``: no ground truth reaches this
    class, so it cannot leak an answer even by accident.
    """

    def __init__(self, task: Any) -> None:
        obs = task.observation
        self.task_id = str(task.task_id)
        self.times = np.asarray(obs.times_days, dtype=float)
        self.rvs = np.asarray(obs.rvs_ms, dtype=float)
        self.sigmas = np.asarray(obs.sigmas_ms, dtype=float)
        self.instruments = np.asarray(obs.instruments)
        self.baseline_days = float(obs.baseline_days)

    def compute(
        self,
        values_ms: np.ndarray | None = None,
        *,
        min_period_days: float = DEFAULT_MIN_PERIOD_DAYS,
        max_period_days: float | None = None,
        top_k: int = 5,
    ) -> dict[str, Any]:
        """Periodogram of ``values_ms`` (default: the observed RVs).

        ``values_ms`` lets ``rv_residual`` reuse this machinery on residuals
        without duplicating the grid logic or the peak thinning.
        """
        y = self.rvs if values_ms is None else np.asarray(values_ms, dtype=float)
        freqs = frequency_grid(
            self.times,
            min_period_days=min_period_days,
            max_period_days=max_period_days,
            oversample=OVERSAMPLE,
        )
        periods = 1.0 / freqs
        power = gls_power(self.times, y, self.sigmas, freqs)
        window = spectral_window_power(self.times, freqs)

        n_independent = max(
            (freqs[-1] - freqs[0]) * self.baseline_days if self.baseline_days > 0 else 1.0, 1.0
        )
        peak_idx = find_peaks(periods, power, top_k=top_k)
        peaks = [
            {
                "rank": rank + 1,
                "period_days": float(periods[i]),
                "power": float(power[i]),
                "false_alarm_probability_approx": _false_alarm_probability(
                    float(power[i]), int(y.size), n_independent
                ),
                "spectral_window_power_here": float(window[i]),
                "alias_family_days": alias_family(float(periods[i]), self.baseline_days),
            }
            for rank, i in enumerate(peak_idx)
        ]

        window_idx = find_peaks(periods, window, top_k=3)
        return {
            "task_id": self.task_id,
            "n_points": int(y.size),
            "baseline_days": self.baseline_days,
            "searched_period_range_days": [float(periods.min()), float(periods.max())],
            "n_frequencies": int(freqs.size),
            "peaks": peaks,
            "spectral_window_peaks_days": [float(periods[i]) for i in window_idx],
            "notes": (
                "Generalised Lomb-Scargle with per-point weights and floating mean. "
                "false_alarm_probability_approx assumes white noise and is optimistic "
                "if the star is active. spectral_window_peaks_days are properties of the "
                "observing cadence, not of the star."
            ),
        }

    def as_tool(self):
        """Return the closure to register with AG2.

        Docstring and annotations become the schema the LLM sees, so they are
        written for the agent, not for us.
        """

        def rv_periodogram(
            min_period_days: float = DEFAULT_MIN_PERIOD_DAYS,
            max_period_days: float | None = None,
            top_k: int = 5,
        ) -> dict[str, Any]:
            """Find candidate orbital periods in the radial-velocity data.

            Returns the strongest periodogram peaks with their power and an
            approximate false-alarm probability, plus the spectral window peaks
            (periods produced by the observing cadence itself, not by planets)
            and, for each peak, its arithmetic alias relatives.

            Args:
                min_period_days: shortest period to search.
                max_period_days: longest period to search; defaults to twice the
                    observing baseline, beyond which a period is unconstrained.
                top_k: how many distinct peaks to return.
            """
            return self.compute(
                min_period_days=min_period_days,
                max_period_days=max_period_days,
                top_k=top_k,
            )

        return rv_periodogram
