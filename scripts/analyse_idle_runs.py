"""Size a potential 'stop when idle' rule from traces already on disk.

Answers the two questions a stop rule needs settled before it can be written:

  1. HOW LONG do idle runs get -- stretches of agent messages that call no tool?
  2. Does a long one ever happen on a trial that SUCCEEDS?

Question 2 is the safety check and matters more. A threshold that would have cut
a successful run converts a slow success into a recorded failure, corrupting the
failure statistics the project exists to measure. If any threshold shows
successful trials being cut, that threshold is too low regardless of how much it
would save.

The report also estimates the saving, in agent messages, from stopping at each
threshold. Messages are a crude cost proxy, but a conservative one in the right
direction: idle messages sit at the END of a trial, carrying the largest context,
and every turn resends the whole history -- so cost grows roughly quadratically
in turn count and the tail messages are the most expensive in the run.

No LLM, no evaluator, no network. Reads trace files and nothing else.

Usage:
    uv run python scripts/analyse_idle_runs.py data/batch/<batch>
    uv run python scripts/analyse_idle_runs.py data/batch/<batch> --threshold 5
    uv run python scripts/analyse_idle_runs.py data/batch/<batch> --show-worst 5
    uv run python scripts/analyse_idle_runs.py data/batch/<batch> --json idle.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from traj_eval.metrics.astro.artifacts import extract_astro_artifacts
from traj_eval.metrics.astro.batch_report import list_trial_files
from traj_eval.metrics.astro.idle import IdleReport, analyse_idle_runs, summarise
from traj_eval.trace_core.storage import read_trial

CANDIDATE_THRESHOLDS = (3, 4, 5, 6, 8, 10, 12)


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{100.0 * value:5.1f}%"


def collect(folder: Path) -> tuple[list[tuple[IdleReport, bool]], list[tuple[str, str]]]:
    """Return [(idle report, trial solved)] plus any files that could not be read."""
    out: list[tuple[IdleReport, bool]] = []
    skipped: list[tuple[str, str]] = []
    for path in list_trial_files(folder):
        try:
            meta, events = read_trial(path)
        except Exception as exc:  # noqa: BLE001 - one bad file must not abort the sweep
            skipped.append((path.name, f"{type(exc).__name__}: {exc}"))
            continue
        artifacts = extract_astro_artifacts(events, trial_id=meta.trial_id, task_id=meta.task_id)
        report = analyse_idle_runs(events, artifacts, trial_id=meta.trial_id, task_id=meta.task_id)
        out.append((report, artifacts.solved))
    return out, skipped


def report_batch(folder: Path, show_worst: int, json_path: Path | None) -> int:
    rows, skipped = collect(folder)
    if not rows:
        print(f"No readable trials in {folder}")
        for name, err in skipped:
            print(f"  skipped {name}: {err}")
        return 1

    reports = [r for r, _ in rows]
    solved = [r for r, ok in rows if ok]
    failed = [r for r, ok in rows if not ok]
    n = len(reports)

    print(f"=== idle runs across {n} trial(s) in {folder} ===\n")

    print("-- how long do idle runs get? --")
    lengths = [r.max_idle_run for r in reports]
    lengths_sorted = sorted(lengths)
    print(
        f"  max idle run per trial: median {lengths_sorted[n // 2]}   "
        f"90th pct {lengths_sorted[int(0.9 * (n - 1))]}   max {max(lengths)}"
    )
    dist = Counter(lengths)
    print("  distribution: " + "  ".join(f"{k}:{dist[k]}" for k in sorted(dist)))
    ended_idle = [r for r in reports if r.terminal_idle_run]
    print(
        f"  trials that ENDED inside an idle run: {len(ended_idle)}/{n} "
        f"({_pct(len(ended_idle) / n)})"
    )
    if ended_idle:
        tails = sorted(r.wasted_tail for r in ended_idle)
        print(
            f"    their wasted tails: median {tails[len(tails) // 2]}  max {max(tails)}  "
            f"total {sum(tails)} messages"
        )

    print("\n-- solved vs failed --")
    for label, group in (("solved", solved), ("failed", failed)):
        if not group:
            print(f"  {label:7s}: none")
            continue
        g = sorted(r.max_idle_run for r in group)
        excess = [r.excess_idle_messages for r in group]
        print(
            f"  {label:7s}: n={len(group):3d}  max idle run: median {g[len(g) // 2]} "
            f"max {max(g)}   mean churn {sum(excess) / len(excess):.1f} messages"
        )

    print("\n-- would a stop rule be safe, and what would it save? --")
    print(
        f"  {'threshold':>9}  {'trials cut':>10}  {'SOLVED cut':>11}  "
        f"{'msgs saved':>10}  {'of total':>9}"
    )
    total_messages = sum(r.n_agent_messages for r in reports)
    for thr in CANDIDATE_THRESHOLDS:
        cut = [r for r in reports if r.would_trip(thr)]
        cut_solved = [r for r, ok in rows if ok and r.would_trip(thr)]
        saved = sum(r.messages_saved(thr) for r in reports)
        flag = "  <-- UNSAFE" if cut_solved else ""
        print(
            f"  {thr:>9}  {len(cut):>10}  {len(cut_solved):>11}  "
            f"{saved:>10}  {_pct(saved / total_messages) if total_messages else 'n/a':>9}"
            f"{flag}"
        )
    print("\n  'SOLVED cut' is the safety column: any non-zero value means that")
    print("  threshold would have turned a success into a recorded failure.")

    if show_worst:
        print(f"\n-- the {show_worst} longest idle runs --")
        worst = sorted(reports, key=lambda r: -r.max_idle_run)[:show_worst]
        by_id = {r.trial_id: ok for r, ok in rows}
        for r in worst:
            run = max(r.runs, key=lambda x: x.length, default=None)
            if run is None:
                continue
            outcome = "solved" if by_id.get(r.trial_id) else "failed"
            print(
                f"  {r.trial_id:24s} [{outcome}] {run.length} messages, "
                f"seq {run.start_seq}-{run.end_seq}, ended_by={run.ended_by}"
            )
            print(f"      {run.role_cycle[:150]}")

    if skipped:
        print(f"\n-- skipped {len(skipped)} file(s) --")
        for name, err in skipped:
            print(f"  {name}: {err}")

    if json_path is not None:
        payload = {
            "folder": str(folder),
            "n_trials": n,
            "thresholds": {
                str(thr): {
                    "trials_cut": sum(1 for r in reports if r.would_trip(thr)),
                    "solved_cut": sum(1 for r, ok in rows if ok and r.would_trip(thr)),
                    "messages_saved": sum(r.messages_saved(thr) for r in reports),
                }
                for thr in CANDIDATE_THRESHOLDS
            },
            "trials": [{**summarise(r), "solved": ok} for r, ok in rows],
        }
        json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nwrote {json_path}")
    return 0


def report_trial(path: Path) -> int:
    meta, events = read_trial(path)
    artifacts = extract_astro_artifacts(events, trial_id=meta.trial_id, task_id=meta.task_id)
    report = analyse_idle_runs(events, artifacts, trial_id=meta.trial_id, task_id=meta.task_id)
    print(f"=== {report.trial_id} ({path.name}) ===")
    print(
        f"  agent messages {report.n_agent_messages}   tool calls {report.n_tool_calls}   "
        f"solved={artifacts.solved}"
    )
    print(
        f"  idle runs: {len(report.runs)}   longest {report.max_idle_run}   "
        f"churn {report.excess_idle_messages} messages "
        f"({_pct(report.excess_share)} of agent turns)"
    )
    for run in report.runs:
        mark = "TAIL" if run.is_terminal else "    "
        print(
            f"    {mark} seq {run.start_seq:>3}-{run.end_seq:<3} len={run.length:<3} "
            f"ended_by={run.ended_by:<13} {run.role_cycle[:90]}"
        )
    if report.wasted_tail:
        print(f"  ended inside an idle run: {report.wasted_tail} messages produced nothing")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", type=Path, help="a trial .jsonl, or a folder of them")
    ap.add_argument(
        "--threshold", type=int, default=None, help="also report this specific threshold"
    )
    ap.add_argument(
        "--show-worst", type=int, default=5, help="show the N longest idle runs (0 to skip)"
    )
    ap.add_argument("--json", type=Path, default=None, help="write a JSON summary")
    args = ap.parse_args(argv)

    if args.threshold is not None and args.threshold not in CANDIDATE_THRESHOLDS:
        CANDIDATE_THRESHOLDS_LOCAL = tuple(sorted({*CANDIDATE_THRESHOLDS, args.threshold}))
        globals()["CANDIDATE_THRESHOLDS"] = CANDIDATE_THRESHOLDS_LOCAL

    if args.path.is_file():
        return report_trial(args.path)
    if args.path.is_dir():
        return report_batch(args.path, args.show_worst, args.json)
    print(f"No such file or directory: {args.path}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
