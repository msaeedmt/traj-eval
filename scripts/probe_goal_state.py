"""Probe: what does the proof/goal state look like in response.sorries?

Same discipline as probe_exact / probe_leansearch: hit the REAL compiler and
print exactly what comes back, so the goal-inspection tool is built against
reality, not a guess about lean_interact's internals.

We do NOT guess the shape of a sorry's `goal` field. We feed the compiler
snippets with `sorry` at known goal positions and print, verbatim, every
LeanSorry (goal text + position) and the raw response.sorries objects behind
them, so we can see:

  * Is `goal` the full turnstile form (`h : P ⊢ Q`) or just the target `Q`?
  * Does a snippet with N open goals yield N sorries or one blob?
  * Does it survive our Mathlib pin (Lean 4.32.0)?
  * What extra attrs does the raw sorry object carry (proofState id? etc.)

Run:  uv run python scripts/probe_goal_state.py
"""

from __future__ import annotations

from pathlib import Path

from traj_eval.tools.lean_compiler import LeanCompiler

PROJECT_DIR = Path.home() / "lean_anchor"

# Each probe is (label, code). Chosen to exercise the cases the tool must handle.
PROBES: list[tuple[str, str]] = [
    # 1. Single open goal after an intro: does the hypothesis show in context?
    (
        "single goal, one hyp in context",
        "import Mathlib\n"
        "example (p q : Prop) (h : p ∧ q) : q := by\n"
        "  obtain ⟨hp, hq⟩ := h\n"
        "  sorry",
    ),
    # 2. Two open goals (constructor on an And): one sorry or two?
    (
        "two open goals after constructor",
        "import Mathlib\n"
        "example (p q : Prop) (hp : p) (hq : q) : p ∧ q := by\n"
        "  constructor\n"
        "  · sorry\n"
        "  · sorry",
    ),
    # 3. The fatem_019 shape: an iff, sketch both directions with sorry.
    (
        "iff sketch, both directions sorry (fatem_019 shape)",
        "import Mathlib\n"
        "example (n : ℕ) : IsField (ZMod n) ↔ Nat.Prime n := by\n"
        "  constructor\n"
        "  · intro h\n"
        "    sorry\n"
        "  · intro h\n"
        "    sorry",
    ),
    # 4. Mid-proof after a rewrite: goal after progress, not at the start.
    (
        "goal after a rewrite step",
        "import Mathlib\n"
        "example (a b : Nat) : a + b = b + a := by\n"
        "  rw [Nat.add_comm]\n"
        "  sorry",
    ),
    # 5. A metavariable / dependent goal, to see how context is rendered.
    (
        "existential goal",
        "import Mathlib\n" "example : ∃ n : Nat, n > 3 := by\n" "  sorry",
    ),
]


def main() -> int:
    print(f"Starting REAL Lean compiler against {PROJECT_DIR} (first run slow)...")
    compiler = LeanCompiler(PROJECT_DIR)
    print("Compiler ready.\n")

    for label, code in PROBES:
        print("=" * 70)
        print(f"PROBE: {label}")
        print("-" * 70)
        print(code)
        print("---- result ----")
        result = compiler.check(code)
        print(
            f"compiled={result.compiled}  n_sorries={result.n_sorries}  "
            f"n_errors={result.n_errors}"
        )
        if result.errors:
            print("  errors:")
            for e in result.errors:
                print(f"    [{e.line}:{e.column}] {e.data.splitlines()[0] if e.data else ''}")
        print(f"  sorries ({len(result.sorries)}):")
        for i, s in enumerate(result.sorries):
            print(f"    --- sorry #{i} at line {s.line}, col {s.column} ---")
            # Print the goal verbatim, indented, so we can SEE its exact shape.
            for ln in (s.goal or "<empty>").splitlines() or ["<empty>"]:
                print(f"      | {ln}")
        print()

    # Also crack open ONE raw response so we see attrs beyond what _build_result
    # keeps -- e.g. whether a sorry carries a proofState id we could thread.
    print("=" * 70)
    print("RAW response.sorries object attrs (probe #1):")
    print("-" * 70)
    from lean_interact import Command  # noqa: PLC0415

    resp = compiler._server.run(Command(cmd=PROBES[0][1]), timeout=120)
    raw = list(getattr(resp, "sorries", None) or [])
    print(f"  response has {len(raw)} raw sorry object(s)")
    for i, s in enumerate(raw):
        attrs = [a for a in dir(s) if not a.startswith("_")]
        print(f"  sorry[{i}] type={type(s).__name__} attrs={attrs}")
        for a in attrs:
            try:
                v = getattr(s, a)
            except Exception:  # noqa: BLE001
                continue
            if callable(v):
                continue
            sval = str(v).replace("\n", "\\n")
            print(f"      {a} = {sval[:120]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
