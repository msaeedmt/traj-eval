from __future__ import annotations

from dataclasses import dataclass

from traj_eval.tools.lean_tactic import _extract_suggestions, make_try_tactic


@dataclass
class _Message:
    data: str


@dataclass
class _Result:
    warnings: list
    errors: list
    compiled: bool = True


class _Compiler:
    def __init__(self, result):
        self.result = result

    def check(self, code):
        return self.result


def test_extracts_real_exact_suggestion():
    message = _Message("Try this:\n  [apply] exact Nat.add_comm a b")
    assert _extract_suggestions([message]) == ["exact Nat.add_comm a b"]


def test_tool_returns_suggestion():
    result = _Result([_Message("Try this:\n  [apply] exact Nat.add_comm a b")], [])
    tool = make_try_tactic(_Compiler(result))

    output = tool("import Mathlib\nexample (a b : Nat) : a + b = b + a := by\n  exact?")

    assert "exact Nat.add_comm a b" in output


def test_tool_requires_search_hole():
    tool = make_try_tactic(_Compiler(_Result([], [])))
    assert "No `exact?`" in tool("example : True := by trivial")
