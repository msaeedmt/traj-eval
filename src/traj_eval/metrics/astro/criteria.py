"""Stargazer's four-criterion conjunction gate, plus the split this study needs.

Deliberately PURE Python: it consumes the dict that
``stargazer.evaluator.evaluate_submission`` already returned and applies the
pass/fail logic itself. No Stargazer import, no numpy-on-tasks, no rebound --
so this module and its tests run in bare CI, mirroring the Group A / Group B
split already used for Lean (``metrics/lean/validator.py``). The thin
stargazer-importing wrapper lives in ``metrics/astro/evaluate.py``.

The logic is a faithful re-implementation of ``stargazer.env.RvEnv
._evaluate_success`` for ``submission_mode='params_and_model'``. Re-implementing
rather than calling it is deliberate: ``RvEnv`` also owns episode bookkeeping
(``max_steps``, ``done``) and emits a hard-coded non-English hint string, none of
which belongs in a multi-agent controller. The four thresholds themselves are
reproduced exactly, and ``test_criteria.py`` pins them.

Two details that are easy to get wrong and both matter on the real-data tasks:

  * The thresholds are OVERRIDABLE PER TASK via ``meta.hints``. A task carrying
    ``hints.max_rms_ms`` (> 0) replaces ``1.5 * median_sigma``, and
    ``hints.target_match_score`` (>= 0) replaces the 0.8 match threshold. Miss
    this and every ``real_*`` task is graded against the wrong gate.
  * ``components['match']`` ALREADY includes the ``-0.25 * |n_truth - n_guess|``
    count penalty (see ``evaluator.parameter_matching_score``). So ok_match and
    ok_count are not independent: a wrong count depresses the match score too.
    Worth remembering when reading a criterion breakdown.

The study-specific addition is the statistical/physical decomposition. In Lean,
``silent_failure`` means "the team declared success and the in-loop compiler was
happy, but the independent validator rejects it" -- there are two separate
oracles. Astro has only one oracle: the in-loop ``submit_action`` and our
out-of-loop validator both call the same ``evaluate_submission``, so that gap is
identically zero and the Lean definition does not transfer.

What replaces it is the dissociation Stargazer itself documents (§4.1, "good
statistics != good physics"):

    statistical_pass = ok_delta_bic AND ok_rms      (does the model fit?)
    physical_pass    = ok_match     AND ok_count    (is it the right system?)
    silent_failure   = declared_success AND statistical_pass AND NOT physical_pass

i.e. a trial whose final artefact clears the statistical gate while violating
the physical one -- the operational definition given in the proposal (§2.1).
``declared_success`` is supplied by the trace layer (critic APPROVE / terminal
marker), not by this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Stargazer defaults (stargazer.env.RvEnv.success_criteria).
DEFAULT_MIN_DELTA_BIC_PER_POINT = 0.0
DEFAULT_MAX_RMS_FACTOR = 1.5  # multiplied by the MEDIAN reported sigma
DEFAULT_MIN_MATCH_SCORE = 0.8


def _hint_float(hints: dict[str, Any] | None, key: str) -> float | None:
    """Read a numeric hint, tolerating absent / malformed / non-finite values."""
    if not isinstance(hints, dict):
        return None
    raw = hints.get(key)
    if raw is None:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    # Reject nan / inf without importing numpy (val != val catches nan).
    if val != val or val in (float("inf"), float("-inf")):
        return None
    return val


@dataclass(frozen=True)
class AstroCriteria:
    """The four criteria plus the thresholds they were judged against.

    Thresholds are carried alongside the verdicts so a logged trial is
    self-describing: reading a trace later never requires re-deriving which gate
    a real-data task was held to.
    """

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

    # ---- conjunctions -------------------------------------------------

    @property
    def statistical_pass(self) -> bool:
        """Does the submitted model fit the data? (delta-BIC and RMS)"""
        return self.ok_delta_bic and self.ok_rms

    @property
    def physical_pass(self) -> bool:
        """Does it recover the right physical system? (match and count)"""
        return self.ok_match and self.ok_count

    @property
    def solved(self) -> bool:
        """Stargazer's conjunction gate: all four simultaneously."""
        return self.statistical_pass and self.physical_pass

    @property
    def stat_phys_gap(self) -> bool:
        """The 'good statistics != good physics' signal for a single submission.

        Not yet ``silent_failure`` -- that additionally requires the team to have
        DECLARED success, which only the trace layer knows.
        """
        return self.statistical_pass and not self.physical_pass

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

    def failed_criteria(self) -> list[str]:
        """Names of the criteria that failed, in Stargazer's reporting order.

        This is what the in-loop ``submit`` tool hands back to the agent as
        per-criterion diagnostic feedback.
        """
        checks = (
            ("ok_delta_bic", self.ok_delta_bic),
            ("ok_rms", self.ok_rms),
            ("ok_match", self.ok_match),
            ("ok_count", self.ok_count),
        )
        return [name for name, ok in checks if not ok]


def evaluate_criteria(
    info: dict[str, Any],
    *,
    median_sigma_ms: float,
    hints: dict[str, Any] | None = None,
) -> AstroCriteria:
    """Apply the four-criterion gate to an ``evaluate_submission`` info dict.

    ``info`` is the second element of the ``(reward, info)`` tuple returned by
    ``stargazer.evaluator.evaluate_submission`` in ``params_and_model`` mode.
    ``median_sigma_ms`` comes from the task's own sigmas (see
    ``AstroObservation.median_sigma_ms``) -- the RMS threshold is the only one
    that adapts to data quality, so it must be the task's median, not the
    residuals'.
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

    # RMS threshold: per-task hint wins over 1.5 * median sigma.
    rms_hint = _hint_float(hints, "max_rms_ms")
    max_rms_ms = (
        rms_hint
        if (rms_hint is not None and rms_hint > 0.0)
        else DEFAULT_MAX_RMS_FACTOR * float(median_sigma_ms)
    )

    # Match threshold: per-task hint wins over 0.8.
    match_hint = _hint_float(hints, "target_match_score")
    min_match = (
        match_hint if (match_hint is not None and match_hint >= 0.0) else DEFAULT_MIN_MATCH_SCORE
    )

    ok_delta_bic = (
        delta_bic_pp is not None and float(delta_bic_pp) > DEFAULT_MIN_DELTA_BIC_PER_POINT
    )
    ok_rms = rms is not None and float(rms) <= max_rms_ms
    ok_match = match_score is not None and float(match_score) >= min_match
    # count_term is -|n_truth - n_guess|; exactly 0.0 means the counts agree.
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
    """Pick the episode's scoring submission, Stargazer-style.

    Stargazer counts only the BEST submission of an episode toward the score, so
    any per-trial number we report has to use the same rule or it will not line
    up with the published pass rates (Table 1). 'Best' is ordered by: all four
    criteria, then physical pass, then statistical pass, then match score. This
    ordering is a choice, not something upstream specifies -- it is pinned here
    (and in tests) so every report uses one definition.
    """
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
