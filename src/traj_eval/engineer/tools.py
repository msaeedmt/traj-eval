from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from .core import (
    RunContext,
    emit_event,
    git_output,
    repo_relative_path,
    repo_relative_string,
    run_process,
    write_text,
)


def tool_read_file(ctx: RunContext, action: dict[str, Any], _: argparse.Namespace) -> dict[str, Any]:
    path = repo_relative_path(ctx.repo, str(action["path"]))
    text = path.read_text(encoding=action.get("encoding", "utf-8"))
    output_path = ctx.run_dir / "tool_outputs" / f"{ctx.seq + 1:04d}_read_file.txt"
    write_text(output_path, text)
    return {
        "path": repo_relative_string(ctx.repo, path),
        "bytes": len(text.encode("utf-8")),
        "output": str(output_path),
        "preview": text[:500],
    }


def tool_write_file(ctx: RunContext, action: dict[str, Any], _: argparse.Namespace) -> dict[str, Any]:
    path = repo_relative_path(ctx.repo, str(action["path"]))
    content = str(action.get("content", ""))
    write_text(path, content)
    return {"path": repo_relative_string(ctx.repo, path), "bytes": len(content.encode("utf-8"))}


def tool_append_file(ctx: RunContext, action: dict[str, Any], _: argparse.Namespace) -> dict[str, Any]:
    path = repo_relative_path(ctx.repo, str(action["path"]))
    content = str(action.get("content", ""))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    return {
        "path": repo_relative_string(ctx.repo, path),
        "bytes_appended": len(content.encode("utf-8")),
    }


def tool_run(ctx: RunContext, action: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    command = str(action["command"])
    if not args.allow_shell:
        return {"command": command, "skipped": True, "reason": "pass --allow-shell to execute run actions"}
    result = run_process(command, ctx.repo, shell=True)
    stem = f"{ctx.seq + 1:04d}_run"
    stdout_path = ctx.run_dir / "tool_outputs" / f"{stem}.stdout.txt"
    stderr_path = ctx.run_dir / "tool_outputs" / f"{stem}.stderr.txt"
    write_text(stdout_path, result.stdout)
    write_text(stderr_path, result.stderr)
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "stdout_preview": result.stdout[:500],
        "stderr_preview": result.stderr[:500],
    }


def tool_git_status(ctx: RunContext, _: dict[str, Any], __: argparse.Namespace) -> dict[str, Any]:
    status = git_output(ctx.repo, "status", "--short", "--branch")
    output_path = ctx.run_dir / "tool_outputs" / f"{ctx.seq + 1:04d}_git_status.txt"
    write_text(output_path, status)
    return {"output": str(output_path), "text": status}


def tool_git_diff(ctx: RunContext, _: dict[str, Any], __: argparse.Namespace) -> dict[str, Any]:
    diff = git_output(ctx.repo, "diff", "--binary")
    output_path = ctx.run_dir / "tool_outputs" / f"{ctx.seq + 1:04d}_git_diff.patch"
    write_text(output_path, diff)
    return {"output": str(output_path), "bytes": len(diff.encode("utf-8"))}


def tool_finish(ctx: RunContext, action: dict[str, Any], _: argparse.Namespace) -> dict[str, Any]:
    return {"message": str(action.get("message", ""))}


TOOLS: dict[str, Callable[[RunContext, dict[str, Any], argparse.Namespace], dict[str, Any]]] = {
    "read_file": tool_read_file,
    "write_file": tool_write_file,
    "append_file": tool_append_file,
    "run": tool_run,
    "git_status": tool_git_status,
    "git_diff": tool_git_diff,
    "finish": tool_finish,
}


def load_actions(path: Path) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        try:
            action = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
        if not isinstance(action, dict) or "tool" not in action:
            raise ValueError(f"{path}:{line_no}: action must be an object with a tool field")
        actions.append(action)
    return actions


def scrub_action_for_log(action: dict[str, Any]) -> dict[str, Any]:
    clean = dict(action)
    if "content" in clean:
        content = str(clean["content"])
        clean["content_preview"] = content[:300]
        clean["content_bytes"] = len(content.encode("utf-8"))
        clean.pop("content", None)
    return clean


def execute_action_list(ctx: RunContext, args: argparse.Namespace, actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for action in actions:
        tool = str(action["tool"])
        handler = TOOLS.get(tool)
        if handler is None:
            raise ValueError(f"Unknown tool {tool!r}. Available tools: {', '.join(sorted(TOOLS))}")
        before = emit_event(
            ctx,
            event_type="tool_call",
            agent_role="engineer",
            payload={"tool": tool, "args": scrub_action_for_log(action)},
        )
        try:
            result = handler(ctx, action, args)
            ok = not (tool == "run" and int(result.get("returncode", 0)) != 0)
            error = None
        except Exception as exc:
            result = {}
            ok = False
            error = f"{type(exc).__name__}: {exc}"
        after = emit_event(
            ctx,
            event_type="execution_result" if tool == "run" else "code_event",
            agent_role="executor" if tool == "run" else "engineer",
            caused_by=[before],
            payload={"tool": tool, "ok": ok, "result": result, "error": error},
        )
        results.append({"tool": tool, "ok": ok, "event_id": after, "result": result, "error": error})
        if not ok:
            break
    return results


def execute_actions(ctx: RunContext, args: argparse.Namespace) -> list[dict[str, Any]]:
    actions_file = args.actions_file
    if args.qwen and args.execute_qwen_actions:
        actions_file = str(ctx.run_dir / "qwen_actions.jsonl")
    if not actions_file:
        return []
    return execute_action_list(ctx, args, load_actions(Path(actions_file)))
