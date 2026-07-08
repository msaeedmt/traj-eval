from __future__ import annotations

from traj_eval.agents.contracts import (
    CommandSpec,
    EvaluationSpec,
    PlanStep,
    RuntimePlan,
    StepCriteria,
    StepStatus,
    VerifierSpec,
    validate_runtime_plan,
)


def test_runtime_plan_uses_visible_criteria_and_hidden_evaluation() -> None:
    evaluation = EvaluationSpec(
        kind="stargazer",
        commands=[CommandSpec(argv=["python", "--version"])],
        invariants={"secret_marker": "SECRET_EVAL"},
    )
    plan = RuntimePlan(
        immutable_goal="Run one step.",
        steps=[
            PlanStep(
                id="s1",
                objective="Create a small artifact.",
                allowed_paths=["runs/"],
                criteria=StepCriteria(success_criteria=["artifact exists"]),
                evaluation=evaluation,
            )
        ],
        final_evaluation=evaluation,
    )

    decoded = RuntimePlan.model_validate(plan.model_dump(mode="json"))

    assert decoded.steps[0].status is StepStatus.PENDING
    assert decoded.steps[0].criteria.success_criteria == ["artifact exists"]
    assert decoded.steps[0].evaluation is not None
    assert decoded.steps[0].evaluation.invariants["secret_marker"] == "SECRET_EVAL"


def test_legacy_verifier_alias_decodes_as_posthoc_evaluation() -> None:
    step = PlanStep.model_validate(
        {
            "id": "legacy",
            "objective": "compatibility",
            "allowed_paths": ["src/"],
            "verifier": VerifierSpec(kind="python", commands=[]).model_dump(mode="json"),
        }
    )

    assert step.evaluation is not None
    assert step.evaluation.kind == "python"


def test_plan_validation_reports_unusable_plans() -> None:
    plan = RuntimePlan(
        immutable_goal="bad plan",
        steps=[
            PlanStep(
                id="",
                objective="",
                allowed_paths=[],
            )
        ],
    )

    errors = validate_runtime_plan(plan)

    assert "step 1: missing id" in errors
    assert "1: missing objective" in errors
    assert "1: missing allowed_paths" in errors
