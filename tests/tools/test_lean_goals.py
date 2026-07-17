"""Tests for the goal-state presentation contract used by show_goals."""

from __future__ import annotations

from dataclasses import dataclass, field

from traj_eval.tools.lean_goals import make_show_goals
from traj_eval.tools.lean_tactic import make_try_tactic


@dataclass
class _Msg:
    data: str
    line: int | None = None


@dataclass
class _Sorry:
    goal: str
    line: int | None = None
    column: int | None = None


@dataclass
class _Result:
    compiled: bool = True
    n_sorries: int = 0
    sorries: list[_Sorry] = field(default_factory=list)
    errors: list[_Msg] = field(default_factory=list)
    warnings: list[_Msg] = field(default_factory=list)
    verification_status: str | None = None
    infrastructure_error: str | None = None
    summary: str = ""


class _Compiler:
    def __init__(self, result: _Result):
        self.result = result
        self.calls = 0

    def check(self, code: str) -> _Result:
        self.calls += 1
        return self.result


def test_show_goals_displays_context_and_target():
    compiler = _Compiler(
        _Result(
            n_sorries=1,
            sorries=[_Sorry("p q : Prop\nh : p ∧ q\n⊢ q", line=4)],
        )
    )

    out = make_show_goals(compiler)("example (p q : Prop) (h : p ∧ q) : q := by\n  sorry")

    assert "1 open goal" in out
    assert "h : p ∧ q" in out
    assert "⊢ q" in out


def test_show_goals_relays_malformed_skeleton_error():
    compiler = _Compiler(
        _Result(compiled=False, errors=[_Msg("unexpected token 'end'", line=3)])
    )

    out = make_show_goals(compiler)("example : True := by\n  end\n  sorry")

    assert "does not compile (line 3)" in out
    assert "unexpected token" in out


def test_show_goals_handles_rejection_without_error_payload():
    compiler = _Compiler(_Result(compiled=False))

    out = make_show_goals(compiler)("example : True := by\n  sorry")

    assert "without a diagnostic" in out


def test_show_goals_reports_infrastructure_unknown_without_false_completion():
    compiler = _Compiler(
        _Result(
            compiled=False,
            verification_status="infrastructure_unknown",
            infrastructure_error="lean timed out after 7s",
        )
    )

    out = make_show_goals(compiler)("example : True := by\n  sorry")

    assert "infrastructure could not inspect" in out
    assert "timed out" in out
    assert "Do not treat this proof as complete" in out


def test_show_goals_never_false_completes_when_goal_payload_is_missing():
    compiler = _Compiler(_Result(n_sorries=1, sorries=[]))

    out = make_show_goals(compiler)("example : True := by\n  sorry")

    assert "unresolved `sorry` goals" in out
    assert "Do not treat this proof as complete" in out


def test_show_goals_uses_traced_cli_goal_state():
    compiler = _Compiler(
        _Result(
            n_sorries=1,
            warnings=[
                _Msg(
                    "p q : Prop\nh : p ∧ q\n⊢ q\n"
                    "<stdin>:5:2: warning: declaration uses 'sorry'"
                )
            ],
        )
    )

    out = make_show_goals(compiler)("example (p q : Prop) (h : p ∧ q) : q := by\n  sorry")

    assert "h : p ∧ q" in out
    assert "⊢ q" in out


def test_show_goals_splits_multiple_traced_states():
    compiler = _Compiler(
        _Result(
            n_sorries=2,
            warnings=[
                _Msg(
                    "p q : Prop\nhp : p\nhq : q\n⊢ p\n"
                    "p q : Prop\nhp : p\nhq : q\n⊢ q\n"
                    "<stdin>:8:2: warning: declaration uses 'sorry'"
                )
            ],
        )
    )

    out = make_show_goals(compiler)(
        "example (p q : Prop) (hp : p) (hq : q) : p ∧ q := by\n"
        "  constructor\n  · sorry\n  · sorry"
    )

    assert "2 open goal" in out
    assert "⊢ p" in out
    assert "⊢ q" in out


def test_show_goals_without_sorry_is_not_a_verifier():
    compiler = _Compiler(_Result())

    out = make_show_goals(compiler)("example : True := by\n  trivial")

    assert "NOT a verifier" in out
    assert compiler.calls == 0


def test_try_tactic_reports_infrastructure_unknown_not_missing_lemma():
    compiler = _Compiler(
        _Result(
            compiled=False,
            verification_status="infrastructure_unknown",
            infrastructure_error="lean timed out after 7s",
        )
    )

    out = make_try_tactic(compiler)(
        "import Mathlib\nexample (a b : Nat) : a + b = b + a := by\n  exact?"
    )

    assert "infrastructure could not run tactic search" in out
    assert "timed out" in out
    assert "not evidence that no lemma exists" in out
