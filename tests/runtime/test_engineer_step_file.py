from __future__ import annotations

import json

from traj_eval.agents.engineer.cli import parse_args
from traj_eval.agents.engineer.session import task_from_step_file
from traj_eval.agents.runtime_cli import _step_payload
from traj_eval.agents.contracts import (
    EvaluationSpec,
    PlanStep,
    StepCriteria,
)


def test_engineer_cli_keeps_old_task_mode() -> None:
    args = parse_args(["--task-id", "old", "--task", "do the task"])

    assert args.task == "do the task"
    assert args.task_file is None
    assert args.step_file is None


def test_engineer_cli_accepts_step_file_mode() -> None:
    args = parse_args(["--task-id", "step", "--step-file", "step.json"])

    assert args.step_file == "step.json"
    assert args.task is None
    assert args.task_file is None


def test_step_file_prompt_hides_posthoc_evaluation(tmp_path) -> None:
    path = tmp_path / "step.json"
    path.write_text(
        json.dumps(
            {
                "step": {
                    "id": "contracts",
                    "objective": "Add runtime contracts.",
                    "allowed_paths": ["src/traj_eval/agents/contracts.py"],
                    "criteria": {
                        "success_criteria": ["RuntimePlan round trips"],
                        "expected_artifacts": ["runtime_status.json"],
                        "suggested_commands": [{"argv": ["python", "-m", "pytest"]}],
                    },
                    "evaluation": {
                        "kind": "stargazer",
                        "invariants": {"secret_marker": "SECRET_EVAL"},
                    },
                },
                "attempt": 1,
                "previous_step_summaries": ["planner: accepted"],
                "critic_feedback": ["add a focused test"],
            }
        ),
        encoding="utf-8",
    )

    prompt = task_from_step_file(path)

    assert "Add runtime contracts." in prompt
    assert "RuntimePlan round trips" in prompt
    assert "runtime_status.json" in prompt
    assert "planner: accepted" in prompt
    assert "add a focused test" in prompt
    assert "SECRET_EVAL" not in prompt
    assert "stargazer" not in prompt.lower()


def test_runtime_step_payload_excludes_evaluation() -> None:
    step = PlanStep(
        id="s1",
        objective="Visible work only.",
        allowed_paths=["src/"],
        criteria=StepCriteria(success_criteria=["visible"]),
        evaluation=EvaluationSpec(kind="python", invariants={"secret": "hidden"}),
    )

    payload = _step_payload(step, 0, [], [])

    assert payload["step"]["objective"] == "Visible work only."
    assert payload["step"]["criteria"]["success_criteria"] == ["visible"]
    assert "evaluation" not in payload["step"]
