"""The counterfactual oracle: what the team held, versus what it submitted.

Re-scoring a submission offline would be a tautology in this testbed. Lean has
two oracles -- the in-loop compiler and an independent re-verification -- and the
gap between them defines silent failure. Astro has one: ``rv_submit`` and any
offline re-scoring both call ``evaluate_submission``, so the difference is
identically zero.

The independent judgement has to come from somewhere else, and the natural place
is the set of submissions the team COULD have made. For every successful fit,
enumerate the non-empty subsets of its planets and score each one. Then:

    oracle_best   -- the best-scoring system the team ever had in hand
    best_actual   -- the best it actually submitted
    had_it_and_lost_it -- oracle_best solved, best_actual did not

This is not the validator doing science the team did not do. Dropping an entry
from an ``rv_fit`` result is a submission the team could have made verbatim, by
deleting a line -- every subset is literally reachable from an artifact already
in its context. That is what keeps the claim defensible: we are selecting among
what the team produced, not producing something new.

The motivating case is real. On seed53_diff5 the very first fit contained the
true planet at 10.53 d alongside a spurious 2.41 d one; the team submitted both,
failed on count, then escalated to three planets and failed worse. Stripping the
count penalty (-0.25 * |dn|, folded into ``components['match']``) shows the
orbital recovery was never the problem: the two-planet submission scores ~0.97 on
match alone, the three-planet ~0.92, both far above the 0.8 threshold. The
subset {10.53 d} was in hand at event #5.

Cost: with the fitter capped at 6 planets, a fit yields at most 63 subsets, each
one forward-model evaluation. Milliseconds, no LLM, no network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Any

from traj_eval.metrics.astro.artifacts import AstroTrialArtifacts
from traj_eval.metrics.astro.criteria import AstroCriteria, best_criteria
from traj_eval.metrics.astro.evaluate import SubmissionShapeError, score_submission

# Guard against a pathological trace: 2**n subsets, so refuse absurd n rather
# than hanging. The fitter caps at 6, so this only trips on malformed input.
MAX_SUBSET_PLANETS = 8


@dataclass(frozen=True)
class Candidate:
    """One system the team could have submitted, with its score."""

    seq: int  # the fit (or submission) it came from
    source: str  # 'fit' | 'submitted'
    planets: list[dict[str, Any]]
    criteria: AstroCriteria

    @property
    def n_planets(self) -> int:
        return len(self.planets)

    @property
    def periods(self) -> list[float]:
        return sorted(float(p.get("P_days", float("nan"))) for p in self.planets)

    @property
    def match_without_count_penalty(self) -> float | None:
        """Match score with the -0.25*|dn| count term added back.

        ``components['match']`` already contains the count penalty, so a
        submission with the right orbits but the wrong number of planets looks
        far worse on match than its orbital recovery warrants. Removing it
        separates "wrong orbits" from "wrong count" -- the distinction that made
        seed53 legible.
        """
        if self.criteria.match_score is None or self.criteria.count_term is None:
            return None
        return self.criteria.match_score + 0.25 * abs(self.criteria.count_term)


@dataclass(frozen=True)
class OracleReport:
    """What the team held versus what it submitted."""

    n_candidates: int
    best_reachable: Candidate | None = None
    best_submitted: Candidate | None = None
    solved_candidates: list[Candidate] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def reachable_solved(self) -> bool:
        return self.best_reachable is not None and self.best_reachable.criteria.solved

    @property
    def submitted_solved(self) -> bool:
        return self.best_submitted is not None and self.best_submitted.criteria.solved

    @property
    def had_it_and_lost_it(self) -> bool:
        """The team produced a passing system and submitted something else.

        The sharpest single verdict this layer yields: it converts "the trial
        failed" into "the trial failed by SELECTION", which is attributable to a
        specific event, rather than by an inability to fit.
        """
        return self.reachable_solved and not self.submitted_solved

    @property
    def first_solved_seq(self) -> int | None:
        """Trace position at which a passing answer first existed.

        The localisation target for O1: everything after this event was, in
        hindsight, avoidable.
        """
        if not self.solved_candidates:
            return None
        return min(c.seq for c in self.solved_candidates)

    @property
    def match_gap(self) -> float | None:
        """How much match score was left on the table."""
        if self.best_reachable is None or self.best_submitted is None:
            return None
        a = self.best_reachable.criteria.match_score
        b = self.best_submitted.criteria.match_score
        if a is None or b is None:
            return None
        return a - b


def _subsets(planets: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Every non-empty subset, smallest first.

    Smallest-first matters for ``first_solved_seq`` ties and makes the common
    interesting case -- a single true planet buried among spurious ones -- appear
    early in the enumeration.
    """
    out: list[list[dict[str, Any]]] = []
    for size in range(1, len(planets) + 1):
        for combo in combinations(range(len(planets)), size):
            out.append([planets[i] for i in combo])
    return out


def _score(
    planets: list[dict[str, Any]],
    *,
    task: Any,
    truth: Any,
    stargazer_task: Any,
    min_match_score: float | None = None,
) -> AstroCriteria | None:
    try:
        criteria, _ = score_submission(
            {"planets": planets},
            task=task,
            truth=truth,
            stargazer_task=stargazer_task,
            min_match_score=min_match_score,
        )
    except (SubmissionShapeError, ValueError, KeyError, TypeError):
        return None
    return criteria


def run_oracle(
    artifacts: AstroTrialArtifacts,
    *,
    task: Any,
    truth: Any,
    stargazer_task: Any = None,
    include_submitted: bool = True,
    min_match_score: float | None = None,
) -> OracleReport:
    """Score every system reachable from the team's own fits.

    ``include_submitted`` also scores what was actually submitted, so
    ``best_submitted`` is derived by the same path as ``best_reachable`` and the
    two are directly comparable. It reproduces the in-loop verdict, which is a
    useful consistency check -- a disagreement would mean the submitted planet
    list in the trace is not what the tool actually scored.
    """
    candidates: list[Candidate] = []
    errors: list[str] = []
    seen: set[tuple[int, tuple[float, ...]]] = set()

    for fit in artifacts.fits:
        if not fit.ok or not fit.planets:
            continue
        if len(fit.planets) > MAX_SUBSET_PLANETS:
            errors.append(
                f"fit at seq {fit.seq} has {len(fit.planets)} planets; "
                f"skipped (subset enumeration capped at {MAX_SUBSET_PLANETS})"
            )
            continue
        for subset in _subsets(fit.planets):
            key = (fit.seq, tuple(sorted(float(p.get("P_days", 0.0)) for p in subset)))
            if key in seen:
                continue
            seen.add(key)
            criteria = _score(
                subset,
                task=task,
                truth=truth,
                stargazer_task=stargazer_task,
                min_match_score=min_match_score,
            )
            if criteria is None:
                errors.append(f"could not score a subset from the fit at seq {fit.seq}")
                continue
            candidates.append(
                Candidate(seq=fit.seq, source="fit", planets=subset, criteria=criteria)
            )

    submitted: list[Candidate] = []
    if include_submitted:
        for sub in artifacts.submissions:
            if not sub.accepted or not sub.planets:
                continue
            criteria = _score(
                sub.planets,
                task=task,
                truth=truth,
                stargazer_task=stargazer_task,
                min_match_score=min_match_score,
            )
            if criteria is None:
                errors.append(f"could not score the submission at seq {sub.seq}")
                continue
            submitted.append(
                Candidate(seq=sub.seq, source="submitted", planets=sub.planets, criteria=criteria)
            )

    all_candidates = candidates + submitted
    best_reachable = _best(all_candidates)
    best_submitted = _best(submitted)

    return OracleReport(
        n_candidates=len(all_candidates),
        best_reachable=best_reachable,
        best_submitted=best_submitted,
        solved_candidates=[c for c in all_candidates if c.criteria.solved],
        errors=errors,
    )


def _best(candidates: list[Candidate]) -> Candidate | None:
    """Pick the best candidate using the same ordering as ``best_criteria``.

    Ties broken toward the EARLIER trace position and the SMALLER system, so
    ``first_solved_seq`` reports the first moment a passing answer existed and
    the reported candidate is the most parsimonious one.
    """
    if not candidates:
        return None
    best = best_criteria([c.criteria for c in candidates])
    if best is None:
        return None
    matching = [c for c in candidates if c.criteria is best]
    if not matching:  # criteria compared equal but is not the same object
        matching = [
            c
            for c in candidates
            if c.criteria.solved == best.solved and c.criteria.match_score == best.match_score
        ]
    return min(matching, key=lambda c: (c.seq, c.n_planets))


def summarise(report: OracleReport) -> dict[str, Any]:
    """Flat dict for reporting/serialisation."""
    reach, sub = report.best_reachable, report.best_submitted
    return {
        "n_candidates": report.n_candidates,
        "reachable_solved": report.reachable_solved,
        "submitted_solved": report.submitted_solved,
        "had_it_and_lost_it": report.had_it_and_lost_it,
        "first_solved_seq": report.first_solved_seq,
        "match_gap": report.match_gap,
        "best_reachable_periods": reach.periods if reach else None,
        "best_reachable_match": reach.criteria.match_score if reach else None,
        "best_submitted_periods": sub.periods if sub else None,
        "best_submitted_match": sub.criteria.match_score if sub else None,
        "n_errors": len(report.errors),
    }
