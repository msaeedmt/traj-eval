"""Aggregate saved trial logs into per-task success/failure counts.

Two modes:

  * fast (default) -- reads each trace and decides success from what was logged:
    the trial produced at least one compiling, sorry-free check_lean result AND
    the critic approved (declared_success). No Lean kernel needed, so it runs
    anywhere and is instant. This is a PROVISIONAL success signal -- it trusts
    the in-loop compiler verdicts already in the log.

  * --validate -- additionally re-runs the offline validator against the real
    kernel (needs ~/lean_anchor) for the authoritative Group B, and reports
    silent_failure (declared success but the kernel rejects the final proof).
    Slower; use to confirm the fast counts and surface silent failures.

Usage:
    uv run python scripts/analyze_batch.py data/batch
    uv run python scripts/analyze_batch.py data/batch --validate
    uv run python scripts/analyze_batch.py data/batch --difficulty easy
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path

from traj_eval.detectors.perseveration import detect_perseveration
from traj_eval.metrics.lean.artifacts import extract_artifacts
from traj_eval.trace_core.storage import read_trial

# filename like easy_fatem_011_t3.jsonl -> task "easy_fatem_011", trial 3
_NAME = re.compile(r"^(?P<task>.+)_t(?P<trial>\d+)\.jsonl$")


def _task_and_trial(path: Path) -> tuple[str, int] | None:
    m = _NAME.match(path.name)
    if not m:
        return None
    return m.group("task"), int(m.group("trial"))


def _offline_success(events) -> bool:
    """Provisional success from the trace alone: some check_lean call compiled
    sorry-free AND the critic approved (declared_success). Trusts the in-loop
    verdicts already logged; no kernel re-check."""
    art = extract_artifacts(events)
    got_clean = any(c.compiled and c.sorry_free for c in art.tool_calls)
    return bool(got_clean and art.declared_success)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("log_dir", help="directory of *.jsonl trial logs")
    ap.add_argument("--difficulty", default=None, help="filter task ids by prefix, e.g. easy")
    ap.add_argument("--validate", action="store_true", help="re-run kernel validation (slow)")
    args = ap.parse_args()

    log_dir = Path(args.log_dir)
    paths = sorted(log_dir.glob("*.jsonl"))

    compiler = None
    if args.validate:
        from traj_eval.tools.lean_compiler import LeanCompiler

        print("Starting Lean compiler for --validate (first run slow)...")
        compiler = LeanCompiler(Path.home() / "lean_anchor")
        print("Compiler ready.\n")
        from traj_eval.dataset.loader import load_dataset, to_lean_task

        tasks = {r.id: to_lean_task(r) for r in load_dataset(Path("dataset/Lean"))}
        from traj_eval.metrics.lean.validator import validate

    # per-task tallies
    success: dict[str, int] = defaultdict(int)
    fail: dict[str, int] = defaultdict(int)
    thrash: dict[str, int] = defaultdict(int)  # trials with retry_success_rate == 0 and >0 fails
    silent: dict[str, int] = defaultdict(int)
    total: dict[str, int] = defaultdict(int)

    for p in paths:
        tt = _task_and_trial(p)
        if not tt:
            continue
        task, _ = tt
        if args.difficulty and not task.startswith(args.difficulty):
            continue
        try:
            _, events = read_trial(p)
        except Exception as e:  # noqa: BLE001
            print(f"  skip {p.name}: {type(e).__name__}: {e}")
            continue

        total[task] += 1
        ok = _offline_success(events)

        if args.validate and compiler is not None and task in tasks:
            try:
                m = validate(events, tasks[task], compiler=compiler)
            except Exception as e:  # noqa: BLE001 -- one bad trial must not abort the batch
                print(f"  validate error on {p.name}: {type(e).__name__}: {str(e)[:100]}")
                fail[task] += 1
                continue
            ok = bool(
                m.final_proof_compiles
                and m.final_proof_sorry_free
                and m.statement_preserved
                and m.axiom_clean
            )
            if m.silent_failure:
                silent[task] += 1

        if ok:
            success[task] += 1
        else:
            fail[task] += 1

        rep = detect_perseveration(extract_artifacts(events).tool_calls)
        if rep.n_failed_compiles > 0 and rep.retry_success_rate == 0.0 and not ok:
            thrash[task] += 1

    if not total:
        print(f"No matching trial logs in {log_dir} (pattern *_t<N>.jsonl).")
        return 0

    # ---- report ----
    mode = "kernel-validated" if args.validate else "offline (trace verdicts)"
    print(f"\n==================== per-task success/failure [{mode}] ====================")
    header = f"{'task':22s} {'n':>3s} {'success':>7s} {'fail':>5s} {'rate':>6s} {'thrash':>6s}"
    if args.validate:
        header += f" {'silent':>6s}"
    print(header)
    grand_s = grand_n = 0
    for task in sorted(total):
        n, s = total[task], success[task]
        grand_s += s
        grand_n += n
        line = f"{task:22s} {n:3d} {s:7d} {fail[task]:5d} {s / n:6.2f} {thrash[task]:6d}"
        if args.validate:
            line += f" {silent[task]:6d}"
        print(line)
    print(
        f"\n{'TOTAL':22s} {grand_n:3d} {grand_s:7d} {grand_n - grand_s:5d} {grand_s / grand_n:6.2f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
