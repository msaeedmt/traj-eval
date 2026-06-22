from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from .core import (
    git_output,
    repo_relative_path,
    repo_relative_string,
    run_git,
    write_json,
    write_text,
)


VERSION_INDEX_SCHEMA = "traj_eval_engineer_version_index_v1"


def capture_git_state(repo: Path, run_dir: Path, prefix: str) -> dict[str, str]:
    files = {
        "branch": run_dir / f"{prefix}_branch.txt",
        "head": run_dir / f"{prefix}_head.txt",
        "status": run_dir / f"{prefix}_status.txt",
        "diff": run_dir / f"{prefix}_diff.patch",
        "cached_diff": run_dir / f"{prefix}_cached_diff.patch",
    }
    write_text(files["branch"], git_output(repo, "branch", "--show-current"))
    write_text(files["head"], git_output(repo, "rev-parse", "HEAD"))
    write_text(files["status"], git_output(repo, "status", "--short", "--branch"))
    write_text(files["diff"], git_output(repo, "diff", "--binary"))
    write_text(files["cached_diff"], git_output(repo, "diff", "--cached", "--binary"))
    return {name: str(path) for name, path in files.items()}


def changed_paths(repo: Path) -> list[str]:
    paths: set[str] = set()
    for args in [
        ("diff", "--name-only"),
        ("diff", "--cached", "--name-only"),
        ("ls-files", "--others", "--exclude-standard"),
    ]:
        result = run_git(repo, *args)
        if result.returncode == 0:
            paths.update(line.strip() for line in result.stdout.splitlines() if line.strip())
    return sorted(paths)


def snapshot_changed_files(repo: Path, run_dir: Path) -> list[dict[str, Any]]:
    snapshot_dir = run_dir / "changed_snapshots"
    rows: list[dict[str, Any]] = []
    for rel in changed_paths(repo):
        source = repo / rel
        exists = source.exists()
        copied_to = None
        if exists and source.is_file():
            digest = hashlib.sha1(rel.encode("utf-8")).hexdigest()[:12]
            suffix = Path(rel).suffix
            stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(rel).stem).strip("-._") or "file"
            target = snapshot_dir / f"{digest}-{stem[:48]}{suffix}"
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied_to = str(target)
        rows.append({"path": rel, "exists": exists, "snapshot": copied_to})
    write_json(run_dir / "changed_files.json", rows)
    return rows


def collect_artifacts(repo: Path, rel_roots: list[str] | None) -> list[dict[str, Any]]:
    if not rel_roots:
        return []
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rel_root in rel_roots:
        root = repo_relative_path(repo, rel_root)
        if not root.exists():
            continue
        files = [root] if root.is_file() else sorted(path for path in root.rglob("*") if path.is_file())
        for path in files:
            rel = repo_relative_string(repo, path)
            if rel in seen:
                continue
            seen.add(rel)
            rows.append({"path": rel, "bytes": path.stat().st_size})
    return rows


def check_repo_guard(repo: Path, skip: bool) -> dict[str, str]:
    branch = git_output(repo, "branch", "--show-current").strip()
    origin = git_output(repo, "remote", "get-url", "origin").strip()
    if not skip:
        if branch != "Han":
            raise RuntimeError(f"Expected branch Han, found {branch!r}")
        if "msaeedmt/traj-eval" not in origin:
            raise RuntimeError(f"Expected msaeedmt/traj-eval origin, found {origin!r}")
    return {"branch": branch, "origin": origin}


def classification_score(classification: str) -> int:
    scores = {
        "completed_with_verification": 60,
        "completed_without_verification": 50,
        "incomplete_no_finish": 40,
        "verification_or_tool_failure": 30,
        "read_only_no_execution": 20,
        "qwen_call_failed": 10,
        "no_actions_executed": 5,
        "prompt_only": 0,
    }
    return scores.get(classification, -1)


def load_json_if_exists(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def summarize_manifest(path: Path) -> dict[str, Any] | None:
    manifest = load_json_if_exists(path)
    if not manifest:
        return None
    diagnosis = manifest.get("run_diagnosis") or {}
    qwen = manifest.get("qwen") or {}
    return {
        "run_id": manifest.get("run_id") or path.parent.name,
        "manifest": str(path),
        "classification": diagnosis.get("classification", "unknown"),
        "score": classification_score(str(diagnosis.get("classification", ""))),
        "tools_requested": diagnosis.get("tools_requested", []),
        "failed_tools": diagnosis.get("failed_tools", []),
        "run_returncodes": diagnosis.get("run_returncodes", []),
        "qwen_ok": qwen.get("ok"),
        "qwen_mode": qwen.get("mode", "one_shot" if qwen else None),
        "trace_validation_ok": (manifest.get("trace_validation") or {}).get("ok"),
    }


def recommended_steps(previous_versions: list[dict[str, Any]]) -> list[str]:
    if not previous_versions:
        return [
            "No previous version found for this task_id; produce a complete action list.",
            "Prefer write/run/git_status/git_diff/finish when the task has enough context.",
        ]
    latest = previous_versions[-1]
    classification = str(latest.get("classification", ""))
    if classification == "read_only_no_execution":
        return [
            "Do not stop after read_file. Use --qwen-interactive-tools or preload files with --context-file.",
            "Continue from file evidence to write_file or run actions, then end with finish.",
        ]
    if classification == "verification_or_tool_failure":
        return [
            "Inspect the previous failed tool result and repair the concrete stderr/stdout issue.",
            "Run the same verification command again before finish.",
        ]
    if classification in {"prompt_only", "no_actions_executed"}:
        return [
            "This task still needs executable tool actions, not only a prompt artifact.",
            "Return a complete ordered JSONL action list ending with finish.",
        ]
    if classification == "incomplete_no_finish":
        return [
            "Previous actions did not finish cleanly; add git_status, git_diff, and finish.",
            "Keep the successful earlier actions and add the missing terminal step.",
        ]
    if classification == "completed_with_verification":
        return [
            "A verified previous version exists; use it as the baseline.",
            "Only change the next run if there is a concrete improvement over the verified manifest.",
        ]
    return [
        "Compare against the best previous manifest and preserve any successful verification steps.",
        "Use tool evidence rather than prose to justify the next engineer action.",
    ]


def build_version_index(repo: Path, task_id: str, run_id: str, run_dir: Path, limit: int = 8) -> dict[str, Any]:
    task_root = repo / "runs" / "engineer" / task_id
    manifests = []
    if task_root.exists():
        for manifest_path in sorted(task_root.glob("*/run_manifest.json")):
            if manifest_path.parent.resolve() == run_dir.resolve():
                continue
            row = summarize_manifest(manifest_path)
            if row:
                manifests.append(row)
    previous_versions = manifests[-limit:]
    best_previous = max(previous_versions, key=lambda row: row.get("score", -1), default=None)
    return {
        "schema": VERSION_INDEX_SCHEMA,
        "task_id": task_id,
        "current_run_id": run_id,
        "previous_count": len(manifests),
        "previous_versions": previous_versions,
        "best_previous": best_previous,
        "recommended_engineer_steps": recommended_steps(previous_versions),
    }


def ensure_clean_if_branching(repo: Path, create_branch: bool, allow_dirty: bool) -> None:
    status = git_output(repo, "status", "--porcelain").strip()
    if create_branch and status and not allow_dirty:
        raise RuntimeError("Refusing to create a task branch from a dirty worktree.")


def maybe_create_branch(repo: Path, create: bool, branch_prefix: str, task_id: str) -> str | None:
    if not create:
        return None
    branch = branch_prefix + task_id
    result = run_git(repo, "switch", "-c", branch)
    if result.returncode != 0:
        raise RuntimeError(f"Could not create branch {branch!r}:\n{result.stderr}")
    return branch


def validate_with_traj_eval_schema(repo: Path, event_log: Path) -> dict[str, Any]:
    src = repo / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    try:
        from traj_eval.trace_core.storage import read_trial
    except Exception as exc:
        return {"ok": False, "stage": "import", "error": f"{type(exc).__name__}: {exc}"}

    try:
        meta, events = read_trial(event_log)
    except Exception as exc:
        return {"ok": False, "stage": "read_trial", "error": f"{type(exc).__name__}: {exc}"}

    return {
        "ok": True,
        "trial_id": meta.trial_id,
        "task_id": meta.task_id,
        "architecture": meta.architecture,
        "event_count": len(events),
        "roles": sorted({event.agent_role.value for event in events}),
        "event_types": sorted({event.event_type.value for event in events}),
    }


def diagnose_run(
    args: argparse.Namespace,
    qwen_record: dict[str, Any] | None,
    action_results: list[dict[str, Any]],
    trace_validation: dict[str, Any],
) -> dict[str, Any]:
    tools = [str(row.get("tool", "")) for row in action_results]
    run_returncodes = [
        row.get("result", {}).get("returncode")
        for row in action_results
        if row.get("tool") == "run" and "returncode" in row.get("result", {})
    ]
    failed_tools = [
        {
            "tool": row.get("tool"),
            "error": row.get("error"),
            "returncode": row.get("result", {}).get("returncode"),
        }
        for row in action_results
        if not row.get("ok") or row.get("result", {}).get("returncode") not in (None, 0)
    ]
    has_write = any(tool in {"write_file", "append_file"} for tool in tools)
    has_run = "run" in tools
    has_finish = "finish" in tools
    if args.write_prompt_only:
        classification = "prompt_only"
    elif qwen_record and not qwen_record.get("ok"):
        classification = "qwen_call_failed"
    elif not action_results:
        classification = "no_actions_executed"
    elif failed_tools:
        classification = "verification_or_tool_failure"
    elif tools and set(tools) <= {"read_file"}:
        classification = "read_only_no_execution"
    elif not has_finish:
        classification = "incomplete_no_finish"
    elif has_run:
        classification = "completed_with_verification"
    else:
        classification = "completed_without_verification"
    return {
        "classification": classification,
        "tools_requested": tools,
        "read_only_actions": bool(tools and set(tools) <= {"read_file"}),
        "has_write": has_write,
        "has_run": has_run,
        "has_finish": has_finish,
        "failed_tools": failed_tools,
        "run_returncodes": run_returncodes,
        "trace_validation_ok": bool(trace_validation.get("ok")),
    }
