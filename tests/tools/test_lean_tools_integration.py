from __future__ import annotations

import os
from pathlib import Path

import pytest

from traj_eval.tools.lean_cli_compiler import LeanCliCompiler
from traj_eval.tools.lean_goals import make_show_goals
from traj_eval.tools.lean_tactic import make_try_tactic

PROJECT = Path(os.environ.get("TRAJ_EVAL_LEAN_PROJECT", "dataset/Lean"))
pytestmark = pytest.mark.skipif(
    not (PROJECT / ".lake").is_dir(),
    reason="real Lean project artifacts are not configured",
)


@pytest.fixture(scope="module")
def compiler() -> LeanCliCompiler:
    return LeanCliCompiler(PROJECT, timeout=120)


def test_real_lean_stdin_accepts_valid_and_rejects_invalid(compiler):
    valid = compiler.check("import Mathlib\nexample : True := by trivial")
    invalid = compiler.check("import Mathlib\nexample : True := by exact False.elim")

    assert valid.compiled is True and valid.sorry_free is True
    assert invalid.compiled is False


def test_real_try_tactic_returns_nat_add_comm(compiler):
    output = make_try_tactic(compiler)(
        "import Mathlib\nexample (a b : Nat) : a + b = b + a := by\n  exact?"
    )

    assert "Nat.add_comm" in output


def test_real_show_goals_displays_hypothesis_and_target(compiler):
    output = make_show_goals(compiler)(
        "import Mathlib\nexample (p q : Prop) (h : p ∧ q) : q := by\n  sorry"
    )

    assert "h : p ∧ q" in output
    assert "⊢ q" in output
    assert "Do not treat this proof as complete" not in output


def test_real_show_goals_rejects_malformed_skeleton(compiler):
    output = make_show_goals(compiler)(
        "import Mathlib\nexample : True := by\n  exact\n  sorry"
    )

    assert "does not compile" in output


def test_real_show_goals_never_calls_unresolved_sorry_complete(compiler):
    output = make_show_goals(compiler)(
        "import Mathlib\nexample : True := by\n  sorry"
    )

    assert "No open goals" not in output
    assert "open goal" in output
