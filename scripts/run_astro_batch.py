"""Batch runner for the astro testbed: N trials over a difficulty tier.

The astro counterpart of ``run_batch.py``. It writes into the same on-disk layout
the dashboard already reads -- ``data/batch/<batch>/<task_id>_t<N>.jsonl`` plus a
``config.json`` -- so astro batches appear alongside Lean ones with no dashboard
changes.

Outcome classification (mutually exclusive, checked in order):
  * no_submission  -- the team never reached a scored submission (ran out of
                      turns, or got stuck first). Kept separate because it is a
                      different failure from submitting the wrong thing, and
                      Stargazer reports the two separately for the same reason:
                      an agent cut off by budget tells you about the budget, not
                      about its science.
  * solved         -- best-of-episode passes all four criteria.
  * silent_failure -- unsolved, and at least one named failure mode fired.
  * unsolved       -- submitted, failed, nothing diagnostic fired.

Resumable by design: a trial whose log already exists is skipped, so an
interrupted batch resumes instead of re-paying for completed work. Use
``--force`` to re-run.

Usage:
    uv run python scripts/run_astro_batch.py --tier medium --dry-run
    TRAJ_EVAL_MODEL=gpt-4o-mini uv run python scripts/run_astro_batch.py \
        --tier medium --trials 3 --min-planets 2
    TRAJ_EVAL_MODEL=gpt-4o-mini uv run python scripts/run_astro_batch.py \
        --tier hard --trials 2 --max-turns 90 --max-submissions 10
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from traj_eval.agents import (
    RoutingLedger,
    StepContext,
    TraceObserver,
    build_llm_config,
    make_trial_meta,
)
from traj_eval.agents.astro_team import (
    astro_task_prompt,
    build_astro_free_team,
    build_astro_tools,
)
from traj_eval.agents.free_routing import finalize_run
from traj_eval.dataset.astro_bank import (
    AstroDatasetError,
    dataset_root,
    list_task_files,
    read_task_file,
)
from traj_eval.dataset.astro_loader import split_task
from traj_eval.metrics.astro.batch_report import analyse_astro_batch
from traj_eval.metrics.astro.ceiling import ceilings_path, load_ceilings
from traj_eval.metrics.astro.criteria import (
    DEFAULT_MIN_MATCH_SCORE,
    threshold_for_tolerance,
)
from traj_eval.metrics.astro.validator import validate_astro_trial
from traj_eval.trace_core.storage import TrialLogWriter, read_trial

BATCH_ROOT = Path("data/batch")

# Turn budgets per tier. Sized so a team that spends its whole submission budget
# terminates for a scientific reason rather than a clock one: an observed
# submission cycle costs roughly 7 events, and the no-progress (6) and
# identical-call (4) bounds catch genuine thrashing long before these.
DEFAULT_MAX_TURNS = {"easy": 30, "medium": 50, "hard": 90, "real": 90}


def _pct(value: float | None) -> str:
    """Percentage, or 'n/a'.

    Every rate in the batch report is legitimately None on a small or degenerate
    batch -- a single trial that never submitted leaves critic_verified_rate and
    the per-criterion rates undefined, since their denominator is zero. Formatting
    those with ':.1%' raised a TypeError that swallowed the rest of the report,
    which is exactly the case you hit while debugging.
    """
    return "n/a" if value is None else f"{100.0 * value:.1f}%"


def _fmt(value: float | None, spec: str = ".3f") -> str:
    return "n/a" if value is None else format(value, spec)


@dataclass
class TrialOutcome:
    task_id: str
    tier: str
    difficulty: int
    trial: int
    outcome: str
    termination: str | None
    n_tool_calls: int
    n_submissions: int
    solved: bool
    had_it_and_lost_it: bool | None
    n_period_violations: int | None
    max_idle_messages_seen: int = 0
    cycle_period: int = 0
    max_tool_errors_seen: int = 0
    flags: list[str] = field(default_factory=list)
    tool_counts: dict[str, int] = field(default_factory=dict)


def _classify(metrics) -> str:
    if metrics.solved:
        return "solved"
    if not metrics.has_submission:
        return "no_submission"
    if metrics.silent_failure:
        return "silent_failure"
    return "unsolved"


def _solvable_task_ids(threshold: float) -> set[str] | None:
    """Task ids whose ML reference match clears ``threshold``.

    Reads the cache written by scripts/compute_match_ceilings.py. Returns None
    when the cache is absent, which callers treat as "no filter available"
    rather than "nothing is solvable" -- silently running zero tasks because a
    cache was missing would be the worst possible failure here.

    Note the reference is re-thresholded here rather than trusting the cached
    ``ceiling_solved`` flag, so a batch at a relaxed threshold selects the tasks
    that are reachable AT THAT threshold without recomputing the sweep.
    """
    cache = load_ceilings(ceilings_path(dataset_root()))
    if not cache:
        return None
    return {
        task_id
        for task_id, c in cache.items()
        if c.ceiling_match is not None and c.ceiling_match >= threshold
    }


def _select_tasks(
    tiers: list[str],
    kind: str,
    min_planets: int,
    limit: int | None,
    *,
    max_difficulty: int | None = None,
    solvable: set[str] | None = None,
    task_ids: set[str] | None = None,
):
    """Load and filter the task slice, returning (task, truth, stargazer_task)."""
    selected = []
    for path in list_task_files(kind):
        try:
            raw = read_task_file(path)
        except AstroDatasetError as exc:
            print(f"  skipping {path.name}: {exc}")
            continue
        task, truth = split_task(raw, kind=kind)
        # An explicit id list bypasses every other filter: naming a task means
        # you want that task, not that task if it also happens to pass the
        # tier/planet/solvability screens.
        if task_ids is not None:
            if task.task_id in task_ids:
                selected.append((task, truth, raw))
            continue
        if tiers and task.tier not in tiers:
            continue
        if max_difficulty is not None and task.difficulty > max_difficulty:
            continue
        # Tasks whose maximum-likelihood reference cannot clear the match gate
        # cannot be passed by any fitting procedure, so a failure there measures
        # the benchmark rather than the agents.
        if solvable is not None and task.task_id not in solvable:
            continue
        # Single-planet tasks cannot exercise escalation, count decisions, or
        # alias confusion between planets, so they produce near-empty
        # trajectories. Filtering on planet count is a better selector than tier.
        if truth.n_planets < min_planets:
            continue
        selected.append((task, truth, raw))
    selected.sort(key=lambda t: (t[0].difficulty, t[0].task_id))
    return selected[:limit] if limit else selected


def run_one_trial(
    task,
    truth,
    stargazer_task,
    trial: int,
    *,
    out_dir: Path,
    max_turns: int,
    max_submissions: int | None,
    epoch_hint: bool,
    min_match_score: float | None = None,
) -> TrialOutcome:
    trial_id = f"{task.task_id}_t{trial}"
    log_path = out_dir / f"{trial_id}.jsonl"

    tools, submit_tool = build_astro_tools(
        task,
        truth,
        stargazer_task=stargazer_task,
        max_attempts=max_submissions,
        min_match_score=min_match_score,
    )
    llm_config = build_llm_config()
    ledger = RoutingLedger()
    step_context = StepContext()
    manager, user, groupchat, run_state = build_astro_free_team(
        llm_config,
        tools=tools,
        max_turns=max_turns,
        epoch_hint=epoch_hint,
        ledger=ledger,
        step_context=step_context,
    )

    meta = make_trial_meta(
        trial_id=trial_id,
        task_id=task.task_id,
        backbone=os.environ.get("TRAJ_EVAL_MODEL", "gpt-4o-mini"),
        testbed="astro",
        grounding=epoch_hint,
        config={
            "kind": task.kind,
            "difficulty": task.difficulty,
            "tier": task.tier,
            "max_submissions": submit_tool.max_attempts,
            "max_turns": max_turns,
            "n_obs": task.observation.n_obs,
            "n_truth_planets": truth.n_planets,
            "trial": trial,
            # Recorded so offline analysis scores counterfactuals against the
            # same gate the team faced.
            "min_match_score": submit_tool.min_match_score,
        },
    )
    writer = TrialLogWriter(log_path, meta)
    observer = TraceObserver(writer, trial_id=trial_id, ledger=ledger, step_context=step_context)
    observer.attach([a for a in groupchat.agents if a.name != "user"])

    prompt = astro_task_prompt(task)
    observer.record_task(prompt)
    user.initiate_chat(manager, message=prompt, clear_history=True)
    writer.close()
    finalize_run(run_state)

    _, events = read_trial(log_path)
    metrics = validate_astro_trial(
        events,
        trial_id=trial_id,
        task_id=task.task_id,
        task=task,
        truth=truth,
        stargazer_task=stargazer_task,
        min_match_score=min_match_score,
    )
    return TrialOutcome(
        task_id=task.task_id,
        tier=task.tier,
        difficulty=task.difficulty,
        trial=trial,
        outcome=_classify(metrics),
        termination=run_state.reason,
        max_idle_messages_seen=run_state.max_idle_messages_seen,
        cycle_period=run_state.cycle_period,
        max_tool_errors_seen=run_state.max_tool_errors_seen,
        n_tool_calls=metrics.n_tool_calls,
        n_submissions=metrics.n_submissions,
        solved=metrics.solved,
        had_it_and_lost_it=metrics.had_it_and_lost_it,
        n_period_violations=metrics.n_period_violations,
        flags=metrics.flags.fired,
        tool_counts=dict(metrics.tool_call_counts),
    )


def _write_config(
    out_dir: Path, args, n_tasks: int, tiers: list[str], effective_threshold: float
) -> None:
    """The config.json the dashboard's batch discovery reads."""
    payload = {
        "phase": args.phase,
        "arm_id": args.arm_id,
        "testbed": "astro",
        "models": {"backbone": os.environ.get("TRAJ_EVAL_MODEL", "gpt-4o-mini")},
        "trials_per_task": args.trials,
        "tiers": tiers,
        "kind": args.kind,
        "min_planets": args.min_planets,
        "max_turns": args.max_turns,
        "max_submissions": args.max_submissions,
        "epoch_hint": args.epoch_hint,
        "min_match_score": args.min_match_score,
        "tolerance": args.tolerance,
        "effective_match_threshold": effective_threshold,
        "solvable_only": args.solvable_only,
        "max_difficulty": args.max_difficulty,
        "n_tasks": n_tasks,
        "created_at": datetime.now(UTC).isoformat(),
    }
    (out_dir / "config.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--tier",
        nargs="+",
        default=["medium"],
        choices=("easy", "medium", "hard", "real"),
        help="difficulty tiers to run",
    )
    ap.add_argument("--kind", default="synthetic", choices=("synthetic", "real"))
    ap.add_argument("--trials", type=int, default=3, help="trials per task")
    ap.add_argument(
        "--max-turns",
        type=int,
        default=None,
        help="turn cap; defaults per tier (easy 30, medium 50, hard/real 90)",
    )
    ap.add_argument(
        "--max-submissions",
        type=int,
        default=None,
        help="override the tier's submission budget (easy 3, medium 5, hard 10)",
    )
    ap.add_argument(
        "--min-planets",
        type=int,
        default=1,
        help="skip tasks with fewer true planets; 2 selects the informative ones",
    )
    ap.add_argument(
        "--task-id",
        nargs="+",
        default=None,
        help="run these task ids only, ignoring the tier/planet/solvable filters",
    )
    ap.add_argument("--limit", type=int, default=None, help="cap the number of tasks")
    ap.add_argument(
        "--max-difficulty",
        type=int,
        default=None,
        help="skip tasks above this difficulty (1-10)",
    )
    ap.add_argument(
        "--solvable-only",
        action="store_true",
        help="only tasks whose ML reference match clears the threshold "
        "(needs scripts/compute_match_ceilings.py)",
    )
    ap.add_argument(
        "--min-match-score",
        type=float,
        default=None,
        help=f"match threshold; default {DEFAULT_MIN_MATCH_SCORE} (Stargazer's)",
    )
    ap.add_argument(
        "--tolerance",
        type=float,
        default=None,
        help="widen every parameter tolerance by this factor instead of setting "
        "the threshold directly; 2x -> 0.64, 3x -> 0.51",
    )
    ap.add_argument(
        "--epoch-hint", action="store_true", help="grounding arm: state the l_rad epoch"
    )
    ap.add_argument("--batch-name", default=None, help="folder under data/batch")
    ap.add_argument("--phase", default=None, help="recorded in config.json")
    ap.add_argument("--arm-id", default=None, help="recorded in config.json")
    ap.add_argument("--force", action="store_true", help="re-run trials that already have logs")
    ap.add_argument("--dry-run", action="store_true", help="list what would run and exit")
    args = ap.parse_args(argv)

    if args.min_match_score is not None and args.tolerance is not None:
        print("Give either --min-match-score or --tolerance, not both.")
        return 1
    threshold = args.min_match_score
    if args.tolerance is not None:
        threshold = threshold_for_tolerance(args.tolerance)
    effective_threshold = threshold if threshold is not None else DEFAULT_MIN_MATCH_SCORE

    solvable = None
    if args.solvable_only:
        solvable = _solvable_task_ids(effective_threshold)
        if solvable is None:
            print(
                "--solvable-only needs the ML reference cache. Run:\n"
                "  uv run python scripts/compute_match_ceilings.py"
            )
            return 1

    tiers = list(args.tier)
    try:
        selected = _select_tasks(
            tiers,
            args.kind,
            args.min_planets,
            args.limit,
            max_difficulty=args.max_difficulty,
            solvable=solvable,
            task_ids=set(args.task_id) if args.task_id else None,
        )
    except AstroDatasetError as exc:
        print(exc)
        return 1
    if not selected:
        if args.task_id:
            print(f"No {args.kind} task matched id(s): {', '.join(args.task_id)}")
            return 1
        print(
            f"No {args.kind} tasks matched tier(s) {tiers} with >= {args.min_planets} "
            f"planet(s)"
            + (f", solvable at {effective_threshold:.3f}" if solvable else "")
            + (f", difficulty <= {args.max_difficulty}" if args.max_difficulty else "")
            + "."
        )
        return 1

    model = os.environ.get("TRAJ_EVAL_MODEL", "gpt-4o-mini")
    batch_name = args.batch_name or (
        f"astro_{'_'.join(args.task_id) if args.task_id else '_'.join(tiers)}"
        f"_{model.replace('/', '-')}_t{args.trials}"
    )
    out_dir = BATCH_ROOT / batch_name

    planned: list[tuple] = []
    for task, truth, raw in selected:
        turns = args.max_turns or DEFAULT_MAX_TURNS.get(task.tier, 50)
        for trial in range(args.trials):
            log_path = out_dir / f"{task.task_id}_t{trial}.jsonl"
            planned.append((task, truth, raw, trial, turns, log_path.exists()))

    existing = sum(1 for p in planned if p[5])
    todo = len(planned) - (0 if args.force else existing)

    print(f"batch      : {out_dir}")
    print(f"backbone   : {model}")
    print(
        f"tasks      : {len(selected)}  (tier {', '.join(tiers)}, >= {args.min_planets} planets"
        + (f", solvable @ {effective_threshold:.3f}" if solvable else "")
        + (f", difficulty <= {args.max_difficulty}" if args.max_difficulty else "")
        + ")"
    )
    print(
        f"match gate : {effective_threshold:.4f}"
        + (f"  ({args.tolerance:g}x tolerance)" if args.tolerance else "")
        + ("  [Stargazer default]" if threshold is None else "  [relaxed]")
    )
    print(f"trials     : {args.trials} per task -> {len(planned)} total")
    if existing:
        print(f"existing   : {existing} " + ("(will be re-run)" if args.force else "(skipped)"))
    print(f"to run     : {todo}")
    print(
        f"max_turns  : {args.max_turns or 'per tier ' + str(DEFAULT_MAX_TURNS)}   "
        f"max_submissions: {args.max_submissions or 'per tier'}"
    )

    if args.dry_run:
        print("\nplanned trials:")
        for task, truth, _raw, trial, turns, exists in planned:
            mark = "skip" if (exists and not args.force) else "run "
            print(
                f"  [{mark}] {task.task_id:22s} d{task.difficulty:<2d} {task.tier:7s} "
                f"planets={truth.n_planets} t{trial} turns={turns}"
            )
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    _write_config(out_dir, args, len(selected), tiers, effective_threshold)

    outcomes: list[TrialOutcome] = []
    errors: list[tuple[str, str]] = []
    for i, (task, truth, raw, trial, turns, exists) in enumerate(planned, start=1):
        label = f"{task.task_id} t{trial}"
        if exists and not args.force:
            print(f"  [{i}/{len(planned)}] {label}: already logged, skipping")
            continue
        print(f"  [{i}/{len(planned)}] {label} (turns={turns}) ...", flush=True)
        try:
            outcome = run_one_trial(
                task,
                truth,
                raw,
                trial,
                out_dir=out_dir,
                max_turns=turns,
                max_submissions=args.max_submissions,
                epoch_hint=args.epoch_hint,
                min_match_score=threshold,
            )
        except Exception as exc:  # noqa: BLE001 - one bad trial must not kill the batch
            errors.append((label, f"{type(exc).__name__}: {str(exc)[:200]}"))
            print(f"      ERROR {type(exc).__name__}: {str(exc)[:160]}")
            continue
        outcomes.append(outcome)
        print(
            f"      -> {outcome.outcome:14s} termination={outcome.termination} "
            f"submissions={outcome.n_submissions} flags={len(outcome.flags)}"
            + (
                f" idle={outcome.max_idle_messages_seen}"
                if outcome.max_idle_messages_seen >= 3
                else ""
            )
            + (f" cycle={outcome.cycle_period}" if outcome.cycle_period else "")
            + (
                f" tool_errors={outcome.max_tool_errors_seen}"
                if outcome.max_tool_errors_seen >= 2
                else ""
            )
        )

    _report(outcomes, errors, out_dir)
    return 0


def _report(outcomes: list[TrialOutcome], errors: list[tuple[str, str]], out_dir: Path) -> None:
    if not outcomes:
        print("\nNo trials completed.")
        for label, err in errors:
            print(f"  {label}: {err}")
        return

    print("\n==================== per-task ====================")
    by_task: dict[str, list[TrialOutcome]] = {}
    for o in outcomes:
        by_task.setdefault(o.task_id, []).append(o)
    for task_id, group in sorted(by_task.items()):
        counts = Counter(o.outcome for o in group)
        summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        print(f"  {task_id:22s} [d{group[0].difficulty:<2d} {group[0].tier:6s}] {summary}")

    print("\n==================== by tier ====================")
    by_tier: dict[str, list[TrialOutcome]] = {}
    for o in outcomes:
        by_tier.setdefault(o.tier, []).append(o)
    for tier, group in sorted(by_tier.items()):
        counts = Counter(o.outcome for o in group)
        n = len(group)
        solved = counts.get("solved", 0)
        print(f"  {tier:8s} n={n:3d}  " + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
        # Conditioned on reaching a submission, matching Stargazer's convention:
        # a trial cut off before submitting says nothing about the science.
        submitted = n - counts.get("no_submission", 0)
        print(
            f"           pass rate (of submitted): {solved}/{submitted}"
            + (f" = {solved / submitted:.2f}" if submitted else "  (none submitted)")
        )

    print("\n==================== termination ====================")
    for reason, count in sorted(Counter(o.termination for o in outcomes).items()):
        print(f"  {str(reason):12s} {count}")
    idle = [o.max_idle_messages_seen for o in outcomes]
    if idle:
        stalled = sum(1 for o in outcomes if o.termination == "stuck_idle")
        cycled = sum(1 for o in outcomes if o.termination == "stuck_cycle")
        print(
            f"  max idle run: median {sorted(idle)[len(idle) // 2]}  max {max(idle)}"
            f"   stuck_idle: {stalled}/{len(outcomes)}"
            f"   stuck_cycle: {cycled}/{len(outcomes)}"
        )
        periods = [o.cycle_period for o in outcomes if o.cycle_period]
        if periods:
            print(f"  cycle periods seen: {sorted(set(periods))}")
        never = sum(1 for o in outcomes if o.termination == "stuck_no_submission")
        if never:
            # Busy but goal-less: novel, well-formed, successful tool calls that
            # never reach a submission. Usually means the role holding the submit
            # tool was never handed control.
            print(f"  stopped having NEVER SUBMITTED: {never}/{len(outcomes)}")
        tool_err = sum(1 for o in outcomes if o.termination == "stuck_tool_error")
        if tool_err:
            # A tool-usability failure, not agent perseveration: worth fixing in
            # the tool rather than reporting as a failure mode.
            print(
                f"  stopped by repeated TOOL ERRORS: {tool_err}/{len(outcomes)}"
                f"   <- fix the tool, not the agent"
            )

    print("\n==================== failure modes ====================")
    mode_counts: Counter[str] = Counter()
    for o in outcomes:
        mode_counts.update(o.flags)
    if mode_counts:
        for mode, count in mode_counts.most_common():
            print(f"  {mode:30s} {count:3d}/{len(outcomes)}")
    else:
        print("  none fired")
    lost = [o for o in outcomes if o.had_it_and_lost_it]
    failed = [o for o in outcomes if not o.solved and o.had_it_and_lost_it is not None]
    if failed:
        print(f"\n  had_it_and_lost_it: {len(lost)}/{len(failed)} of scored failures")

    print("\n==================== tool usage by outcome ====================")
    all_tools = sorted({t for o in outcomes for t in o.tool_counts})
    if all_tools:
        by_outcome: dict[str, list[TrialOutcome]] = {}
        for o in outcomes:
            by_outcome.setdefault(o.outcome, []).append(o)
        print("  " + f"{'outcome':16s}" + "".join(f"{t:>16s}" for t in all_tools))
        for name, group in sorted(by_outcome.items()):
            means = [sum(o.tool_counts.get(t, 0) for o in group) / len(group) for t in all_tools]
            print("  " + f"{name:16s}" + "".join(f"{m:>16.2f}" for m in means))
        print("  (mean calls per trial, by outcome)")

    if errors:
        print(f"\n==================== {len(errors)} error(s) ====================")
        for label, err in errors:
            print(f"  {label}: {err}")

    # The full Layer-1 / Layer-2 tables, recomputed from the logs so this matches
    # exactly what analyse_astro_trials.py and the dashboard report.
    print("\n==================== batch report ====================")
    try:
        from traj_eval.dataset.astro_loader import load_astro_task

        def load(task_id: str):
            return load_astro_task(task_id, kind="synthetic")

        report = analyse_astro_batch(out_dir, load_task=load)
        sp = report.statistical_vs_physical()
        print(
            f"  pass rate {_pct(report.pass_rate)}   "
            f"submission rate {_pct(report.submission_rate)}"
        )
        print(f"  statistical {_pct(sp['statistical'])}   physical {_pct(sp['physical'])}")
        traj = report.trajectory_summary()
        print(
            f"  mean revision ratio {_fmt(traj['mean_revision_ratio'])}   "
            f"critic verified {_pct(traj['critic_verified_rate'])}"
        )
    except Exception as exc:  # noqa: BLE001 - reporting must not fail the batch
        print(f"  (unavailable: {type(exc).__name__}: {exc})")

    print(f"\n  logs in {out_dir}")
    print(f"  uv run python scripts/analyse_astro_trials.py {out_dir}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
