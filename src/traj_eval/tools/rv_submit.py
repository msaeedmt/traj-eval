"""Submission tool: hand the final answer to the evaluator, under a budget.

Wraps ``metrics.astro.evaluate.score_submission`` and returns the per-criterion
verdict the agent needs to iterate, while enforcing the tier's attempt budget
(3 easy / 5 medium / 10 hard).

Why the budget is load-bearing
------------------------------
With unlimited attempts, resubmitting the same wrong answer costs nothing and
means nothing. Under a budget it is a visible, countable pathology -- which is
what makes *perseveration* measurable rather than anecdotal, and what gives the
critic something real to do: blocking a doomed resubmission has a cost the team
can feel. Every attempt is recorded with its criteria, so the offline detector
can later ask whether repeated attempts were refinement or repetition.

Malformed submissions are accounted separately
----------------------------------------------
A submission the evaluator cannot parse is a different failure from one it can
parse and rejects. The first is *format fragility*: the agent's science may be
fine while its serialisation is broken. So malformed attempts do NOT consume the
scoring budget (the agent gets a chance to fix its formatting rather than losing
a scientific attempt to a typo), but they are capped separately by
``max_invalid`` and counted, because an unbounded retry loop would burn the token
budget instead.

That split is OUR choice, not upstream's, and it is recorded here because it
affects comparability: an agent that would have exhausted Stargazer's budget on
malformed attempts survives longer here. The counts are in the trace, so the
effect can be reported.

What ``ok`` means here
----------------------
``ok`` reports whether the submission was ACCEPTED AND SCORED -- not whether it
passed. A rejected-but-scored answer is real progress: the agent learns which
criteria failed. Only an unparseable submission or an exhausted budget returns
``ok: false``. Note the controller's no-progress bound reads ``rv_fit``'s
verdict, not this one -- with a budget of 3 to 10 this tool could never reach a
bound of 6 anyway.

The scoring is out-of-loop truth: this is the one tool that holds ``AstroTruth``,
so it must never echo any part of it back to the agent. The returned dict carries
criteria, thresholds and the agent's own numbers -- never the true planets, never
the true count.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from traj_eval.metrics.astro.criteria import AstroCriteria, best_criteria
from traj_eval.metrics.astro.evaluate import (
    SubmissionShapeError,
    score_submission,
    validate_submission_shape,
)

DEFAULT_MAX_INVALID = 3

# Per-criterion guidance. Diagnostic only: each line names what the criterion
# measures and where to look, without hinting at the true system.
_CRITERION_HELP = {
    "ok_delta_bic": (
        "The model does not beat a flat line by enough to justify its parameters. "
        "Either the signal is not real or the model is over-parameterised."
    ),
    "ok_rms": (
        "Residual scatter exceeds 1.5x the median reported uncertainty: the model "
        "does not follow the data. Check for a missed planet or a wrong period."
    ),
    "ok_match": (
        "The orbits do not correspond to the underlying system closely enough. A "
        "good statistical fit at the wrong period, or a phase/epoch convention "
        "error in l_rad, both land here. l_rad is the mean longitude at the FIRST "
        "observation epoch, times_days[0]."
    ),
    "ok_count": "The number of planets submitted differs from the number present.",
}


@dataclass
class SubmissionAttempt:
    """One scored attempt, retained for the offline validator and detectors."""

    index: int
    planets: list[dict[str, Any]]
    criteria: AstroCriteria
    n_planets: int


@dataclass
class RvSubmit:
    """Submission tool bound to one task, its truth, and its attempt budget.

    The only astro tool holding ``AstroTruth``. Everything it returns to the
    agent is derived from the criteria, never from the truth directly.
    """

    task: Any  # AstroTask
    truth: Any  # AstroTruth
    stargazer_task: Any = None  # parsed Task, if the caller already holds it
    max_attempts: int | None = None  # defaults to the task's tier budget
    max_invalid: int = DEFAULT_MAX_INVALID
    # Experiment-level match threshold. None keeps Stargazer's 0.80 (or the
    # task's own hints.target_match_score). The runners record the value used in
    # the trial meta so offline analysis scores counterfactuals against the same
    # gate the team faced -- a relaxed run analysed at 0.80 would report
    # reachable answers the team was never offered.
    min_match_score: float | None = None

    attempts: list[SubmissionAttempt] = field(default_factory=list)
    n_invalid: int = 0

    def __post_init__(self) -> None:
        if self.max_attempts is None:
            self.max_attempts = int(self.task.max_submissions)

    # ---- state the trace and validator care about ----------------------

    @property
    def n_attempts(self) -> int:
        return len(self.attempts)

    @property
    def attempts_remaining(self) -> int:
        return max(int(self.max_attempts) - self.n_attempts, 0)

    @property
    def solved(self) -> bool:
        best = self.best()
        return bool(best and best.solved)

    def best(self) -> AstroCriteria | None:
        """The episode's scoring submission, using Stargazer's best-of rule."""
        return best_criteria([a.criteria for a in self.attempts])

    def submit(self, submission: dict[str, Any]) -> dict[str, Any]:
        """Score one submission against the evaluator, consuming an attempt."""
        if self.attempts_remaining <= 0:
            return {
                "ok": False,
                "task_id": self.task.task_id,
                "error": "submission budget exhausted",
                "attempts_used": self.n_attempts,
                "attempts_remaining": 0,
            }

        # Shape problems first: they do not consume a scoring attempt.
        try:
            warnings = validate_submission_shape(submission)
        except SubmissionShapeError as exc:
            self.n_invalid += 1
            exhausted = self.n_invalid >= self.max_invalid
            return {
                "ok": False,
                "task_id": self.task.task_id,
                "error": f"malformed submission: {exc}",
                "invalid_attempts_used": self.n_invalid,
                "invalid_attempts_remaining": max(self.max_invalid - self.n_invalid, 0),
                "attempts_used": self.n_attempts,
                "attempts_remaining": self.attempts_remaining,
                "note": (
                    "Malformed submissions do not consume a scoring attempt, but they "
                    "are capped."
                    + (
                        " You have used them all; the next must be well-formed."
                        if exhausted
                        else ""
                    )
                ),
            }

        criteria, info = score_submission(
            submission,
            task=self.task,
            truth=self.truth,
            stargazer_task=self.stargazer_task,
            min_match_score=self.min_match_score,
        )
        planets = list(submission.get("planets") or [])
        self.attempts.append(
            SubmissionAttempt(
                index=self.n_attempts + 1,
                planets=planets,
                criteria=criteria,
                n_planets=len(planets),
            )
        )

        failed = criteria.failed_criteria()
        return {
            "ok": True,
            "task_id": self.task.task_id,
            "attempt": self.n_attempts,
            "attempts_remaining": self.attempts_remaining,
            "solved": criteria.solved,
            "criteria": {
                "ok_delta_bic": criteria.ok_delta_bic,
                "ok_rms": criteria.ok_rms,
                "ok_match": criteria.ok_match,
                "ok_count": criteria.ok_count,
            },
            "failed_criteria": failed,
            "guidance": [_CRITERION_HELP[name] for name in failed],
            "measured": {
                "delta_bic_per_point": criteria.delta_bic_per_point,
                "rms_ms": criteria.rms_ms,
                "rms_threshold_ms": criteria.max_rms_ms,
                "match_score": criteria.match_score,
                "match_threshold": criteria.min_match_score,
            },
            "n_planets_submitted": len(planets),
            "gamma_per_instrument_ms": info.get("gamma_per_instrument_ms", {}),
            "shape_warnings": warnings,
            "notes": (
                "Systemic velocities are fitted per instrument by the evaluator; do not "
                "submit them. Omitted planet fields are silently defaulted, which is a "
                "common cause of a good fit scoring badly -- see shape_warnings."
            ),
        }

    def as_tool(self):
        """Return the closure to register with AG2."""

        def rv_submit(
            planets: list[dict[str, Any]], sigma_jitter_ms: float = 0.0
        ) -> dict[str, Any]:
            """Submit your final planetary system for scoring.

            Returns which of the four criteria passed (model significance,
            residual scatter, orbital agreement, planet count), the measured
            values against their thresholds, and how many attempts remain. Your
            attempts are limited, so submit when your residuals are at the noise
            level and you believe the planet count is right.

            Each planet needs P_days, m_sin_i_mjup, e, omega_rad and l_rad, where
            l_rad is the mean longitude at the first observation epoch. Do not
            include systemic velocities; they are fitted for you.

            Args:
                planets: the planetary system, as returned by rv_fit.
                sigma_jitter_ms: extra white noise in m/s to include in the
                    likelihood.
            """
            return self.submit(
                {"planets": planets, "noise": {"sigma_jitter_ms": float(sigma_jitter_ms)}}
            )

        return rv_submit
