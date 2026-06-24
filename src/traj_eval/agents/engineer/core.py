from __future__ import annotations

import json
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TRACE_SCHEMA_VERSION = "0.1.0"
RUN_SCHEMA = "traj_eval_codex_style_engineer_run_v1"


@dataclass
class RunContext:
    repo: Path
    run_dir: Path
    task_id: str
    trial_id: str
    event_log: Path
    seq: int = 0


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def slugify(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
    return text[:80] or "task"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_json(path: Path, value: Any) -> None:
    write_text(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False) + "\n")


def run_process(args: list[str] | str, cwd: Path, *, shell: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        text=True,
        capture_output=True,
        shell=shell,
        encoding="utf-8",
        errors="replace",
    )


def run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return run_process(["git", "-C", str(repo), *args], repo)


def git_output(repo: Path, *args: str) -> str:
    result = run_git(repo, *args)
    output = result.stdout if result.returncode == 0 else result.stderr
    return output or ""


def find_repo_root(start: Path) -> Path:
    probe = run_process(["git", "rev-parse", "--show-toplevel"], start)
    if probe.returncode == 0 and probe.stdout.strip():
        return Path(probe.stdout.strip()).resolve()
    for candidate in [start.resolve(), *start.resolve().parents]:
        if (candidate / ".git").exists() and (candidate / "src" / "traj_eval").exists():
            return candidate
    raise RuntimeError(f"Could not find traj-eval repo root from {start}")


def repo_relative_path(repo: Path, raw_path: str) -> Path:
    candidate = (repo / raw_path).resolve()
    repo_resolved = repo.resolve()
    if candidate == repo_resolved:
        return candidate
    if repo_resolved not in candidate.parents:
        raise ValueError(f"path escapes repo root: {raw_path}")
    if ".git" in candidate.relative_to(repo_resolved).parts:
        raise ValueError(f"tool actions may not write inside .git: {raw_path}")
    return candidate


def repo_relative_string(repo: Path, path: Path) -> str:
    return path.resolve().relative_to(repo.resolve()).as_posix()


def emit_event(
    ctx: RunContext,
    *,
    event_type: str,
    agent_role: str,
    payload: dict[str, Any],
    caused_by: list[str] | None = None,
) -> str:
    ctx.seq += 1
    event_id = f"{ctx.trial_id}:{ctx.seq:04d}"
    append_jsonl(
        ctx.event_log,
        {
            "schema_version": TRACE_SCHEMA_VERSION,
            "event_id": event_id,
            "trial_id": ctx.trial_id,
            "seq": ctx.seq,
            "timestamp": now_iso(),
            "event_type": event_type,
            "agent_role": agent_role,
            "caused_by": caused_by or [],
            "payload": payload,
            "anchor": None,
        },
    )
    return event_id


def monitor_call(label: str, log_path: Path, stop: threading.Event, interval: float) -> None:
    start = time.time()
    append_jsonl(log_path, {"type": "start", "label": label, "timestamp": now_iso()})
    while not stop.wait(interval):
        elapsed = round(time.time() - start, 1)
        append_jsonl(log_path, {"type": "tick", "label": label, "timestamp": now_iso(), "elapsed_seconds": elapsed})
        print(f"[{label}] running for {elapsed}s", flush=True)
    append_jsonl(
        log_path,
        {
            "type": "end",
            "label": label,
            "timestamp": now_iso(),
            "elapsed_seconds": round(time.time() - start, 1),
        },
    )
