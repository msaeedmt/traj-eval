from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    REVIEWING = "reviewing"
    ACCEPTED = "accepted"
    FAILED = "failed"
    BLOCKED = "blocked"


class ReviewDecision(StrEnum):
    ACCEPT_STEP = "accept_step"
    RETRY_STEP = "retry_step"
    REPLAN = "replan"
    BLOCK = "block"
    APPROVE_SUBMISSION = "approve_submission"
    REJECT_SUBMISSION = "reject_submission"


# Backward-compatible name for earlier local planning/tests.
PlannerDecision = ReviewDecision


class CommandSpec(BaseModel):
    argv: list[str]
    cwd: str = "."
    timeout_seconds: int = Field(default=120, ge=1, le=3600)
    expected_exit_codes: set[int] = Field(default_factory=lambda: {0})


class StepCriteria(BaseModel):
    success_criteria: list[str] = Field(default_factory=list)
    expected_artifacts: list[str] = Field(default_factory=list)
    suggested_commands: list[CommandSpec] = Field(default_factory=list)
    forbidden_added_patterns: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class EvaluationSpec(BaseModel):
    kind: Literal["lean", "python", "scientific", "stargazer", "composite"]
    commands: list[CommandSpec] = Field(default_factory=list)
    forbidden_added_patterns: list[str] = Field(default_factory=list)
    expected_artifacts: list[str] = Field(default_factory=list)
    invariants: dict[str, Any] = Field(default_factory=dict)


# Backward-compatible name for earlier local planning/tests. Evaluation is
# post-hoc in the living runtime; it must not be shown to the engineer prompt.
VerifierSpec = EvaluationSpec


class PlanStep(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    objective: str
    allowed_paths: list[str]
    criteria: StepCriteria = Field(default_factory=StepCriteria)
    evaluation: EvaluationSpec | None = Field(
        default=None,
        validation_alias=AliasChoices("evaluation", "verifier"),
    )
    depends_on: list[str] = Field(default_factory=list)
    max_engineer_turns: int = Field(default=8, ge=1, le=100)
    max_step_retries: int = Field(default=2, ge=0, le=10)
    status: StepStatus = StepStatus.PENDING


class RuntimePlan(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    version: int = 1
    immutable_goal: str
    assumptions: list[str] = Field(default_factory=list)
    steps: list[PlanStep]
    final_evaluation: EvaluationSpec | None = Field(
        default=None,
        validation_alias=AliasChoices("final_evaluation", "final_verifier"),
    )


class StepReport(BaseModel):
    step_id: str
    attempt: int
    summary: str
    run_dir: str | None = None
    manifest_path: str | None = None
    diff_path: str | None = None
    artifacts: dict[str, str] = Field(default_factory=dict)


class CriticReview(BaseModel):
    decision: ReviewDecision
    message: str = ""
    engineer_feedback: str = ""


class AttemptRecord(BaseModel):
    report: StepReport
    critic_review: CriticReview
    complete: bool


class StepRun(BaseModel):
    step_id: str
    status: StepStatus
    attempts: list[AttemptRecord] = Field(default_factory=list)


class CommandResult(BaseModel):
    argv: list[str]
    cwd: str
    returncode: int | None
    passed: bool
    stdout: str = ""
    stderr: str = ""
    error: str | None = None


class EvaluationReport(BaseModel):
    passed: bool | None
    message: str = ""
    commands: list[CommandResult] = Field(default_factory=list)
    expected_artifacts: list[str] = Field(default_factory=list)
    missing_artifacts: list[str] = Field(default_factory=list)


class RuntimeResult(BaseModel):
    status: StepStatus
    steps: list[StepRun] = Field(default_factory=list)
    evaluation: EvaluationReport | None = None
    errors: list[str] = Field(default_factory=list)


def validate_runtime_plan(plan: RuntimePlan) -> list[str]:
    errors: list[str] = []
    if not plan.steps:
        errors.append("plan has no executable steps")

    seen: set[str] = set()
    for index, step in enumerate(plan.steps, start=1):
        if not step.id.strip():
            errors.append(f"step {index}: missing id")
        elif step.id in seen:
            errors.append(f"{step.id}: duplicate step id")
        seen.add(step.id)

        if not step.objective.strip():
            errors.append(f"{step.id or index}: missing objective")
        if not step.allowed_paths:
            errors.append(f"{step.id or index}: missing allowed_paths")
    return errors
