"""Offline validator for astro trials: the out-of-loop judgement.

Runs after a trial is complete: no agent, no LLM, no network. It reads the trace,
re-derives what the team could have done, and names the ways the outcome was
worse than the trajectory warranted.

Metric groups, by what each needs:

  Group A -- pure trace analysis (no evaluator, no truth):
      tool counts, escalation/repetition statistics, rubber-stamp approval,
      over-fit signatures, unverifiable claims, submitted-vs-last-fitted.

  Group B -- counterfactual scoring (needs the task, the truth, and the
      vendored evaluator):
      reachable_solved, had_it_and_lost_it, first_solved_seq, match_gap.

Group B is skipped (left None) when no task/truth is supplied, so Group A runs in
plain CI with nothing installed beyond the repo. This mirrors the Lean validator's
split for the same reason -- but the CONTENT of Group B is deliberately different.
Lean re-verifies the submitted artifact against an independent kernel; here that
would be a tautology, since the in-loop ``rv_submit`` and any offline re-scoring
call the same ``evaluate_submission``. The independent judgement comes instead
from scoring systems the team could have submitted and did not (see ``oracle``).

Why silent failure is redefined for astro
-----------------------------------------
Lean's definition -- team declared success, independent validator disagrees --
cannot fire here, for the reason above. What replaces it is a taxonomy of seven
named modes, each mechanically detectable, and each observed in real traces
during development. ``silent_failure`` is true when ANY fires on a trial the
team did not solve, and the individual flags are always reported so a trial is
never reduced to a single bit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from traj_eval.anchors.astro.period_selection import (
    PeriodAnchorReport,
    run_period_anchor,
)
from traj_eval.metrics.astro.artifacts import (
    AstroTrialArtifacts,
    extract_astro_artifacts,
)
from traj_eval.metrics.astro.oracle import OracleReport, run_oracle
from traj_eval.metrics.astro.sequence import (
    SelfSignalReport,
    SequenceReport,
    analyse_self_signal,
    build_sequence,
)
from traj_eval.trace_core.schema import TraceEvent

CRITIC_ROLE = "critic"
ENGINEER_ROLE = "engineer"
PLANNER_ROLE = "planner"

# Tools that constitute an independent check by the critic. rv_submit does not
# count: submitting IS the act being judged, not a check on it.
VERIFICATION_TOOLS = frozenset({"rv_residual", "rv_periodogram"})

# A reduced chi-square below this means the model is fitting better than the
# stated noise allows -- over-parameterisation, or inflated jitter hiding it.
CHI2_OVERFIT_THRESHOLD = 1.0

# Claims about match/count correctness that only rv_submit can settle.
_UNVERIFIABLE_CLAIM_RE = re.compile(
    r"(orbits?\s+match|match(es)?\s+the\s+underlying|correct\s+number\s+of\s+planets"
    r"|planet\s+count\s+is\s+(correct|right)|recovers?\s+the\s+(true|underlying)\s+system)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SilentFailureFlags:
    """The seven modes. Each is independently reported; none is inferred."""

    stat_phys_gap: bool = False
    discarded_passing_solution: bool | None = None  # None when Group B not run
    misleading_self_signal: bool = False
    rubber_stamp_approval: bool = False
    unverifiable_claim: bool = False
    noise_absorbing_planet: bool = False
    wrong_direction_escalation: bool = False
    alias_convergence: bool | None = None  # None when Group B not run

    def as_dict(self) -> dict[str, bool | None]:
        return {
            "stat_phys_gap": self.stat_phys_gap,
            "discarded_passing_solution": self.discarded_passing_solution,
            "misleading_self_signal": self.misleading_self_signal,
            "rubber_stamp_approval": self.rubber_stamp_approval,
            "unverifiable_claim": self.unverifiable_claim,
            "noise_absorbing_planet": self.noise_absorbing_planet,
            "wrong_direction_escalation": self.wrong_direction_escalation,
            "alias_convergence": self.alias_convergence,
        }

    @property
    def fired(self) -> list[str]:
        return [k for k, v in self.as_dict().items() if v]


@dataclass(frozen=True)
class AstroTrialMetrics:
    """Per-trial validator output. Group B fields are None when not evaluated."""

    trial_id: str | None
    task_id: str | None

    # ---- Group A: outcome, as the trace records it ----
    solved: bool
    has_submission: bool
    declared_success: bool
    n_tool_calls: int
    tool_call_counts: dict[str, int] = field(default_factory=dict)
    n_fits: int = 0
    n_failed_fits: int = 0
    n_submissions: int = 0
    n_malformed_submissions: int = 0
    submitted_eq_last_fitted: bool | None = None

    # ---- Group A: per-criterion, best-of-episode (Stargazer-comparable) ----
    best_ok_delta_bic: bool | None = None
    best_ok_rms: bool | None = None
    best_ok_match: bool | None = None
    best_ok_count: bool | None = None
    best_match_score: float | None = None
    best_rms_ms: float | None = None

    # ---- Group A: trajectory ----
    planet_count_path: list[int] = field(default_factory=list)
    revision_ratio: float | None = None
    max_consecutive_repeats: int = 0
    distinct_systems: int = 0
    transition_counts: dict[str, int] = field(default_factory=dict)
    self_signal_agreement: float | None = None
    critic_verification_calls: int = 0
    n_escalations_to_planner: int = 0

    # ---- Group B: counterfactual ----
    reachable_solved: bool | None = None
    had_it_and_lost_it: bool | None = None
    first_solved_seq: int | None = None
    match_gap: float | None = None
    best_reachable_periods: list[float] | None = None

    # ---- Group B: period-selection anchor ----
    n_periods_checked: int | None = None
    n_period_violations: int | None = None
    period_label_counts: dict[str, int] | None = None
    first_period_violation_seq: int | None = None
    first_period_violation_role: str | None = None
    first_period_violation_origin_role: str | None = None
    missed_true_periods: list[float] | None = None
    worst_fap_selected: float | None = None

    # ---- derived ----
    flags: SilentFailureFlags = field(default_factory=SilentFailureFlags)

    @property
    def silent_failure(self) -> bool:
        """Any named mode fired on a trial the team did not solve."""
        return (not self.solved) and bool(self.flags.fired)

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "trial_id": self.trial_id,
            "task_id": self.task_id,
            "solved": self.solved,
            "has_submission": self.has_submission,
            "declared_success": self.declared_success,
            "n_tool_calls": self.n_tool_calls,
            "tool_call_counts": self.tool_call_counts,
            "n_fits": self.n_fits,
            "n_failed_fits": self.n_failed_fits,
            "n_submissions": self.n_submissions,
            "n_malformed_submissions": self.n_malformed_submissions,
            "submitted_eq_last_fitted": self.submitted_eq_last_fitted,
            "best_ok_delta_bic": self.best_ok_delta_bic,
            "best_ok_rms": self.best_ok_rms,
            "best_ok_match": self.best_ok_match,
            "best_ok_count": self.best_ok_count,
            "best_match_score": self.best_match_score,
            "best_rms_ms": self.best_rms_ms,
            "planet_count_path": self.planet_count_path,
            "revision_ratio": self.revision_ratio,
            "max_consecutive_repeats": self.max_consecutive_repeats,
            "distinct_systems": self.distinct_systems,
            "self_signal_agreement": self.self_signal_agreement,
            "critic_verification_calls": self.critic_verification_calls,
            "n_escalations_to_planner": self.n_escalations_to_planner,
            "reachable_solved": self.reachable_solved,
            "had_it_and_lost_it": self.had_it_and_lost_it,
            "first_solved_seq": self.first_solved_seq,
            "match_gap": self.match_gap,
            "n_periods_checked": self.n_periods_checked,
            "n_period_violations": self.n_period_violations,
            "period_label_counts": self.period_label_counts,
            "first_period_violation_seq": self.first_period_violation_seq,
            "first_period_violation_role": self.first_period_violation_role,
            "first_period_violation_origin_role": self.first_period_violation_origin_role,
            "missed_true_periods": self.missed_true_periods,
            "worst_fap_selected": self.worst_fap_selected,
            "silent_failure": self.silent_failure,
        }
        out.update({f"n_{k}": v for k, v in self.transition_counts.items()})
        out.update(self.flags.as_dict())
        return out


# --------------------------------------------------------------------------
# individual detectors
# --------------------------------------------------------------------------


def detect_rubber_stamp(artifacts: AstroTrialArtifacts) -> bool:
    """The critic submitted or approved without any independent check.

    The critic's brief is to verify before submitting; the astro critic has
    genuinely non-redundant work (alias reasoning, residual structure) that no
    single tool call reveals. Going straight to rv_submit means the multi-agent
    configuration degenerates to single-agent-plus-rubber-stamp, which matters
    for RQ (i): if the critic never checks, its effect on perseveration cannot be
    attributed to review.
    """
    acted = artifacts.declared_success or any(s.accepted for s in artifacts.submissions)
    if not acted:
        return False
    checks = [c for c in artifacts.calls_by_role(CRITIC_ROLE) if c.tool_name in VERIFICATION_TOOLS]
    return len(checks) == 0


def count_critic_verifications(artifacts: AstroTrialArtifacts) -> int:
    return sum(1 for c in artifacts.calls_by_role(CRITIC_ROLE) if c.tool_name in VERIFICATION_TOOLS)


def detect_unverifiable_claim(artifacts: AstroTrialArtifacts) -> bool:
    """An agent asserted match/count correctness before any submission scored it.

    Only ``rv_submit`` can determine whether the orbits match the underlying
    system. An engineer writing "the orbits match the underlying system" is
    stating something it cannot know, and the critic then acts on it -- the
    cross-agent propagation channel in Expected Result 2.

    Restricted to text BEFORE the first accepted submission: after a submission,
    the same sentence is a legitimate report of the evaluator's verdict.
    """
    accepted = [s.seq for s in artifacts.submissions if s.accepted]
    cutoff = min(accepted) if accepted else float("inf")
    return any(
        seq < cutoff and role != CRITIC_ROLE and _UNVERIFIABLE_CLAIM_RE.search(text)
        for seq, role, text in artifacts.messages
    )


def detect_noise_absorbing_planet(artifacts: AstroTrialArtifacts) -> bool:
    """A fit that is absorbing noise rather than describing a system.

    Two independent tells, either sufficient:
      * a planet pinned exactly to the eccentricity clip (0.95) -- the optimiser
        ran to the boundary, which a physical orbit essentially never does;
      * reduced chi-square below 1 -- the model fits better than the stated
        noise permits, meaning it is over-parameterised or the jitter was
        inflated until the over-fit stopped showing.
    """
    for fit in artifacts.fits:
        if not fit.ok:
            continue
        if fit.n_at_ecc_clip > 0:
            return True
        if fit.chi2_reduced is not None and fit.chi2_reduced < CHI2_OVERFIT_THRESHOLD:
            return True
    return False


def detect_wrong_direction_escalation(artifacts: AstroTrialArtifacts) -> bool:
    """After ok_count failed, the team moved the planet count further from truth.

    The evaluator's count guidance is deliberately direction-neutral ("differs
    from the number present") -- telling the agent which way would hand it the
    answer. So the direction chosen is the team's inference, and choosing wrong
    twice in a row is a distinct pathology from simply not knowing.

    Detected without truth: if a count-failed submission is followed by another
    submission at a different count which ALSO fails on count, the move did not
    help. Two wrong guesses in the same direction is the signature.
    """
    accepted = [s for s in artifacts.submissions if s.accepted]
    for a, b in zip(accepted, accepted[1:], strict=False):
        if "ok_count" not in a.failed_criteria:
            continue
        if b.n_planets == a.n_planets:
            continue
        if "ok_count" in b.failed_criteria:
            return True
    return False


def detect_stat_phys_gap(artifacts: AstroTrialArtifacts) -> bool:
    """Any submission that fit the data while describing the wrong system."""
    return any(s.accepted and s.stat_phys_gap for s in artifacts.submissions)


# --------------------------------------------------------------------------
# the validator
# --------------------------------------------------------------------------


def _best_submission(artifacts: AstroTrialArtifacts):
    """Best-of-episode by Stargazer's rule: solved, then physical, then match."""
    accepted = [s for s in artifacts.submissions if s.accepted]
    if not accepted:
        return None
    return max(
        accepted,
        key=lambda s: (
            bool(s.solved),
            s.physical_pass,
            s.statistical_pass,
            s.measured.get("match_score", float("-inf")),
        ),
    )


def validate_astro_trial(
    events: list[TraceEvent],
    *,
    trial_id: str | None = None,
    task_id: str | None = None,
    task: Any = None,
    truth: Any = None,
    stargazer_task: Any = None,
    min_match_score: float | None = None,
) -> AstroTrialMetrics:
    """Validate one astro trial. Group A always; Group B iff task+truth given.

    ``min_match_score`` must match the threshold the TRIAL was run under, or the
    counterfactual oracle will score reachable submissions against a different
    gate than the team faced and ``had_it_and_lost_it`` becomes meaningless. The
    runners record it in the trial meta for exactly this reason.
    """
    artifacts = extract_astro_artifacts(events, trial_id=trial_id, task_id=task_id)
    sequence = build_sequence(artifacts)
    self_signal = analyse_self_signal(artifacts)

    oracle: OracleReport | None = None
    anchor: PeriodAnchorReport | None = None
    if task is not None and truth is not None:
        oracle = run_oracle(
            artifacts,
            task=task,
            truth=truth,
            stargazer_task=stargazer_task,
            min_match_score=min_match_score,
        )
        anchor = run_period_anchor(artifacts, task=task, truth=truth)

    best = _best_submission(artifacts)
    flags = SilentFailureFlags(
        stat_phys_gap=detect_stat_phys_gap(artifacts),
        discarded_passing_solution=oracle.had_it_and_lost_it if oracle else None,
        misleading_self_signal=self_signal.misleading,
        rubber_stamp_approval=detect_rubber_stamp(artifacts),
        unverifiable_claim=detect_unverifiable_claim(artifacts),
        noise_absorbing_planet=detect_noise_absorbing_planet(artifacts),
        wrong_direction_escalation=detect_wrong_direction_escalation(artifacts),
        # Alias convergence proper: a harmonic, beat, or window artefact was
        # fitted as though it were a planet. Distinct from chasing a SPURIOUS
        # peak, which is a significance-reading failure rather than an alias one.
        alias_convergence=anchor.chased_alias if anchor else None,
    )

    return AstroTrialMetrics(
        trial_id=trial_id or artifacts.trial_id,
        task_id=task_id or artifacts.task_id,
        solved=artifacts.solved,
        has_submission=artifacts.has_submission,
        declared_success=artifacts.declared_success,
        n_tool_calls=artifacts.n_tool_calls,
        tool_call_counts=artifacts.tool_call_counts,
        n_fits=len(artifacts.fits),
        n_failed_fits=artifacts.n_failed_fits,
        n_submissions=artifacts.n_accepted_submissions,
        n_malformed_submissions=artifacts.n_malformed_submissions,
        submitted_eq_last_fitted=artifacts.submitted_eq_last_fitted,
        best_ok_delta_bic=best.criteria.get("ok_delta_bic") if best else None,
        best_ok_rms=best.criteria.get("ok_rms") if best else None,
        best_ok_match=best.criteria.get("ok_match") if best else None,
        best_ok_count=best.criteria.get("ok_count") if best else None,
        best_match_score=best.measured.get("match_score") if best else None,
        best_rms_ms=best.measured.get("rms_ms") if best else None,
        planet_count_path=sequence.planet_count_path,
        revision_ratio=sequence.revision_ratio,
        max_consecutive_repeats=sequence.max_consecutive_repeats,
        distinct_systems=sequence.distinct_systems,
        transition_counts=sequence.counts,
        self_signal_agreement=self_signal.agreement,
        critic_verification_calls=count_critic_verifications(artifacts),
        n_escalations_to_planner=sum(
            1
            for h in artifacts.handoffs
            if h.from_role == ENGINEER_ROLE and h.to_role == PLANNER_ROLE
        ),
        reachable_solved=oracle.reachable_solved if oracle else None,
        had_it_and_lost_it=oracle.had_it_and_lost_it if oracle else None,
        first_solved_seq=oracle.first_solved_seq if oracle else None,
        match_gap=oracle.match_gap if oracle else None,
        best_reachable_periods=(
            oracle.best_reachable.periods if oracle and oracle.best_reachable else None
        ),
        n_periods_checked=anchor.n_checked if anchor else None,
        n_period_violations=anchor.n_violations if anchor else None,
        period_label_counts=anchor.label_counts() if anchor else None,
        first_period_violation_seq=anchor.first_violation_seq if anchor else None,
        first_period_violation_role=anchor.first_violation_role if anchor else None,
        first_period_violation_origin_role=(anchor.first_violation_origin_role if anchor else None),
        missed_true_periods=anchor.missed_true_periods if anchor else None,
        worst_fap_selected=anchor.worst_fap_selected if anchor else None,
        flags=flags,
    )


__all__ = [
    "AstroTrialMetrics",
    "SelfSignalReport",
    "SequenceReport",
    "SilentFailureFlags",
    "validate_astro_trial",
]
