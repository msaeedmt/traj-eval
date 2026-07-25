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
    TOOL_ROUTED_SUBGOALS_V1,
    TOOL_ROUTED_SUBGOALS_WITH_GOAL_TOOLS_V1,
    build_lean_free_team,
)
from traj_eval.dataset.loader import ProblemRecord, load_dataset, to_lean_task
from traj_eval.detectors.perseveration import detect_perseveration
from traj_eval.metrics.communication import CommunicationSummary, summarize_communication
from traj_eval.metrics.lean.artifacts import extract_artifacts
from traj_eval.metrics.lean.outcomes import classify_outcome
from traj_eval.metrics.lean.validator import validate
from traj_eval.trace_core.schema import AgentRole
from traj_eval.trace_core.storage import TrialLogWriter, read_trial

DATASET_ROOT = Path("dataset/Lean")
PROJECT_DIR = Path(os.environ.get("TRAJ_EVAL_LEAN_PROJECT", str(DATASET_ROOT)))
LEAN_TIMEOUT = int(os.environ.get("TRAJ_EVAL_LEAN_TIMEOUT", "360"))
LOG_DIR = Path("data/batch")
LEAN_TOOL_NAMES = ("check_lean", "search_lemmas", "try_tactic", "show_goals")
LEAN_AGENT_ROLES = (
    AgentRole.REASONER,
    AgentRole.ENGINEER,
    AgentRole.CRITIC,
)
DEFAULT_MAX_TURNS = 30
DEFAULT_WORKER_MAX_TOKENS = 1500
DEFAULT_WORKER_TIMEOUT_SECONDS = 180.0


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


def _task_prompt(
    record: ProblemRecord, *, setup: str = RECOVERY_TRIANGLE_V1
) -> str:
    context_note = (
        f"\n\nThe theorem is stated in this context (already in scope; do not restate it, "
        f"and keep these when you write the proof):\n{record.context}"
        if record.context
        else ""
    )
    coordination = (
        "Use the typed subgoal tools to create at least two concrete work "
        "subgoals and one final integration subgoal. Route only through tools; "
        "do not emit HANDOFF or VERDICT markers."
        if setup
        in {
            TOOL_ROUTED_SUBGOALS_V1,
            TOOL_ROUTED_SUBGOALS_WITH_GOAL_TOOLS_V1,
        }
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


def _configure_console() -> None:
    """Keep Lean symbols printable in Windows terminals."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="backslashreplace")


def _resolve_worker_thinking(model: str, mode: str) -> bool | None:
    """Map the CLI mode to the provider request; Qwen defaults to non-thinking."""
    if mode == "enabled":
        return True
    if mode == "disabled":
        return False
    if mode != "auto":
        raise ValueError(f"unsupported worker thinking mode: {mode}")
    return False if "qwen" in model.casefold() else None


def _resolve_role_models(
    *,
    worker_model: str | None,
    reasoner_model: str | None,
    engineer_model: str | None,
    critic_model: str | None,
) -> dict[AgentRole, str]:
    """Resolve role-specific models with the legacy worker model as fallback."""

    fallback = worker_model or os.environ.get("TRAJ_EVAL_MODEL", "gpt-4o-mini")
    requested = {
        AgentRole.REASONER: reasoner_model or fallback,
        AgentRole.ENGINEER: engineer_model or fallback,
        AgentRole.CRITIC: critic_model or fallback,
    }
    resolved: dict[AgentRole, str] = {}
    for role, model in requested.items():
        if not model:
            raise ValueError(f"missing model selection for role {role.value}")
        resolved[role] = model
    return resolved


def _resolve_role_max_tokens(
    *,
    worker_max_tokens: int,
    reasoner_max_tokens: int | None,
    engineer_max_tokens: int | None,
    critic_max_tokens: int | None,
) -> dict[AgentRole, int]:
    """Resolve per-role budgets with the legacy worker budget as fallback."""

    budgets = {
        AgentRole.REASONER: (
            reasoner_max_tokens
            if reasoner_max_tokens is not None
            else worker_max_tokens
        ),
        AgentRole.ENGINEER: (
            engineer_max_tokens
            if engineer_max_tokens is not None
            else worker_max_tokens
        ),
        AgentRole.CRITIC: (
            critic_max_tokens
            if critic_max_tokens is not None
            else worker_max_tokens
        ),
    }
    invalid = [role.value for role, budget in budgets.items() if budget < 1]
    if invalid:
        raise ValueError(
            f"role max-token budgets must be positive for: {', '.join(invalid)}"
        )
    return budgets


def _backbone_label(role_models: dict[AgentRole, str]) -> str:
    unique_models = set(role_models.values())
    return next(iter(unique_models)) if len(unique_models) == 1 else "mixed"


def _trial_id(record_id: str, trial: int, run_id: str | None) -> str:
    if run_id is None:
        return f"{record_id}_t{trial}"
    return f"{run_id}__{record_id}__t{trial + 1:02d}"


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


def _build_agent_tools(compiler) -> dict:
    """Build the fixed tool surface around one kernel-backed compiler."""
    from traj_eval.tools.lean_goals import make_show_goals
    from traj_eval.tools.lean_search import make_search_lemmas
    from traj_eval.tools.lean_tactic import make_try_tactic

    return {
        "check_lean": compiler.as_tool(),
        "search_lemmas": make_search_lemmas(num_results=5),
        "try_tactic": make_try_tactic(compiler),
        "show_goals": make_show_goals(compiler),
    }


def _build_trial_tools(compiler, record: ProblemRecord, setup: str):
    """Build a matched tool surface and optional trial-local subgoal state."""
    if setup == RECOVERY_TRIANGLE_V1:
        return _build_agent_tools(compiler), None, None

    raise RuntimeError(
        f"Setup {setup!r} requires the excluded subgoal-agent implementation. "
        f"This experiment is restricted to {RECOVERY_TRIANGLE_V1!r}."
    )


def run_one_trial(
    record: ProblemRecord,
    trial: int,
    compiler,
    *,
    output_dir: Path = LOG_DIR,
    setup: str = RECOVERY_TRIANGLE_V1,
    max_turns: int = DEFAULT_MAX_TURNS,
    worker_model: str | None = None,
    reasoner_model: str | None = None,
    engineer_model: str | None = None,
    critic_model: str | None = None,
    worker_thinking: str = "auto",
    worker_max_tokens: int = DEFAULT_WORKER_MAX_TOKENS,
    reasoner_max_tokens: int | None = None,
    engineer_max_tokens: int | None = None,
    critic_max_tokens: int | None = None,
    worker_timeout_seconds: float = DEFAULT_WORKER_TIMEOUT_SECONDS,
    temperature: float = 0.2,
    run_id: str | None = None,
) -> TrialOutcome:
    prompt = _task_prompt(record, setup=setup)

    role_models = _resolve_role_models(
        worker_model=worker_model,
        reasoner_model=reasoner_model,
        engineer_model=engineer_model,
        critic_model=critic_model,
    )
    role_max_tokens = _resolve_role_max_tokens(
        worker_max_tokens=worker_max_tokens,
        reasoner_max_tokens=reasoner_max_tokens,
        engineer_max_tokens=engineer_max_tokens,
        critic_max_tokens=critic_max_tokens,
    )
    role_thinking = {
        role: _resolve_worker_thinking(model, worker_thinking)
        for role, model in role_models.items()
    }
    role_llm_configs = {
        role: build_llm_config(
            model=role_models[role],
            temperature=temperature,
            enable_thinking=role_thinking[role],
            max_tokens=role_max_tokens[role],
            timeout_seconds=worker_timeout_seconds,
        )
        for role in LEAN_AGENT_ROLES
    }
    llm_config = role_llm_configs[AgentRole.REASONER]
    ledger = RoutingLedger()
    step_context = StepContext()
    tools, subgoal_ledger, post_tool_route = _build_trial_tools(
        compiler, record, setup
    )
    manager, user, groupchat, run_state = build_lean_free_team(
        llm_config,
        tools=tools,
        setup=setup,
        max_turns=max_turns,
        ledger=ledger,
        step_context=step_context,
        role_llm_configs=role_llm_configs,
        post_tool_route=post_tool_route,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    trial_id = _trial_id(record.id, trial, run_id)
    log_path = output_dir / f"{trial_id}.jsonl"
    if log_path.exists():
        raise FileExistsError(
            f"Refusing to overwrite existing trial trace: {log_path}"
        )
    meta = make_trial_meta(
        trial_id=trial_id,
        task_id=record.id,
        backbone=_backbone_label(role_models),
        testbed="lean",
        architecture=f"lean_{setup}",
        grounding=True,
        config={
            "setup": setup,
            "prompt_revision": setup,
            "routing_policy": (
                "tool_routed_subgoal_dag"
                if subgoal_ledger is not None
                else "agent_chosen_handoffs"
            ),
            "provider_route": "openai_compatible",
            "tools": sorted(tools),
            "max_turns": max_turns,
            "worker_model": worker_model,
            "worker_models": {
                role.value: model for role, model in role_models.items()
            },
            "worker_enable_thinking": worker_thinking,
            "role_enable_thinking": {
                role.value: enabled for role, enabled in role_thinking.items()
            },
            "worker_max_tokens": worker_max_tokens,
            "role_max_tokens": {
                role.value: budget for role, budget in role_max_tokens.items()
            },
            "worker_timeout_seconds": worker_timeout_seconds,
            "temperature": temperature,
            "run_id": run_id,
        },
    )
    writer = TrialLogWriter(log_path, meta)
    observer = TraceObserver(
        writer, trial_id=trial_id, ledger=ledger, step_context=step_context
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
            if subgoal_ledger is not None:
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
    ap.add_argument(
        "--task-id",
        nargs="+",
        help="optional exact task IDs, kept in the order supplied",
    )
    ap.add_argument("--trials", type=int, default=3, help="trials per problem")
    ap.add_argument(
        "--max-turns",
        type=int,
        default=DEFAULT_MAX_TURNS,
        help="maximum agent turns per trial",
    )
    ap.add_argument(
        "--worker-thinking",
        choices=["auto", "enabled", "disabled"],
        default="auto",
        help="Qwen thinking mode; auto disables it for Qwen models",
    )
    ap.add_argument(
        "--worker-model",
        help="legacy model fallback for roles without an explicit model",
    )
    ap.add_argument("--reasoner-model", help="Reasoner model ID")
    ap.add_argument("--engineer-model", help="Engineer model ID")
    ap.add_argument("--critic-model", help="Critic model ID")
    ap.add_argument(
        "--worker-max-tokens",
        type=int,
        default=DEFAULT_WORKER_MAX_TOKENS,
        help="maximum output tokens per worker call",
    )
    ap.add_argument("--reasoner-max-tokens", type=int)
    ap.add_argument("--engineer-max-tokens", type=int)
    ap.add_argument("--critic-max-tokens", type=int)
    ap.add_argument(
        "--worker-timeout-seconds",
        type=float,
        default=DEFAULT_WORKER_TIMEOUT_SECONDS,
        help="provider timeout for each worker call",
    )
    ap.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="sampling temperature used for every role",
    )
    ap.add_argument(
        "--setup",
        choices=[RECOVERY_TRIANGLE_V1],
        default=RECOVERY_TRIANGLE_V1,
        help="faithful Lean-anchor setup recorded in TrialMeta",
    )
    ap.add_argument("--run-id", help="immutable run ID prefixed to every trial ID")
    ap.add_argument(
        "--output-dir",
        type=Path,
        default=LOG_DIR,
        help="isolated trace directory",
    )
    ap.add_argument(
        "--analysis-dir",
        type=Path,
        help="summary directory; defaults to --output-dir",
    )
    ap.add_argument("--skip-existing", action="store_true", help="skip existing valid trace files")
    ap.add_argument(
        "--summarize-existing",
        action="store_true",
        help="score existing traces and write summaries without calling the model",
    )
    ap.add_argument("--dry-run", action="store_true", help="list problems and exit")
    args = ap.parse_args()
    if args.trials < 1:
        ap.error("--trials must be at least 1")
    if args.max_turns < 1:
        ap.error("--max-turns must be at least 1")
    if args.worker_max_tokens < 1:
        ap.error("--worker-max-tokens must be at least 1")
    if args.worker_timeout_seconds <= 0:
        ap.error("--worker-timeout-seconds must be positive")
    for name in (
        "reasoner_max_tokens",
        "engineer_max_tokens",
        "critic_max_tokens",
    ):
        value = getattr(args, name)
        if value is not None and value < 1:
            ap.error(f"--{name.replace('_', '-')} must be at least 1")

    records: list[ProblemRecord] = []
    for diff in args.difficulty:
        records.extend(load_dataset(DATASET_ROOT, difficulty=diff))
    if args.task_id:
        by_id = {record.id: record for record in records}
        missing = [task_id for task_id in args.task_id if task_id not in by_id]
        if missing:
            ap.error(
                "unknown task IDs for the selected difficulties: "
                + ", ".join(missing)
            )
        records = [by_id[task_id] for task_id in args.task_id]

    role_models = _resolve_role_models(
        worker_model=args.worker_model,
        reasoner_model=args.reasoner_model,
        engineer_model=args.engineer_model,
        critic_model=args.critic_model,
    )
    role_max_tokens = _resolve_role_max_tokens(
        worker_max_tokens=args.worker_max_tokens,
        reasoner_max_tokens=args.reasoner_max_tokens,
        engineer_max_tokens=args.engineer_max_tokens,
        critic_max_tokens=args.critic_max_tokens,
    )
    analysis_dir = args.analysis_dir or args.output_dir

    if args.dry_run:
        print(
            f"Would run setup={args.setup}, max_turns={args.max_turns}: "
            f"{len(records)} problems x {args.trials} trials into {args.output_dir}:"
        )
        print(
            "  models: "
            + ", ".join(
                f"{role.value}={role_models[role]}" for role in LEAN_AGENT_ROLES
            )
        )
        print(
            "  max tokens: "
            + ", ".join(
                f"{role.value}={role_max_tokens[role]}"
                for role in LEAN_AGENT_ROLES
            )
        )
        for r in records:
            print(f"  {r.id:22s} {r.source:8s} {r.difficulty}")
        return 0

    print(f"Starting Lean CLI validator against {PROJECT_DIR}...")
    from traj_eval.tools.lean_cli_compiler import LeanCliCompiler

    compiler = LeanCliCompiler(PROJECT_DIR, timeout=LEAN_TIMEOUT)
    print("Lean validator and tools ready.\n")

    outcomes: list[TrialOutcome] = []
    errors: list[dict[str, str | int]] = []
    observed_models: set[str] = set()
    for r in records:
        for t in range(args.trials):
            trial_id = _trial_id(r.id, t, args.run_id)
            log_path = args.output_dir / f"{trial_id}.jsonl"
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
                    trace_meta, _ = read_trial(log_path)
                    observed_models.add(trace_meta.backbone)
                    outcomes.append(
                        _score_trace(r, t, compiler, log_path, termination="offline_rescore")
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
                        worker_model=args.worker_model,
                        reasoner_model=args.reasoner_model,
                        engineer_model=args.engineer_model,
                        critic_model=args.critic_model,
                        worker_thinking=args.worker_thinking,
                        worker_max_tokens=args.worker_max_tokens,
                        reasoner_max_tokens=args.reasoner_max_tokens,
                        engineer_max_tokens=args.engineer_max_tokens,
                        critic_max_tokens=args.critic_max_tokens,
                        worker_timeout_seconds=args.worker_timeout_seconds,
                        temperature=args.temperature,
                        run_id=args.run_id,
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
        else _backbone_label(role_models)
    )
    summary = _build_run_summary(
        outcomes,
        expected_trials=len(records) * args.trials,
        setup=args.setup,
        model=summary_model,
        worker_models={
            role.value: model for role, model in role_models.items()
        },
        errors=errors,
    )
    _report(outcomes, summary)
    _write_summary(analysis_dir, summary)
    return 0


def _build_run_summary(
    outcomes: list[TrialOutcome],
    *,
    expected_trials: int,
    setup: str,
    model: str,
    worker_models: dict[str, str] | None = None,
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

    if eligible == 0:
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
        "schema_version": "lean_recovery_triangle_summary_v1",
        "setup": setup,
        "model": model,
        "worker_models": worker_models or {},
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
            "O3": "not claimed from one trial per task",
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
        "# Lean Recovery Triangle Run",
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
            "",
            "## Proposal Interpretation",
            "",
            "This run tests O1/O2 observability of agent-chosen recovery routes.",
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
