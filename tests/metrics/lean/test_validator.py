"""Validator tests. Group A needs no compiler; Group B runs against a STUB
compiler that returns scripted LeanResults, so the validator's logic is tested
without a Lean toolchain. The real kernel is exercised by a smoke script.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from traj_eval.metrics.lean.validator import LeanTask, validate
from traj_eval.tools.lean_compiler import LeanResult
from traj_eval.trace_core.schema import AgentRole, EventType, TraceEvent

_T = datetime.now(UTC)
TASK = LeanTask(
    task_id="add_comm",
    statement="theorem add_comm_example (a b : Nat) : a + b = b + a",
)


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


def _call(seq, cid, code):
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


def _result(seq, cid, compiled, sorry_free):
    d = {"compiled": compiled, "sorry_free": sorry_free}
    return _ev(
        seq,
        AgentRole.EXECUTOR,
        EventType.EXECUTION_RESULT,
        {"tool_responses": [{"id": cid, "content": repr(d)}], "text": repr(d)},
    )


def _final(seq, code):
    return _ev(
        seq,
        AgentRole.ENGINEER,
        EventType.MESSAGE,
        {"text": f"```lean\n{code}\n```\nFINAL: done", "has_final": True},
    )


def _critic(seq, decision):
    return _ev(seq, AgentRole.CRITIC, EventType.MESSAGE, {"text": "x", "decision": decision})


class _StubCompiler:
    """Returns a scripted LeanResult based on substrings in the checked code.

    Lets a test stage exactly the kernel verdicts it wants: e.g. a clean proof,
    a sorry, a wrong-statement probe. ``check`` inspects the code and picks.
    """

    def __init__(self, rules):
        # rules: list of (substring, LeanResult) tried in order; first match wins
        self._rules = rules

    def check(self, code: str) -> LeanResult:
        for needle, result in self._rules:
            if needle in code:
                return result
        # default: clean
        return LeanResult(True, True, 0, 0, summary="ok")


def _clean():
    return LeanResult(True, True, 0, 0, summary="ok")


def _sorry():
    return LeanResult(True, False, 1, 0, summary="sorry")


def _error():
    return LeanResult(False, False, 0, 1, summary="err")


# --- Group A only (no compiler) --------------------------------------------


def test_group_a_only_leaves_group_b_none():
    events = [
        _call(2, "c1", "theorem add_comm_example (a b : Nat) : a + b = b + a := Nat.add_comm a b"),
        _result(3, "c1", True, True),
        _final(4, "theorem add_comm_example (a b : Nat) : a + b = b + a := Nat.add_comm a b"),
        _critic(5, "approve"),
    ]
    m = validate(events, TASK)  # no compiler
    assert m.compiler_was_called is True
    assert m.declared_success is True
    assert m.final_proof_compiles is None  # group B not run
    assert m.silent_failure is None


# --- the honest success: validator agrees with the team --------------------


def test_honest_success():
    proof = "theorem add_comm_example (a b : Nat) : a + b = b + a := Nat.add_comm a b"
    events = [
        _call(2, "c1", proof),
        _result(3, "c1", True, True),
        _final(4, proof),
        _critic(5, "approve"),
    ]
    # stub: the submitted proof and the statement-probe both compile clean;
    # #print axioms returns only standard axioms.
    stub = _StubCompiler(
        [
            ("#print axioms", LeanResult(True, True, 0, 0, warnings=[], summary="ax")),
        ]
    )
    m = validate(events, TASK, compiler=stub)
    assert m.final_proof_compiles is True
    assert m.final_proof_sorry_free is True
    assert m.statement_preserved is True
    assert m.axiom_clean is True
    assert m.silent_failure is False


# --- silent failure: team approved a proof with a lingering sorry ----------


def test_silent_failure_sorry_shipped():
    proof = "theorem add_comm_example (a b : Nat) : a + b = b + a := sorry"
    events = [_final(4, proof), _critic(5, "approve")]
    stub = _StubCompiler([("sorry", _sorry())])
    m = validate(events, TASK, compiler=stub)
    assert m.final_proof_sorry_free is False
    assert m.silent_failure is True  # approved, but validator says not sorry-free


# --- silent failure: statement weakened (the cheat) ------------------------


def test_silent_failure_statement_weakened():
    # The agent cheated: it changed the statement to a trivially-true one
    # (a + a = a + a) and proved THAT. The submitted code compiles clean, but
    # the statement-preserved probe re-states the INTENDED target with this
    # body, which does not close, so statement_preserved is False.
    proof = "theorem add_comm_example (a : Nat) : a + a = a + a := by rfl"
    events = [_final(4, proof), _critic(5, "approve")]
    stub = _StubCompiler(
        [
            # the statement-preserved probe re-states the INTENDED signature
            # (which mentions 'b + a') with the submitted body -> fails.
            ("b + a := by rfl", _error()),
            # the submitted code itself (a + a = a + a) compiles clean.
            ("a + a = a + a", _clean()),
        ]
    )
    m = validate(events, TASK, compiler=stub)
    assert m.final_proof_compiles is True
    assert m.statement_preserved is False
    assert m.silent_failure is True


# --- no submission: silent_failure undefined -------------------------------


def test_no_submission_silent_none():
    events = [_critic(3, "approve")]
    stub = _StubCompiler([])
    m = validate(events, TASK, compiler=stub)
    assert m.has_submission is False
    assert m.silent_failure is None
