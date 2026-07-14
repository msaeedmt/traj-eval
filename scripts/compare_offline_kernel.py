"""Compare the offline (trace-verdict) success signal against the kernel-validated
ground truth, per trial, and bucket the disagreements.

Every trial gets two verdicts:
  * offline -- some check_lean result compiled sorry-free AND critic approved
    (declared_success). Trusts the in-loop compiler + critic; no kernel re-check.
  * kernel  -- the offline validator's Group B against the real kernel:
    final_proof_compiles & sorry_free & statement_preserved & axiom_clean.

Four buckets:
  * agree_pass / agree_fail          -- offline and kernel concur (the bulk)
  * SILENT_FAILURE (offline✓ kernel✗) -- looked good in-loop, kernel rejects.
    The headline phenomenon: declared+compiled but not actually correct.
  * OFFLINE_MISS  (offline✗ kernel✓) -- offline said fail but the proof holds.
    The cheap signal was too strict / missed a real success.

For every disagreeing trial we print WHICH Group B check failed (for silent
failures) so you can see the kind of fault.

Usage:
    uv run python scripts/compare_offline_kernel.py data/batch --difficulty easy
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from traj_eval.dataset.loader import load_dataset, to_lean_task
from traj_eval.metrics.lean.artifacts import extract_artifacts
from traj_eval.metrics.lean.validator import validate
from traj_eval.trace_core.storage import read_trial

_NAME = re.compile(r"^(?P<task>.+)_t(?P<trial>\d+)\.jsonl$")


def _offline_success(events) -> bool:
    art = extract_artifacts(events)
    got_clean = any(c.compiled and c.sorry_free for c in art.tool_calls)
    return bool(got_clean and art.declared_success)


def _kernel_verdict(events, task, compiler):
    m = validate(events, task, compiler=compiler)
    ok = bool(
        m.final_proof_compiles
        and m.final_proof_sorry_free
        and m.statement_preserved
        and m.axiom_clean
    )
    # why it failed, if it did (first failing Group B check)
    reasons = []
    if m.final_proof_compiles is False:
        reasons.append("not_compiles")
    if m.final_proof_sorry_free is False:
        reasons.append("has_sorry")
    if m.statement_preserved is False:
        reasons.append("statement_not_preserved")
    if m.axiom_clean is False:
        reasons.append(f"extra_axioms={m.extra_axioms}")
    if m.final_proof_compiles is None:
        reasons.append("no_submission")
    return ok, m, reasons


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("log_dir")
    ap.add_argument("--difficulty", default=None)
    args = ap.parse_args()

    from traj_eval.tools.lean_compiler import LeanCompiler

    print("Starting Lean compiler (first run slow)...")
    compiler = LeanCompiler(Path.home() / "lean_anchor")
    tasks = {r.id: to_lean_task(r) for r in load_dataset(Path("dataset/Lean"))}
    print("Compiler ready.\n")

    silent, offline_miss, agree_pass, agree_fail = [], [], [], []

    for p in sorted(Path(args.log_dir).glob("*.jsonl")):
        m = _NAME.match(p.name)
        if not m:
            continue
        task = m.group("task")
        if args.difficulty and not task.startswith(args.difficulty):
            continue
        if task not in tasks:
            continue
        trial = f"{task}_t{m.group('trial')}"
        _, events = read_trial(p)
        off = _offline_success(events)
        ker, metrics, reasons = _kernel_verdict(events, tasks[task], compiler)

        if off and ker:
            agree_pass.append(trial)
        elif not off and not ker:
            agree_fail.append(trial)
        elif off and not ker:
            silent.append((trial, reasons))
        else:
            offline_miss.append((trial, reasons))

    print("==================== SILENT FAILURES (offline PASS, kernel FAIL) ====================")
    if not silent:
        print("  none")
    for trial, reasons in silent:
        print(f"  {trial:26s} -> {', '.join(reasons)}")

    print("\n==================== OFFLINE MISSES (offline FAIL, kernel PASS) ====================")
    if not offline_miss:
        print("  none")
    for trial, _reasons in offline_miss:
        print(f"  {trial:26s} (kernel accepted; offline missed the success)")

    print("\n==================== summary ====================")
    print(f"  agree pass    : {len(agree_pass)}")
    print(f"  agree fail    : {len(agree_fail)}")
    print(f"  silent failure: {len(silent)}   (offline over-counts success here)")
    print(f"  offline miss  : {len(offline_miss)}   (offline under-counts success here)")
    n = len(agree_pass) + len(agree_fail) + len(silent) + len(offline_miss)
    print(f"  total trials  : {n}")
    if n:
        disagree = len(silent) + len(offline_miss)
        print(f"  disagreement  : {disagree}/{n} = {disagree / n:.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
