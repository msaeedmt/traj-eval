"""Group A (pure) tests for the offline validator's artifact extraction.

Fixtures mirror the real smoke_lean.jsonl shapes: tool-call payloads with JSON
``arguments``, execution-result payloads whose ``tool_responses[].content`` is a
Python-repr of the result dict, FINAL engineer messages with fenced ```lean.
No kernel, no ag2.
"""

from __future__ import annotations

from datetime import UTC, datetime

from traj_eval.metrics.lean.artifacts import extract_artifacts
from traj_eval.trace_core.schema import AgentRole, EventType, TraceEvent

_T = datetime.now(UTC)


def _ev(seq, role, etype, payload):
    return TraceEvent(
        event_id=f"e{seq}",
        trial_id="t",
        seq=seq,
        timestamp=_T,
        event_type=etype,
        agent_role=role,
        payload=payload,
    )


def _tool_call(seq, cid, code):
    import json

    return _ev(
        seq,
        AgentRole.ENGINEER,
        EventType.TOOL_CALL,
        {
            "tool_calls": [
                {"id": cid, "name": "check_lean", "arguments": json.dumps({"code": code})}
            ]
        },
    )


def _tool_result(seq, cid, compiled, sorry_free):
    # content is a PYTHON REPR (single quotes, True/False), like ag2 produces.
    d = {"compiled": compiled, "sorry_free": sorry_free, "n_sorries": 0, "summary": "x"}
    return _ev(
        seq,
        AgentRole.EXECUTOR,
        EventType.EXECUTION_RESULT,
        {"tool_responses": [{"id": cid, "content": repr(d)}], "text": repr(d)},
    )


def _engineer_final(seq, code):
    text = f"Here is the proof:\n```lean\n{code}\n```\nFINAL: done"
    return _ev(seq, AgentRole.ENGINEER, EventType.MESSAGE, {"text": text, "has_final": True})


def _critic(seq, decision):
    return _ev(seq, AgentRole.CRITIC, EventType.MESSAGE, {"text": "...", "decision": decision})


# --- the happy path, mirroring the real add_comm smoke run -----------------


def test_smoke_like_trace():
    proof = "import Mathlib\ntheorem t (a b : Nat) : a + b = b + a := Nat.add_comm a b"
    events = [
        _tool_call(2, "c1", "import Mathlib\ntheorem t (a b : Nat) : a + b = b + a := sorry"),
        _tool_result(3, "c1", compiled=True, sorry_free=False),
        _tool_call(4, "c2", proof),
        _tool_result(5, "c2", compiled=True, sorry_free=True),
        _engineer_final(6, proof),
        _critic(7, "approve"),
    ]
    art = extract_artifacts(events)
    assert art.submitted is not None and "Nat.add_comm" in art.submitted
    assert art.last_verified is not None and "Nat.add_comm" in art.last_verified
    assert art.compiler_was_called is True
    assert art.n_tool_calls == 2
    assert art.declared_success is True
    # submitted matches the last verified snippet
    assert art.submitted_eq_last_verified is True


# --- submitted != last verified (the silent-shipping case) -----------------


def test_submitted_differs_from_verified():
    verified = "import Mathlib\ntheorem t : True := trivial"
    shipped = "import Mathlib\ntheorem t (a b : Nat) : a + b = b + a := sorry"  # never verified
    events = [
        _tool_call(2, "c1", verified),
        _tool_result(3, "c1", compiled=True, sorry_free=True),
        _engineer_final(4, shipped),
        _critic(5, "approve"),
    ]
    art = extract_artifacts(events)
    assert art.submitted_eq_last_verified is False


# --- compiler never called -------------------------------------------------


def test_compiler_never_called():
    events = [
        _engineer_final(2, "theorem t : True := trivial"),
        _critic(3, "approve"),
    ]
    art = extract_artifacts(events)
    assert art.compiler_was_called is False
    assert art.last_verified is None
    assert art.submitted_eq_last_verified is None  # undefined, not False


# --- failed compiles counted ------------------------------------------------


def test_failed_compiles_counted():
    events = [
        _tool_call(2, "c1", "bad code"),
        _tool_result(3, "c1", compiled=False, sorry_free=False),
        _tool_call(4, "c2", "theorem t : True := trivial"),
        _tool_result(5, "c2", compiled=True, sorry_free=True),
        _engineer_final(6, "theorem t : True := trivial"),
        _critic(7, "approve"),
    ]
    art = extract_artifacts(events)
    assert art.n_failed_compiles == 1
    assert art.n_tool_calls == 2
    # last_verified is the SUCCESSFUL one, not the failed first call
    assert "True" in art.last_verified


# --- rejection -> declared_success False -----------------------------------


def test_final_rejection():
    events = [
        _engineer_final(2, "theorem t : True := trivial"),
        _critic(3, "reject"),
    ]
    art = extract_artifacts(events)
    assert art.declared_success is False


# --- trailing 'thanks' engineer turn (no FINAL) is ignored -----------------


def test_multi_block_final_picks_last_block():
    # The real failure mode: the FINAL message shows the sorry scaffold AND the
    # real proof as two fenced blocks. The submitted artifact must be the LAST
    # block (the real proof), never the two glued together.
    scaffold = "import Mathlib\ntheorem t (a b : Nat) : a + b = b + a := sorry"
    real = "import Mathlib\ntheorem t (a b : Nat) : a + b = b + a := Nat.add_comm a b"
    text = (
        f"First the scaffold:\n```lean\n{scaffold}\n```\n"
        f"Then the proof:\n```lean\n{real}\n```\nFINAL: done"
    )
    events = [
        _ev(2, AgentRole.ENGINEER, EventType.MESSAGE, {"text": text, "has_final": True}),
        _critic(3, "approve"),
    ]
    art = extract_artifacts(events)
    assert art.submitted == real
    assert "sorry" not in art.submitted  # the scaffold block was NOT included


def test_trailing_non_final_message_ignored():
    proof = "theorem t : True := trivial"
    events = [
        _engineer_final(2, proof),
        _critic(3, "approve"),
        _ev(4, AgentRole.ENGINEER, EventType.MESSAGE, {"text": "Thanks for the approval!"}),
        _critic(5, "approve"),
    ]
    art = extract_artifacts(events)
    # submitted is still the real proof, not the empty 'thanks' turn
    assert art.submitted is not None and "True" in art.submitted
