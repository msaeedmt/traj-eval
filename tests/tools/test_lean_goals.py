from __future__ import annotations

from dataclasses import dataclass, field

from traj_eval.tools.lean_goals import make_show_goals


@dataclass
class _Message:
    data: str
    line: int | None = None


@dataclass
class _Sorry:
    goal: str
    line: int | None = None


@dataclass
class _Result:
    compiled: bool = True
    n_sorries: int = 0
    sorries: list[_Sorry] = field(default_factory=list)
    errors: list[_Message] = field(default_factory=list)
    warnings: list[_Message] = field(default_factory=list)
    verification_status: str | None = None
    infrastructure_error: str | None = None
    summary: str = ""


class _Compiler:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def check(self, code):
        self.calls += 1
        return self.result


def test_displays_context_and_target():
    compiler = _Compiler(
        _Result(n_sorries=1, sorries=[_Sorry("p q : Prop\nh : p ∧ q\n⊢ q", 4)])
    )

    output = make_show_goals(compiler)(
        "example (p q : Prop) (h : p ∧ q) : q := by\n  sorry"
    )

    assert "h : p ∧ q" in output
    assert "⊢ q" in output


def test_relays_malformed_skeleton_error():
    compiler = _Compiler(_Result(compiled=False, errors=[_Message("unexpected token", 3)]))
    output = make_show_goals(compiler)("example : True := by\n  end\n  sorry")
    assert "does not compile (line 3)" in output


def test_never_false_completes_missing_goal_payload():
    compiler = _Compiler(_Result(n_sorries=1))
    output = make_show_goals(compiler)("example : True := by\n  sorry")
    assert "unresolved `sorry` goals" in output
    assert "Do not treat this proof as complete" in output


def test_without_sorry_is_not_verifier():
    compiler = _Compiler(_Result())
    output = make_show_goals(compiler)("example : True := by\n  trivial")
    assert "NOT a verifier" in output
    assert compiler.calls == 0
