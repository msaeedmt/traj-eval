"""Stargazer's four-criterion conjunction gate, plus the split this study needs.

Pure Python: consumes the dict ``evaluate_submission`` returns and applies the
pass/fail logic itself, so this module and its tests run without Stargazer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_MIN_DELTA_BIC_PER_POINT = 0.0
DEFAULT_MAX_RMS_FACTOR = 1.5

# Stargazer's match threshold. It is a TOLERANCE, not an exactness requirement:
# the grader scores exp(-d) with
#     d = 4.0*rv_curve + 1.0*|dlnP| + 0.5*|dlnK| + 0.5*|de|
# so 0.80 means d <= 0.223, and because rv_curve carries weight 4 and dominates
# the sum (84% of it on a representative task), the real requirement is that the
# predicted RV curve trace the true one to within ~5.6% of its semi-amplitude.
#
# That is strict enough to be unreachable on many tasks: the maximum-likelihood
# fit -- the best any fitting procedure can produce -- scores below 0.80 on 64%
# of the synthetic bank, because with finite data the likelihood peak sits
# further from the truth than 5.6% of K. See metrics/astro/ceiling.py.
#
# Since d is LINEAR in the weights, widening every parameter tolerance by a
# factor m is exactly equivalent to lowering the threshold to 0.8**m:
#
#     threshold   tolerance   curve agreement   ML-reachable tasks
#       0.80         1x            5.6%               36 / 100
#       0.64         2x           11.2%               46 / 100
#       0.51         3x           16.7%               56 / 100
#       0.41         4x           22.3%               65 / 100
#
# The default stays at Stargazer's value so nothing changes silently. Pass
# ``min_match_score`` to relax it, and record the value used in the trial meta so
# a result is never ambiguous about which gate produced it.
DEFAULT_MIN_MATCH_SCORE = 0.8


def threshold_for_tolerance(multiplier: float) -> float:
    """The match threshold equivalent to widening every tolerance ``multiplier``x.

    ``d`` is linear in the parameter weights, so scaling them all by 1/m scales
    the distance by 1/m, and ``exp(-d/m) >= T`` becomes ``exp(-d) >= T**m``.
    """
    if multiplier <= 0.0:
        raise ValueError(f"tolerance multiplier must be > 0, got {multiplier}")
    return float(DEFAULT_MIN_MATCH_SCORE**multiplier)


def _hint_float(hints: dict[str, Any] | None, key: str) -> float | None:
    if not isinstance(hints, dict):
        return None
    raw = hints.get(key)
    if raw is None:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if val != val or val in (float("inf"), float("-inf")):
        return None
    return val


@dataclass(frozen=True)
class AstroCriteria:
    ok_delta_bic: bool
    ok_rms: bool
    ok_match: bool
    ok_count: bool
    delta_bic_per_point: float | None
    rms_ms: float | None
    match_score: float | None
    count_term: float | None
    max_rms_ms: float
    min_match_score: float
    min_delta_bic_per_point: float
    median_sigma_ms: float

    @property
    def statistical_pass(self) -> bool:
        return self.ok_delta_bic and self.ok_rms

    @property
    def physical_pass(self) -> bool:
        return self.ok_match and self.ok_count

    @property
    def solved(self) -> bool:
        return self.statistical_pass and self.physical_pass

    @property
    def stat_phys_gap(self) -> bool:
        return self.statistical_pass and not self.physical_pass

    def failed_criteria(self) -> list[str]:
        checks = (
            ("ok_delta_bic", self.ok_delta_bic),
            ("ok_rms", self.ok_rms),
            ("ok_match", self.ok_match),
            ("ok_count", self.ok_count),
        )
        return [name for name, ok in checks if not ok]

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok_delta_bic": self.ok_delta_bic,
            "ok_rms": self.ok_rms,
            "ok_match": self.ok_match,
            "ok_count": self.ok_count,
            "statistical_pass": self.statistical_pass,
            "physical_pass": self.physical_pass,
            "solved": self.solved,
            "delta_bic_per_point": self.delta_bic_per_point,
            "rms_ms": self.rms_ms,
            "match_score": self.match_score,
            "count_term": self.count_term,
            "max_rms_ms": self.max_rms_ms,
            "min_match_score": self.min_match_score,
            "median_sigma_ms": self.median_sigma_ms,
        }


def evaluate_criteria(
    info: dict[str, Any],
    *,
    median_sigma_ms: float,
    hints: dict[str, Any] | None = None,
    min_match_score: float | None = None,
) -> AstroCriteria:
    """Apply the four-criterion gate.

    Precedence for the match threshold, strictest source last:
    ``min_match_score`` argument -> the task's ``hints.target_match_score``
    -> ``DEFAULT_MIN_MATCH_SCORE``. The explicit argument wins because it is the
    experiment's choice, whereas the hint is a property of the task; a run that
    deliberately relaxes the gate should relax it everywhere.
    """
    components = info.get("components") or {}
    residuals = info.get("residuals") or {}
    if not isinstance(components, dict):
        components = {}
    if not isinstance(residuals, dict):
        residuals = {}
    delta_bic_pp = components.get("delta_bic")
    rms = residuals.get("rms")
    match_score = components.get("match")
    count_term = components.get("count")

    rms_hint = _hint_float(hints, "max_rms_ms")
    max_rms_ms = (
        rms_hint
        if (rms_hint is not None and rms_hint > 0.0)
        else DEFAULT_MAX_RMS_FACTOR * float(median_sigma_ms)
    )
    if min_match_score is not None:
        min_match = float(min_match_score)
    else:
        match_hint = _hint_float(hints, "target_match_score")
        min_match = (
            match_hint
            if (match_hint is not None and match_hint >= 0.0)
            else DEFAULT_MIN_MATCH_SCORE
        )
    ok_delta_bic = (
        delta_bic_pp is not None and float(delta_bic_pp) > DEFAULT_MIN_DELTA_BIC_PER_POINT
    )
    ok_rms = rms is not None and float(rms) <= max_rms_ms
    ok_match = match_score is not None and float(match_score) >= min_match
    ok_count = count_term is not None and float(count_term) == 0.0
    return AstroCriteria(
        ok_delta_bic=bool(ok_delta_bic),
        ok_rms=bool(ok_rms),
        ok_match=bool(ok_match),
        ok_count=bool(ok_count),
        delta_bic_per_point=float(delta_bic_pp) if delta_bic_pp is not None else None,
        rms_ms=float(rms) if rms is not None else None,
        match_score=float(match_score) if match_score is not None else None,
        count_term=float(count_term) if count_term is not None else None,
        max_rms_ms=float(max_rms_ms),
        min_match_score=float(min_match),
        min_delta_bic_per_point=float(DEFAULT_MIN_DELTA_BIC_PER_POINT),
        median_sigma_ms=float(median_sigma_ms),
    )


def best_criteria(candidates: list[AstroCriteria]) -> AstroCriteria | None:
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda c: (
            c.solved,
            c.physical_pass,
            c.statistical_pass,
            c.match_score if c.match_score is not None else float("-inf"),
        ),
    )
