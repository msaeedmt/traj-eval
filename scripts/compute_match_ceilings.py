"""Compute the match ceiling for every task, once, and cache it.

For each task this finds the maximum-likelihood fit at the true planet count and
scores its match. That number is the best any fitting-based agent could achieve,
so it separates two things every aggregate currently conflates:

    ceiling >= 0.80  ->  solvable; a match failure is the agents' doing
    ceiling <  0.80  ->  unsolvable; no fitter can pass, exclude or report apart

Some tasks really are unsolvable. On seed22_diff4 the maximum-likelihood solution
sits at P = 3.1011 d against a true 3.1170 d and fits the data BETTER than the
truth (RMS 4.034 vs 4.409) -- noise displaces the likelihood peak by more than
the match threshold allows. Its ceiling is 0.774. The team that ran it scored
0.7741, i.e. exactly the ceiling: it found the optimum and was marked wrong.

No LLM, no network, a few seconds per task. Run once after preparing the dataset;
the analysis tools pick the cache up automatically.

Usage:
    uv run python scripts/compute_match_ceilings.py
    uv run python scripts/compute_match_ceilings.py --tier medium hard
    uv run python scripts/compute_match_ceilings.py --task-id seed22_diff4 --verbose
    uv run python scripts/compute_match_ceilings.py --force
"""

from __future__ import annotations

import argparse
import math
import sys
from collections import Counter
from pathlib import Path

from traj_eval.dataset.astro_bank import (
    AstroDatasetError,
    dataset_root,
    list_task_files,
    read_task_file,
)
from traj_eval.dataset.astro_loader import split_task
from traj_eval.metrics.astro.ceiling import (
    MatchCeiling,
    ceilings_path,
    compute_ceiling,
    load_ceilings,
    save_ceilings,
)
from traj_eval.metrics.astro.criteria import (
    DEFAULT_MIN_MATCH_SCORE,
    threshold_for_tolerance,
)


def _fmt(value: float | None, spec: str = ".4f") -> str:
    return "n/a" if value is None else format(value, spec)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kind", nargs="+", default=["synthetic"], choices=("synthetic", "real"))
    ap.add_argument("--tier", nargs="+", default=None, choices=("easy", "medium", "hard", "real"))
    ap.add_argument("--task-id", default=None, help="compute one task only")
    ap.add_argument("--force", action="store_true", help="recompute tasks already cached")
    ap.add_argument("--verbose", action="store_true", help="one line per task")
    ap.add_argument("--out", type=Path, default=None, help="cache path")
    ap.add_argument(
        "--min-match-score",
        type=float,
        default=None,
        help=f"match threshold to judge reachability against "
        f"(default {DEFAULT_MIN_MATCH_SCORE})",
    )
    ap.add_argument(
        "--tolerance",
        type=float,
        default=None,
        help="widen every parameter tolerance by this factor instead; 2x -> 0.64",
    )
    ap.add_argument(
        "--sweep",
        action="store_true",
        help="print reachable-task counts across a range of thresholds and exit",
    )
    args = ap.parse_args(argv)

    if args.min_match_score is not None and args.tolerance is not None:
        print("Give either --min-match-score or --tolerance, not both.")
        return 1
    threshold = args.min_match_score
    if args.tolerance is not None:
        threshold = threshold_for_tolerance(args.tolerance)

    out_path = args.out or ceilings_path(dataset_root())
    if args.sweep:
        cached = load_ceilings(out_path)
        if not cached:
            print(f"No cache at {out_path}; compute it first.")
            return 1
        _sweep(list(cached.values()))
        return 0
    cached = {} if args.force else load_ceilings(out_path)
    if cached:
        print(f"loaded {len(cached)} cached ceiling(s) from {out_path}")

    pending: list[tuple] = []
    for kind in args.kind:
        try:
            paths = list_task_files(kind)
        except AstroDatasetError as exc:
            print(exc)
            return 1
        for path in paths:
            try:
                raw = read_task_file(path)
            except AstroDatasetError as exc:
                print(f"  skipping {path.name}: {exc}")
                continue
            task, truth = split_task(raw, kind=kind)
            if args.task_id and task.task_id != args.task_id:
                continue
            if args.tier and task.tier not in args.tier:
                continue
            pending.append((task, truth, raw))

    if not pending:
        print("No tasks matched.")
        return 1

    todo = [p for p in pending if p[0].task_id not in cached]
    print(f"{len(pending)} task(s) selected; {len(todo)} to compute")

    results: dict[str, MatchCeiling] = dict(cached)
    for i, (task, truth, raw) in enumerate(todo, start=1):
        try:
            ceiling = compute_ceiling(task, truth, stargazer_task=raw, min_match_score=threshold)
        except Exception as exc:  # noqa: BLE001 - one bad task must not abort the sweep
            print(f"  [{i}/{len(todo)}] {task.task_id}: ERROR {type(exc).__name__}: {exc}")
            continue
        results[task.task_id] = ceiling
        if args.verbose or not ceiling.ceiling_solved:
            mark = "OK      " if ceiling.ceiling_solved else "UNSOLVE "
            print(
                f"  [{i}/{len(todo)}] {mark} {task.task_id:22s} d{task.difficulty:<2d} "
                f"n={ceiling.n_truth_planets} ceiling={_fmt(ceiling.ceiling_match)} "
                f"rms={_fmt(ceiling.ceiling_rms_ms, '.3f')} vs truth "
                f"{_fmt(ceiling.truth_rms_ms, '.3f')}"
            )
        elif i % 10 == 0:
            print(f"  [{i}/{len(todo)}] ...")

    save_ceilings(sorted(results.values(), key=lambda c: c.task_id), out_path)
    _report(list(results.values()))
    print(f"\nwrote {out_path}")
    print("The analysis tools will pick this up automatically.")
    return 0


def _sweep(ceilings: list[MatchCeiling]) -> None:
    """Reachable-task counts across thresholds, without recomputing anything.

    The reference score does not depend on the threshold, so re-thresholding a
    cached sweep is exact.
    """
    scored = [c for c in ceilings if c.ceiling_match is not None]
    if not scored:
        print("No scored ceilings.")
        return
    bands = [("d1-3", 1, 3), ("d4-6", 4, 6), ("d7-10", 7, 10)]
    print(f"{len(scored)} task(s) in the cache\n")
    print("tolerance  threshold  curve agree   all   " + "  ".join(f"{b[0]:>6}" for b in bands))
    for mult in (1.0, 1.5, 2.0, 3.0, 4.0, 6.0):
        thr = DEFAULT_MIN_MATCH_SCORE**mult
        curve = -math.log(thr) / 4.0
        n_all = sum(1 for c in scored if c.ceiling_match >= thr)
        row = f"  {mult:>4.1f}x     {thr:>6.3f}     {curve:>6.1%}     {n_all:>3d}   "
        for _, lo, hi in bands:
            g = [c for c in scored if lo <= c.difficulty <= hi]
            n = sum(1 for c in g if c.ceiling_match >= thr)
            row += f"{n:>3d}/{len(g):<3d}"
        print(row)
    print("\n  'curve agree' is how closely the predicted RV curve must trace the")
    print("  true one, as a fraction of its semi-amplitude.")


def _report(ceilings: list[MatchCeiling]) -> None:
    scored = [c for c in ceilings if c.ceiling_match is not None]
    if not scored:
        print("\nNo ceilings computed.")
        return

    print(f"\n==================== {len(scored)} task(s) ====================")
    solvable = [c for c in scored if c.ceiling_solved]
    unsolvable = [c for c in scored if not c.ceiling_solved]
    print(f"  solvable   : {len(solvable):3d}  ({len(solvable) / len(scored):.1%})")
    print(f"  UNSOLVABLE : {len(unsolvable):3d}  ({len(unsolvable) / len(scored):.1%})")

    outfit = [c for c in scored if c.outfits_truth]
    print(
        f"  ML out-fits the truth on {len(outfit)}/{len(scored)} tasks "
        f"({len(outfit) / len(scored):.1%}) -- the data favours parameters other "
        f"than the true ones"
    )

    print("\n  by difficulty:")
    by_diff: dict[int, list[MatchCeiling]] = {}
    for c in scored:
        by_diff.setdefault(c.difficulty, []).append(c)
    print(f"    {'diff':>4}  {'n':>4}  {'solvable':>9}  {'mean ceiling':>13}  {'min':>7}")
    for diff, group in sorted(by_diff.items()):
        ok = sum(1 for c in group if c.ceiling_solved)
        means = [c.ceiling_match for c in group if c.ceiling_match is not None]
        print(
            f"    {diff:>4}  {len(group):>4}  {ok / len(group):>8.1%}  "
            f"{sum(means) / len(means):>13.4f}  {min(means):>7.4f}"
        )

    print("\n  by planet count:")
    by_n: dict[int, list[MatchCeiling]] = {}
    for c in scored:
        by_n.setdefault(c.n_truth_planets, []).append(c)
    for n, group in sorted(by_n.items()):
        ok = sum(1 for c in group if c.ceiling_solved)
        print(f"    {n} planet(s): {len(group):3d} tasks, {ok / len(group):.1%} solvable")

    if unsolvable:
        print(f"\n  unsolvable tasks ({len(unsolvable)}):")
        for c in sorted(unsolvable, key=lambda x: x.ceiling_match or 0.0):
            print(
                f"    {c.task_id:22s} d{c.difficulty:<2d} n={c.n_truth_planets} "
                f"ceiling={_fmt(c.ceiling_match)}"
            )

    errors = Counter(c.error for c in ceilings if c.error)
    if errors:
        print("\n  errors:")
        for msg, count in errors.items():
            print(f"    {count}x {msg}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
