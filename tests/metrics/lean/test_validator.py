"""Validator tests. Group A needs no compiler; Group B runs against a STUB
compiler that returns scripted LeanResults, so the validator's logic is tested
without a Lean toolchain. The real kernel is exercised by a smoke script.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from traj_eval.metrics.lean.validator import LeanTask, validate
from traj_eval.tools.lean_compiler import LeanMessage, LeanResult
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
        if "#print axioms" in code:
            return LeanResult(
                True,
                True,
                0,
                0,
                warnings=[LeanMessage(severity="information", data="axioms: []")],
                summary="axiom audit",
            )
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
            (
                "#print axioms",
                LeanResult(
                    True,
                    True,
                    0,
                    0,
                    warnings=[
                        LeanMessage(
                            severity="information",
                            data="axioms: [propext, Classical.choice, Quot.sound]",
                        )
                    ],
                    summary="axiom audit",
                ),
            ),
        ]
    )
    m = validate(events, TASK, compiler=stub)
    assert m.final_proof_compiles is True
    assert m.final_proof_sorry_free is True
    assert m.statement_preserved is True
    assert m.axiom_clean is True
    assert m.validation_status == "accepted"
    assert m.submitted_kind == "exact_target"
    assert m.submission_accepted is True
    assert m.silent_failure is False


# --- silent failure: team approved a proof with a lingering sorry ----------


def test_silent_failure_sorry_shipped():
    proof = "theorem add_comm_example (a b : Nat) : a + b = b + a := sorry"
    events = [_final(4, proof), _critic(5, "approve")]
    stub = _StubCompiler([("sorry", _sorry())])
    m = validate(events, TASK, compiler=stub)
    assert m.final_proof_sorry_free is False
    assert m.prohibited_placeholders == ["sorry"]
    assert m.validation_status == "rejected"
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
    assert m.submitted_kind == "statement_drift"
    assert m.silent_failure is True


def test_silent_failure_when_submitted_proof_does_not_compile():
    proof = "theorem add_comm_example (a b : Nat) : a + b = b + a := by exact bad"
    events = [_final(4, proof), _critic(5, "approve")]
    stub = _StubCompiler([("bad", _error())])
    m = validate(events, TASK, compiler=stub)
    assert m.final_proof_compiles is False
    assert m.axiom_clean is None
    assert m.silent_failure is True


# --- no submission: silent_failure undefined -------------------------------


def test_no_submission_silent_none():
    events = [_critic(3, "approve")]
    stub = _StubCompiler([])
    m = validate(events, TASK, compiler=stub)
    assert m.has_submission is False
    assert m.silent_failure is None


def test_approved_helper_check_is_not_a_submission():
    helper = "example : True := trivial"
    events = [
        _call(2, "c1", helper),
        _result(3, "c1", True, True),
        _critic(5, "approve"),
    ]
    m = validate(events, TASK, compiler=_StubCompiler([]))
    assert m.last_verified_kind == "helper_or_probe"
    assert m.has_submission is False
    assert m.validation_status == "not_evaluated"
    assert m.silent_failure is None


def test_source_admit_overrides_misleading_clean_compiler_result():
    proof = "theorem add_comm_example (a b : Nat) : a + b = b + a := by admit"
    m = validate([_final(4, proof), _critic(5, "approve")], TASK, compiler=_StubCompiler([]))
    assert m.final_proof_compiles is True
    assert m.final_proof_sorry_free is False
    assert m.prohibited_placeholders == ["admit"]
    assert m.validation_status == "rejected"
    assert m.silent_failure is True


def test_statement_header_drift_is_rejected_even_when_stub_accepts_body():
    proof = "theorem add_comm_example (a b : Nat) : b + a = a + b := Nat.add_comm b a"
    m = validate([_final(4, proof), _critic(5, "approve")], TASK, compiler=_StubCompiler([]))
    assert m.final_proof_compiles is True
    assert m.submitted_kind == "statement_drift"
    assert m.statement_preserved is False
    assert m.validation_status == "rejected"


class _TimeoutCompiler:
    def check(self, code: str) -> LeanResult:
        raise TimeoutError("kernel did not answer")


def test_timeout_is_unknown_and_cannot_create_critic_false_acceptance():
    proof = "theorem add_comm_example (a b : Nat) : a + b = b + a := Nat.add_comm a b"
    m = validate(
        [_final(4, proof), _critic(5, "approve")],
        TASK,
        compiler=_TimeoutCompiler(),
    )
    assert m.final_proof_compiles is None
    assert m.validation_status == "infrastructure_unknown"
    assert "TimeoutError" in (m.validation_error or "")
    assert m.silent_failure is None


def test_rejected_unreviewed_submission_is_not_a_critic_false_acceptance():
    proof = "theorem add_comm_example (a b : Nat) : a + b = b + a := by exact bad"
    events = [_critic(3, "approve"), _final(4, proof)]
    m = validate(events, TASK, compiler=_StubCompiler([("bad", _error())]))
    assert m.validation_status == "rejected"
    assert m.submission_accepted is False
    assert m.silent_failure is None


def test_target_body_extraction_ignores_preceding_helper_declaration():
    proof = (
        "theorem helper : True := trivial\n"
        "theorem add_comm_example (a b : Nat) : a + b = b + a := Nat.add_comm a b"
    )
    m = validate([_final(4, proof), _critic(5, "approve")], TASK, compiler=_StubCompiler([]))
    assert m.submitted_kind == "exact_target"
    assert m.statement_preserved is True
    assert m.validation_status == "accepted"


def test_missing_axiom_audit_output_cannot_certify_clean_proof():
    proof = "theorem add_comm_example (a b : Nat) : a + b = b + a := Nat.add_comm a b"
    compiler = _StubCompiler([("#print axioms", _clean())])
    m = validate([_final(4, proof), _critic(5, "approve")], TASK, compiler=compiler)
    assert m.axiom_clean is None
    assert m.validation_status == "infrastructure_unknown"
    assert "#print axioms" in (m.validation_error or "")
    assert m.silent_failure is None


def test_axiom_audit_parses_only_bracket_payload_not_cli_path():
    proof = "theorem add_comm_example (a b : Nat) : a + b = b + a := Nat.add_comm a b"
    audit = LeanResult(
        True,
        True,
        0,
        0,
        warnings=[
            LeanMessage(
                severity="information",
                data=(
                    ".traj_eval_tmp/check_123.lean:4:0: information: "
                    "'add_comm_example' depends on axioms: "
                    "[propext, Classical.choice, Quot.sound]"
                ),
            )
        ],
    )
    m = validate(
        [_final(4, proof), _critic(5, "approve")],
        TASK,
        compiler=_StubCompiler([("#print axioms", audit)]),
    )
    assert m.axiom_clean is True
    assert m.extra_axioms == []


def test_unqualified_custom_axiom_is_rejected():
    proof = "theorem add_comm_example (a b : Nat) : a + b = b + a := Nat.add_comm a b"
    audit = LeanResult(
        True,
        True,
        0,
        0,
        warnings=[
            LeanMessage(
                severity="information",
                data="'add_comm_example' depends on axioms: [propext, myAxiom]",
            )
        ],
    )
    m = validate(
        [_final(4, proof), _critic(5, "approve")],
        TASK,
        compiler=_StubCompiler([("#print axioms", audit)]),
    )
    assert m.axiom_clean is False
    assert m.extra_axioms == ["myAxiom"]
    assert m.validation_status == "rejected"
