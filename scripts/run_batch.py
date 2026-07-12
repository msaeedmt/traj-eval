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
import json
import os
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from traj_eval.agents import (
    RoutingLedger,
    StepContext,
    TraceObserver,
    build_llm_config,
    make_trial_meta,
)
from traj_eval.agents.free_routing import finalize_run
from traj_eval.agents.lean_team import (
    RECOVERY_TRIANGLE_V1,
    SUPPORTED_LEAN_SETUPS,
    TOOL_ROUTED_SUBGOALS_V1,
    build_lean_free_team,
)
from traj_eval.agents.subgoal_state import SubgoalLedger, make_subgoal_tools
from traj_eval.dataset.loader import ProblemRecord, load_dataset, to_lean_task
from traj_eval.detectors.perseveration import detect_perseveration
from traj_eval.metrics.communication import CommunicationSummary, summarize_communication
from traj_eval.metrics.lean.artifacts import extract_artifacts
from traj_eval.metrics.lean.outcomes import classify_outcome
from traj_eval.metrics.lean.validator import validate, validate_candidate
from traj_eval.trace_core.graph import build_graph
from traj_eval.trace_core.schema import AgentRole
from traj_eval.trace_core.storage import TrialLogWriter, read_trial

DATASET_ROOT = Path("dataset/Lean")
PROJECT_DIR = Path(os.environ.get("TRAJ_EVAL_LEAN_PROJECT", str(DATASET_ROOT)))
LEAN_TIMEOUT = int(os.environ.get("TRAJ_EVAL_LEAN_TIMEOUT", "360"))
LOG_DIR = Path("data/batch")


@dataclass
class TrialOutcome:
    task_id: str
    difficulty: str
    trial: int
    outcome: str  # 'solved' | 'silent_failure' | 'unsolved' | 'import_error' | 'validation_unknown'
    termination: str | None
    n_tool_calls: int
    perseverated: bool
    communication: CommunicationSummary


def _trace_is_valid(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        read_trial(path)
    except Exception:  # noqa: BLE001 -- invalid traces should be regenerated
        return False
    return True


def _recorded_termination(events) -> str:
    for event in reversed(events):
        if event.payload.get("phase") == "termination":
            return str(event.payload.get("termination_reason") or "framework_stop")
    return "offline_rescore"


def _explore_trace(path: Path) -> dict:
    """Return compact deterministic plan and causal-graph facts for one JSONL trace."""
    meta, events = read_trial(path)
    graph = build_graph(events)
    plan_event = next(
        (event for event in reversed(events) if event.payload.get("phase") == "controller_plan"),
        None,
    )
    plan = plan_event.payload.get("plan", {}) if plan_event else {}
    final_state = plan.get("final_state", {})
    role_path = [event.agent_role.value for event in events]
    transitions = Counter(
        f"{left}->{right}" for left, right in zip(role_path, role_path[1:], strict=False)
    )
    return {
        "trial_id": meta.trial_id,
        "task_id": meta.task_id,
        "path": path.name,
        "n_events": len(events),
        "graph": {
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
            "roots": sum(graph.in_degree(node) == 0 for node in graph.nodes),
            "leaves": sum(graph.out_degree(node) == 0 for node in graph.nodes),
        },
        "role_transitions": dict(sorted(transitions.items())),
        "controller_plan": {
            "present": plan_event is not None,
            "owner_role": plan.get("owner_role"),
            "history_length": len(plan.get("history", [])),
            "version": final_state.get("version"),
            "plan_ready": final_state.get("plan_ready"),
            "active_subgoal": final_state.get("active_subgoal"),
            "forced_recoveries": final_state.get("forced_recoveries"),
            "strategy_revisions": final_state.get("strategy_revisions"),
            "nodes": final_state.get("nodes", []),
        },
    }


def _explore_traces(output_dir: Path, records: list[ProblemRecord], trials: int) -> list[dict]:
    explored = []
    for record in records:
        for trial in range(trials):
            path = output_dir / f"{record.id}_t{trial}.jsonl"
            if _trace_is_valid(path):
                explored.append(_explore_trace(path))
    return explored


def _task_prompt(
    record: ProblemRecord, *, setup: str = RECOVERY_TRIANGLE_V1
) -> str:
    context_note = (
        f"\n\nThe theorem is stated in this context (already in scope; do not restate it, "
        f"and keep these when you write the proof):\n{record.context}"
        if record.context
        else ""
    )
    medium_detail = (
        "For this medium task, define four to six concrete compile-verifiable artifacts; "
        "do not use vague understand/find/investigate subgoals. "
        if record.difficulty == "medium"
        else ""
    )
    coordination = (
        "Use the typed subgoal tools to decompose, verify, review, and route. "
        f"{medium_detail}"
        "Build at least two work subgoals plus one final integration subgoal; "
        "use sequential dependencies when the mathematics is sequential. "
        "Do not use HANDOFF or VERDICT text markers."
        if setup == TOOL_ROUTED_SUBGOALS_V1
        else "Each role chooses its next allowed action."
    )
    return (
        f"Prove this Lean 4 theorem (source: {record.source}, difficulty: {record.difficulty}).\n\n"
        f"Informal statement:\n{record.informal}\n\n"
        f"Formal statement to prove:\n{record.statement}{context_note}\n\n"
        f"{coordination} Use search_lemmas and compiler tools "
        "when they resolve real uncertainty. Hand off only when the receiving role can "
        "act on concrete mathematical, compiler, or review evidence. A non-linear route "
        "is allowed, but extra communication is not itself success. The final proof must "
        "compile, preserve the exact statement, and contain no sorry, admit, or added axiom."
    )


def _resolve_worker_thinking(model: str, mode: str) -> bool | None:
    """Map the CLI mode to the provider request; Qwen defaults to non-thinking."""
    if mode == "enabled":
        return True
    if mode == "disabled":
        return False
    if mode != "auto":
        raise ValueError(f"unsupported worker thinking mode: {mode}")
    return False if "qwen" in model.casefold() else None


def _configure_console() -> None:
    """Keep Lean symbols printable in Windows terminals."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="backslashreplace")


def _score_trace(
    record: ProblemRecord,
    trial: int,
    compiler,
    log_path: Path,
    *,
    termination: str | None,
) -> TrialOutcome:
    task = to_lean_task(record)
    _, events = read_trial(log_path)
    metrics = validate(events, task, compiler=compiler)
    art = extract_artifacts(events)
    rep = detect_perseveration(art.tool_calls)

    return TrialOutcome(
        task_id=record.id,
        difficulty=record.difficulty,
        trial=trial,
        outcome=classify_outcome(events, metrics),
        termination=termination,
        n_tool_calls=rep.n_tool_calls,
        perseverated=rep.perseverated,
        communication=summarize_communication(events),
    )


def run_one_trial(
    record: ProblemRecord,
    trial: int,
    compiler,
    *,
    output_dir: Path = LOG_DIR,
    setup: str = RECOVERY_TRIANGLE_V1,
    max_turns: int = 30,
    max_engineer_failures: int = 3,
    max_forced_replans: int = 2,
    worker_model: str | None = None,
    reasoner_max_tokens: int = 2048,
    engineer_max_tokens: int = 4096,
    critic_max_tokens: int = 2048,
    outer_orchestrator: str = "external_controller",
    worker_thinking: str = "auto",
) -> TrialOutcome:
    from traj_eval.tools.lean_search import make_search_lemmas

    prompt = _task_prompt(record, setup=setup)

    worker_model = worker_model or os.environ.get("TRAJ_EVAL_MODEL", "gpt-4o-mini")
    enable_thinking = _resolve_worker_thinking(worker_model, worker_thinking)
    role_budgets = {
        AgentRole.REASONER: reasoner_max_tokens,
        AgentRole.ENGINEER: engineer_max_tokens,
        AgentRole.CRITIC: critic_max_tokens,
    }
    role_llm_configs = {
        role: build_llm_config(
            model=worker_model,
            max_tokens=budget,
            enable_thinking=enable_thinking,
        )
        for role, budget in role_budgets.items()
    }
    # Speaker selection is deterministic, so the manager model is only an AG2
    # construction requirement and receives the smallest worker budget.
    llm_config = build_llm_config(
        model=worker_model,
        max_tokens=min(role_budgets.values()),
        enable_thinking=enable_thinking,
    )
    routing_ledger = RoutingLedger()
    step_context = StepContext()
    search_lemmas = make_search_lemmas(num_results=5)
    if setup == TOOL_ROUTED_SUBGOALS_V1:
        task = to_lean_task(record)
        subgoal_ledger = SubgoalLedger(
            min_nodes=4 if record.difficulty == "medium" else 3,
            max_failures=max_engineer_failures,
            max_forced_replans=max_forced_replans,
        )
        tools = make_subgoal_tools(
            compiler,
            subgoal_ledger,
            final_validator=lambda code: validate_candidate(code, task, compiler),
            prelude=record.import_block,
            auto_submit_verified=True,
        )
        tools["search_lemmas"] = search_lemmas

        def post_tool_route(
            caller: AgentRole, called: frozenset[str]
        ) -> tuple[AgentRole, str] | None:
            if (
                caller is AgentRole.REASONER
                and subgoal_ledger.plan_ready
                and "route_next_agent" not in called
            ):
                return AgentRole.ENGINEER, "controller_plan_ready_fallback"
            return None
    else:
        tools = {
            "check_lean": compiler.as_tool(),
            "search_lemmas": search_lemmas,
        }
        post_tool_route = None
    manager, user, groupchat, run_state = build_lean_free_team(
        llm_config,
        tools=tools,
        setup=setup,
        max_turns=max_turns,
        ledger=routing_ledger,
        step_context=step_context,
        role_llm_configs=role_llm_configs,
        post_tool_route=post_tool_route,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / f"{record.id}_t{trial}.jsonl"
    meta = make_trial_meta(
        trial_id=f"{record.id}_t{trial}",
        task_id=record.id,
        backbone=worker_model,
        testbed="lean",
        architecture=f"lean_{setup}",
        grounding=True,
        config={
            "setup": setup,
            "prompt_revision": setup,
            "routing_policy": (
                "tool_routed_subgoal_dag"
                if setup == TOOL_ROUTED_SUBGOALS_V1
                else "agent_chosen_handoffs"
            ),
            "provider_route": "openai_compatible",
            "tools": sorted(tools),
            "max_turns": max_turns,
            "max_engineer_failures": max_engineer_failures,
            "max_forced_replans": max_forced_replans,
            "min_subgoals": (
                subgoal_ledger.min_nodes if setup == TOOL_ROUTED_SUBGOALS_V1 else None
            ),
            "outer_orchestrator": outer_orchestrator,
            "worker_models": {
                role.value: worker_model for role in role_budgets
            },
            "role_max_tokens": {
                role.value: budget for role, budget in role_budgets.items()
            },
            "controller_uses_llm": False,
            "worker_enable_thinking": enable_thinking,
            "compiler_context": "canonical_task_prelude",
        },
    )
    writer = TrialLogWriter(log_path, meta)
    observer = TraceObserver(
        writer,
        trial_id=f"{record.id}_t{trial}",
        ledger=routing_ledger,
        step_context=step_context,
    )
    observer.attach([a for a in groupchat.agents if a.name != "user"])
    observer.record_task(prompt)

    try:
        user.initiate_chat(manager, message=prompt, clear_history=True)
    except Exception as exc:
        observer.record_infrastructure_error(exc)
        raise
    finally:
        finalize_run(run_state)
        try:
            if setup == TOOL_ROUTED_SUBGOALS_V1:
                observer.record_controller_plan(subgoal_ledger.plan_record())
            observer.record_termination(
                run_state.reason or "framework_stop",
                turns=run_state.turns,
                invalid_handoffs=run_state.invalid_handoffs,
                tool_handoffs=run_state.tool_handoffs,
                forced_recoveries=run_state.forced_recoveries,
                completion_gate_denials=run_state.completion_gate_denials,
                tool_protocol_errors=run_state.tool_protocol_errors,
                controller_fallback_routes=run_state.controller_fallback_routes,
            )
        finally:
            writer.close()

    return _score_trace(
        record,
        trial,
        compiler,
        log_path,
        termination=run_state.reason,
    )


def main() -> int:
    _configure_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("--difficulty", nargs="+", default=["easy"], help="tiers to run")
    ap.add_argument("--trials", type=int, default=3, help="trials per problem")
    ap.add_argument(
        "--task-id",
        nargs="+",
        help="run one or more exact dataset task ids",
    )
    ap.add_argument(
        "--setup",
        choices=SUPPORTED_LEAN_SETUPS,
        default=RECOVERY_TRIANGLE_V1,
        help="named Lean agent setup recorded in TrialMeta",
    )
    ap.add_argument("--output-dir", type=Path, default=LOG_DIR, help="isolated trace directory")
    ap.add_argument("--max-turns", type=int, default=30, help="routing decision budget")
    ap.add_argument(
        "--worker-model",
        help="low-cost model used by reasoner, engineer, and critic",
    )
    ap.add_argument("--reasoner-max-tokens", type=int, default=2048)
    ap.add_argument("--engineer-max-tokens", type=int, default=4096)
    ap.add_argument("--critic-max-tokens", type=int, default=2048)
    ap.add_argument(
        "--worker-thinking",
        choices=("auto", "disabled", "enabled"),
        default="auto",
        help="Qwen thinking mode; auto disables it for Qwen models",
    )
    ap.add_argument(
        "--outer-orchestrator",
        default="external_controller",
        help="research orchestrator identity recorded in TrialMeta only",
    )
    ap.add_argument(
        "--max-engineer-failures",
        type=int,
        default=3,
        help="failed proof compiles before tool-directed reasoner recovery",
    )
    ap.add_argument(
        "--max-forced-replans",
        type=int,
        default=2,
        help="maximum forced reasoner recoveries per trial",
    )
    ap.add_argument("--skip-existing", action="store_true", help="skip existing valid trace files")
    ap.add_argument(
        "--summarize-existing",
        action="store_true",
        help="score existing traces and write summaries without calling the model",
    )
    ap.add_argument("--dry-run", action="store_true", help="list problems and exit")
    args = ap.parse_args()

    records: list[ProblemRecord] = []
    for diff in args.difficulty:
        records.extend(load_dataset(DATASET_ROOT, difficulty=diff))
    if args.task_id:
        requested = set(args.task_id)
        records = [record for record in records if record.id in requested]
        missing = requested - {record.id for record in records}
        if missing:
            ap.error(f"task ids not found in selected difficulties: {sorted(missing)}")

    if args.dry_run:
        print(
            f"Would run setup={args.setup}: {len(records)} problems x {args.trials} trials "
            f"into {args.output_dir}:"
        )
        for r in records:
            print(f"  {r.id:22s} {r.source:8s} {r.difficulty}")
        return 0

    print(f"Starting REAL Lean compiler against {PROJECT_DIR}...")
    from traj_eval.tools.lean_cli_compiler import LeanCliCompiler

    compiler = LeanCliCompiler(PROJECT_DIR, timeout=LEAN_TIMEOUT)
    print("Compiler ready.\n")

    outcomes: list[TrialOutcome] = []
    errors: list[dict[str, str | int]] = []
    observed_models: set[str] = set()
    for r in records:
        for t in range(args.trials):
            log_path = args.output_dir / f"{r.id}_t{t}.jsonl"
            if args.summarize_existing:
                if not _trace_is_valid(log_path):
                    errors.append(
                        {
                            "task_id": r.id,
                            "trial": t,
                            "error_type": "InvalidTrace",
                            "message": f"missing or invalid trace: {log_path}",
                        }
                    )
                    continue
                print(f"  scoring {r.id} trial {t + 1}/{args.trials} ...", flush=True)
                try:
                    trace_meta, trace_events = read_trial(log_path)
                    observed_models.add(trace_meta.backbone)
                    outcomes.append(
                        _score_trace(
                            r,
                            t,
                            compiler,
                            log_path,
                            termination=_recorded_termination(trace_events),
                        )
                    )
                except Exception as e:  # noqa: BLE001 -- report every invalid trial
                    print(f"    ERROR in {r.id} t{t}: {type(e).__name__}: {str(e)[:200]}")
                    errors.append(
                        {
                            "task_id": r.id,
                            "trial": t,
                            "error_type": type(e).__name__,
                            "message": str(e)[:200],
                        }
                    )
                continue
            if args.skip_existing and _trace_is_valid(log_path):
                print(f"  skipping {r.id} trial {t + 1}/{args.trials} (existing valid trace)")
                continue
            print(f"  running {r.id} trial {t + 1}/{args.trials} ...", flush=True)
            try:
                outcomes.append(
                    run_one_trial(
                        r,
                        t,
                        compiler,
                        output_dir=args.output_dir,
                        setup=args.setup,
                        max_turns=args.max_turns,
                        max_engineer_failures=args.max_engineer_failures,
                        max_forced_replans=args.max_forced_replans,
                        worker_model=args.worker_model,
                        reasoner_max_tokens=args.reasoner_max_tokens,
                        engineer_max_tokens=args.engineer_max_tokens,
                        critic_max_tokens=args.critic_max_tokens,
                        outer_orchestrator=args.outer_orchestrator,
                        worker_thinking=args.worker_thinking,
                    )
                )
            except Exception as e:  # noqa: BLE001 -- one bad trial must not kill the batch
                print(f"    ERROR in {r.id} t{t}: {type(e).__name__}: {str(e)[:200]}")
                errors.append(
                    {
                        "task_id": r.id,
                        "trial": t,
                        "error_type": type(e).__name__,
                        "message": str(e)[:200],
                    }
                )

    summary_model = (
        ", ".join(sorted(observed_models))
        if observed_models
        else (args.worker_model or os.environ.get("TRAJ_EVAL_MODEL", "gpt-4o-mini"))
    )
    summary = _build_run_summary(
        outcomes,
        expected_trials=len(records) * args.trials,
        setup=args.setup,
        model=summary_model,
        errors=errors,
    )
    summary["trace_exploration"] = _explore_traces(args.output_dir, records, args.trials)
    _report(outcomes, summary)
    _write_summary(args.output_dir, summary)
    return 0


def _build_run_summary(
    outcomes: list[TrialOutcome],
    *,
    expected_trials: int,
    setup: str,
    model: str,
    errors: list[dict[str, str | int]] | None = None,
) -> dict:
    errors = errors or []
    outcome_counts = Counter(outcome.outcome for outcome in outcomes)
    termination_counts = Counter(outcome.termination or "unknown" for outcome in outcomes)
    eligible = sum(outcome.communication.failed_compile_results > 0 for outcome in outcomes)
    evidence_backed = sum(
        outcome.communication.evidence_backed_revisions > 0 for outcome in outcomes
    )
    productive = sum(
        outcome.outcome == "solved"
        and outcome.communication.revision_followed_by_compile_success
        for outcome in outcomes
    )
    verified_completions = sum(
        outcome.communication.verified_completion for outcome in outcomes
    )

    if setup == TOOL_ROUTED_SUBGOALS_V1:
        tool_handoffs = sum(outcome.communication.tool_handoffs for outcome in outcomes)
        accepted_subgoals = sum(
            outcome.communication.subgoals_accepted for outcome in outcomes
        )
        forced_recoveries = sum(
            outcome.communication.forced_recoveries for outcome in outcomes
        )
        revisions = sum(outcome.communication.strategy_revisions for outcome in outcomes)
        if tool_handoffs == 0:
            decision = "tool_routing_not_adopted"
        elif accepted_subgoals == 0:
            decision = "subgoal_gate_not_reached"
        elif verified_completions > 0 and outcome_counts.get("solved", 0) > 0:
            decision = "feasibility_demonstrated_no_o3_claim"
        elif verified_completions > 0 and outcome_counts.get("silent_failure", 0) > 0:
            decision = "final_faithfulness_gate_required"
        elif forced_recoveries > 0 and revisions == 0:
            decision = "reasoner_recovery_not_adopted"
        else:
            decision = "revise_subgoal_strategy"
    elif eligible == 0:
        decision = "inconclusive_no_recovery_opportunity"
    elif evidence_backed == 0:
        decision = "advance_to_strategy_critic"
    elif productive == 0:
        decision = "revise_prompt_or_tool_evidence"
    else:
        decision = "scale_recovery_triangle_to_10_trials"

    communication_fields = (
        "explicit_handoffs",
        "reasoner_to_engineer",
        "engineer_to_reasoner",
        "engineer_to_critic",
        "critic_to_engineer",
        "implicit_reasoner_reentries",
        "failed_compile_results",
        "successful_compile_results",
        "critic_rechecks",
        "critic_approvals",
        "critic_rejections",
        "evidence_backed_revisions",
        "tool_handoffs",
        "forced_recoveries",
        "strategy_revisions",
        "subgoals_defined",
        "subgoals_accepted",
        "subgoals_rejected",
        "critic_gate_denials",
    )
    communication = {
        field: sum(getattr(outcome.communication, field) for outcome in outcomes)
        for field in communication_fields
    }
    communication.update(
        {
            "eligible_recovery_trials": eligible,
            "evidence_backed_revision_trials": evidence_backed,
            "productive_recovery_trials": productive,
            "verified_completion_trials": verified_completions,
            "engineer_local_repair_trials": sum(
                outcome.communication.failed_compile_results > 0
                and outcome.communication.successful_compile_results > 0
                and outcome.communication.evidence_backed_revisions == 0
                for outcome in outcomes
            ),
            "reasoner_stall_trials": sum(
                outcome.communication.reasoner_to_engineer == 0 for outcome in outcomes
            ),
            "unfinished_before_critic_trials": sum(
                outcome.communication.reasoner_to_engineer > 0
                and outcome.communication.engineer_to_critic == 0
                and outcome.communication.engineer_to_reasoner == 0
                for outcome in outcomes
            ),
            "critic_masking_trials": sum(
                outcome.outcome == "silent_failure"
                and outcome.communication.critic_approvals > 0
                for outcome in outcomes
            ),
        }
    )

    return {
        "schema_version": "lean_agent_setup_summary_v1",
        "setup": setup,
        "model": model,
        "expected_trials": expected_trials,
        "completed_trials": len(outcomes),
        "provider_status": "complete" if not errors else "partial_or_failed",
        "outcomes": dict(sorted(outcome_counts.items())),
        "termination_reasons": dict(sorted(termination_counts.items())),
        "communication": communication,
        "decision": decision,
        "proposal_status": {
            "O1": "pilot evidence for explicit handoff localisation",
            "O2": "pilot evidence for coordination and recovery labels",
            "O3": "not claimed from this feasibility pilot",
        },
        "errors": errors,
        "trials": [
            {
                "task_id": outcome.task_id,
                "trial": outcome.trial,
                "outcome": outcome.outcome,
                "termination": outcome.termination,
                "perseverated": outcome.perseverated,
                "communication": asdict(outcome.communication),
            }
            for outcome in outcomes
        ],
    }


def _write_summary(output_dir: Path, summary: dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    communication = summary["communication"]
    lines = [
        "# Qwen Lean Agent Pilot",
        "",
        f"- Setup: `{summary['setup']}`",
        f"- Model: `{summary['model']}`",
        f"- Completed: {summary['completed_trials']}/{summary['expected_trials']}",
        f"- Provider status: `{summary['provider_status']}`",
        f"- Decision: `{summary['decision']}`",
        "",
        "## Outcomes",
        "",
    ]
    lines.extend(f"- {name}: {count}" for name, count in summary["outcomes"].items())
    lines.extend(
        [
            "",
            "## Communication",
            "",
            f"- Explicit handoffs: {communication['explicit_handoffs']}",
            f"- Engineer to reasoner: {communication['engineer_to_reasoner']}",
            f"- Critic to engineer: {communication['critic_to_engineer']}",
            f"- Eligible recovery trials: {communication['eligible_recovery_trials']}",
            "- Evidence-backed revision trials: "
            f"{communication['evidence_backed_revision_trials']}",
            f"- Productive recovery trials: {communication['productive_recovery_trials']}",
            "- Implicit/fallback reasoner reentries: "
            f"{communication['implicit_reasoner_reentries']}",
            f"- Engineer-local repair trials: {communication['engineer_local_repair_trials']}",
            f"- Reasoner stall trials: {communication['reasoner_stall_trials']}",
            f"- Critic masking trials: {communication['critic_masking_trials']}",
            f"- Tool handoffs: {communication['tool_handoffs']}",
            f"- Forced recoveries: {communication['forced_recoveries']}",
            f"- Strategy revisions: {communication['strategy_revisions']}",
            f"- Subgoals accepted: {communication['subgoals_accepted']}",
            f"- Critic gate denials: {communication['critic_gate_denials']}",
            "- Verified completion trials: "
            f"{communication['verified_completion_trials']}",
            "",
            "## Proposal Interpretation",
            "",
            "This pilot tests O1/O2 observability of tool-routed recovery and review.",
            "It does not support an O3 architecture-improvement claim.",
        ]
    )
    (output_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _report(outcomes: list[TrialOutcome], summary: dict) -> None:
    print("\n==================== per-problem ====================")
    by_task: dict[str, list[TrialOutcome]] = {}
    for o in outcomes:
        by_task.setdefault(o.task_id, []).append(o)
    for task_id, os_ in sorted(by_task.items()):
        c = Counter(o.outcome for o in os_)
        diff = os_[0].difficulty
        outcome_text = ", ".join(f"{k}={v}" for k, v in sorted(c.items()))
        print(f"  {task_id:22s} [{diff:6s}] {outcome_text}")

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
    print("\n==================== communication ====================")
    for key, value in summary["communication"].items():
        print(f"    {key:32s}: {value}")
    print(f"  decision: {summary['decision']}")


if __name__ == "__main__":
    raise SystemExit(main())
