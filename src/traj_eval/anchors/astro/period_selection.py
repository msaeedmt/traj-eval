"""Period-selection anchor: was each period the team chose a real planet?

The automatic alias-convergence detector, and the primary O1 localisation
primitive for the astro testbed. Pure trace analysis plus the task's ground
truth: no LLM, no network, arithmetic only.

The gap it closes
-----------------
Without it, a failed trial reports only that ``ok_match`` and ``ok_count``
failed. It cannot say WHICH period was wrong, or in what way. That distinction
is the whole diagnosis: a team that seeds a HARMONIC has a subtle physics
problem (the alias genuinely fits the data), while a team that seeds a SPURIOUS
peak has a significance-reading problem (it chased noise). Identical failed
criteria, completely different causes.

Classification
--------------
Each requested period is compared against every true period and labelled with
the first matching rule:

  TRUE      -- within tolerance of a true period
  HARMONIC  -- half or double a true period (P/2, 2P)
  BEAT      -- a beat against the nightly observing rhythm, 1/(1/P +- 1)
  WINDOW    -- coincides with a spectral-window peak, i.e. an artefact of WHEN
               the telescope observed rather than of the star
  SPURIOUS  -- none of the above; noise

Only TRUE is a PASS. Everything else is a VIOLATION, and the first one in causal
order is the trial's localisation point: an event index and an agent.

Why the tolerance is computed per task
--------------------------------------
A periodogram cannot resolve a period more finely than its own frequency grid.
With a grid uniform in frequency at ``oversample`` samples per ``1/baseline``,
the spacing in PERIOD near P is

    dP ~ P^2 / (oversample * baseline)

so the relative resolution is ``P / (oversample * baseline)`` -- worse for long
periods and short baselines. On seed1108_diff2 (truth 5.283 d, baseline 15.0 d)
that is ~3.5%, and the periodogram duly reported its peak at 5.187 d, 1.8% off.
A fixed 1% tolerance would have labelled a CORRECT choice as a violation.

Two details of that calculation were got wrong in a first version and are worth
recording, because both produced FALSE VIOLATIONS ON A SOLVED TRIAL:

  * The tolerance must be evaluated at the REFERENCE period (the true period, or
    the alias being tested), not at the period the agent requested. The
    resolution is a property of where the real peak sits.
  * One grid step is not enough headroom. A peak is displaced both by grid
    quantisation and by noise, so the observed offset can exceed a full step.
    On seed210_diff2 the planner took the peak at 20.823 d for a true period of
    21.68 d -- a 3.97% error against a 4.0% resolution, which a one-step
    tolerance rejected by 0.12 percentage points, on a trial that went on to
    solve the task. ``GRID_TOLERANCE_FACTOR`` gives 1.5 steps of headroom.

The classes stay comfortably disjoint at that width: a harmonic is 50% or 100%
away, so even a 7-8% tolerance cannot absorb one.

What the labels are NOT
-----------------------
A label describes the period, not the agent's competence. Seeding a harmonic is
often reasonable -- the alias may genuinely be the stronger peak. The anchor
records what was chosen and lets the detectors and the report decide what it
means.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from traj_eval.metrics.astro.artifacts import AstroTrialArtifacts
from traj_eval.trace_core.schema import AnchorCheck, AnchorStatus

ANCHOR_NAME = "period_selection"

# Must match rv_periodogram.OVERSAMPLE, since the resolution argument above is
# only valid for the grid the agent actually saw.
DEFAULT_OVERSAMPLE = 10.0

# Headroom in units of the periodogram grid step: quantisation alone displaces a
# peak by up to half a step, and noise adds more. Measured at 1.0 steps on
# seed210_diff2; 1.5 leaves margin without approaching the 50% gap to a harmonic.
GRID_TOLERANCE_FACTOR = 1.5

# Floor on the relative tolerance. A very long baseline drives the computed
# resolution toward zero, which would start flagging correct picks on
# floating-point noise; 1% is far below any real period error.
MIN_RELATIVE_TOLERANCE = 0.01

# Ceiling, so a short baseline cannot make the tolerance so loose that a
# harmonic is absorbed into TRUE. 2P is 100% away, P/2 is 50%, so 25% keeps the
# classes disjoint by a wide margin.
MAX_RELATIVE_TOLERANCE = 0.25

# Sampling rhythms that produce beat aliases. 1.0 d is the nightly cadence that
# dominates ground-based RV; the sidereal day matters for long campaigns.
BEAT_FREQUENCIES_PER_DAY = (1.0, 1.0027379)


class PeriodLabel(StrEnum):
    TRUE = "true"
    HARMONIC = "harmonic"
    BEAT = "beat"
    WINDOW = "window"
    SPURIOUS = "spurious"

    @property
    def is_violation(self) -> bool:
        return self is not PeriodLabel.TRUE


def relative_tolerance(
    reference_days: float,
    baseline_days: float,
    *,
    oversample: float = DEFAULT_OVERSAMPLE,
) -> float:
    """Relative tolerance at ``reference_days``, from the periodogram resolution.

    ``reference_days`` is the period being matched AGAINST (a true period, or an
    alias of one) -- not the period the agent requested. See the module
    docstring. Clamped into [MIN_RELATIVE_TOLERANCE, MAX_RELATIVE_TOLERANCE].
    """
    if baseline_days <= 0.0 or oversample <= 0.0:
        return MAX_RELATIVE_TOLERANCE
    resolution = float(reference_days) / (oversample * float(baseline_days))
    scaled = GRID_TOLERANCE_FACTOR * resolution
    return float(min(max(scaled, MIN_RELATIVE_TOLERANCE), MAX_RELATIVE_TOLERANCE))


def _close(a: float, b: float, rtol: float) -> bool:
    if b == 0.0:
        return abs(a) <= rtol
    return abs(a - b) / abs(b) <= rtol


def _beat_periods(period_days: float) -> list[float]:
    """Beat aliases of ``period_days`` against the sampling rhythms."""
    out: list[float] = []
    f = 1.0 / period_days
    for f_sample in BEAT_FREQUENCIES_PER_DAY:
        for beat in (f - f_sample, f + f_sample):
            if abs(beat) > 1e-9:
                out.append(abs(1.0 / beat))
    return out


@dataclass(frozen=True)
class PeriodVerdict:
    """One period the team asked for, and what it actually was."""

    period_days: float
    label: PeriodLabel
    nearest_true_days: float | None
    relative_error: float | None
    tolerance: float
    detail: str
    fap_at_selection: float | None = None

    @property
    def is_violation(self) -> bool:
        return self.label.is_violation

    def to_anchor_check(self) -> AnchorCheck:
        """Render as the schema's AnchorCheck, for attaching to the event."""
        return AnchorCheck(
            name=ANCHOR_NAME,
            status=AnchorStatus.VIOLATION if self.is_violation else AnchorStatus.PASS,
            expected=self.nearest_true_days,
            observed=self.period_days,
            detail=self.detail,
        )


@dataclass(frozen=True)
class FitVerdict:
    """Every period requested at one rv_fit call.

    ``role`` is who MADE the call; ``upstream_role`` is who handed the work to
    them immediately before. The distinction matters: the engineer executes the
    planner's hypothesis, so a bad period surfaces at an engineer event while
    the DECISION belonged to the planner. Expected Result 2 compares
    planner-introduced against engineer-introduced errors, and collapsing the
    two would attribute every period error to the engineer.

    ``upstream_role`` is derived structurally from the handoff immediately
    preceding the call -- never by parsing prose for numbers, which would be
    fragile and would silently mis-attribute whenever an agent paraphrased.
    """

    seq: int
    role: str
    verdicts: list[PeriodVerdict] = field(default_factory=list)
    upstream_role: str | None = None

    @property
    def has_violation(self) -> bool:
        return any(v.is_violation for v in self.verdicts)

    @property
    def n_true(self) -> int:
        return sum(1 for v in self.verdicts if v.label is PeriodLabel.TRUE)


@dataclass(frozen=True)
class PeriodAnchorReport:
    """Per-trial period-selection anchor results."""

    fits: list[FitVerdict] = field(default_factory=list)
    true_periods_days: list[float] = field(default_factory=list)
    missed_true_periods: list[float] = field(default_factory=list)

    @property
    def all_verdicts(self) -> list[tuple[int, str, PeriodVerdict]]:
        return [(f.seq, f.role, v) for f in self.fits for v in f.verdicts]

    @property
    def n_checked(self) -> int:
        return len(self.all_verdicts)

    @property
    def n_violations(self) -> int:
        return sum(1 for _, _, v in self.all_verdicts if v.is_violation)

    @property
    def violation_rate(self) -> float | None:
        return self.n_violations / self.n_checked if self.n_checked else None

    def label_counts(self) -> dict[str, int]:
        counts = {label.value: 0 for label in PeriodLabel}
        for _, _, verdict in self.all_verdicts:
            counts[verdict.label.value] += 1
        return counts

    @property
    def first_violation(self) -> tuple[int, str, PeriodVerdict] | None:
        """Earliest anchor violation in causal order: the O1 localisation point.

        Returns (event seq, originating agent, verdict). This is the answer to
        "where did this trial go wrong, and whose decision was it".
        """
        violations = [t for t in self.all_verdicts if t[2].is_violation]
        return min(violations, key=lambda t: t[0]) if violations else None

    @property
    def first_violation_seq(self) -> int | None:
        first = self.first_violation
        return first[0] if first else None

    @property
    def first_violation_role(self) -> str | None:
        """The agent whose tool call carried the first bad period."""
        first = self.first_violation
        return first[1] if first else None

    @property
    def first_violation_origin_role(self) -> str | None:
        """The agent whose DECISION the first bad period came from.

        The upstream role where one exists, otherwise the calling role. This is
        the attribution Expected Result 2 needs.
        """
        first = self.first_violation
        if not first:
            return None
        seq = first[0]
        for fit in self.fits:
            if fit.seq == seq:
                return fit.upstream_role or fit.role
        return first[1]

    @property
    def chased_spurious(self) -> bool:
        """A period matching nothing at all -- noise, not an alias."""
        return any(v.label is PeriodLabel.SPURIOUS for _, _, v in self.all_verdicts)

    @property
    def chased_alias(self) -> bool:
        """Alias convergence: a harmonic, beat, or window artefact was fitted."""
        return any(
            v.label in (PeriodLabel.HARMONIC, PeriodLabel.BEAT, PeriodLabel.WINDOW)
            for _, _, v in self.all_verdicts
        )

    @property
    def ever_found_all_true(self) -> bool:
        """Every true period was proposed at some point, whatever else was too."""
        return not self.missed_true_periods

    @property
    def worst_fap_selected(self) -> float | None:
        """Highest false-alarm probability among periods the team chose to fit.

        Turns "the planner chose noise" into "the planner chose something the
        tool reported as 30% likely to be noise" -- attributable rather than
        merely unlucky.
        """
        faps = [
            v.fap_at_selection for _, _, v in self.all_verdicts if v.fap_at_selection is not None
        ]
        return max(faps) if faps else None


def classify_period(
    period_days: float,
    *,
    true_periods: list[float],
    baseline_days: float,
    window_peaks_days: list[float] | None = None,
    oversample: float = DEFAULT_OVERSAMPLE,
    fap_at_selection: float | None = None,
) -> PeriodVerdict:
    """Label one requested period against the truth and the observing window."""
    window_peaks = window_peaks_days or []

    def tol_at(reference: float) -> float:
        return relative_tolerance(reference, baseline_days, oversample=oversample)

    # Reported tolerance: the one that applies at the nearest true period, which
    # is the comparison a reader will want to check.
    nearest: float | None = None
    if true_periods:
        nearest = min(true_periods, key=lambda t: abs(math.log(period_days / t)))
    rel_err = abs(period_days - nearest) / nearest if nearest else None
    tol = tol_at(nearest) if nearest else tol_at(period_days)

    # 1. a real planet
    for truth in true_periods:
        if _close(period_days, truth, tol_at(truth)):
            return PeriodVerdict(
                period_days=period_days,
                label=PeriodLabel.TRUE,
                nearest_true_days=truth,
                relative_error=abs(period_days - truth) / truth,
                tolerance=tol_at(truth),
                detail=f"within {tol_at(truth):.1%} of the true period {truth:.6g} d",
                fap_at_selection=fap_at_selection,
            )

    # 2. a harmonic of a real planet
    for truth in true_periods:
        for factor, name in ((0.5, "half"), (2.0, "double")):
            if _close(period_days, truth * factor, tol_at(truth * factor)):
                return PeriodVerdict(
                    period_days=period_days,
                    label=PeriodLabel.HARMONIC,
                    nearest_true_days=truth,
                    relative_error=rel_err,
                    tolerance=tol,
                    detail=f"{name} the true period {truth:.6g} d",
                    fap_at_selection=fap_at_selection,
                )

    # 3. a beat against the sampling rhythm
    for truth in true_periods:
        for beat in _beat_periods(truth):
            if _close(period_days, beat, tol_at(beat)):
                return PeriodVerdict(
                    period_days=period_days,
                    label=PeriodLabel.BEAT,
                    nearest_true_days=truth,
                    relative_error=rel_err,
                    tolerance=tol,
                    detail=(
                        f"beat alias of the true period {truth:.6g} d "
                        f"against the ~1 d sampling rhythm ({beat:.6g} d)"
                    ),
                    fap_at_selection=fap_at_selection,
                )

    # 4. an artefact of the observing cadence
    for peak in window_peaks:
        if _close(period_days, peak, tol_at(peak)):
            return PeriodVerdict(
                period_days=period_days,
                label=PeriodLabel.WINDOW,
                nearest_true_days=nearest,
                relative_error=rel_err,
                tolerance=tol,
                detail=f"coincides with the spectral-window peak at {peak:.6g} d",
                fap_at_selection=fap_at_selection,
            )

    # 5. nothing at all
    return PeriodVerdict(
        period_days=period_days,
        label=PeriodLabel.SPURIOUS,
        nearest_true_days=nearest,
        relative_error=rel_err,
        tolerance=tol,
        detail=(
            "matches no true period, harmonic, beat, or window peak"
            + (f"; nearest true period is {nearest:.6g} d" if nearest else "")
        ),
        fap_at_selection=fap_at_selection,
    )


def _upstream_role(artifacts: AstroTrialArtifacts, seq: int) -> str | None:
    """Who handed work to the agent acting at ``seq``, most recently before it."""
    earlier = [h for h in artifacts.handoffs if h.seq < seq]
    return earlier[-1].from_role if earlier else None


def _window_peaks_before(artifacts: AstroTrialArtifacts, seq: int) -> list[float]:
    """Window peaks from the most recent periodogram at or before ``seq``.

    Uses what the team could actually have known at that moment rather than the
    whole trial's peaks, so the anchor never labels a period a WINDOW artefact on
    evidence that only appeared later.
    """
    earlier = [p for p in artifacts.periodograms if p.seq <= seq and p.window_peaks_days]
    return earlier[-1].window_peaks_days if earlier else []


def _fap_for(artifacts: AstroTrialArtifacts, seq: int, period: float, tol: float) -> float | None:
    """The false-alarm probability reported for this period, if it was a peak.

    Searches periodograms at or before ``seq``, most recent first, so the value
    is what the team saw when it made the choice.
    """
    for record in reversed([p for p in artifacts.periodograms if p.seq <= seq]):
        for peak in record.peaks:
            peak_period = peak.get("period_days")
            if peak_period is None:
                continue
            if _close(float(period), float(peak_period), tol):
                fap = peak.get("false_alarm_probability_approx")
                return float(fap) if fap is not None else None
    return None


def run_period_anchor(
    artifacts: AstroTrialArtifacts,
    *,
    task: Any,
    truth: Any,
    oversample: float = DEFAULT_OVERSAMPLE,
) -> PeriodAnchorReport:
    """Classify every period requested across the trial's rv_fit calls.

    Classification uses the periods the AGENT ASKED FOR (``period_guesses``),
    not the fitted results: the choice is the decision under study, and the
    fitter can only move it by +-20% anyway.
    """
    true_periods = [float(p) for p in truth.periods_days]
    baseline = float(task.observation.baseline_days)

    fits: list[FitVerdict] = []
    proposed: list[float] = []

    for fit in artifacts.fits:
        if not fit.period_guesses:
            continue
        window_peaks = _window_peaks_before(artifacts, fit.seq)
        verdicts: list[PeriodVerdict] = []
        for period in fit.period_guesses:
            if not (period > 0.0 and math.isfinite(period)):
                continue
            tol = relative_tolerance(period, baseline, oversample=oversample)
            # ``tol`` here is only used to match the period back to a periodogram
            # peak for its FAP; classification computes its own per-reference
            # tolerances.
            verdicts.append(
                classify_period(
                    period,
                    true_periods=true_periods,
                    baseline_days=baseline,
                    window_peaks_days=window_peaks,
                    oversample=oversample,
                    fap_at_selection=_fap_for(artifacts, fit.seq, period, tol),
                )
            )
            proposed.append(period)
        if verdicts:
            fits.append(
                FitVerdict(
                    seq=fit.seq,
                    role=fit.role,
                    verdicts=verdicts,
                    upstream_role=_upstream_role(artifacts, fit.seq),
                )
            )

    missed = [
        truth_period
        for truth_period in true_periods
        if not any(
            _close(
                p,
                truth_period,
                relative_tolerance(truth_period, baseline, oversample=oversample),
            )
            for p in proposed
        )
    ]

    return PeriodAnchorReport(fits=fits, true_periods_days=true_periods, missed_true_periods=missed)


def summarise(report: PeriodAnchorReport) -> dict[str, Any]:
    """Flat dict for reporting/serialisation."""
    return {
        "n_periods_checked": report.n_checked,
        "n_period_violations": report.n_violations,
        "period_violation_rate": report.violation_rate,
        "period_label_counts": report.label_counts(),
        "first_period_violation_seq": report.first_violation_seq,
        "first_period_violation_role": report.first_violation_role,
        "first_period_violation_origin_role": report.first_violation_origin_role,
        "chased_spurious_period": report.chased_spurious,
        "chased_alias_period": report.chased_alias,
        "found_all_true_periods": report.ever_found_all_true,
        "missed_true_periods": report.missed_true_periods,
        "worst_fap_selected": report.worst_fap_selected,
    }
