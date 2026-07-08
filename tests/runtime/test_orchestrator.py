from __future__ import annotations

import sys

from traj_eval.agents.contracts import (
    CommandSpec,
    CriticReview,
    EvaluationSpec,
    PlanStep,
    ReviewDecision,
    RuntimePlan,
    StepReport,
    StepStatus,
)
from traj_eval.agents.orchestrator import run_evaluation_spec, run_orchestrator


def _step(step_id: str, *, max_step_retries: int = 1) -> PlanStep:
    return PlanStep(
        id=step_id,
        objective=f"Complete {step_id}",
        allowed_paths=["runs/"],
        max_step_retries=max_step_retries,
    )


def _plan(*steps: PlanStep) -> RuntimePlan:
    return RuntimePlan(immutable_goal="orchestrator smoke", steps=list(steps))


def test_orchestrator_retries_then_accepts_step() -> None:
    seen_feedback: list[list[str]] = []

    def engineer(
        step: PlanStep,
        attempt: int,
        _previous: list[str],
        feedback: list[str],
    ) -> StepReport:
        seen_feedback.append(list(feedback))
        return StepReport(step_id=step.id, attempt=attempt, summary=f"attempt {attempt}")

    def critic(_step: PlanStep, report: StepReport, _previous: list[str]) -> CriticReview:
        if report.attempt == 0:
            return CriticReview(
                decision=ReviewDecision.RETRY_STEP,
                message="needs more evidence",
                engineer_feedback="add evidence",
            )
        return CriticReview(decision=ReviewDecision.ACCEPT_STEP, message="ok")

    result = run_orchestrator(_plan(_step("s1", max_step_retries=2)), engineer=engineer, critic=critic)

    assert result.status is StepStatus.ACCEPTED
    assert [attempt.complete for attempt in result.steps[0].attempts] == [False, True]
    assert seen_feedback == [[], ["add evidence"]]


def test_orchestrator_stops_on_block() -> None:
    called_steps: list[str] = []

    def engineer(step: PlanStep, attempt: int, _previous: list[str], _feedback: list[str]):
        called_steps.append(step.id)
        return StepReport(step_id=step.id, attempt=attempt, summary="blocked")

    def critic(_step: PlanStep, _report: StepReport, _previous: list[str]) -> CriticReview:
        return CriticReview(decision=ReviewDecision.BLOCK, message="blocked")

    result = run_orchestrator(_plan(_step("s1"), _step("s2")), engineer=engineer, critic=critic)

    assert result.status is StepStatus.BLOCKED
    assert called_steps == ["s1"]
    assert len(result.steps) == 1


def test_orchestrator_stops_on_replan_request() -> None:
    def engineer(step: PlanStep, attempt: int, _previous: list[str], _feedback: list[str]):
        return StepReport(step_id=step.id, attempt=attempt, summary="needs replan")

    def critic(_step: PlanStep, _report: StepReport, _previous: list[str]) -> CriticReview:
        return CriticReview(decision=ReviewDecision.REPLAN, message="plan is stale")

    result = run_orchestrator(_plan(_step("s1")), engineer=engineer, critic=critic)

    assert result.status is StepStatus.BLOCKED
    assert result.steps[0].attempts[0].critic_review.decision is ReviewDecision.REPLAN


def test_posthoc_evaluation_runs_after_live_loop(tmp_path) -> None:
    spec = EvaluationSpec(
        kind="python",
        commands=[CommandSpec(argv=[sys.executable, "--version"])],
        expected_artifacts=["missing-artifact.txt"],
    )

    report = run_evaluation_spec(tmp_path, spec)

    assert report is not None
    assert report.passed is False
    assert report.commands[0].passed is True
    assert report.missing_artifacts == ["missing-artifact.txt"]


def test_orchestrator_only_evaluates_after_all_steps_are_accepted() -> None:
    calls: list[str] = []
    plan = RuntimePlan(
        immutable_goal="gate evaluation",
        steps=[_step("s1"), _step("s2")],
        final_evaluation=EvaluationSpec(kind="python"),
    )

    def engineer(step: PlanStep, attempt: int, _previous: list[str], _feedback: list[str]):
        calls.append(f"engineer:{step.id}")
        return StepReport(step_id=step.id, attempt=attempt, summary="done")

    def critic(step: PlanStep, _report: StepReport, _previous: list[str]) -> CriticReview:
        calls.append(f"critic:{step.id}")
        if step.id == "s2":
            return CriticReview(decision=ReviewDecision.BLOCK, message="blocked")
        return CriticReview(decision=ReviewDecision.ACCEPT_STEP, message="ok")

    def evaluator(_plan: RuntimePlan, _result):
        calls.append("evaluator")
        raise AssertionError("evaluation must not run after a blocked live loop")

    result = run_orchestrator(plan, engineer=engineer, critic=critic, evaluator=evaluator)

    assert result.status is StepStatus.BLOCKED
    assert calls == ["engineer:s1", "critic:s1", "engineer:s2", "critic:s2"]
