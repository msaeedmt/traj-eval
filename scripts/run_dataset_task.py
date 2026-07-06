"""Run one benchmark problem end-to-end through the free-routing Lean team, then
score it with the offline validator and the perseveration detector.

This is the first script that runs the pipeline on REAL dataset problems rather
than the hand-written add_comm smoke. It loads a problem by id from
dataset/Lean, hands the agents its informal + formal statement, runs with the
real compiler + retrieval, and prints: the trajectory, the termination reason,
the validator metrics (including silent_failure and statement_preserved against
the intended statement), and the perseveration report.

Usage:
    TRAJ_EVAL_MODEL=gpt-4o uv run python scripts/run_dataset_task.py easy_fatem_011
    uv run python scripts/run_dataset_task.py                 # lists ids and exits
    uv run python scripts/run_dataset_task.py --difficulty easy   # first easy id
"""

from __future__ import annotations

import sys
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
from traj_eval.dataset.loader import load_dataset, to_lean_task
from traj_eval.detectors.perseveration import detect_perseveration
from traj_eval.metrics.lean.artifacts import extract_artifacts
from traj_eval.metrics.lean.validator import validate
from traj_eval.trace_core.storage import TrialLogWriter, read_trial

DATASET_ROOT = Path("dataset/Lean")
PROJECT_DIR = Path.home() / "lean_anchor"
LOG_DIR = Path("data/runs")


def _task_prompt(record) -> str:
    return (
        f"Prove this Lean 4 theorem (source: {record.source}, "
        f"difficulty: {record.difficulty}).\n\n"
        f"Informal statement:\n{record.informal}\n\n"
        f"Formal statement to prove:\n{record.statement}\n\n"
        "The reasoner should give a strategy (use search_lemmas to find relevant "
        "Mathlib results), the engineer should formalise and verify with "
        "check_lean, and the critic should review faithfulness."
    )


def main(argv: list[str]) -> int:
    records = load_dataset(DATASET_ROOT)
    if not argv:
        print("Available problem ids:\n")
        for r in records:
            print(f"  {r.id:22s} {r.source:8s} {r.difficulty}")
        print("\nRun:  uv run python scripts/run_dataset_task.py <id>")
        return 0

    if argv[0] == "--difficulty":
        wanted = load_dataset(DATASET_ROOT, difficulty=argv[1])
        record = wanted[0]
    else:
        record = next((r for r in records if r.id == argv[0]), None)
        if record is None:
            print(f"Unknown id {argv[0]!r}. Run with no args to list ids.")
            return 1

    task = to_lean_task(record)
    prompt = _task_prompt(record)
    print(f"=== {record.id} ({record.source}, {record.difficulty}) ===")
    print(f"imports: {record.imports}\n")

    from traj_eval.tools.lean_compiler import LeanCompiler
    from traj_eval.tools.lean_search import make_search_lemmas

    print(f"Starting REAL Lean compiler against {PROJECT_DIR} (first run is slow)...")
    compiler = LeanCompiler(PROJECT_DIR)
    print("Compiler ready.\n")

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
    log_path = LOG_DIR / f"{record.id}.jsonl"
    meta = make_trial_meta(
        trial_id=record.id,
        task_id=record.id,
        backbone="env:TRAJ_EVAL_MODEL",
        testbed="lean",
    )
    writer = TrialLogWriter(log_path, meta)
    observer = TraceObserver(writer, trial_id=record.id, ledger=ledger, step_context=step_context)
    observer.attach([a for a in groupchat.agents if a.name != "user"])
    observer.record_task(prompt)

    user.initiate_chat(manager, message=prompt, clear_history=True)
    writer.close()
    finalize_run(run_state)

    _, events = read_trial(log_path)

    print("\n==================== trajectory ====================")
    for e in events:
        marker = ""
        if e.payload.get("handoff_target"):
            marker = f"-> HANDOFF:{e.payload['handoff_target']}"
        elif e.payload.get("decision"):
            marker = f"[{e.payload['decision']}]"
        body = (e.payload.get("text", "") or "").replace("\n", " ")[:45]
        print(f"  {e.agent_role.value:9s}#{e.seq} {e.event_type.value:17s} {marker:22s} {body!r}")

    print("\n==================== checks ====================")
    print(f"  termination reason : {run_state.reason}")
    print(f"  total turns        : {run_state.turns}")
    print(f"  max identical calls: {run_state.max_identical_calls_seen}")

    # Offline validation (Group A + Group B) against the intended statement.
    metrics = validate(events, task, compiler=compiler)
    print("\n==================== validator ====================")
    for k, v in metrics.__dict__.items():
        print(f"  {k:24s}: {v}")

    # Perseveration detector.
    art = extract_artifacts(events)
    rep = detect_perseveration(art.tool_calls)
    print("\n==================== perseveration ====================")
    print(f"  tool calls         : {rep.n_tool_calls}")
    print(f"  failed compiles    : {rep.n_failed_compiles}")
    print(f"  perseverated       : {rep.perseverated}")
    print(f"  max_repeat         : {rep.max_repeat}")
    print(f"  retry_success_rate : {rep.retry_success_rate}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
