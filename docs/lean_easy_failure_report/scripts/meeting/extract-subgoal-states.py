"""Safely extract typed-tool results and replay subgoal ledger states.

The AG2 tool transport stores Python ``repr`` strings in execution-result
records.  ``ast.literal_eval`` is intentionally used here instead of eval.
The script writes one deterministic JSON document to stdout and never mutates
the experiment directory.
"""

from __future__ import annotations

import argparse
import ast
import copy
import json
import sys
from pathlib import Path
from typing import Any


def parse_arguments(raw: Any) -> Any:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def parse_result(raw: Any) -> tuple[Any, str | None]:
    if not isinstance(raw, str) or not raw.strip():
        return None, "empty tool response"
    try:
        return ast.literal_eval(raw), None
    except (SyntaxError, ValueError) as exc:
        if raw.lstrip().startswith("Error:"):
            return {"ok": False, "error": raw, "protocol_error": True}, None
        return None, f"{type(exc).__name__}: {exc}"


def state_from_result(result: Any) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    automatic = result.get("automatic_submission")
    if isinstance(automatic, dict) and isinstance(automatic.get("state"), dict):
        return copy.deepcopy(automatic["state"])
    if isinstance(result.get("state"), dict):
        return copy.deepcopy(result["state"])
    if isinstance(result.get("nodes"), list) and "version" in result:
        return copy.deepcopy(result)
    return None


def node_map(state: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not state:
        return {}
    return {
        str(node.get("id")): node
        for node in state.get("nodes", [])
        if isinstance(node, dict) and node.get("id") is not None
    }


def compact(text: Any, limit: int = 300) -> str:
    return " ".join(str(text or "").split())[:limit]


def apply_unsnapshotted_check(
    state: dict[str, Any] | None,
    arguments: Any,
    result: Any,
) -> dict[str, Any] | None:
    if not state or not isinstance(arguments, dict) or not isinstance(result, dict):
        return state
    if result.get("ok") is not True:
        return state
    purpose = result.get("purpose", arguments.get("purpose", "subgoal"))
    if purpose not in {"subgoal", "final"}:
        return state
    subgoal_id = result.get("subgoal_id", arguments.get("subgoal_id"))
    nodes = node_map(state)
    node = nodes.get(str(subgoal_id))
    if node is None:
        return state

    next_state = copy.deepcopy(state)
    next_node = node_map(next_state)[str(subgoal_id)]
    next_state["version"] = int(next_state.get("version", 0)) + 1
    next_node["attempts"] = int(next_node.get("attempts", 0)) + 1
    if result.get("compiled") is True:
        next_node["consecutive_failures"] = 0
    elif result.get("compiled") is False:
        next_node["consecutive_failures"] = int(
            next_node.get("consecutive_failures", 0)
        ) + 1
        failures = list(next_node.get("failures") or [])
        failures.append(compact(result.get("summary")))
        max_notes = int((next_state.get("limits") or {}).get("max_failure_notes", 3))
        next_node["failures"] = failures[-max_notes:]
        if result.get("recovery_required") or result.get("recovery_exhausted"):
            next_node["status"] = "blocked"
            if next_state.get("active_subgoal") == subgoal_id:
                next_state["active_subgoal"] = None
    return next_state


def transition_kind(before: str | None, after: str | None) -> str:
    if before is None:
        return "created"
    if after == "active" and before != "active":
        return "activated"
    if after == "candidate" and before != "candidate":
        return "candidate"
    if after == "accepted" and before != "accepted":
        return "accepted"
    if after == "rejected" and before != "rejected":
        return "rejected"
    if after == "blocked" and before != "blocked":
        return "blocked"
    if after == "pending" and before not in {None, "pending"}:
        return "descendant_reset"
    return "status_changed"


def diff_states(
    before: dict[str, Any] | None,
    after: dict[str, Any],
    *,
    seq: int,
    event_id: str | None,
    tool: str,
    result: Any,
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    old_nodes = node_map(before)
    new_nodes = node_map(after)
    for subgoal_id, node in new_nodes.items():
        prior = old_nodes.get(subgoal_id)
        if prior is None:
            changes.append(
                {
                    "seq": seq,
                    "event_id": event_id,
                    "subgoal_id": subgoal_id,
                    "kind": "created",
                    "from_status": None,
                    "to_status": node.get("status"),
                    "detail": node.get("objective", ""),
                }
            )
            continue
        if prior.get("objective") != node.get("objective") or prior.get(
            "depends_on"
        ) != node.get("depends_on"):
            changes.append(
                {
                    "seq": seq,
                    "event_id": event_id,
                    "subgoal_id": subgoal_id,
                    "kind": "revised",
                    "from_status": prior.get("status"),
                    "to_status": node.get("status"),
                    "detail": node.get("objective", ""),
                }
            )
        if prior.get("status") != node.get("status"):
            changes.append(
                {
                    "seq": seq,
                    "event_id": event_id,
                    "subgoal_id": subgoal_id,
                    "kind": transition_kind(prior.get("status"), node.get("status")),
                    "from_status": prior.get("status"),
                    "to_status": node.get("status"),
                    "detail": compact(node.get("feedback"), 500),
                }
            )
        attempt_delta = int(node.get("attempts", 0)) - int(prior.get("attempts", 0))
        if attempt_delta > 0:
            compiled = result.get("compiled") if isinstance(result, dict) else None
            changes.append(
                {
                    "seq": seq,
                    "event_id": event_id,
                    "subgoal_id": subgoal_id,
                    "kind": "attempt_succeeded" if compiled is True else "attempt_failed",
                    "from_status": prior.get("status"),
                    "to_status": node.get("status"),
                    "detail": compact(
                        result.get("summary") if isinstance(result, dict) else "",
                        500,
                    ),
                    "attempt_delta": attempt_delta,
                }
            )
    if int(after.get("forced_recoveries", 0)) > int(
        (before or {}).get("forced_recoveries", 0)
    ):
        changes.append(
            {
                "seq": seq,
                "event_id": event_id,
                "subgoal_id": None,
                "kind": "forced_recovery",
                "from_status": None,
                "to_status": None,
                "detail": f"forced recoveries={after.get('forced_recoveries')}",
            }
        )
    if int(after.get("strategy_revisions", 0)) > int(
        (before or {}).get("strategy_revisions", 0)
    ):
        changes.append(
            {
                "seq": seq,
                "event_id": event_id,
                "subgoal_id": None,
                "kind": "strategy_revision",
                "from_status": None,
                "to_status": None,
                "detail": f"strategy revisions={after.get('strategy_revisions')}",
            }
        )
    return changes


def canonical_state(state: dict[str, Any] | None) -> Any:
    if state is None:
        return None
    return json.loads(json.dumps(state, sort_keys=True, ensure_ascii=False))


def state_mismatches(observed: Any, expected: Any) -> list[str]:
    if observed == expected:
        return []
    mismatches: list[str] = []
    for key in [
        "version",
        "active_subgoal",
        "plan_ready",
        "forced_recoveries",
        "strategy_revisions",
        "nodes",
    ]:
        if (observed or {}).get(key) != (expected or {}).get(key):
            mismatches.append(key)
    return mismatches or ["state"]


def extract_trial(path: Path) -> dict[str, Any]:
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    header, events = records[0], records[1:]
    call_tool_by_id: dict[str, str | None] = {}
    for event in events:
        if event.get("event_type") != "tool_call":
            continue
        for call in (event.get("payload") or {}).get("tool_calls") or []:
            call_tool_by_id[str(call.get("id"))] = call.get("name")
    result_by_id: dict[str, dict[str, Any]] = {}
    parse_errors: list[dict[str, Any]] = []
    for event in events:
        if event.get("event_type") != "execution_result":
            continue
        for response in (event.get("payload") or {}).get("tool_responses") or []:
            tool = call_tool_by_id.get(str(response.get("id")))
            if tool == "search_lemmas":
                parsed, error = None, None
            else:
                parsed, error = parse_result(response.get("content"))
            result_by_id[str(response.get("id"))] = {
                "result": parsed,
                "parse_error": error,
                "result_seq": event.get("seq"),
                "result_event_id": event.get("event_id"),
            }
            if error:
                parse_errors.append(
                    {
                        "call_id": response.get("id"),
                        "result_seq": event.get("seq"),
                        "error": error,
                    }
                )

    invocations: list[dict[str, Any]] = []
    for event in events:
        if event.get("event_type") != "tool_call":
            continue
        for call in (event.get("payload") or {}).get("tool_calls") or []:
            response = result_by_id.get(str(call.get("id")), {})
            invocations.append(
                {
                    "call_id": call.get("id"),
                    "tool": call.get("name"),
                    "call_seq": event.get("seq"),
                    "call_event_id": event.get("event_id"),
                    "role": event.get("agent_role"),
                    "arguments": parse_arguments(call.get("arguments")),
                    "result_seq": response.get("result_seq"),
                    "result_event_id": response.get("result_event_id"),
                    "result": response.get("result"),
                    "parse_error": response.get("parse_error"),
                    "matched": bool(response),
                }
            )
    invocations.sort(key=lambda item: (int(item.get("call_seq") or -1), str(item.get("call_id"))))

    state: dict[str, Any] | None = None
    frames: list[dict[str, Any]] = []
    transitions: list[dict[str, Any]] = []
    for invocation in invocations:
        result = invocation.get("result")
        next_state = state_from_result(result)
        if next_state is None and invocation.get("tool") == "check_lean":
            next_state = apply_unsnapshotted_check(
                state,
                invocation.get("arguments"),
                result,
            )
        if next_state is None or canonical_state(next_state) == canonical_state(state):
            continue
        changes = diff_states(
            state,
            next_state,
            seq=int(invocation.get("result_seq") or invocation.get("call_seq") or -1),
            event_id=invocation.get("result_event_id") or invocation.get("call_event_id"),
            tool=str(invocation.get("tool") or ""),
            result=result,
        )
        state = next_state
        transitions.extend(changes)
        frames.append(
            {
                "seq": int(invocation.get("result_seq") or invocation.get("call_seq") or -1),
                "event_id": invocation.get("result_event_id")
                or invocation.get("call_event_id"),
                "version": state.get("version"),
                "tool": invocation.get("tool"),
                "active_subgoal": state.get("active_subgoal"),
                "plan_ready": state.get("plan_ready"),
                "forced_recoveries": state.get("forced_recoveries", 0),
                "strategy_revisions": state.get("strategy_revisions", 0),
                "nodes": copy.deepcopy(state.get("nodes") or []),
                "changes": copy.deepcopy(changes),
            }
        )

    plan_event = next(
        (
            event
            for event in reversed(events)
            if (event.get("payload") or {}).get("phase") == "controller_plan"
        ),
        None,
    )
    terminal_event = next(
        (
            event
            for event in reversed(events)
            if (event.get("payload") or {}).get("phase") == "termination"
        ),
        None,
    )
    expected = (
        (((plan_event or {}).get("payload") or {}).get("plan") or {}).get("final_state")
    )
    observed = canonical_state(state)
    expected_canonical = canonical_state(expected)
    mismatches = state_mismatches(observed, expected_canonical)
    if expected_canonical is None:
        replay_status = "unavailable"
    else:
        replay_status = "matched" if not mismatches else "gap"

    return {
        "trial_id": header.get("trial_id"),
        "task_id": header.get("task_id"),
        "tool_invocations": invocations,
        "frames": frames,
        "transitions": transitions,
        "terminal_state": expected,
        "replay_validation": {
            "status": replay_status,
            "expected_version": (expected or {}).get("version"),
            "observed_version": (state or {}).get("version"),
            "mismatches": mismatches,
        },
        "termination": (terminal_event or {}).get("payload") or {},
        "parse_errors": parse_errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir", type=Path)
    args = parser.parse_args()
    paths = sorted(args.input_dir.glob("*.jsonl"), key=lambda path: path.name)
    payload = {
        "schema_version": "subgoal-extraction.v1",
        "trials": [extract_trial(path) for path in paths],
    }
    json.dump(payload, sys.stdout, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
