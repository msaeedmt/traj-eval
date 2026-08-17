"""Run one Stargazer RV task end-to-end through the free-routing astro team.

The astro counterpart of ``run_dataset_task.py``: loads a prepared task from
``dataset/Astro``, hands the team the observations (never the truth), runs with
the four real tools, writes the trace, and prints the trajectory, the
termination reason, and the submission history.

This is the first script that spends API budget, so it defaults to ONE task and
prints enough to diagnose a bad trajectory without re-running. Start on an easy
task with a small backbone before scaling anything.

What is deliberately NOT here: anchors and detectors. Those come next and run
offline over the written trace, so re-analysing a trial never costs another API
call. Everything needed for that analysis is in the jsonl plus the submission
attempts printed below.

Usage:
    uv run python scripts/run_astro_task.py                       # list ids
    TRAJ_EVAL_MODEL=gpt-4o-mini uv run python scripts/run_astro_task.py seed1108_diff2
    uv run python scripts/run_astro_task.py --tier easy           # first easy task
    uv run python scripts/run_astro_task.py seed210_diff2 --epoch-hint
    uv run python scripts/run_astro_task.py seed210_diff2 --max-turns 40
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from traj_eval.agents import (
    RoutingLedger,
    StepContext,
    TraceObserver,
    build_llm_config,
    make_trial_meta,
)
from traj_eval.agents.astro_team import astro_task_prompt, build_astro_free_team, build_astro_tools
from traj_eval.agents.free_routing import finalize_run
from traj_eval.dataset.astro_bank import AstroDatasetError, read_task_file, task_file
from traj_eval.dataset.astro_loader import list_astro_task_ids, load_astro_task, split_task
from traj_eval.trace_core.storage import TrialLogWriter, read_trial

LOG_DIR = Path("data/runs")


def _list_tasks(kind: str) -> int:
    try:
        ids = list_astro_task_ids(kind=kind)
    except AstroDatasetError as exc:
        print(exc)
        return 1
    if not ids:
        print(
            f"No prepared {kind} tasks found. Run the one-time preparation step:\n"
            "  uv run --with rebound --with celerite2 python "
            "scripts/prepare_astro_dataset.py --stargazer-root /path/to/Stargazer"
        )
        return 1
    print(f"Available {kind} task ids ({len(ids)}):\n")
    for task_id in ids:
        task, truth = load_astro_task(task_id, kind=kind)
        print(
            f"  {task_id:22s} difficulty {task.difficulty:2d}  {task.tier:7s} "
            f"n_obs={task.observation.n_obs:3d}  planets={truth.n_planets}"
        )
    print("\nRun:  uv run python scripts/run_astro_task.py <id>")
    return 0


def _first_in_tier(kind: str, tier: str) -> str | None:
    for task_id in list_astro_task_ids(kind=kind):
        task, _ = load_astro_task(task_id, kind=kind)
        if task.tier == tier:
            return task_id
    return None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_id", nargs="?", help="task id, e.g. seed1108_diff2")
    parser.add_argument("--kind", default="synthetic", choices=("synthetic", "real"))
    parser.add_argument("--tier", default=None, choices=("easy", "medium", "hard", "real"))
    parser.add_argument("--max-turns", type=int, default=30)
    parser.add_argument(
        "--epoch-hint",
        action="store_true",
        help="add the l_rad epoch convention to the prompts (grounding axis)",
    )
    parser.add_argument("--trial-id", default=None, help="log filename; defaults to the task id")
    args = parser.parse_args(argv)

    task_id = args.task_id
    if task_id is None and args.tier:
        try:
            task_id = _first_in_tier(args.kind, args.tier)
        except AstroDatasetError as exc:
            print(exc)
            return 1
        if task_id is None:
            print(f"No {args.tier}-tier task found in the {args.kind} bank.")
            return 1
    if task_id is None:
        return _list_tasks(args.kind)

    # Load the parsed Task once and split it, so the submission tool can reuse the
    # already-parsed config/observations instead of rebuilding them per call.
    path = task_file(task_id, args.kind)
    if not path.is_file():
        print(f"Unknown task id {task_id!r}. Run with no arguments to list ids.")
        return 1
    try:
        stargazer_task = read_task_file(path)
    except AstroDatasetError as exc:
        print(exc)
        return 1
    task, truth = split_task(stargazer_task, kind=args.kind)

    obs = task.observation
    print(f"=== {task.task_id} ({task.kind}, difficulty {task.difficulty}, {task.tier}) ===")
    print(
        f"    n_obs={obs.n_obs}  baseline={obs.baseline_days:.1f} d  "
        f"median_sigma={obs.median_sigma_ms:.3g} m/s  "
        f"attempts={task.max_submissions}  epoch_hint={args.epoch_hint}"
    )
    # Printed for OUR benefit while debugging a trajectory; the agents never see it.
    print(
        f"    [truth, not shown to agents] {truth.n_planets} planet(s) at "
        f"{', '.join(f'{p:.4g}' for p in truth.periods_days)} d\n"
    )

    tools, submit_tool = build_astro_tools(task, truth, stargazer_task=stargazer_task)
    llm_config = build_llm_config()
    ledger = RoutingLedger()
    step_context = StepContext()
    manager, user, groupchat, run_state = build_astro_free_team(
        llm_config,
        tools=tools,
        max_turns=args.max_turns,
        epoch_hint=args.epoch_hint,
        ledger=ledger,
        step_context=step_context,
    )

    trial_id = args.trial_id or task.task_id
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"astro_{trial_id}.jsonl"
    meta = make_trial_meta(
        trial_id=trial_id,
        task_id=task.task_id,
        backbone="env:TRAJ_EVAL_MODEL",
        testbed="astro",
        grounding=args.epoch_hint,
        config={
            "kind": task.kind,
            "difficulty": task.difficulty,
            "tier": task.tier,
            "max_submissions": task.max_submissions,
            "max_turns": args.max_turns,
            "n_obs": obs.n_obs,
            "n_truth_planets": truth.n_planets,
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

    print("\n==================== trajectory ====================")
    for event in events:
        marker = ""
        if event.payload.get("handoff_target"):
            marker = f"-> HANDOFF:{event.payload['handoff_target']}"
        elif event.payload.get("tool_request"):
            marker = f"-> TOOL:{event.payload['tool_request']}"
        elif event.payload.get("decision"):
            marker = f"[{event.payload['decision']}]"
        body = (event.payload.get("text", "") or "").replace("\n", " ")[:45]
        print(
            f"  {event.agent_role.value:9s}#{event.seq} "
            f"{event.event_type.value:17s} {marker:24s} {body!r}"
        )

    print("\n==================== run ====================")
    print(f"  termination reason : {run_state.reason}")
    print(f"  total turns        : {run_state.turns}")
    print(f"  invalid hand-offs  : {run_state.invalid_handoffs}")
    print(f"  max identical calls: {run_state.max_identical_calls_seen}")
    print(f"  max no-progress    : {run_state.max_no_progress_seen}")

    print("\n==================== submissions ====================")
    print(f"  scoring attempts   : {submit_tool.n_attempts}/{submit_tool.max_attempts}")
    print(f"  malformed attempts : {submit_tool.n_invalid}")
    if not submit_tool.attempts:
        print("  (none -- the team never submitted)")
    for attempt in submit_tool.attempts:
        criteria = attempt.criteria
        flags = "".join(
            code if ok else "-"
            for code, ok in (
                ("B", criteria.ok_delta_bic),
                ("R", criteria.ok_rms),
                ("M", criteria.ok_match),
                ("C", criteria.ok_count),
            )
        )
        periods = ", ".join(f"{p.get('P_days', float('nan')):.4g}" for p in attempt.planets)
        print(
            f"    #{attempt.index} [{flags}] "
            f"n={attempt.n_planets} rms={criteria.rms_ms:.3g}/{criteria.max_rms_ms:.3g} "
            f"match={criteria.match_score:+.3f} P=[{periods}]"
        )

    best = submit_tool.best()
    print("\n==================== outcome ====================")
    if best is None:
        print("  no scored submission")
    else:
        print(f"  solved (best-of)   : {best.solved}")
        print(f"  statistical pass   : {best.statistical_pass}")
        print(f"  physical pass      : {best.physical_pass}")
        # The dissociation the astro testbed exists to measure: a model that fits
        # the data while describing the wrong system.
        print(f"  stat/phys gap      : {best.stat_phys_gap}")
        if best.failed_criteria():
            print(f"  failed criteria    : {', '.join(best.failed_criteria())}")

    print(f"\n  trace written to {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
