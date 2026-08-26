"""The model sequence: how the team's hypothesis moved over the episode.

Stargazer's abstract states as a finding that "successful agents escalate model
complexity while failed agents repeat", but the paper establishes it with two
hand-written case studies -- counting by eye that one agent "resubmits the same
2-planet alias solution 4 times identically" and "never attempts a 3-planet
model". The claim is never operationalised, because with a bare PythonREPL the
hypothesis at each step is buried in code output.

Our typed tools make the hypothesis explicit: every ``rv_fit`` names its period
guesses and every ``rv_submit`` names its planets. So the model sequence is
directly readable, and the escalate/repeat dichotomy becomes a number.

Classification
--------------
Consecutive models are compared and each transition labelled:

  ESCALATE  -- the planet count increased
  DESCALATE -- the planet count decreased
  EXPLORE   -- same count, but at materially different periods
  REFINE    -- same count, same periods, parameters moved
  COMMIT    -- a fit handed straight to submission, unchanged
  REPEAT    -- the same system produced again, within tolerance

REPEAT is the pathology Stargazer describes; ESCALATE and EXPLORE are the
behaviours it associates with success. REFINE sits between: legitimate when a
fit is being improved, pathological when it substitutes for revision.

COMMIT exists to stop the intended workflow from scoring as repetition. Fitting a
system and then submitting that same system is one logical step performed by two
roles -- the engineer measures, the critic ships -- and counting it as a repeat
made a clean single-shot success look like pure thrashing (revision_ratio 0.0 on
a trial that solved the task on its first submission). It is excluded from the
escalate/repeat accounting entirely rather than being counted on either side,
because it is evidence of neither.

Why EXPLORE counts as revision, not repetition
----------------------------------------------
A definitional choice, made explicit because it shapes the headline number.
Stargazer's pathology is "the same wrong answer is resubmitted without any model
escalation" -- the failure is *not revising the hypothesis*, and moving to a
genuinely different period is a revision even at constant planet count. So
EXPLORE is grouped with ESCALATE in ``revision_ratio``. The raw counts are all
retained, so the alternative grouping can be computed without re-deriving
anything.

Period comparison tolerance
---------------------------
Two periods count as "the same" within ``PERIOD_RTOL`` (default 2%). This is not
arbitrary: a periodogram's own grid resolution near period P is roughly
``P^2 / (oversample * baseline)``, which on a typical Easy task is ~1.8% -- so a
tighter tolerance would label grid quantisation as exploration. Callers with the
task in hand can pass a task-specific tolerance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from traj_eval.metrics.astro.artifacts import AstroTrialArtifacts

# See the module docstring: must exceed periodogram grid quantisation.
PERIOD_RTOL = 0.02


class Transition(StrEnum):
    ESCALATE = "escalate"
    DESCALATE = "descalate"
    EXPLORE = "explore"
    REFINE = "refine"
    COMMIT = "commit"
    REPEAT = "repeat"


class ModelSource(StrEnum):
    FIT = "fit"
    SUBMIT = "submit"


@dataclass(frozen=True)
class ModelState:
    """One hypothesis the team held, in trajectory order."""

    seq: int
    role: str
    source: ModelSource
    periods: list[float]
    n_planets: int
    # Fit-quality at this state, where the source reports it.
    rms_ms: float | None = None
    match_score: float | None = None
    solved: bool | None = None

    def signature(self, rtol: float = PERIOD_RTOL) -> tuple[int, ...]:
        """Coarse identity of the system: periods bucketed at ``rtol``.

        Buckets on a log grid so the tolerance is relative at every scale --
        a 2% difference means the same thing at 3 d and at 300 d.
        """
        import math

        step = math.log1p(rtol)
        return tuple(sorted(int(round(math.log(p) / step)) for p in self.periods if p > 0))


@dataclass(frozen=True)
class TransitionRecord:
    from_state: ModelState
    to_state: ModelState
    kind: Transition


@dataclass(frozen=True)
class SequenceReport:
    """The model sequence and the escalate/repeat statistics over it."""

    states: list[ModelState] = field(default_factory=list)
    transitions: list[TransitionRecord] = field(default_factory=list)

    def count(self, kind: Transition) -> int:
        return sum(1 for t in self.transitions if t.kind is kind)

    @property
    def counts(self) -> dict[str, int]:
        return {k.value: self.count(k) for k in Transition}

    @property
    def n_transitions(self) -> int:
        return len(self.transitions)

    @property
    def revision_ratio(self) -> float | None:
        """Revisions / (revisions + repeats). Stargazer's dichotomy, as a number.

        None when the team never produced two models to compare -- undefined, not
        zero, since a single-shot success has no repetition to measure.
        """
        revise = self.count(Transition.ESCALATE) + self.count(Transition.EXPLORE)
        repeat = self.count(Transition.REPEAT)
        total = revise + repeat
        return revise / total if total else None

    @property
    def n_productive_steps(self) -> int:
        """Transitions that carried information, excluding the commit handoff."""
        return sum(1 for t in self.transitions if t.kind is not Transition.COMMIT)

    @property
    def max_consecutive_repeats(self) -> int:
        best = run = 0
        for t in self.transitions:
            run = run + 1 if t.kind is Transition.REPEAT else 0
            best = max(best, run)
        return best

    @property
    def planet_count_path(self) -> list[int]:
        return [s.n_planets for s in self.states]

    @property
    def distinct_systems(self) -> int:
        """How many materially different systems the team ever considered."""
        return len({s.signature() for s in self.states})


def _classify(a: ModelState, b: ModelState, rtol: float) -> Transition:
    # Fit -> submission of the identical system is the intended handoff, not a
    # repeat: the engineer measures and the critic ships. See the module
    # docstring for why this is excluded rather than counted.
    if (
        a.source is ModelSource.FIT
        and b.source is ModelSource.SUBMIT
        and a.signature(rtol) == b.signature(rtol)
        and _params_equal(a, b)
    ):
        return Transition.COMMIT
    if b.n_planets > a.n_planets:
        return Transition.ESCALATE
    if b.n_planets < a.n_planets:
        return Transition.DESCALATE
    if a.signature(rtol) != b.signature(rtol):
        return Transition.EXPLORE
    # Same count, same periods: did anything move at all?
    if _params_equal(a, b):
        return Transition.REPEAT
    return Transition.REFINE


def _params_equal(a: ModelState, b: ModelState, *, rtol: float = 1e-9) -> bool:
    """Exact-ish equality on the periods, used to separate REPEAT from REFINE.

    Deliberately tight: REFINE means the optimiser actually moved something,
    REPEAT means the identical system came round again. Parameters other than
    period are not compared here because ``rv_submit`` and ``rv_fit`` expose
    different field sets; period is the one both always carry.
    """
    pa = sorted(a.periods)
    pb = sorted(b.periods)
    if len(pa) != len(pb):
        return False
    return all(abs(x - y) <= rtol * max(abs(x), abs(y), 1e-12) for x, y in zip(pa, pb, strict=True))


def build_sequence(
    artifacts: AstroTrialArtifacts,
    *,
    include_fits: bool = True,
    include_submissions: bool = True,
    rtol: float = PERIOD_RTOL,
) -> SequenceReport:
    """Order every hypothesis the team held and classify the moves between them.

    Both fits and submissions are included by default: a team can thrash inside
    the fitting loop without ever submitting, and Stargazer's failure case
    thrashes at the submission layer. Restricting to one source would make the
    metric blind to half the pathology.
    """
    states: list[ModelState] = []

    if include_fits:
        for fit in artifacts.fits:
            if not fit.ok or not fit.planets:
                continue  # a failed fit is not a hypothesis the team held
            states.append(
                ModelState(
                    seq=fit.seq,
                    role=fit.role,
                    source=ModelSource.FIT,
                    periods=fit.periods,
                    n_planets=fit.n_planets,
                    rms_ms=fit.rms_ms,
                )
            )
    if include_submissions:
        for sub in artifacts.submissions:
            if not sub.accepted:
                continue  # malformed: never scored, so not a model state
            states.append(
                ModelState(
                    seq=sub.seq,
                    role=sub.role,
                    source=ModelSource.SUBMIT,
                    periods=sub.periods,
                    n_planets=sub.n_planets,
                    rms_ms=sub.measured.get("rms_ms"),
                    match_score=sub.measured.get("match_score"),
                    solved=sub.solved,
                )
            )

    states.sort(key=lambda s: s.seq)
    transitions = [
        TransitionRecord(from_state=a, to_state=b, kind=_classify(a, b, rtol))
        for a, b in zip(states, states[1:], strict=False)
    ]
    return SequenceReport(states=states, transitions=transitions)


# --------------------------------------------------------------------------
# Misleading self-signal
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SelfSignalReport:
    """Does the team's own quality proxy track the truth, or contradict it?

    Within an episode the team steers on what it can see -- residual RMS -- while
    being graded on what it cannot -- the match score. Comparing the two across
    submissions asks whether its feedback loop points the right way.

    ``misleading`` is the case that matters: RMS improved while match got worse,
    so every signal available to the team endorsed a change that made the answer
    worse. Stargazer measured the statistical/physical dissociation ACROSS
    models; this measures it WITHIN one trajectory, over time.
    """

    n_pairs: int
    rms_deltas: list[float] = field(default_factory=list)
    match_deltas: list[float] = field(default_factory=list)
    n_misleading_steps: int = 0

    @property
    def misleading(self) -> bool:
        return self.n_misleading_steps > 0

    @property
    def agreement(self) -> float | None:
        """Fraction of steps where the proxy and the truth moved together.

        None with fewer than two scored submissions. Low values mean the team's
        visible feedback was actively unhelpful, which is a stronger statement
        than "the team was wrong".
        """
        if not self.n_pairs:
            return None
        agree = sum(
            1
            for dr, dm in zip(self.rms_deltas, self.match_deltas, strict=True)
            # RMS down is good, match up is good.
            if (dr < 0 and dm > 0) or (dr > 0 and dm < 0) or (dr == 0 and dm == 0)
        )
        return agree / self.n_pairs


def analyse_self_signal(artifacts: AstroTrialArtifacts) -> SelfSignalReport:
    """Compare RMS movement against match movement across scored submissions."""
    scored = [
        s
        for s in artifacts.submissions
        if s.accepted and "rms_ms" in s.measured and "match_score" in s.measured
    ]
    rms_deltas: list[float] = []
    match_deltas: list[float] = []
    misleading = 0
    for a, b in zip(scored, scored[1:], strict=False):
        d_rms = b.measured["rms_ms"] - a.measured["rms_ms"]
        d_match = b.measured["match_score"] - a.measured["match_score"]
        rms_deltas.append(d_rms)
        match_deltas.append(d_match)
        if d_rms < 0 and d_match < 0:
            misleading += 1
    return SelfSignalReport(
        n_pairs=len(rms_deltas),
        rms_deltas=rms_deltas,
        match_deltas=match_deltas,
        n_misleading_steps=misleading,
    )


def summarise(report: SequenceReport) -> dict[str, Any]:
    """Flat dict for reporting/serialisation."""
    return {
        "n_states": len(report.states),
        "n_transitions": report.n_transitions,
        "planet_count_path": report.planet_count_path,
        "distinct_systems": report.distinct_systems,
        "revision_ratio": report.revision_ratio,
        "max_consecutive_repeats": report.max_consecutive_repeats,
        **{f"n_{k}": v for k, v in report.counts.items()},
    }
