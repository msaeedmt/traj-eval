"""Tests for the try_tactic (exact?/apply?) tool. Parsing is tested against the
EXACT message format the live probe returned; no kernel needed (a fake compiler
returns canned warnings)."""

from __future__ import annotations

from dataclasses import dataclass

from traj_eval.tools.lean_tactic import _extract_suggestions, make_try_tactic


@dataclass
class _Msg:
    data: str
    severity: str = "info"


@dataclass
class _Result:
    warnings: list
    errors: list
    compiled: bool = True


class _Compiler:
    def __init__(self, result):
        self._result = result

    def check(self, code):
        return self._result


# The real format from scripts/probe_exact.py:
_REAL = "Try this:\n  [apply] exact Nat.add_comm a b"


def test_extract_real_suggestion():
    got = _extract_suggestions([_Msg(_REAL)])
    assert got == ["exact Nat.add_comm a b"]


def test_extract_strips_bracket_tag():
    got = _extract_suggestions([_Msg("Try this:\n  [rw] rw [foo, bar]")])
    assert got == ["rw [foo, bar]"]


def test_extract_none_when_no_try_this():
    assert _extract_suggestions([_Msg("some unrelated info")]) == []


def test_tool_returns_suggestion():
    comp = _Compiler(_Result(warnings=[_Msg(_REAL)], errors=[]))
    tool = make_try_tactic(comp)
    out = tool("import Mathlib\nexample (a b : Nat) : a + b = b + a := by\n  exact?")
    assert "exact Nat.add_comm a b" in out


def test_tool_requires_exact_marker():
    comp = _Compiler(_Result(warnings=[], errors=[]))
    tool = make_try_tactic(comp)
    out = tool("import Mathlib\nexample : True := trivial")
    assert "No `exact?`" in out


def test_tool_relays_error_when_no_suggestion():
    err = _Msg("unsolved goals", severity="error")
    comp = _Compiler(_Result(warnings=[], errors=[err], compiled=False))
    tool = make_try_tactic(comp)
    out = tool("import Mathlib\nexample : 1 = 2 := by\n  exact?")
    assert "No lemma found" in out
