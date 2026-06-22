"""Smoke test for the offline validator with the REAL kernel.

Loads a saved trace JSONL and runs validate() with a live LeanCompiler against
~/lean_anchor, so Group B (final_proof_compiles, sorry_free, statement_preserved,
axiom_clean) is exercised on actual data. Group A needs no kernel.

Run: uv run python scripts/smoke_validate.py [path/to/trace.jsonl]
Default trace: data/smoke_lean.jsonl (produced by scripts/smoke_lean.py).

The intended LeanTask is hand-written here (the dataset layer will provide these
later). It is set to the add_comm task that smoke_lean.py runs.
"""

from __future__ import annotations

import sys
from pathlib import Path

from traj_eval.metrics.lean.validator import LeanTask, validate
from traj_eval.tools.lean_compiler import LeanCompiler
from traj_eval.trace_core.storage import read_trial

PROJECT_DIR = Path.home() / "lean_anchor"
DEFAULT_TRACE = Path("data/smoke_lean.jsonl")

# Must match the theorem smoke_lean.py asks the agent to prove.
TASK = LeanTask(
    task_id="add_comm",
    statement="theorem add_comm_example (a b : Nat) : a + b = b + a",
)


def main() -> None:
    trace_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TRACE
    if not trace_path.exists():
        print(f"Trace not found: {trace_path}. Run scripts/smoke_lean.py first.")
        return

    _, events = read_trial(trace_path)
    print(f"Loaded {len(events)} events from {trace_path}")

    print(f"Starting Lean compiler against {PROJECT_DIR} (first run is slow)...")
    compiler = LeanCompiler(PROJECT_DIR)
    print("Compiler ready.\n")

    m = validate(events, TASK, compiler=compiler)

    print("==================== Group A (trace) ====================")
    print(f"  compiler_was_called       : {m.compiler_was_called}")
    print(f"  n_tool_calls              : {m.n_tool_calls}")
    print(f"  n_failed_compiles         : {m.n_failed_compiles}")
    print(f"  submitted_eq_last_verified: {m.submitted_eq_last_verified}")
    print(f"  declared_success          : {m.declared_success}")
    print(f"  has_submission            : {m.has_submission}")
    print("==================== Group B (kernel) ===================")
    print(f"  final_proof_compiles      : {m.final_proof_compiles}")
    print(f"  final_proof_sorry_free    : {m.final_proof_sorry_free}")
    print(f"  statement_preserved       : {m.statement_preserved}")
    print(f"  axiom_clean               : {m.axiom_clean}")
    print(f"  extra_axioms              : {m.extra_axioms}")
    print("==================== Derived ============================")
    print(f"  silent_failure            : {m.silent_failure}")


if __name__ == "__main__":
    main()
