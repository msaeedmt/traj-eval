from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import Any

from .evidence import (
    build_version_index,
    capture_git_state,
    check_repo_guard,
    collect_artifacts,
    diagnose_run,
    ensure_clean_if_branching,
    maybe_create_branch,
    snapshot_changed_files,
    validate_with_traj_eval_schema,
)
from .prompts import (
    append_context_files,
    append_version_context,
    build_engineer_prompt,
    build_stargazer_smoke_task,
    write_action_example,
    write_critic_note,
)
from .qwen_client import build_qwen_client, request_qwen_actions, write_actions
from .core import RUN_SCHEMA, RunContext, append_jsonl, emit_event, find_repo_root, now_iso, slugify, stamp, write_json, write_text
from .tools import execute_action_list, execute_actions


def task_from_args(args: argparse.Namespace) -> str:
    if args.task_file:
        return Path(args.task_file).read_text(encoding="utf-8")
    if args.stargazer_smoke_task:
        repo = find_repo_root(Path(args.repo_root))
        return build_stargazer_smoke_task(repo, args.stargazer_output_rel)
    return str(args.task)


def write_trace_header(ctx: RunContext, task: str, guard: dict[str, str]) -> None:
    append_jsonl(
        ctx.event_log,
        {
            "trial_id": ctx.trial_id,
            "schema_version": "0.1.0",
            "testbed": "worktree",
            "task_id": ctx.task_id,
            "architecture": "codex_style_engineer_tools",
            "backbone": "external_engineer_actions",
            "grounding": True,
            "stress_level": 0,
            "started_at": now_iso(),
            "config": {
                "repo": str(ctx.repo),
                "branch": guard["branch"],
                "origin": guard["origin"],
                "task_preview": task[:300],
            },
        },
    )


def qwen_system_message(interactive: bool) -> str:
    if interactive:
        return (
            "You are the engineer agent in an interactive tool loop. "
            "Return only JSONL tool actions. No Markdown fences. "
            "After tool results, continue with the next actions. End with finish."
        )
    return "You are the engineer agent. Return only JSONL tool actions. No Markdown fences. No prose outside JSON objects."


def tool_results_message(turn: int, results: list[dict[str, Any]]) -> str:
    enriched: list[dict[str, Any]] = []
    for result in results:
        row = dict(result)
        tool_result = dict(row.get("result") or {})
        if row.get("tool") == "read_file" and tool_result.get("output"):
            try:
                tool_result["content"] = Path(str(tool_result["output"])).read_text(encoding="utf-8")
            except OSError as exc:
                tool_result["content_error"] = f"{type(exc).__name__}: {exc}"
        row["result"] = tool_result
        enriched.append(row)
    return (
        f"Tool results for turn {turn}. Continue with the next JSONL tool actions. "
        "If the task is complete, return a finish action.\n\n"
        + json.dumps(enriched, indent=2, ensure_ascii=False)
    )


def call_qwen_once(ctx: RunContext, prompt: str, args: argparse.Namespace) -> dict[str, Any]:
    client, model, config = build_qwen_client(ctx.repo, args)
    write_json(ctx.run_dir / "qwen_config_redacted.json", config)
    messages = [
        {"role": "system", "content": qwen_system_message(interactive=False)},
        {"role": "user", "content": prompt},
    ]
    record, actions, _ = request_qwen_actions(ctx, client, model, messages, args, turn=None, caused_by=None)
    write_actions(ctx.run_dir / "qwen_actions.jsonl", actions)
    record["base_url"] = config["base_url"]
    return record


def call_qwen_interactive(ctx: RunContext, prompt: str, args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    client, model, config = build_qwen_client(ctx.repo, args)
    write_json(ctx.run_dir / "qwen_config_redacted.json", config)
    messages = [
        {"role": "system", "content": qwen_system_message(interactive=True)},
        {"role": "user", "content": prompt},
    ]
    all_actions: list[dict[str, Any]] = []
    all_results: list[dict[str, Any]] = []
    turns: list[dict[str, Any]] = []
    caused_by: str | None = None

    for turn in range(1, args.max_tool_turns + 1):
        record, actions, text = request_qwen_actions(ctx, client, model, messages, args, turn=turn, caused_by=caused_by)
        caused_by = record.get("event_id")
        all_actions.extend(actions)
        write_actions(ctx.run_dir / "qwen_actions.jsonl", all_actions)

        turn_results = execute_action_list(ctx, args, actions)
        all_results.extend(turn_results)
        turns.append(
            {
                "turn": turn,
                "elapsed_seconds": record["elapsed_seconds"],
                "text_path": record["text_path"],
                "actions_path": record["actions_path"],
                "action_count": len(actions),
                "tools": [str(action.get("tool", "")) for action in actions],
            }
        )
        if any(not row.get("ok") for row in turn_results):
            break
        if any(row.get("tool") == "finish" and row.get("ok") for row in turn_results):
            break
        messages.append({"role": "assistant", "content": text})
        messages.append({"role": "user", "content": tool_results_message(turn, turn_results)})

    return (
        {
            "ok": True,
            "mode": "interactive_tools",
            "model": model,
            "base_url": config["base_url"],
            "turns": turns,
            "turn_count": len(turns),
            "action_count": sum(turn["action_count"] for turn in turns),
            "actions_path": str(ctx.run_dir / "qwen_actions.jsonl"),
        },
        all_results,
    )


def run_session(args: argparse.Namespace) -> Path:
    if args.stargazer_smoke_task and not args.stargazer_output_rel:
        args.stargazer_output_rel = "runs/engineer/tmp/stargazer_qwen_smoke"

    repo = find_repo_root(Path(args.repo_root))
    task_id = slugify(args.task_id)
    task = task_from_args(args)
    guard = check_repo_guard(repo, args.skip_repo_guard)
    ensure_clean_if_branching(repo, args.create_branch, args.allow_dirty)

    run_id = f"{stamp()}-{task_id}"
    run_dir = repo / "runs" / "engineer" / task_id / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    ctx = RunContext(
        repo=repo,
        run_dir=run_dir,
        task_id=task_id,
        trial_id=f"engineer-{task_id}-{uuid.uuid4().hex[:8]}",
        event_log=run_dir / "events.jsonl",
    )

    write_text(run_dir / "task.md", task)
    version_index = build_version_index(repo, task_id, run_id, run_dir)
    write_json(run_dir / "version_index.json", version_index)
    engineer_prompt = append_context_files(repo, build_engineer_prompt(task_id, task), args.context_file)
    engineer_prompt = append_version_context(engineer_prompt, version_index)
    write_text(run_dir / "engineer_prompt.md", engineer_prompt)
    example_actions = write_action_example(run_dir)

    branch_created = maybe_create_branch(repo, args.create_branch, args.branch_prefix, task_id)
    write_trace_header(ctx, task, guard)
    before = capture_git_state(repo, run_dir, "before")

    action_results: list[dict[str, Any]] = []
    qwen_record: dict[str, Any] | None = None
    if args.qwen and not args.write_prompt_only:
        try:
            if args.qwen_interactive_tools:
                qwen_record, action_results = call_qwen_interactive(ctx, engineer_prompt, args)
            else:
                qwen_record = call_qwen_once(ctx, engineer_prompt, args)
        except Exception as exc:
            qwen_record = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            emit_event(ctx, event_type="message", agent_role="system", payload={"phase": "qwen_error", **qwen_record})

    should_execute_qwen = bool(
        args.qwen
        and not args.qwen_interactive_tools
        and args.execute_qwen_actions
        and qwen_record
        and qwen_record.get("ok")
    )
    if (args.actions_file or should_execute_qwen) and not args.write_prompt_only:
        action_results = execute_actions(ctx, args)

    after = capture_git_state(repo, run_dir, "after")
    changed = snapshot_changed_files(repo, run_dir)
    artifact_roots = list(args.artifact_rel or [])
    if args.stargazer_output_rel:
        artifact_roots.append(args.stargazer_output_rel)
    private_artifacts = collect_artifacts(repo, artifact_roots)
    critic_note = write_critic_note(run_dir, ctx.task_id, ctx.trial_id)
    trace_validation = validate_with_traj_eval_schema(repo, ctx.event_log)
    write_json(run_dir / "trace_validation.json", trace_validation)
    run_diagnosis = diagnose_run(args, qwen_record, action_results, trace_validation)

    write_json(
        run_dir / "run_manifest.json",
        {
            "schema": RUN_SCHEMA,
            "task_id": task_id,
            "trial_id": ctx.trial_id,
            "run_id": run_id,
            "repo": str(repo),
            "repo_guard": guard,
            "branch_created": branch_created,
            "task": str(run_dir / "task.md"),
            "engineer_prompt": str(run_dir / "engineer_prompt.md"),
            "version_index": str(run_dir / "version_index.json"),
            "example_actions": str(example_actions),
            "actions_file": args.actions_file,
            "qwen": qwen_record,
            "execute_qwen_actions": args.execute_qwen_actions,
            "qwen_interactive_tools": args.qwen_interactive_tools,
            "max_tool_turns": args.max_tool_turns,
            "write_prompt_only": args.write_prompt_only,
            "allow_shell": args.allow_shell,
            "before": before,
            "after": after,
            "events": str(ctx.event_log),
            "trace_validation": trace_validation,
            "action_results": action_results,
            "run_diagnosis": run_diagnosis,
            "changed_files": changed,
            "private_artifacts": private_artifacts,
            "critic_entrypoint": str(critic_note),
        },
    )

    print(f"run_dir: {run_dir}")
    print(f"engineer_prompt: {run_dir / 'engineer_prompt.md'}")
    print(f"example_actions: {example_actions}")
    print(f"critic_entrypoint: {critic_note}")
    print(f"changed_files: {len(changed)}")
    if args.write_prompt_only or (not args.actions_file and not args.execute_qwen_actions):
        print("No actions executed. Give engineer_prompt.md to the engineer model, then pass --actions-file or use --qwen --execute-qwen-actions.")
    return run_dir
