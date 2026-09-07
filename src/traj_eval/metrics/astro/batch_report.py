"""Aggregate astro trials into the tables a report needs.

Two layers, deliberately separated:

  LAYER 1 -- Stargazer-comparable. Pass rate, the four per-criterion rates
      conditioned on >=1 submission, and the statistical-vs-physical means. These
      exist so our numbers can sit next to the published baseline; they must
      match their definitions exactly, including best-of-episode scoring and the
      conditioning (their Table 7 reports per-criterion rates "among tasks with
      >=1 submission", which changes the denominator).

  LAYER 2 -- the trajectory contribution. Escalation/repetition statistics,
      critic verification rate, silent-failure mode frequencies. These are what
      Stargazer asserts qualitatively ("successful agents escalate model
      complexity while failed agents repeat") but never measures, because a bare
      PythonREPL leaves the per-step hypothesis unreadable.

Pure: reads trial JSONL files, optionally scores counterfactuals through the
vendored evaluator, and returns dataclasses. It never prints and never decides
how to render, so the CLI and any dashboard read the same numbers.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from traj_eval.metrics.astro.ceiling import MatchCeiling
from traj_eval.metrics.astro.validator import AstroTrialMetrics, validate_astro_trial
from traj_eval.trace_core.storage import read_trial

# astro_<task>.jsonl, or astro_<task>_t<N>.jsonl for repeated trials.
TRIAL_NAME_RE = re.compile(r"^(?:astro_)?(?P<task>.+?)(?:_t(?P<trial>\d+))?\.jsonl$")


def parse_trial_filename(path: Path) -> tuple[str, int] | None:
    m = TRIAL_NAME_RE.match(path.name)
    if not m:
        return None
    return m.group("task"), int(m.group("trial") or 0)


def list_trial_files(folder: Path) -> list[Path]:
    return sorted(p for p in Path(folder).glob("*.jsonl") if parse_trial_filename(p))


@dataclass(frozen=True)
class AstroBatchReport:
    folder: Path
    metrics: list[AstroTrialMetrics] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    # Trials analysed WITHOUT counterfactual scoring because their task could not
    # be loaded. Kept separate from ``skipped``: these trials are in ``metrics``
    # and contribute to every Layer-1 and trace-only Layer-2 number, so calling
    # them skipped would misreport the sample.
    degraded: list[tuple[str, str]] = field(default_factory=list)
    scored_counterfactuals: bool = False
    # task_id -> the best match a maximum-likelihood fitter could achieve. Empty
    # when the cache has not been computed; every ceiling-conditioned number then
    # returns None rather than silently reporting the unconditioned one.
    ceilings: dict[str, MatchCeiling] = field(default_factory=dict)

    # ---- Layer 1: Stargazer-comparable ----

    @property
    def n(self) -> int:
        return len(self.metrics)

    @property
    def pass_rate(self) -> float | None:
        return _frac(sum(1 for m in self.metrics if m.solved), self.n)

    @property
    def submission_rate(self) -> float | None:
        """Fraction reaching a scored submission at all.

        Stargazer reports this separately from pass rate because a large share of
        their failures never submitted -- an agent cut off by budget is a
        different failure from one that submitted the wrong thing.
        """
        return _frac(sum(1 for m in self.metrics if m.has_submission), self.n)

    def criterion_rates(self) -> dict[str, float | None]:
        """Per-criterion pass rates among trials with >=1 submission.

        Conditioning matches their Table 7; without it a batch with many
        no-submission trials reports artificially low criterion rates and is not
        comparable.
        """
        submitted = [m for m in self.metrics if m.has_submission]
        d = len(submitted)
        return {
            "ok_delta_bic": _frac(sum(1 for m in submitted if m.best_ok_delta_bic), d),
            "ok_rms": _frac(sum(1 for m in submitted if m.best_ok_rms), d),
            "ok_match": _frac(sum(1 for m in submitted if m.best_ok_match), d),
            "ok_count": _frac(sum(1 for m in submitted if m.best_ok_count), d),
        }

    def statistical_vs_physical(self) -> dict[str, float | None]:
        """Their headline decomposition: mean of the two statistical criteria
        against the mean of the two physical ones."""
        rates = self.criterion_rates()
        stat = [rates["ok_delta_bic"], rates["ok_rms"]]
        phys = [rates["ok_match"], rates["ok_count"]]
        return {
            "statistical": _mean(stat),
            "physical": _mean(phys),
            "gap": (
                _mean(stat) - _mean(phys)
                if _mean(stat) is not None and _mean(phys) is not None
                else None
            ),
        }

    # ---- Layer 2: trajectory ----

    def trajectory_summary(self) -> dict[str, Any]:
        ratios = [m.revision_ratio for m in self.metrics if m.revision_ratio is not None]
        agreements = [
            m.self_signal_agreement for m in self.metrics if m.self_signal_agreement is not None
        ]
        return {
            "mean_revision_ratio": _mean(ratios),
            "n_with_revision_ratio": len(ratios),
            "mean_self_signal_agreement": _mean(agreements),
            "n_with_self_signal": len(agreements),
            "critic_verified_rate": _frac(
                sum(1 for m in self.metrics if m.critic_verification_calls > 0), self.n
            ),
            "mean_escalations_to_planner": _mean(
                [float(m.n_escalations_to_planner) for m in self.metrics]
            ),
            "mean_distinct_systems": _mean([float(m.distinct_systems) for m in self.metrics]),
            "any_repeat_rate": _frac(
                sum(1 for m in self.metrics if m.max_consecutive_repeats > 0), self.n
            ),
        }

    def revision_ratio_by_outcome(self) -> dict[str, float | None]:
        """The direct test of Stargazer's escalate-vs-repeat claim.

        Their claim predicts solved trials revise more than failed ones. This is
        the number that confirms or refutes it.
        """
        solved = [
            m.revision_ratio for m in self.metrics if m.solved and m.revision_ratio is not None
        ]
        failed = [
            m.revision_ratio for m in self.metrics if not m.solved and m.revision_ratio is not None
        ]
        return {
            "solved": _mean(solved),
            "failed": _mean(failed),
            "n_solved": len(solved),
            "n_failed": len(failed),
        }

    # ---- ceiling-conditioned: the honest denominators --------------------

    def _with_ceiling(self) -> list[tuple[AstroTrialMetrics, MatchCeiling]]:
        return [(m, self.ceilings[m.task_id]) for m in self.metrics if m.task_id in self.ceilings]

    @property
    def has_ceilings(self) -> bool:
        return bool(self.ceilings)

    def solvability(self) -> dict[str, Any]:
        """How much of the failure is the benchmark rather than the agents.

        ``pass_rate_solvable`` is the number that actually measures the agents:
        an unsolvable task cannot be passed by any fitting procedure, so counting
        it as a failure measures the benchmark's threshold, not the team.
        """
        pairs = self._with_ceiling()
        if not pairs:
            return {}
        solvable = [m for m, c in pairs if c.ceiling_solved]
        unsolvable = [m for m, c in pairs if not c.ceiling_solved]
        deficits = [
            c.deficit_for(m.best_match_score)
            for m, c in pairs
            if c.deficit_for(m.best_match_score) is not None
        ]
        # A trial cannot legitimately beat the ceiling: the ceiling is the best a
        # fitter can do. When one does, the ceiling search settled in a poor
        # basin and the task's "unsolvable" label is wrong -- which would convert
        # agent successes into impossible tasks. Surfaced, never absorbed.
        beat = [
            (m.trial_id, c.task_id, m.best_match_score, c.ceiling_match)
            for m, c in pairs
            if c.deficit_for(m.best_match_score) is not None
            and c.deficit_for(m.best_match_score) < -1e-3
        ]
        # A trial that hit the ceiling did everything a fitter could: any
        # remaining shortfall is the threshold, not the reasoning.
        at_ceiling = [d for d in deficits if d <= 1e-6]
        return {
            "n_with_ceiling": len(pairs),
            "n_on_solvable_tasks": len(solvable),
            "n_on_unsolvable_tasks": len(unsolvable),
            "unsolvable_trial_share": _frac(len(unsolvable), len(pairs)),
            "pass_rate_all": _frac(sum(1 for m, _ in pairs if m.solved), len(pairs)),
            "pass_rate_solvable": _frac(sum(1 for m in solvable if m.solved), len(solvable)),
            "pass_rate_unsolvable": _frac(sum(1 for m in unsolvable if m.solved), len(unsolvable)),
            "mean_match_deficit": _mean(deficits),
            "at_ceiling_rate": _frac(len(at_ceiling), len(deficits)),
            "n_trials_beating_ceiling": len(beat),
            "tasks_with_bad_ceiling": sorted({task_id for _, task_id, _, _ in beat}),
        }

    def period_anchor_summary(self) -> dict[str, Any]:
        """Aggregate period-selection results across the batch.

        ``localised_rate`` is the O1 headline: the fraction of failures whose
        first anchor violation can be attributed to a specific event and agent.
        """
        checked = [m for m in self.metrics if m.n_periods_checked is not None]
        if not checked:
            return {}
        total = sum(m.n_periods_checked or 0 for m in checked)
        violations = sum(m.n_period_violations or 0 for m in checked)
        labels: Counter[str] = Counter()
        for m in checked:
            labels.update(m.period_label_counts or {})
        # Attribute by ORIGIN (whose decision) rather than by who made the tool
        # call: the engineer executes the planner's hypothesis, so counting the
        # caller would credit every period error to the engineer.
        by_role: Counter[str] = Counter(
            m.first_period_violation_origin_role
            for m in checked
            if m.first_period_violation_origin_role
        )
        failed = [m for m in checked if not m.solved]
        return {
            "n_trials_with_anchor": len(checked),
            "n_periods_checked": total,
            "n_period_violations": violations,
            "period_violation_rate": _frac(violations, total),
            "label_counts": dict(labels),
            "first_violation_by_origin_role": dict(by_role),
            "localised_rate": _frac(
                sum(1 for m in failed if m.first_period_violation_seq is not None),
                len(failed),
            ),
            "found_all_true_rate": _frac(
                sum(1 for m in checked if not m.missed_true_periods), len(checked)
            ),
        }

    def flag_counts(self) -> dict[str, int]:
        """How often each silent-failure mode fired across the batch."""
        counter: Counter[str] = Counter()
        for m in self.metrics:
            for name in m.flags.fired:
                counter[name] += 1
        return dict(counter)

    @property
    def silent_failure_rate(self) -> float | None:
        return _frac(sum(1 for m in self.metrics if m.silent_failure), self.n)

    @property
    def had_it_and_lost_it_rate(self) -> float | None:
        """Among failures, how many held a passing answer and discarded it.

        The most actionable number this layer produces: it separates failures of
        SELECTION from failures of FITTING, which is the difference between "the
        team could not do the science" and "the team could, and chose wrong".
        """
        if not self.scored_counterfactuals:
            return None
        # Only trials that actually got scored can answer this.
        failed = [m for m in self.metrics if not m.solved and m.had_it_and_lost_it is not None]
        return _frac(sum(1 for m in failed if m.had_it_and_lost_it), len(failed))


def _frac(num: int, den: int) -> float | None:
    return num / den if den else None


def _mean(values: list[float | None]) -> float | None:
    clean = [v for v in values if v is not None]
    return sum(clean) / len(clean) if clean else None


def analyse_astro_batch(
    folder: Path | str,
    *,
    load_task: Any = None,
    ceilings: dict[str, MatchCeiling] | None = None,
) -> AstroBatchReport:
    """Validate every trial in ``folder``.

    ``load_task`` is an optional callable ``task_id -> (task, truth)``. When
    given, counterfactual scoring runs and the Group-B metrics are populated;
    when omitted, Layer 1 and the trace-only parts of Layer 2 still work with no
    dataset present. Injected rather than imported so a caller that only wants
    the offline signal pays nothing for the evaluator.
    """
    folder = Path(folder)
    metrics: list[AstroTrialMetrics] = []
    skipped: list[tuple[str, str]] = []
    degraded: list[tuple[str, str]] = []
    scored = False

    for path in list_trial_files(folder):
        try:
            meta, events = read_trial(path)
        except Exception as exc:  # noqa: BLE001 - one bad file must not abort the batch
            skipped.append((path.name, f"{type(exc).__name__}: {exc}"))
            continue

        task = truth = None
        if load_task is not None:
            try:
                task, truth = load_task(meta.task_id)
                scored = True
            except Exception as exc:  # noqa: BLE001
                # Trace-only analysis still runs; record the downgrade, not a skip.
                degraded.append((path.name, f"{type(exc).__name__}: {exc}"))

        try:
            metrics.append(
                validate_astro_trial(
                    events,
                    trial_id=meta.trial_id,
                    task_id=meta.task_id,
                    task=task,
                    truth=truth,
                    # Score counterfactuals against the gate the trial actually
                    # faced, not the default: a relaxed run analysed at 0.80
                    # would report reachable answers the team was never offered.
                    min_match_score=(meta.config or {}).get("min_match_score"),
                )
            )
        except Exception as exc:  # noqa: BLE001
            skipped.append((path.name, f"validate {type(exc).__name__}: {exc}"))

    return AstroBatchReport(
        folder=folder,
        metrics=metrics,
        skipped=skipped,
        degraded=degraded,
        scored_counterfactuals=scored,
        ceilings=dict(ceilings or {}),
    )
