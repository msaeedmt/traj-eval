"""Tests for the Lean code extractor (Step 1). Pure, no kernel."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from traj_eval.metrics.lean.extract import (
    Extracted,
    extract_from_event,
    extract_lean_code,
)
from traj_eval.trace_core.schema import AgentRole, EventType, TraceEvent


def _engineer_event(text: str) -> TraceEvent:
    return TraceEvent(
        event_id="e1",
        trial_id="t1",
        seq=1,
        timestamp=datetime.now(UTC),
        event_type=EventType.MESSAGE,
        agent_role=AgentRole.ENGINEER,
        payload={"text": text},
    )


# --- 1. explicit ```lean fences -------------------------------------------


def test_single_lean_block():
    text = (
        "Here is the proof.\n"
        "```lean\n"
        "theorem add_zero_eq (n : Nat) : n + 0 = n := by simp\n"
        "```\n"
        "FINAL: done"
    )
    res = extract_lean_code(text)
    assert res.method == "lean_fence"
    assert res.has_code
    assert "theorem add_zero_eq" in res.code
    assert "FINAL" not in res.code  # marker outside the block isn't captured


def test_lean4_tag_is_accepted():
    text = "```lean4\ndef f := 1\n```"
    res = extract_lean_code(text)
    assert res.method == "lean_fence"
    assert res.code == "def f := 1"


def test_multiple_lean_blocks_concatenated_in_order():
    text = (
        "First the lemma:\n"
        "```lean\nlemma helper : True := trivial\n```\n"
        "Now the theorem:\n"
        "```lean\ntheorem main : True := helper\n```\n"
    )
    res = extract_lean_code(text)
    assert res.method == "lean_fence"
    assert res.code.index("lemma helper") < res.code.index("theorem main")


def test_final_marker_inside_block_is_stripped():
    text = "```lean\ntheorem t : True := trivial\nFINAL: t\n```"
    res = extract_lean_code(text)
    assert "FINAL" not in res.code
    assert res.code == "theorem t : True := trivial"


# --- 2. generic / untagged fences ------------------------------------------


def test_untagged_block_that_looks_like_lean():
    text = "```\ntheorem t (n : Nat) : n = n := rfl\n```"
    res = extract_lean_code(text)
    assert res.method == "generic_fence"
    assert "theorem t" in res.code


def test_untagged_block_that_is_not_lean_is_ignored():
    text = "```\necho hello && ls -la\n```"
    res = extract_lean_code(text)
    assert res.method == "none"
    assert res.code is None


def test_explicit_other_language_tag_is_skipped():
    text = "```python\ndef theorem(): return 1\n```"
    res = extract_lean_code(text)
    # tagged python -> skipped even though body contains the word 'theorem'
    assert res.method == "none"


def test_lean_fence_preferred_over_generic():
    text = (
        "```\ntheorem generic : True := trivial\n```\n"
        "```lean\ntheorem tagged : True := trivial\n```"
    )
    res = extract_lean_code(text)
    assert res.method == "lean_fence"
    assert "tagged" in res.code
    assert "generic" not in res.code


# --- 3. the "no code" outcome (toy arithmetic task) ------------------------


def test_no_code_returns_none_not_raise():
    text = "The 12th Fibonacci number is 144.\nFINAL: 144"
    res = extract_lean_code(text)
    assert res == Extracted(code=None, method="none")
    assert not res.has_code


def test_empty_text():
    assert extract_lean_code("").method == "none"
    assert extract_lean_code(None).method == "none"  # type: ignore[arg-type]


# --- event-level guards -----------------------------------------------------


def test_extract_from_engineer_event():
    ev = _engineer_event("```lean\ntheorem t : True := trivial\n```")
    res = extract_from_event(ev)
    assert res.has_code and "theorem t" in res.code


@pytest.mark.parametrize("role", [AgentRole.PLANNER, AgentRole.CRITIC, AgentRole.SYSTEM])
def test_non_engineer_events_yield_no_code(role):
    ev = TraceEvent(
        event_id="x",
        trial_id="t1",
        seq=2,
        timestamp=datetime.now(UTC),
        event_type=EventType.MESSAGE,
        agent_role=role,
        payload={"text": "```lean\ntheorem t : True := trivial\n```"},
    )
    assert extract_from_event(ev).method == "none"
