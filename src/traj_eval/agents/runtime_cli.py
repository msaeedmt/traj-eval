from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from traj_eval.agents.contracts import CriticReview, PlanStep, ReviewDecision, StepReport
from traj_eval.agents.engineer.core import find_repo_root, slugify, stamp, write_json, write_text
from traj_eval.agents.engineer.session import run_session
from traj_eval.agents.orchestrator import load_plan, run_evaluation_spec, run_orchestrator


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stateful planner-engineer-critic runtime for traj-eval."
    )
    parser.add_argument("--plan-file", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--run-root-rel", default="runs/runtime")
    parser.add_argument("--actions-file", help="JSONL actions for each engineer step.")
    parser.add_argument("--allow-shell", action="store_true")
    parser.add_argument("--qwen", action="store_true")
    parser.add_argument("--execute-qwen-actions", action="store_true")
    parser.add_argument("--qwen-interactive-tools", action="store_true")
    parser.add_argument("--max-tool-turns", type=int, default=6)
    parser.add_argument("--provider-env")
    parser.add_argument("--qwen-model")
    parser.add_argument("--qwen-timeout", type=float)
    parser.add_argument("--qwen-max-retries", type=int)
    parser.add_argument("--qwen-max-tokens", type=int, default=8000)
    parser.add_argument("--qwen-enable-thinking", action="store_true")
    parser.add_argument("--monitor-interval", type=float, default=15.0)
    parser.add_argument("--context-file", action="append")
    parser.add_argument("--artifact-rel", action="append")
    parser.add_argument("--skip-repo-guard", action="store_true")
    parser.add_argument("--skip-changed-files", action="store_true")
    parser.add_argument("--allow-dirty", action="store_true")
    return parser.parse_args(argv)


def _repo_relative(repo: Path, path: Path) -> str:
    return path.resolve().relative_to(repo.resolve()).as_posix()


def _step_payload(
    step: PlanStep,
    attempt: int,
    previous_summaries: list[str],
    feedback: list[str],
) -> dict:
    return {
        "step": step.model_dump(mode="json", exclude={"evaluation"}),
        "attempt": attempt,
        "previous_step_summaries": previous_summaries,
        "critic_feedback": feedback,
    }


def _manifest_summary(manifest_path: Path) -> str:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError:
        return "engineer run did not write a manifest"
    diagnosis = manifest.get("run_diagnosis") or {}
    return str(diagnosis.get("classification") or "engineer run completed")


def _make_engineer(args: argparse.Namespace, repo: Path, run_dir: Path):
    step_input_dir = run_dir / "step_inputs"
    engineer_run_root = run_dir / "engineer"

    def engineer(
        step: PlanStep,
        attempt: int,
        previous_summaries: list[str],
        feedback: list[str],
    ) -> StepReport:
        step_file = step_input_dir / f"{step.id}-attempt-{attempt}.json"
        write_json(step_file, _step_payload(step, attempt, previous_summaries, feedback))
        step_task_id = slugify(f"{args.task_id}-{step.id}-attempt-{attempt}")
        session_args = argparse.Namespace(
            task_id=step_task_id,
            task=None,
            task_file=None,
            step_file=str(step_file),
            repo_root=str(repo),
            actions_file=args.actions_file,
            allow_shell=args.allow_shell,
            write_prompt_only=False,
            qwen=args.qwen,
            execute_qwen_actions=args.execute_qwen_actions,
            qwen_interactive_tools=args.qwen_interactive_tools,
            max_tool_turns=args.max_tool_turns,
            provider_env=args.provider_env,
            qwen_model=args.qwen_model,
            qwen_timeout=args.qwen_timeout,
            qwen_max_retries=args.qwen_max_retries,
            qwen_max_tokens=args.qwen_max_tokens,
            qwen_enable_thinking=args.qwen_enable_thinking,
            monitor_interval=args.monitor_interval,
            context_file=args.context_file,
            artifact_rel=args.artifact_rel,
            run_root_rel=_repo_relative(repo, engineer_run_root),
            skip_changed_files=args.skip_changed_files,
            skip_repo_guard=args.skip_repo_guard,
            create_branch=False,
            branch_prefix="engineer/",
            allow_dirty=args.allow_dirty,
        )
        step_run_dir = run_session(session_args)
        manifest_path = step_run_dir / "run_manifest.json"
        diff_path = step_run_dir / "after_diff.patch"
        return StepReport(
            step_id=step.id,
            attempt=attempt,
            summary=_manifest_summary(manifest_path),
            run_dir=str(step_run_dir),
            manifest_path=str(manifest_path),
            diff_path=str(diff_path),
        )

    return engineer


def deterministic_critic(
    step: PlanStep,
    report: StepReport,
    _previous_summaries: list[str],
) -> CriticReview:
    if report.manifest_path is None:
        return CriticReview(
            decision=ReviewDecision.RETRY_STEP,
            message="engineer did not produce a manifest",
            engineer_feedback="Rerun the step and produce run_manifest.json.",
        )

    try:
        manifest = json.loads(Path(report.manifest_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return CriticReview(
            decision=ReviewDecision.RETRY_STEP,
            message=f"manifest could not be read: {type(exc).__name__}: {exc}",
            engineer_feedback="Repair the engineer run so the manifest is valid JSON.",
        )

    diagnosis = manifest.get("run_diagnosis") or {}
    classification = str(diagnosis.get("classification", "unknown"))
    failed_tools = diagnosis.get("failed_tools") or []
    has_required_commands = bool(step.criteria.suggested_commands)

    if classification == "completed_with_verification":
        return CriticReview(
            decision=ReviewDecision.ACCEPT_STEP,
            message="engineer completed the step with command evidence",
        )
    if classification == "completed_without_verification" and not has_required_commands:
        return CriticReview(
            decision=ReviewDecision.ACCEPT_STEP,
            message="engineer completed an artifact-only step",
        )

    feedback = [
        f"Engineer run classification was {classification}.",
        "Use the current step objective, inspect the manifest/tool outputs, and retry.",
    ]
    if failed_tools:
        feedback.append(f"Failed tools: {json.dumps(failed_tools, ensure_ascii=False)}")
    return CriticReview(
        decision=ReviewDecision.RETRY_STEP,
        message="step does not yet have acceptable engineer evidence",
        engineer_feedback=" ".join(feedback),
    )


def run_runtime(args: argparse.Namespace) -> Path:
    repo = find_repo_root(Path(args.repo_root))
    plan = load_plan(Path(args.plan_file))
    task_id = slugify(args.task_id)
    run_id = f"{stamp()}-{task_id}"
    run_dir = repo / args.run_root_rel / task_id / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    write_text(run_dir / "plan.json", plan.model_dump_json(indent=2))

    def evaluator(runtime_plan, _result):
        report = run_evaluation_spec(repo, runtime_plan.final_evaluation)
        if report is None:
            return None
        write_text(run_dir / "runtime_evaluation.json", report.model_dump_json(indent=2))
        return report

    result = run_orchestrator(
        plan,
        engineer=_make_engineer(args, repo, run_dir),
        critic=deterministic_critic,
        evaluator=evaluator if plan.final_evaluation is not None else None,
        status_path=run_dir / "runtime_status.json",
        event_log_path=run_dir / "runtime_events.jsonl",
    )
    write_text(run_dir / "runtime_result.json", result.model_dump_json(indent=2))
    print(f"runtime_run_dir: {run_dir}")
    print(f"runtime_status: {result.status.value}")
    return run_dir


def main(argv: list[str]) -> int:
    run_runtime(parse_args(argv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
