"""Group A (pure) tests for the offline validator's artifact extraction.

Fixtures mirror the real smoke_lean.jsonl shapes: tool-call payloads with JSON
``arguments``, execution-result payloads whose ``tool_responses[].content`` is a
Python-repr of the result dict, FINAL engineer messages with fenced ```lean.
No kernel, no ag2.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from traj_eval.metrics.lean.artifacts import (
    candidate_kind,
    extract_artifacts,
    prohibited_placeholders,
)
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


def _search_call(seq, cid, query, *, include_name=True):
    return _ev(
        seq,
        AgentRole.ENGINEER,
        EventType.TOOL_CALL,
        {
            "tool_calls": [
                {
                    "id": cid,
                    **({"name": "search_lemmas"} if include_name else {}),
                    "arguments": json.dumps({"query": query}),
                }
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


def _named_call(seq, role, cid, name, arguments):
    return _ev(
        seq,
        role,
        EventType.TOOL_CALL,
        {
            "tool_calls": [
                {"id": cid, "name": name, "arguments": json.dumps(arguments)}
            ]
        },
    )


def _dict_result(seq, cid, payload):
    return _ev(
        seq,
        AgentRole.EXECUTOR,
        EventType.EXECUTION_RESULT,
        {
            "tool_responses": [{"id": cid, "content": repr(payload)}],
            "text": repr(payload),
        },
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


def test_search_calls_do_not_inflate_compiler_attempts():
    events = [
        _search_call(1, "s1", "Nat addition commutative"),
        _search_call(2, "s2", "legacy unnamed search", include_name=False),
        _tool_call(3, "c1", "theorem t : True := trivial"),
        _tool_result(4, "c1", compiled=True, sorry_free=True),
    ]
    art = extract_artifacts(events)
    assert art.compiler_was_called is True
    assert art.n_tool_calls == 1
    assert [record.call_id for record in art.tool_calls] == ["c1"]


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


def test_verified_helper_is_not_inferred_as_submission():
    proof = "example : True := trivial"
    handoff = _ev(
        6,
        AgentRole.ENGINEER,
        EventType.MESSAGE,
        {"text": "HANDOFF: critic", "has_final": True},  # no ```lean block
    )
    events = [
        _tool_call(2, "c1", proof),
        _tool_result(3, "c1", True, True),
        handoff,
        _critic(7, "approve"),
    ]
    art = extract_artifacts(events, target_statement="theorem target : True")
    assert art.last_verified == proof
    assert art.last_verified_kind == "helper_or_probe"
    assert art.submitted is None
    assert art.submission_source == "none"


def test_approved_exact_target_can_be_inferred_from_verified_candidate():
    proof = "theorem target : True := trivial"
    events = [
        _tool_call(2, "c1", proof),
        _tool_result(3, "c1", True, True),
        _ev(
            6,
            AgentRole.ENGINEER,
            EventType.MESSAGE,
            {"text": "HANDOFF: critic", "has_final": True},
        ),
        _critic(7, "approve"),
    ]
    art = extract_artifacts(events, target_statement="theorem target : True")
    assert art.submitted == proof
    assert art.submitted_kind == "exact_target"
    assert art.submission_source == "approved_verified_target"
    assert art.submission_accepted is True
    assert art.submitted_eq_last_verified is True


def test_typed_finish_recovers_only_full_hash_verified_submission():
    proof = "theorem target : True := by trivial"
    evidence_hash = hashlib.sha256(proof.encode("utf-8")).hexdigest()
    events = [
        _tool_call(2, "check", proof),
        _dict_result(
            3,
            "check",
            {
                "compiled": True,
                "sorry_free": True,
                "verification_status": "accepted",
                "ok": True,
                "evidence_hash": evidence_hash,
                "purpose": "final",
            },
        ),
        _named_call(
            4,
            AgentRole.ENGINEER,
            "submit",
            "submit_subgoal",
            {"subgoal_id": "main", "evidence_hash": evidence_hash},
        ),
        _dict_result(
            5,
            "submit",
            {"ok": True, "submitted": True, "evidence_hash": evidence_hash},
        ),
        _named_call(
            6,
            AgentRole.CRITIC,
            "review",
            "review_lean",
            {"subgoal_id": "main", "code": proof},
        ),
        _dict_result(
            7,
            "review",
            {
                "compiled": True,
                "sorry_free": True,
                "ok": True,
                "evidence_hash": evidence_hash,
                "purpose": "review",
            },
        ),
        _named_call(
            8,
            AgentRole.CRITIC,
            "accept",
            "review_subgoal",
            {"subgoal_id": "main", "decision": "accept", "evidence_hash": evidence_hash},
        ),
        _dict_result(
            9,
            "accept",
            {
                "ok": True,
                "decision": "accept",
                "accepted": True,
                "evidence_hash": evidence_hash,
            },
        ),
        _named_call(
            10,
            AgentRole.CRITIC,
            "finish",
            "finish_run",
            {"final_subgoal_id": "main", "evidence_hash": evidence_hash},
        ),
        _dict_result(
            11,
            "finish",
            {"ok": True, "run_complete": True, "evidence_hash": evidence_hash},
        ),
    ]

    art = extract_artifacts(events, target_statement="theorem target : True")

    assert art.submitted == proof
    assert art.last_verified == proof
    assert art.submission_source == "verified_subgoal_finish"
    assert art.declared_success is True
    assert art.submission_accepted is True
    assert art.submitted_eq_last_verified is True


def test_typed_finish_rejects_incomplete_or_gate_denied_chain():
    proof = "theorem target : True := by trivial"
    evidence_hash = hashlib.sha256(proof.encode("utf-8")).hexdigest()
    events = [
        _tool_call(2, "check", proof),
        _dict_result(
            3,
            "check",
            {
                "compiled": True,
                "sorry_free": True,
                "verification_status": "accepted",
                "ok": False,
                "evidence_hash": evidence_hash,
            },
        ),
        _named_call(
            4,
            AgentRole.CRITIC,
            "finish",
            "finish_run",
            {"final_subgoal_id": "main", "evidence_hash": evidence_hash},
        ),
        _dict_result(
            5,
            "finish",
            {"ok": True, "run_complete": True, "evidence_hash": evidence_hash},
        ),
    ]

    art = extract_artifacts(events, target_statement="theorem target : True")

    assert art.last_verified is None
    assert art.submitted is None
    assert art.submission_accepted is False


def test_approval_before_tool_result_does_not_accept_candidate():
    proof = "theorem target : True := trivial"
    events = [
        _tool_call(2, "c1", proof),
        _critic(3, "approve"),
        _tool_result(4, "c1", True, True),
    ]
    art = extract_artifacts(events, target_statement="theorem target : True")
    assert art.last_verified == proof
    assert art.submitted is None


def test_explicit_submission_after_approval_is_not_accepted_by_critic():
    proof = "theorem target : True := trivial"
    events = [_critic(2, "approve"), _engineer_final(3, proof)]
    art = extract_artifacts(events, target_statement="theorem target : True")
    assert art.declared_success is True
    assert art.submitted == proof
    assert art.submission_accepted is False


def test_approved_statement_drift_is_exposed_not_hidden():
    proof = "theorem target : 1 = 1 := rfl"
    events = [
        _tool_call(2, "c1", proof),
        _tool_result(3, "c1", True, True),
        _critic(7, "approve"),
    ]
    art = extract_artifacts(events, target_statement="theorem target : True")
    assert art.submitted == proof
    assert art.submitted_kind == "statement_drift"


def test_whitespace_around_header_punctuation_is_not_statement_drift():
    target = "theorem target {R :Type*} (x : R) : x = x"
    proof = "theorem target {R : Type*} (x : R) : x = x := rfl"
    assert candidate_kind(proof, target) == "exact_target"


def test_approved_renamed_target_is_retained_as_statement_drift():
    target = "theorem fatem_115_transitive_iff {A : Type} : True"
    renamed = "theorem fatem_115_transitive {A : Type} : True := trivial"
    events = [
        _tool_call(2, "c1", renamed),
        _tool_result(3, "c1", True, True),
        _critic(4, "approve"),
    ]
    art = extract_artifacts(events, target_statement=target)
    assert art.last_verified_kind == "statement_drift"
    assert art.submitted == renamed
    assert art.submission_accepted is True


def test_unrelated_helper_theorem_remains_a_helper():
    helper = "theorem useful_helper : True := trivial"
    assert candidate_kind(helper, "theorem target : True") == "helper_or_probe"


def test_opaque_lean_failure_is_unknown_not_compile_rejection():
    result = _ev(
        3,
        AgentRole.EXECUTOR,
        EventType.EXECUTION_RESULT,
        {
            "tool_responses": [
                {
                    "id": "c1",
                    "content": repr(
                        {
                            "compiled": False,
                            "sorry_free": False,
                            "errors": [],
                            "summary": "lean failed",
                        }
                    ),
                }
            ],
            "text": "lean failed",
        },
    )
    art = extract_artifacts([_tool_call(2, "c1", "bad"), result])
    assert art.tool_calls[0].verification_status == "infrastructure_unknown"
    assert art.tool_calls[0].compiled is None
    assert art.n_failed_compiles == 0


def test_source_placeholder_detection_ignores_comments_and_strings():
    safe = '-- sorry\n#check "admit"\ntheorem target : True := trivial'
    unsafe = "theorem target : True := by admit\n#check sorryAx"
    assert prohibited_placeholders(safe) == ()
    assert prohibited_placeholders(unsafe) == ("admit", "sorryAx")


def test_explicit_final_block_still_primary():
    # When the engineer DOES paste a distinct final block, that stays primary
    # (so a real submitted-vs-verified discrepancy remains detectable).
    verified = "example : True := trivial"
    pasted = "example : True := by trivial"  # different text
    events = [
        _tool_call(2, "c1", verified),
        _tool_result(3, "c1", True, True),
        _engineer_final(4, pasted),
        _critic(5, "approve"),
    ]
    art = extract_artifacts(events)
    assert "by trivial" in art.submitted  # the pasted block, not the verified one
    assert art.submitted_eq_last_verified is False
