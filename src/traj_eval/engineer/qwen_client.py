from __future__ import annotations

import argparse
import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from .core import RunContext, emit_event, monitor_call, write_text


def load_env_file(path: Path) -> dict[str, str]:
    loaded: dict[str, str] = {}
    if not path.exists():
        return loaded
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ[key] = value
            loaded[key] = value
    return loaded


def redact_config(values: dict[str, str]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in values.items():
        if "KEY" in key or "TOKEN" in key or "SECRET" in key:
            redacted[key] = {"set": bool(value), "length": len(value)}
        else:
            redacted[key] = value
    return redacted


def resolve_qwen_config(repo: Path, args: argparse.Namespace) -> dict[str, Any]:
    env_path = Path(
        args.provider_env
        or os.getenv("TRAJ_EVAL_PROVIDER_ENV")
        or repo / "configs" / "qwen.remote.local.env"
    ).expanduser()
    loaded = load_env_file(env_path)
    base_url = (os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE") or "").strip()
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    model = (
        args.qwen_model
        or os.getenv("CMBAGENT_EVAL_LOCAL_MODEL")
        or os.getenv("TRAJ_EVAL_MODEL")
        or os.getenv("OPENAI_MODEL")
        or ""
    ).strip()
    return {
        "env_path": str(env_path),
        "loaded_redacted": redact_config(loaded),
        "base_url": base_url,
        "api_key_set": bool(api_key),
        "api_key_length": len(api_key),
        "model": model,
        "timeout": float(args.qwen_timeout or os.getenv("QWEN_REQUEST_TIMEOUT", "300")),
        "max_retries": int(args.qwen_max_retries or os.getenv("QWEN_MAX_RETRIES", "1")),
    }


def extract_qwen_text(message: Any) -> str:
    content = (getattr(message, "content", None) or "").strip()
    reasoning = (getattr(message, "reasoning_content", None) or "").strip()
    return content or reasoning


def strip_fences(text: str) -> str:
    lines = text.strip().splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def parse_jsonl_actions_text(text: str) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    cleaned = strip_fences(text)
    decoder = json.JSONDecoder()
    try:
        parsed_whole = json.loads(cleaned)
        if isinstance(parsed_whole, dict) and "tool" in parsed_whole:
            return [parsed_whole]
        if isinstance(parsed_whole, list):
            whole_actions = [item for item in parsed_whole if isinstance(item, dict) and "tool" in item]
            if whole_actions:
                return whole_actions
    except json.JSONDecodeError:
        pass
    for line in cleaned.splitlines():
        item = line.strip()
        if not item or item.startswith("#"):
            continue
        try:
            parsed = json.loads(item)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and "tool" in parsed:
            actions.append(parsed)
    if actions:
        return actions

    index = 0
    while index < len(cleaned):
        while index < len(cleaned) and cleaned[index].isspace():
            index += 1
        if cleaned[index : index + 2] == "\\n":
            index += 2
            continue
        start = cleaned.find("{", index)
        if start < 0:
            break
        try:
            parsed, end = decoder.raw_decode(cleaned[start:])
        except json.JSONDecodeError:
            index = start + 1
            continue
        if isinstance(parsed, dict) and "tool" in parsed:
            actions.append(parsed)
        index = start + end
    if not actions:
        raise ValueError("Qwen response did not contain parseable JSONL tool actions.")
    return actions


def write_actions(path: Path, actions: list[dict[str, Any]]) -> None:
    write_text(path, "".join(json.dumps(action, ensure_ascii=False) + "\n" for action in actions))


def build_qwen_client(repo: Path, args: argparse.Namespace) -> tuple[Any, str, dict[str, Any]]:
    try:
        from openai import OpenAI
    except Exception as exc:
        raise RuntimeError(f"openai package is not available: {exc}") from exc

    config = resolve_qwen_config(repo, args)
    if not config["base_url"]:
        raise RuntimeError("OPENAI_BASE_URL or OPENAI_API_BASE is missing.")
    if not config["api_key_set"]:
        raise RuntimeError("OPENAI_API_KEY is missing.")

    client = OpenAI(
        base_url=config["base_url"],
        api_key=os.getenv("OPENAI_API_KEY"),
        timeout=config["timeout"],
        max_retries=config["max_retries"],
    )
    model = config["model"]
    if not model:
        model_list = client.models.list()
        model = model_list.data[0].id if model_list.data else ""
    if not model:
        raise RuntimeError("No Qwen model configured and /models returned no model id.")
    return client, model, config


def chat_completion(client: Any, model: str, messages: list[dict[str, str]], args: argparse.Namespace) -> Any:
    return client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0,
        max_tokens=args.qwen_max_tokens,
        extra_body={"chat_template_kwargs": {"enable_thinking": args.qwen_enable_thinking}},
    )


def request_qwen_actions(
    ctx: RunContext,
    client: Any,
    model: str,
    messages: list[dict[str, str]],
    args: argparse.Namespace,
    *,
    turn: int | None,
    caused_by: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    label = f"qwen-engineer-turn-{turn}" if turn else "qwen-engineer"
    monitor_log = ctx.run_dir / "qwen_monitor.jsonl"
    request_event = emit_event(
        ctx,
        event_type="message",
        agent_role="engineer",
        caused_by=[caused_by] if caused_by else None,
        payload={
            "phase": "qwen_request",
            "turn": turn,
            "model": model,
            "prompt": str(ctx.run_dir / "engineer_prompt.md"),
            "enable_thinking": args.qwen_enable_thinking,
        },
    )

    monitor_stop = threading.Event()
    monitor = threading.Thread(
        target=monitor_call,
        args=(label, monitor_log, monitor_stop, args.monitor_interval),
        daemon=True,
    )
    monitor.start()
    started = time.time()
    try:
        response = chat_completion(client, model, messages, args)
    finally:
        monitor_stop.set()
        monitor.join(timeout=5)

    elapsed = round(time.time() - started, 3)
    message = response.choices[0].message
    text = extract_qwen_text(message)
    suffix = f"_turn_{turn:02d}" if turn else ""
    text_path = ctx.run_dir / f"qwen_engineer_response{suffix}.txt"
    actions_path = ctx.run_dir / f"qwen_actions{suffix}.jsonl"
    write_text(text_path, text)
    actions = parse_jsonl_actions_text(text)
    write_actions(actions_path, actions)
    record = {
        "ok": True,
        "model": model,
        "finish_reason": response.choices[0].finish_reason,
        "elapsed_seconds": elapsed,
        "reasoning_present": bool(getattr(message, "reasoning_content", None)),
        "tokens": response.usage.model_dump() if response.usage else {},
        "text_path": str(text_path),
        "actions_path": str(actions_path),
        "action_count": len(actions),
        "monitor_log": str(monitor_log),
    }
    response_event = emit_event(
        ctx,
        event_type="message",
        agent_role="engineer",
        caused_by=[request_event],
        payload={"phase": "qwen_response", "turn": turn, **record},
    )
    record["event_id"] = response_event
    return record, actions, text
