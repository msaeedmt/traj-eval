"""Batch runner: run N trials over a slice of the benchmark and aggregate the
first real distributions (termination reasons, validator verdicts, perseveration
rates) per difficulty tier.

This turns the single-task runner into a measurement tool. For each selected
problem it runs ``--trials`` independent trials, scores each with the offline
validator + perseveration detector, classifies the outcome, and prints a
per-problem table plus tier aggregates.

Outcome classification (mutually exclusive, checked in order):
  * solved       -- validator says final proof compiles, is sorry-free, preserves
                    the statement, and is axiom-clean.
  * silent_failure -- team declared success but the validator rejects it.
  * import_error -- a compile failure whose first error looks like an unresolved
                    import/identifier, i.e. an ENVIRONMENT artifact (Mathlib pin
                    mismatch), NOT a model/coordination failure.
  * validation_unknown -- the post-hoc validator could not produce a proof
                    verdict, e.g. network/cache/tooling failed during
                    revalidation.
  * unsolved     -- ran out of turns / got stuck / never produced a valid proof.

Usage:
    TRAJ_EVAL_MODEL=gpt-4o uv run python scripts/run_batch.py --difficulty easy --trials 3
    TRAJ_EVAL_MODEL=gpt-4o uv run python scripts/run_batch.py --difficulty easy medium --trials 3
    TRAJ_EVAL_MODEL=gpt-4o uv run python scripts/run_batch.py --difficulty easy --trials 10 --skip-existing
    uv run python scripts/run_batch.py --dry-run          # list what would run
"""

from __future__ import annotations

import argparse
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from traj_eval.agents import (
    RoutingLedger,
    StepContext,
    TraceObserver,
    build_llm_config,
    make_trial_meta,
)
from traj_eval.agents.free_routing import finalize_run
from traj_eval.agents.lean_team import build_lean_free_team
from traj_eval.dataset.loader import ProblemRecord, load_dataset, to_lean_task
from traj_eval.detectors.perseveration import detect_perseveration
from traj_eval.metrics.lean.artifacts import extract_artifacts
from traj_eval.metrics.lean.validator import validate
from traj_eval.trace_core.storage import TrialLogWriter, read_trial

DATASET_ROOT = Path("dataset/Lean")
PROJECT_DIR = Path(os.environ.get("TRAJ_EVAL_LEAN_PROJECT", str(DATASET_ROOT)))
LEAN_TIMEOUT = int(os.environ.get("TRAJ_EVAL_LEAN_TIMEOUT", "360"))
LOG_DIR = Path("data/batch")

# Substrings in a first compile error that mark an environment (import) problem
# rather than a proof problem. Kept broad on purpose; these never count against
# the model.
_IMPORT_ERROR_MARKERS = (
    "unknown package",
    "unknown module",
    "unknown identifier",
    "unknown constant",
    "unknown namespace",
    "could not find",
    "file not found",
)


@dataclass
class TrialOutcome:
    task_id: str
    difficulty: str
    trial: int
    outcome: str  # 'solved' | 'silent_failure' | 'unsolved' | 'import_error' | 'validation_unknown'
    termination: str | None
    n_tool_calls: int
    perseverated: bool


def _trace_is_valid(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        read_trial(path)
    except Exception:  # noqa: BLE001 -- invalid traces should be regenerated
        return False
    return True


def _looks_like_import_error(events) -> bool:
    """True if any failed compile in the trace has an import-ish first error.

    We read the tool-call results for failure text. The EXECUTION_RESULT text is
    a Python-repr dict; a cheap substring scan over it is enough to flag the
    environment case without full parsing.
    """
    from traj_eval.trace_core.schema import EventType

    for e in events:
        if e.event_type is EventType.EXECUTION_RESULT:
            text = (e.payload.get("text", "") or "").lower()
            if "compiled': false" in text or "compiled': false" in text.replace('"', "'"):
                if any(m in text for m in _IMPORT_ERROR_MARKERS):
                    return True
    return False


def _classify(events, metrics, run_state) -> str:
    verdict_fields = (
        metrics.final_proof_compiles,
        metrics.final_proof_sorry_free,
        metrics.statement_preserved,
        metrics.axiom_clean,
    )
    if (
        metrics.final_proof_compiles
        and metrics.final_proof_sorry_free
        and metrics.statement_preserved
        and metrics.axiom_clean
    ):
        return "solved"
    if metrics.silent_failure:
        return "silent_failure"
    # Environment artifact after a solved check: an exploratory failed compile
    # must not override a final proof that independently validates.
    if _looks_like_import_error(events):
        return "import_error"
    if metrics.has_submission and any(v is None for v in verdict_fields) and not any(
        v is False for v in verdict_fields
    ):
        return "validation_unknown"
    return "unsolved"


def run_one_trial(record: ProblemRecord, trial: int, compiler) -> TrialOutcome:
    from traj_eval.tools.lean_search import make_search_lemmas

    task = to_lean_task(record)
    context_note = (
        f"\n\nThe theorem is stated in this context (already in scope; do not restate it, "
        f"and keep these when you write the proof):\n{record.context}"
        if record.context
        else ""
    )
    prompt = (
        f"Prove this Lean 4 theorem (source: {record.source}, difficulty: {record.difficulty}).\n\n"
        f"Informal statement:\n{record.informal}\n\n"
        f"Formal statement to prove:\n{record.statement}{context_note}\n\n"
        "The reasoner should give a strategy (use search_lemmas to find relevant "
        "Mathlib results), the engineer should formalise and verify with check_lean, "
        "and the critic should review faithfulness."
    )

    llm_config = build_llm_config()
    ledger = RoutingLedger()
    step_context = StepContext()
    manager, user, groupchat, run_state = build_lean_free_team(
        llm_config,
        tools={
            "check_lean": compiler.as_tool(),
            "search_lemmas": make_search_lemmas(num_results=5),
        },
        max_turns=30,
        ledger=ledger,
        step_context=step_context,
    )

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{record.id}_t{trial}.jsonl"
    meta = make_trial_meta(
        trial_id=f"{record.id}_t{trial}",
        task_id=record.id,
        backbone=os.environ.get("TRAJ_EVAL_MODEL", "gpt-4o-mini"),
        testbed="lean",
    )
    writer = TrialLogWriter(log_path, meta)
    observer = TraceObserver(
        writer, trial_id=f"{record.id}_t{trial}", ledger=ledger, step_context=step_context
    )
    observer.attach([a for a in groupchat.agents if a.name != "user"])
    observer.record_task(prompt)

    user.initiate_chat(manager, message=prompt, clear_history=True)
    writer.close()
    finalize_run(run_state)

    _, events = read_trial(log_path)
    metrics = validate(events, task, compiler=compiler)
    art = extract_artifacts(events)
    rep = detect_perseveration(art.tool_calls)
    outcome = _classify(events, metrics, run_state)

    return TrialOutcome(
        task_id=record.id,
        difficulty=record.difficulty,
        trial=trial,
        outcome=outcome,
        termination=run_state.reason,
        n_tool_calls=rep.n_tool_calls,
        perseverated=rep.perseverated,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--difficulty", nargs="+", default=["easy"], help="tiers to run")
    ap.add_argument("--trials", type=int, default=3, help="trials per problem")
    ap.add_argument("--skip-existing", action="store_true", help="skip existing valid trace files")
    ap.add_argument("--dry-run", action="store_true", help="list problems and exit")
    args = ap.parse_args()

    records: list[ProblemRecord] = []
    for diff in args.difficulty:
        records.extend(load_dataset(DATASET_ROOT, difficulty=diff))

    if args.dry_run:
        print(f"Would run {len(records)} problems x {args.trials} trials:")
        for r in records:
            print(f"  {r.id:22s} {r.source:8s} {r.difficulty}")
        return 0

    print(f"Starting REAL Lean compiler against {PROJECT_DIR}...")
    from traj_eval.tools.lean_cli_compiler import LeanCliCompiler

    compiler = LeanCliCompiler(PROJECT_DIR, timeout=LEAN_TIMEOUT)
    print("Compiler ready.\n")

    outcomes: list[TrialOutcome] = []
    for r in records:
        for t in range(args.trials):
            log_path = LOG_DIR / f"{r.id}_t{t}.jsonl"
            if args.skip_existing and _trace_is_valid(log_path):
                print(f"  skipping {r.id} trial {t + 1}/{args.trials} (existing valid trace)")
                continue
            print(f"  running {r.id} trial {t + 1}/{args.trials} ...", flush=True)
            try:
                outcomes.append(run_one_trial(r, t, compiler))
            except Exception as e:  # noqa: BLE001 -- one bad trial must not kill the batch
                print(f"    ERROR in {r.id} t{t}: {type(e).__name__}: {str(e)[:200]}")

    _report(outcomes, args.trials)
    return 0


def _report(outcomes: list[TrialOutcome], trials: int) -> None:
    print("\n==================== per-problem ====================")
    by_task: dict[str, list[TrialOutcome]] = {}
    for o in outcomes:
        by_task.setdefault(o.task_id, []).append(o)
    for task_id, os_ in sorted(by_task.items()):
        c = Counter(o.outcome for o in os_)
        diff = os_[0].difficulty
        summary = ", ".join(f"{k}={v}" for k, v in sorted(c.items()))
        print(f"  {task_id:22s} [{diff:6s}] {summary}")

    print("\n==================== by tier ====================")
    by_diff: dict[str, list[TrialOutcome]] = {}
    for o in outcomes:
        by_diff.setdefault(o.difficulty, []).append(o)
    for diff, os_ in sorted(by_diff.items()):
        c = Counter(o.outcome for o in os_)
        n = len(os_)
        solved = c.get("solved", 0)
        print(f"  {diff:8s} n={n:3d}  " + "  ".join(f"{k}={v}" for k, v in sorted(c.items())))
        real = n - c.get("import_error", 0)  # exclude env artifacts from the rate
        if real:
            rate = solved / real
            print(f"           solve rate (excl. import errors): {solved}/{real} = {rate:.2f}")

    print("\n==================== overall ====================")
    c = Counter(o.outcome for o in outcomes)
    print(f"  total trials: {len(outcomes)}")
    for k, v in sorted(c.items()):
        print(f"    {k:16s}: {v}")


if __name__ == "__main__":
    raise SystemExit(main())
