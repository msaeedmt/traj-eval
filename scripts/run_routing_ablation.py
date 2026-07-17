"""Run the preregistered Han V4 Lean routing ablation.

This runner is intentionally separate from ``run_batch.py``.  It preserves the
public batch output path and compares only routing policy while keeping tasks,
workers, tools, prompts, Lean validation, and worker budgets fixed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from autogen import ConversableAgent

from traj_eval.agents import RoutingLedger, StepContext, TraceObserver, make_trial_meta
from traj_eval.agents.config import build_llm_config
from traj_eval.agents.lean_routing_ablation import (
    CENTRAL_ARMS,
    CONTROLLER_PROMPT,
    CONTROLLER_STUCK_PROBES,
    RoutingArm,
    build_routing_ablation_team,
    evaluate_controller_stuck_probe,
    finalize_routing_ablation,
)
from traj_eval.dataset.loader import ProblemRecord, load_dataset, to_lean_task
from traj_eval.detectors.perseveration import detect_perseveration
from traj_eval.metrics.communication import summarize_communication
from traj_eval.metrics.lean.artifacts import extract_artifacts
from traj_eval.metrics.lean.outcomes import classify_outcome
from traj_eval.metrics.lean.validator import validate
from traj_eval.trace_core.storage import TrialLogWriter, read_trial

DATASET_ROOT = Path("dataset/Lean")
DEFAULT_OUTPUT_DIR = Path("data/batch/version_4_routing_ablation")
DEFAULT_TASKS = ("easy_fatem_019", "easy_fatem_020")
PROJECT_CONTRACT_FILES = ("lean-toolchain", "lake-manifest.json", "lakefile.lean")
WORKER_MAX_TOKENS = 1_500
CONTROLLER_MAX_TOKENS = 128


@dataclass(frozen=True)
class TrialOutcome:
    arm: str
    task_id: str
    trial: int
    trace: str
    attempt: int
    outcome: str
    termination: str
    worker_turns: int
    controller_turns: int
    total_model_calls: int
    elapsed_seconds: float
    n_tool_calls: int
    perseverated: bool
    reasoner_stuck_to_engineer: int
    engineer_stuck_to_reasoner: int
    engineer_local_retries: int
    communication: dict[str, Any]
    validation: dict[str, Any]


def _configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="backslashreplace")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_lean_project_contract(dataset_root: Path, lean_project: Path) -> dict[str, str]:
    """Require an external build cache to match the checked-in Lean project."""
    dataset_root = dataset_root.resolve()
    lean_project = lean_project.resolve()
    hashes: dict[str, str] = {}
    for name in PROJECT_CONTRACT_FILES:
        source = dataset_root / name
        runtime = lean_project / name
        if not source.is_file() or not runtime.is_file():
            raise FileNotFoundError(f"missing Lean project contract file: {source} or {runtime}")
        source_hash = _sha256(source)
        runtime_hash = _sha256(runtime)
        if source_hash != runtime_hash:
            raise RuntimeError(f"Lean project contract mismatch for {name}")
        hashes[name] = source_hash
    if not (lean_project / ".lake").is_dir():
        raise FileNotFoundError(f"Lean build artifacts are absent: {lean_project / '.lake'}")
    return hashes


def load_provider_env(path: Path) -> None:
    """Load only the two OpenAI-compatible endpoint variables from an ignored file."""
    allowed = {"OPENAI_API_KEY", "OPENAI_BASE_URL"}
    if not path.is_file():
        raise FileNotFoundError(f"provider environment file not found: {path}")
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in allowed:
            os.environ[key] = value.strip().strip("\"'")
    missing = sorted(key for key in allowed if not os.environ.get(key))
    if missing:
        raise RuntimeError(f"provider environment is missing: {', '.join(missing)}")


def task_prompt(record: ProblemRecord) -> str:
    """A routing-neutral prompt shared byte-for-byte by all four arms."""
    context = (
        "\n\nExisting context (keep it in scope; do not change it):\n" + record.context
        if record.context
        else ""
    )
    return (
        "Prove the following Lean 4 theorem. Use `import Mathlib` in every complete "
        "source snippet.\n\n"
        f"Informal statement:\n{record.informal}\n\n"
        f"Exact formal statement:\n{record.statement}{context}\n\n"
        "The final submitted proof must preserve the exact statement, compile in Lean "
        "4.30, and contain no sorry, admit, or added axiom."
    )


def balanced_schedule(
    tasks: tuple[str, ...], arms: tuple[RoutingArm, ...], trials: int
) -> list[tuple[int, str, RoutingArm]]:
    """Rotate arm order and alternate task order without outcome-based stopping."""
    if trials < 1 or not tasks or not arms:
        raise ValueError("schedule requires positive trials, tasks, and arms")
    schedule: list[tuple[int, str, RoutingArm]] = []
    for trial in range(trials):
        offset = trial % len(arms)
        arm_order = arms[offset:] + arms[:offset]
        task_order = tasks if trial % 2 == 0 else tuple(reversed(tasks))
        for task_id in task_order:
            schedule.extend((trial, task_id, arm) for arm in arm_order)
    return schedule


def _trace_path(base: Path, arm: RoutingArm, task_id: str, trial: int) -> Path:
    return base / arm.value / f"{task_id}_t{trial:02d}.jsonl"


def _refuse_existing(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite existing artifact: {path.resolve()}")


def _trace_is_valid(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        _, events = read_trial(path)
    except Exception:  # noqa: BLE001 - resume must reject any malformed evidence
        return False
    return any(event.payload.get("phase") == "termination" for event in events)


def _terminal_details(path: Path) -> dict[str, Any]:
    _, events = read_trial(path)
    for event in reversed(events):
        if event.payload.get("phase") == "termination":
            return event.payload
    return {}


def _usage_snapshot(agents: list[Any]) -> dict[str, Any]:
    usage: dict[str, Any] = {}
    for agent in agents:
        getter = getattr(agent, "get_actual_usage", None)
        if getter is None:
            continue
        value = getter()
        if value:
            usage[agent.name] = value
    return usage


def _trial_config(
    arm: RoutingArm,
    *,
    model: str,
    max_worker_turns: int,
    max_total_model_calls: int,
    contract_hashes: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema": "han_lean_routing_ablation_v4",
        "arm": arm.value,
        "model": model,
        "routing_only_intervention": True,
        "worker_roles": ["reasoner", "engineer", "critic"],
        "tools": ["check_lean", "search_lemmas", "try_tactic", "show_goals"],
        "imports": "Mathlib",
        "max_worker_turns": max_worker_turns,
        "max_total_model_calls": (
            max_total_model_calls
            if arm is RoutingArm.CENTRAL_TOTAL_CALL_MATCHED
            else None
        ),
        "worker_max_tokens": WORKER_MAX_TOKENS,
        "controller_max_tokens": CONTROLLER_MAX_TOKENS if arm in CENTRAL_ARMS else None,
        "lean_project_contract": contract_hashes,
    }


def _score_trace(
    record: ProblemRecord,
    arm: RoutingArm,
    trial: int,
    compiler: Any,
    path: Path,
) -> TrialOutcome:
    _, events = read_trial(path)
    details = _terminal_details(path)
    metrics = validate(events, to_lean_task(record), compiler=compiler)
    communication = summarize_communication(events)
    artifacts = extract_artifacts(events)
    repetition = detect_perseveration(artifacts.tool_calls)
    return TrialOutcome(
        arm=arm.value,
        task_id=record.id,
        trial=trial,
        trace=str(path.as_posix()),
        attempt=int(details.get("attempt", 0)),
        outcome=classify_outcome(events, metrics),
        termination=str(details.get("termination_reason", "missing_terminal_event")),
        worker_turns=int(details.get("worker_turns", 0)),
        controller_turns=int(details.get("controller_turns", 0)),
        total_model_calls=int(details.get("total_model_calls", 0)),
        elapsed_seconds=float(details.get("elapsed_seconds", 0.0)),
        n_tool_calls=repetition.n_tool_calls,
        perseverated=repetition.perseverated,
        reasoner_stuck_to_engineer=int(details.get("reasoner_stuck_to_engineer", 0)),
        engineer_stuck_to_reasoner=int(details.get("engineer_stuck_to_reasoner", 0)),
        engineer_local_retries=int(details.get("engineer_local_retries", 0)),
        communication=asdict(communication),
        validation=asdict(metrics),
    )


def run_one_trial(
    record: ProblemRecord,
    trial: int,
    arm: RoutingArm,
    *,
    path: Path,
    compiler: Any,
    model: str,
    max_worker_turns: int,
    max_total_model_calls: int,
    timeout_seconds: float,
    contract_hashes: dict[str, str],
    attempt: int = 0,
) -> tuple[TrialOutcome | None, BaseException | None]:
    """Run one append-only trace, preserving infrastructure failures as evidence."""
    from traj_eval.tools.lean_goals import make_show_goals
    from traj_eval.tools.lean_search import make_search_lemmas
    from traj_eval.tools.lean_tactic import make_try_tactic

    _refuse_existing(path)
    worker_config = build_llm_config(
        temperature=0.2,
        model=model,
        max_tokens=WORKER_MAX_TOKENS,
        enable_thinking=False,
        timeout_seconds=timeout_seconds,
    )
    controller_config = (
        build_llm_config(
            temperature=0.0,
            model=model,
            max_tokens=CONTROLLER_MAX_TOKENS,
            enable_thinking=False,
            json_mode=True,
            timeout_seconds=timeout_seconds,
        )
        if arm in CENTRAL_ARMS
        else None
    )
    ledger = RoutingLedger()
    step_context = StepContext()
    manager, user, groupchat, state = build_routing_ablation_team(
        worker_config,
        arm=arm,
        tools={
            "check_lean": compiler.as_tool(),
            "search_lemmas": make_search_lemmas(num_results=5),
            "try_tactic": make_try_tactic(compiler),
            "show_goals": make_show_goals(compiler),
        },
        max_worker_turns=max_worker_turns,
        max_total_model_calls=max_total_model_calls,
        controller_llm_config=controller_config,
        ledger=ledger,
        step_context=step_context,
    )
    trial_id = f"v4_{arm.value}_{record.id}_t{trial:02d}"
    if attempt:
        trial_id += f"_retry{attempt}"
    meta = make_trial_meta(
        trial_id=trial_id,
        task_id=record.id,
        backbone=model,
        testbed="lean",
        architecture=f"lean_routing_{arm.value}",
        grounding=True,
        config=_trial_config(
            arm,
            model=model,
            max_worker_turns=max_worker_turns,
            max_total_model_calls=max_total_model_calls,
            contract_hashes=contract_hashes,
        ),
    )
    writer = TrialLogWriter(path, meta)
    observer = TraceObserver(
        writer, trial_id=trial_id, ledger=ledger, step_context=step_context
    )
    observer.attach([agent for agent in groupchat.agents if agent.name != "user"])
    prompt = task_prompt(record)
    observer.record_task(prompt)
    started = time.perf_counter()
    error: BaseException | None = None
    try:
        user.initiate_chat(manager, message=prompt, clear_history=True)
    except Exception as exc:  # noqa: BLE001 - preserve provider/runtime faults in trace
        error = exc
        observer.record_infrastructure_error(exc)
        state.terminated = True
        state.reason = "infrastructure_error"
    finally:
        finalize_routing_ablation(state)
        elapsed = time.perf_counter() - started
        observer.record_termination(
            state.reason or "framework_stop",
            attempt=attempt,
            worker_turns=state.worker_turns,
            controller_turns=state.controller_turns,
            total_model_calls=state.total_model_calls,
            invalid_routes=state.invalid_routes,
            max_identical_calls_seen=state.max_identical_calls_seen,
            max_failed_compiles_seen=state.max_failed_compiles_seen,
            reasoner_stuck_to_engineer=state.reasoner_stuck_to_engineer,
            engineer_stuck_to_reasoner=state.engineer_stuck_to_reasoner,
            engineer_local_retries=state.engineer_local_retries,
            elapsed_seconds=round(elapsed, 6),
            usage=_usage_snapshot(groupchat.agents),
        )
        writer.close()
    if error is not None:
        return None, error
    return _score_trace(record, arm, trial, compiler, path), None


def _retry_path(path: Path) -> Path:
    return path.with_name(f"{path.stem}_retry1{path.suffix}")


def run_trial_with_one_infrastructure_retry(
    record: ProblemRecord,
    trial: int,
    arm: RoutingArm,
    *,
    path: Path,
    resume: bool,
    **kwargs: Any,
) -> TrialOutcome:
    """Retry infrastructure once in a new file; never retry an agent failure."""
    if path.exists():
        if not resume or not _trace_is_valid(path):
            raise FileExistsError(f"existing trace is not safely resumable: {path.resolve()}")
        if _terminal_details(path).get("termination_reason") != "infrastructure_error":
            return _score_trace(record, arm, trial, kwargs["compiler"], path)
        retry_path = _retry_path(path)
        if retry_path.exists():
            if not _trace_is_valid(retry_path):
                raise FileExistsError(f"invalid retry trace: {retry_path.resolve()}")
            if _terminal_details(retry_path).get("termination_reason") == "infrastructure_error":
                raise RuntimeError(
                    f"preserved infrastructure retry also failed: {retry_path.resolve()}"
                )
            return _score_trace(record, arm, trial, kwargs["compiler"], retry_path)
    else:
        outcome, error = run_one_trial(record, trial, arm, path=path, **kwargs)
        if error is None and outcome is not None:
            return outcome
        retry_path = _retry_path(path)

    outcome, error = run_one_trial(
        record, trial, arm, path=retry_path, attempt=1, **kwargs
    )
    if error is not None or outcome is None:
        raise RuntimeError(
            f"infrastructure retry failed for {arm.value}/{record.id}/t{trial:02d}: "
            f"{type(error).__name__ if error else 'unknown'}"
        )
    return outcome


def _arm_summary(
    arm: RoutingArm, outcomes: list[TrialOutcome], expected: int, model: str
) -> dict[str, Any]:
    return {
        "schema": "han_lean_routing_ablation_summary_v4",
        "arm": arm.value,
        "model": model,
        "expected_trials": expected,
        "completed_trials": len(outcomes),
        "outcomes": dict(sorted(Counter(item.outcome for item in outcomes).items())),
        "terminations": dict(
            sorted(Counter(item.termination for item in outcomes).items())
        ),
        "mean_total_model_calls": (
            sum(item.total_model_calls for item in outcomes) / len(outcomes)
            if outcomes
            else 0.0
        ),
        "planner_recoveries": sum(item.reasoner_stuck_to_engineer for item in outcomes),
        "engineer_replans": sum(item.engineer_stuck_to_reasoner for item in outcomes),
        "engineer_local_retries": sum(item.engineer_local_retries for item in outcomes),
        "trials": [asdict(item) for item in outcomes],
    }


def _summary_markdown(summary: dict[str, Any]) -> str:
    outcomes = summary["outcomes"]
    solved = outcomes.get("solved", 0)
    return "\n".join(
        [
            "# Results",
            "",
            f"- Arm: `{summary['arm']}`",
            f"- Model: `{summary['model']}`",
            f"- Completed: {summary['completed_trials']}/{summary['expected_trials']}",
            f"- Kernel-validated solved: {solved}",
            f"- Mean model calls: {summary['mean_total_model_calls']:.2f}",
            f"- Reasoner/planner stuck recoveries: {summary['planner_recoveries']}",
            f"- Engineer strategic replans: {summary['engineer_replans']}",
            f"- Engineer local retries: {summary['engineer_local_retries']}",
            "",
            "These are descriptive results for two selected weak tasks. They do not "
            "establish overall NLP-proposal improvement.",
            "",
        ]
    )


def write_summaries(
    output_dir: Path,
    outcomes: list[TrialOutcome],
    arms: tuple[RoutingArm, ...],
    expected_per_arm: int,
    model: str,
) -> None:
    all_summaries: dict[str, Any] = {}
    for arm in arms:
        arm_outcomes = [item for item in outcomes if item.arm == arm.value]
        summary = _arm_summary(arm, arm_outcomes, expected_per_arm, model)
        summary_path = output_dir / arm.value / "summary.json"
        results_path = output_dir / arm.value / "RESULTS.md"
        _refuse_existing(summary_path)
        _refuse_existing(results_path)
        summary_path.write_text(
            json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
        )
        results_path.write_text(_summary_markdown(summary), encoding="utf-8")
        all_summaries[arm.value] = summary
    manifest_path = output_dir / "run_manifest.json"
    _refuse_existing(manifest_path)
    manifest_path.write_text(
        json.dumps(
            {
                "schema": "han_lean_routing_ablation_run_v4",
                "model": model,
                "arms": all_summaries,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _read_smoke_result(path: Path) -> dict[str, Any]:
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid preserved smoke result: {path.resolve()}") from exc
    if not isinstance(result, dict) or not isinstance(result.get("passed"), bool):
        raise RuntimeError(f"invalid preserved smoke schema: {path.resolve()}")
    return result


def run_controller_stuck_smoke(
    output_dir: Path, model: str, timeout: float, *, resume: bool = False
) -> int:
    """Make two routing-only calls for planner and Engineer stuck scenarios."""
    target_dir = output_dir / "smoke" / "controller_stuck"
    config = build_llm_config(
        temperature=0.0,
        model=model,
        max_tokens=CONTROLLER_MAX_TOKENS,
        enable_thinking=False,
        json_mode=True,
        timeout_seconds=timeout,
    )
    failed = 0
    for probe in (item for item in CONTROLLER_STUCK_PROBES if item.live_smoke):
        target = target_dir / f"{probe.name}.json"
        if target.exists():
            if not resume:
                _refuse_existing(target)
            original = _read_smoke_result(target)
            if original["passed"]:
                continue
            target = target.with_name(f"{target.stem}_retry1{target.suffix}")
        _refuse_existing(target)
        controller = ConversableAgent(
            name="system",
            system_message=CONTROLLER_PROMPT,
            llm_config=config,
            human_input_mode="NEVER",
        )
        request = {
            "transcript": probe.transcript,
            "allowed_next_roles": sorted(role.value for role in probe.allowed_roles),
        }
        raw = controller.generate_reply(
            messages=[{"role": "user", "content": json.dumps(request)}]
        )
        message = raw if isinstance(raw, dict) else {"content": str(raw)}
        passed, reason = evaluate_controller_stuck_probe(probe, message)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {
                    "schema": "han_controller_stuck_smoke_v4",
                    "probe": probe.name,
                    "expected_role": probe.expected_role.value,
                    "request": request,
                    "response": message,
                    "passed": passed,
                    "score_reason": reason,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        failed += not passed
    return 1 if failed else 0


def _records_by_id(task_ids: tuple[str, ...]) -> dict[str, ProblemRecord]:
    available = {record.id: record for record in load_dataset(DATASET_ROOT)}
    missing = sorted(set(task_ids) - available.keys())
    if missing:
        raise ValueError(f"unknown task ids: {', '.join(missing)}")
    return {task_id: available[task_id] for task_id in task_ids}


def _parse_arms(values: list[str]) -> tuple[RoutingArm, ...]:
    selected = tuple(RoutingArm(value) for value in values)
    if len(set(selected)) != len(selected):
        raise ValueError("arms must be unique")
    return selected


def main() -> int:
    _configure_console()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=("dry-run", "controller-smoke", "arm-smoke", "official"),
        default="dry-run",
    )
    parser.add_argument("--tasks", nargs="+", default=list(DEFAULT_TASKS))
    parser.add_argument(
        "--arms", nargs="+", choices=[arm.value for arm in RoutingArm],
        default=[arm.value for arm in RoutingArm]
    )
    parser.add_argument("--trials", type=int, default=20)
    parser.add_argument("--max-worker-turns", type=int, default=200)
    parser.add_argument("--max-total-model-calls", type=int, default=200)
    parser.add_argument("--worker-timeout-seconds", type=float, default=180.0)
    parser.add_argument("--lean-timeout-seconds", type=int, default=360)
    parser.add_argument("--model", required=False)
    parser.add_argument("--provider-env", type=Path)
    parser.add_argument("--lean-project", type=Path, default=DATASET_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    arms = _parse_arms(args.arms)
    tasks = tuple(args.tasks)
    schedule = balanced_schedule(tasks, arms, args.trials)
    print(f"mode={args.mode} tasks={tasks} arms={[arm.value for arm in arms]}")
    print(f"official trial slots={len(schedule)}; max worker turns={args.max_worker_turns}")
    if args.mode == "dry-run":
        for trial, task_id, arm in schedule:
            print(f"t{trial:02d} {task_id} {arm.value}")
        return 0

    if not args.model or not args.provider_env:
        parser.error("live modes require --model and --provider-env")
    load_provider_env(args.provider_env.resolve())
    os.environ["TRAJ_EVAL_MODEL"] = args.model
    if args.mode == "controller-smoke":
        return run_controller_stuck_smoke(
            args.output_dir,
            args.model,
            args.worker_timeout_seconds,
            resume=args.resume,
        )

    contract_hashes = verify_lean_project_contract(DATASET_ROOT, args.lean_project)
    from traj_eval.tools.lean_cli_compiler import LeanCliCompiler

    compiler = LeanCliCompiler(args.lean_project, timeout=args.lean_timeout_seconds)
    records = _records_by_id(tasks)
    run_output = (
        args.output_dir / "smoke" / "arm_smoke"
        if args.mode == "arm-smoke"
        else args.output_dir
    )
    run_schedule = (
        balanced_schedule(tasks, arms, 1) if args.mode == "arm-smoke" else schedule
    )
    outcomes: list[TrialOutcome] = []
    for trial, task_id, arm in run_schedule:
        path = _trace_path(run_output, arm, task_id, trial)
        print(f"running {arm.value}/{task_id}/t{trial:02d}", flush=True)
        outcomes.append(
            run_trial_with_one_infrastructure_retry(
                records[task_id],
                trial,
                arm,
                path=path,
                resume=args.resume,
                compiler=compiler,
                model=args.model,
                max_worker_turns=args.max_worker_turns,
                max_total_model_calls=args.max_total_model_calls,
                timeout_seconds=args.worker_timeout_seconds,
                contract_hashes=contract_hashes,
            )
        )
    expected_per_arm = len(tasks) * (1 if args.mode == "arm-smoke" else args.trials)
    write_summaries(run_output, outcomes, arms, expected_per_arm, args.model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
