from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from traj_eval.agents.contracts import (
    AttemptRecord,
    CommandResult,
    CriticReview,
    EvaluationReport,
    EvaluationSpec,
    PlanStep,
    ReviewDecision,
    RuntimePlan,
    RuntimeResult,
    StepReport,
    StepRun,
    StepStatus,
    validate_runtime_plan,
)


EngineerFn = Callable[[PlanStep, int, list[str], list[str]], StepReport]
CriticFn = Callable[[PlanStep, StepReport, list[str]], CriticReview]
EvaluationFn = Callable[[RuntimePlan, RuntimeResult], EvaluationReport]


def load_plan(path: Path) -> RuntimePlan:
    return RuntimePlan.model_validate_json(path.read_text(encoding="utf-8"))


def write_status(path: Path, result: RuntimeResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")


def append_runtime_event(path: Path | None, event_type: str, payload: dict[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps({"type": event_type, "payload": payload}, ensure_ascii=False) + "\n")


def run_orchestrator(
    plan: RuntimePlan,
    *,
    engineer: EngineerFn,
    critic: CriticFn,
    evaluator: EvaluationFn | None = None,
    status_path: Path | None = None,
    event_log_path: Path | None = None,
) -> RuntimeResult:
    errors = validate_runtime_plan(plan)
    if errors:
        result = RuntimeResult(status=StepStatus.BLOCKED, errors=errors)
        if status_path is not None:
            write_status(status_path, result)
        append_runtime_event(event_log_path, "plan.invalid", {"errors": errors})
        return result

    step_runs: list[StepRun] = []
    previous_summaries: list[str] = []
    feedback_by_step: dict[str, list[str]] = {}
    append_runtime_event(
        event_log_path,
        "run.started",
        {"immutable_goal": plan.immutable_goal, "step_count": len(plan.steps)},
    )

    for step in plan.steps:
        attempts: list[AttemptRecord] = []
        status = StepStatus.RUNNING

        for attempt in range(step.max_step_retries + 1):
            feedback = feedback_by_step.get(step.id, [])
            append_runtime_event(
                event_log_path,
                "step.started",
                {"step_id": step.id, "attempt": attempt},
            )
            report = engineer(step, attempt, previous_summaries, feedback)
            append_runtime_event(
                event_log_path,
                "engineer.report",
                report.model_dump(mode="json"),
            )

            status = StepStatus.REVIEWING
            review = critic(step, report, previous_summaries)
            complete = review.decision is ReviewDecision.ACCEPT_STEP
            attempts.append(
                AttemptRecord(
                    report=report,
                    critic_review=review,
                    complete=complete,
                )
            )
            append_runtime_event(
                event_log_path,
                "critic.review",
                {
                    "step_id": step.id,
                    "attempt": attempt,
                    "decision": review.decision.value,
                    "message": review.message,
                },
            )

            if complete:
                status = StepStatus.ACCEPTED
                previous_summaries.append(f"{step.id}: {report.summary}")
                break
            if review.decision in {
                ReviewDecision.BLOCK,
                ReviewDecision.REPLAN,
                ReviewDecision.REJECT_SUBMISSION,
            }:
                status = StepStatus.BLOCKED
                break
            if attempt == step.max_step_retries:
                status = StepStatus.FAILED
                break

            feedback_by_step.setdefault(step.id, []).append(
                review.engineer_feedback or review.message or "retry requested"
            )
            status = StepStatus.RUNNING

        step_runs.append(StepRun(step_id=step.id, status=status, attempts=attempts))
        result = RuntimeResult(status=status, steps=step_runs)
        if status_path is not None:
            write_status(status_path, result)
        if status is not StepStatus.ACCEPTED:
            append_runtime_event(
                event_log_path,
                "run.completed",
                {"status": status.value, "failed_step": step.id},
            )
            return result

    result = RuntimeResult(status=StepStatus.ACCEPTED, steps=step_runs)
    if evaluator is not None:
        result.evaluation = evaluator(plan, result)
        append_runtime_event(
            event_log_path,
            "evaluation.completed",
            result.evaluation.model_dump(mode="json"),
        )
    if status_path is not None:
        write_status(status_path, result)
    append_runtime_event(event_log_path, "run.completed", {"status": result.status.value})
    return result


def _safe_cwd(repo: Path, raw_cwd: str) -> Path:
    repo_root = repo.resolve()
    cwd = (repo_root / raw_cwd).resolve()
    if cwd != repo_root and repo_root not in cwd.parents:
        raise ValueError(f"evaluation command cwd escapes repo: {raw_cwd}")
    if not cwd.is_dir():
        raise FileNotFoundError(f"evaluation command cwd is not a directory: {raw_cwd}")
    return cwd


def run_evaluation_spec(repo: Path, spec: EvaluationSpec | None) -> EvaluationReport | None:
    if spec is None:
        return None

    command_results: list[CommandResult] = []
    for command in spec.commands:
        try:
            cwd = _safe_cwd(repo, command.cwd)
            completed = subprocess.run(
                command.argv,
                cwd=cwd,
                text=True,
                capture_output=True,
                shell=False,
                timeout=command.timeout_seconds,
                encoding="utf-8",
                errors="replace",
            )
            passed = completed.returncode in command.expected_exit_codes
            command_results.append(
                CommandResult(
                    argv=command.argv,
                    cwd=str(cwd),
                    returncode=completed.returncode,
                    passed=passed,
                    stdout=completed.stdout,
                    stderr=completed.stderr,
                )
            )
        except Exception as exc:
            command_results.append(
                CommandResult(
                    argv=command.argv,
                    cwd=command.cwd,
                    returncode=None,
                    passed=False,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )

    missing = [
        rel
        for rel in spec.expected_artifacts
        if not (repo / rel).exists()
    ]
    commands_passed = all(row.passed for row in command_results) if command_results else True
    passed = commands_passed and not missing
    return EvaluationReport(
        passed=passed,
        message="post-hoc evaluation completed",
        commands=command_results,
        expected_artifacts=spec.expected_artifacts,
        missing_artifacts=missing,
    )
