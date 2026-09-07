"""Analyse completed astro trials offline. No agent, no LLM, no API cost.

Reads traces written by ``run_astro_task.py`` and reports:

  * the Stargazer-comparable outcome table (pass rate, per-criterion rates,
    statistical-vs-physical gap);
  * the trajectory metrics that operationalise their escalate-vs-repeat claim;
  * the silent-failure modes, per trial and aggregated.

Counterfactual scoring (``had_it_and_lost_it``) needs the task bank, so it is
enabled only when the prepared dataset is present; everything else works from
the trace alone. Because this costs nothing to run, re-analysing a trial after
changing a detector is free -- which is the point of writing the trace in the
first place.

Usage:
    uv run python scripts/analyse_astro_trials.py data/runs
    uv run python scripts/analyse_astro_trials.py data/runs/astro_seed53_diff5.jsonl
    uv run python scripts/analyse_astro_trials.py data/runs --no-oracle
    uv run python scripts/analyse_astro_trials.py data/runs --json out.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from traj_eval.anchors.astro.period_selection import run_period_anchor
from traj_eval.metrics.astro.artifacts import extract_astro_artifacts
from traj_eval.metrics.astro.batch_report import analyse_astro_batch
from traj_eval.metrics.astro.ceiling import ceilings_path, load_ceilings
from traj_eval.metrics.astro.sequence import build_sequence
from traj_eval.metrics.astro.validator import validate_astro_trial
from traj_eval.trace_core.storage import read_trial


def _make_loader(enabled: bool):
    """Return a ``task_id -> (task, truth)`` callable, or None.

    Imported lazily so a checkout without the prepared dataset can still run the
    trace-only analysis instead of failing at import time.
    """
    if not enabled:
        return None
    try:
        from traj_eval.dataset.astro_loader import load_astro_task
    except ImportError:
        return None

    def load(task_id: str):
        for kind in ("synthetic", "real"):
            try:
                return load_astro_task(task_id, kind=kind)
            except Exception:  # noqa: BLE001 - try the other bank, then give up
                continue
        raise KeyError(f"task {task_id!r} not found in either bank")

    return load


# Cache so the detailed per-period view does not recompute the anchor.
_ANCHOR_CACHE: dict[str, list] = {}


def run_period_anchor_fits(path, metrics):
    """Per-fit anchor verdicts for the detailed view (already computed once)."""
    return _ANCHOR_CACHE.get(str(path), [])


def _fmt(value, spec: str = ".3f") -> str:
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return format(value, spec)
    return str(value)


def _pct(value) -> str:
    return "n/a" if value is None else f"{100.0 * value:5.1f}%"


def report_trial(path: Path, load_task, override: float | None = None) -> int:
    """Detailed view of one trial: the trajectory, then the verdict."""
    meta, events = read_trial(path)
    artifacts = extract_astro_artifacts(events, trial_id=meta.trial_id, task_id=meta.task_id)
    sequence = build_sequence(artifacts)

    task = truth = None
    if load_task is not None:
        try:
            task, truth = load_task(meta.task_id)
        except Exception as exc:  # noqa: BLE001
            print(f"(counterfactual scoring unavailable: {exc})\n")

    m = validate_astro_trial(
        events,
        trial_id=meta.trial_id,
        task_id=meta.task_id,
        task=task,
        truth=truth,
        min_match_score=override
        if override is not None
        else (meta.config or {}).get("min_match_score"),
    )
    if task is not None and truth is not None:
        _ANCHOR_CACHE[str(path)] = run_period_anchor(artifacts, task=task, truth=truth).fits

    print(f"=== {m.task_id}  ({path.name}) ===")
    cfg = meta.config or {}
    if cfg:
        print(
            f"    tier={cfg.get('tier')} difficulty={cfg.get('difficulty')} "
            f"n_obs={cfg.get('n_obs')} truth_planets={cfg.get('n_truth_planets')}"
        )

    print("\n  -- tool activity --")
    print(f"    calls: {m.tool_call_counts}  (total {m.n_tool_calls})")
    print(
        f"    fits: {m.n_fits} ({m.n_failed_fits} failed)   "
        f"submissions: {m.n_submissions} ({m.n_malformed_submissions} malformed)"
    )
    print(f"    critic verification calls: {m.critic_verification_calls}")
    print(f"    engineer->planner escalations: {m.n_escalations_to_planner}")

    print("\n  -- model sequence --")
    for state in sequence.states:
        periods = ", ".join(f"{p:.4g}" for p in state.periods)
        extra = ""
        if state.match_score is not None:
            extra = f"  match={state.match_score:+.3f} solved={state.solved}"
        elif state.rms_ms is not None:
            extra = f"  rms={state.rms_ms:.3f}"
        print(
            f"    #{state.seq:<3} {state.role:9s} {state.source.value:6s} "
            f"n={state.n_planets} P=[{periods}]{extra}"
        )
    if sequence.transitions:
        print("    transitions: " + ", ".join(t.kind.value for t in sequence.transitions))
    print(
        f"    revision_ratio={_fmt(m.revision_ratio)}  "
        f"max_consecutive_repeats={m.max_consecutive_repeats}  "
        f"distinct_systems={m.distinct_systems}"
    )
    print(f"    self-signal agreement: {_fmt(m.self_signal_agreement)}")

    print("\n  -- outcome --")
    print(f"    solved: {m.solved}   declared_success: {m.declared_success}")
    if m.best_match_score is not None:
        print(
            f"    best submission: match={m.best_match_score:+.4f} "
            f"rms={_fmt(m.best_rms_ms)}  "
            f"bic={_fmt(m.best_ok_delta_bic)} rms_ok={_fmt(m.best_ok_rms)} "
            f"match_ok={_fmt(m.best_ok_match)} count_ok={_fmt(m.best_ok_count)}"
        )

    if m.reachable_solved is not None:
        print("\n  -- counterfactual --")
        print(
            f"    a passing system was reachable from the team's own fits: "
            f"{_fmt(m.reachable_solved)}"
        )
        if m.best_reachable_periods:
            print(f"    best reachable: P={[round(p, 4) for p in m.best_reachable_periods]}")
        print(
            f"    had_it_and_lost_it: {_fmt(m.had_it_and_lost_it)}"
            + (
                f"   (first available at event #{m.first_solved_seq})"
                if m.first_solved_seq is not None
                else ""
            )
        )
        if m.match_gap is not None:
            print(f"    match left on the table: {m.match_gap:+.4f}")

    if m.n_periods_checked is not None:
        print("\n  -- period-selection anchor --")
        print(
            f"    periods checked: {m.n_periods_checked}   " f"violations: {m.n_period_violations}"
        )
        counts = {k: v for k, v in (m.period_label_counts or {}).items() if v}
        print(f"    labels: {counts}")
        for fit in run_period_anchor_fits(path, m):
            for v in fit.verdicts:
                mark = "X" if v.is_violation else "."
                fap = "" if v.fap_at_selection is None else f" (FAP {v.fap_at_selection:.3f})"
                print(
                    f"      {mark} #{fit.seq:<3} {fit.role:9s} "
                    f"{v.period_days:9.4f} d -> {v.label.value.upper():9s}{fap}"
                )
        if m.first_period_violation_seq is not None:
            origin = m.first_period_violation_origin_role
            caller = m.first_period_violation_role
            attribution = (
                f"decision by the {origin}, executed by the {caller}"
                if origin and origin != caller
                else f"by the {caller}"
            )
            print(
                f"    FIRST VIOLATION at event #{m.first_period_violation_seq} " f"({attribution})"
            )
        if m.missed_true_periods:
            print(
                f"    true periods never proposed: "
                f"{[round(p, 4) for p in m.missed_true_periods]}"
            )

    fired = m.flags.fired
    print("\n  -- silent-failure modes --")
    print("    " + (", ".join(fired) if fired else "none"))
    print(f"    silent_failure (unsolved AND a mode fired): {m.silent_failure}")
    print()
    return 0


def _load_ceilings():
    """The ceiling cache, or {} when it has not been computed."""
    try:
        from traj_eval.dataset.astro_bank import dataset_root

        return load_ceilings(ceilings_path(dataset_root()))
    except Exception:  # noqa: BLE001 - absent cache must never break analysis
        return {}


def report_batch(folder: Path, load_task, json_path: Path | None) -> int:
    report = analyse_astro_batch(folder, load_task=load_task, ceilings=_load_ceilings())
    if not report.metrics:
        print(f"No readable trials in {folder}")
        for name, err in report.skipped:
            print(f"  skipped {name}: {err}")
        return 1

    print(f"=== {report.n} trial(s) in {folder} ===\n")

    print("-- Layer 1: Stargazer-comparable --")
    print(f"  pass rate       : {_pct(report.pass_rate)}")
    print(f"  submission rate : {_pct(report.submission_rate)}")
    rates = report.criterion_rates()
    print("  per-criterion (among trials with >=1 submission):")
    for name in ("ok_delta_bic", "ok_rms", "ok_match", "ok_count"):
        print(f"      {name:14s} {_pct(rates[name])}")
    sp = report.statistical_vs_physical()
    print(
        f"  statistical {_pct(sp['statistical'])}   physical {_pct(sp['physical'])}"
        f"   gap {_pct(sp['gap'])}"
    )

    print("\n-- Layer 2: trajectory --")
    traj = report.trajectory_summary()
    print(
        f"  mean revision ratio      : {_fmt(traj['mean_revision_ratio'])} "
        f"(n={traj['n_with_revision_ratio']})"
    )
    by = report.revision_ratio_by_outcome()
    print(
        f"      solved {_fmt(by['solved'])} (n={by['n_solved']})   "
        f"failed {_fmt(by['failed'])} (n={by['n_failed']})"
    )
    print(f"  critic verified          : {_pct(traj['critic_verified_rate'])}")
    print(f"  any repeated system      : {_pct(traj['any_repeat_rate'])}")
    print(f"  mean distinct systems    : {_fmt(traj['mean_distinct_systems'])}")
    print(f"  mean escalations->planner: {_fmt(traj['mean_escalations_to_planner'])}")
    print(
        f"  self-signal agreement    : {_fmt(traj['mean_self_signal_agreement'])} "
        f"(n={traj['n_with_self_signal']})"
    )

    solv = report.solvability()
    if solv:
        print("\n-- solvability (ceiling-conditioned) --")
        print(
            f"  trials on solvable tasks   : {solv['n_on_solvable_tasks']}"
            f"/{solv['n_with_ceiling']}"
        )
        print(
            f"  trials on UNSOLVABLE tasks : {solv['n_on_unsolvable_tasks']} "
            f"({_pct(solv['unsolvable_trial_share'])})"
        )
        print(f"  pass rate, all tasks       : {_pct(solv['pass_rate_all'])}")
        print(
            f"  pass rate, SOLVABLE only   : {_pct(solv['pass_rate_solvable'])}   "
            f"<- measures the agents"
        )
        print(f"  mean match deficit         : {_fmt(solv['mean_match_deficit'])}")
        print(f"  hit the ceiling exactly    : {_pct(solv['at_ceiling_rate'])}")
        if solv.get("n_trials_beating_ceiling"):
            print(
                f"  !! {solv['n_trials_beating_ceiling']} trial(s) BEAT the ceiling on "
                f"{len(solv['tasks_with_bad_ceiling'])} task(s): "
                f"{', '.join(solv['tasks_with_bad_ceiling'])}"
            )
            print(
                "     the ceiling search missed the optimum there; recompute with "
                "--force before trusting their labels"
            )
    else:
        print("\n-- solvability: no ceiling cache " "(run scripts/compute_match_ceilings.py) --")

    anchor = report.period_anchor_summary()
    if anchor:
        print("\n-- period-selection anchor --")
        print(
            f"  periods checked          : {anchor['n_periods_checked']} "
            f"across {anchor['n_trials_with_anchor']} trial(s)"
        )
        print(f"  violation rate           : {_pct(anchor['period_violation_rate'])}")
        print(
            f"  labels                   : "
            f"{ {k: v for k, v in anchor['label_counts'].items() if v} }"
        )
        print(f"  found all true periods   : {_pct(anchor['found_all_true_rate'])}")
        print(f"  failures localised (O1)  : {_pct(anchor['localised_rate'])}")
        if anchor["first_violation_by_origin_role"]:
            print(f"  first violation by origin: " f"{anchor['first_violation_by_origin_role']}")

    print("\n-- silent-failure modes --")
    counts = report.flag_counts()
    if counts:
        for name, count in sorted(counts.items(), key=lambda kv: -kv[1]):
            print(f"  {name:30s} {count:3d}/{report.n}  ({_pct(count / report.n)})")
    else:
        print("  none fired")
    print(f"  silent_failure rate           : {_pct(report.silent_failure_rate)}")
    if report.scored_counterfactuals:
        print(f"  had_it_and_lost_it (of fails) : {_pct(report.had_it_and_lost_it_rate)}")

    if report.degraded:
        print(f"\n-- {len(report.degraded)} trial(s) analysed without counterfactual scoring --")
        for name, why in report.degraded:
            print(f"  {name}: {why}")

    if report.skipped:
        print(f"\n-- skipped {len(report.skipped)} file(s) --")
        for name, err in report.skipped:
            print(f"  {name}: {err}")

    if json_path is not None:
        payload = {
            "folder": str(folder),
            "n": report.n,
            "pass_rate": report.pass_rate,
            "submission_rate": report.submission_rate,
            "criterion_rates": report.criterion_rates(),
            "statistical_vs_physical": report.statistical_vs_physical(),
            "trajectory": report.trajectory_summary(),
            "revision_ratio_by_outcome": report.revision_ratio_by_outcome(),
            "flag_counts": report.flag_counts(),
            "period_anchor": report.period_anchor_summary(),
            "solvability": report.solvability(),
            "silent_failure_rate": report.silent_failure_rate,
            "had_it_and_lost_it_rate": report.had_it_and_lost_it_rate,
            "trials": [m.as_dict() for m in report.metrics],
        }
        json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nwrote {json_path}")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="a trial .jsonl, or a folder of them")
    parser.add_argument(
        "--no-oracle",
        action="store_true",
        help="skip counterfactual scoring (trace-only; no task bank needed)",
    )
    parser.add_argument("--json", type=Path, default=None, help="also write a JSON summary")
    parser.add_argument(
        "--min-match-score",
        type=float,
        default=None,
        help="override the match gate; by default each trial is analysed at the "
        "threshold recorded in its own meta, which is almost always what you want",
    )
    args = parser.parse_args(argv)

    load_task = _make_loader(not args.no_oracle)
    if args.path.is_file():
        return report_trial(args.path, load_task, args.min_match_score)
    if args.path.is_dir():
        return report_batch(args.path, load_task, args.json)
    print(f"No such file or directory: {args.path}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
