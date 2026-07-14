"""Goal-state inspection via `sorry` (the show_goals tool).

The engineer's dominant failure (see fatem_019) is proving BLIND: it composes a
whole term-mode proof, guesses each subterm's type, and fails globally with no
foothold. It never SEES the goal it must close, so it misapplies correctly-
retrieved lemmas (e.g. ZMod.instField's Fact-instance argument) and never makes
partial progress.

This tool makes the goal visible. The engineer writes its proof in TACTIC mode
(`by ...`), does whatever partial work it can, and places `sorry` wherever it is
stuck. The tool returns the proof state at each `sorry`: the hypotheses in
context and the target still to prove. This turns "guess the whole proof" into
"look at what remains, then supply exactly that", and it makes incremental
proving natural -- discharge the easy branch, `sorry` the hard one, inspect the
hard one alone.

It reuses LeanCompiler.check unchanged: a `sorry`-bearing snippet compiles (with
a warning), and the REPL reports each open goal in `response.sorries`, which the
wrapper already surfaces as LeanSorry(goal, line, column). So this tool does NOT
touch lean_interact -- it re-frames the goal state the compiler already
computes into an actionable, engineer-facing message. (Contrast check_lean,
which reports the same sorries as "proof incomplete" -- a failure signal, not a
next-step signal.)

Pairs with try_tactic: use show_goals to SEE the goal, then exact?/apply? (via
try_tactic) to find the lemma that closes it. show_goals answers "what do I need
to prove here?"; try_tactic answers "what closes it?".
"""

from __future__ import annotations


def make_show_goals(compiler):
    """Return the show_goals tool. ``compiler`` is a LeanCompiler (or anything
    exposing ``check(code) -> LeanResult`` with a ``.sorries`` list of objects
    carrying ``.goal``, ``.line``, ``.column``)."""

    def show_goals(code: str) -> str:
        """Show the Lean proof state (hypotheses and goal) at each `sorry`.

        Write your proof in tactic mode (`by ...`), do as much as you can, and
        put `sorry` at every goal you are still stuck on. This returns the
        proof state at each `sorry`: the hypotheses currently in context and the
        target you still need to prove. Use it to SEE what remains before
        writing more -- prove the parts you can, `sorry` the rest, and inspect
        the hard goal in isolation instead of guessing the whole proof at once.

        Put `sorry` ONLY at goals that are still open: a `sorry` after a tactic
        that already closed its goal is an error ("No goals to be solved"), not
        an inspection. If a branch is done, drop its `sorry`.

        Args:
            code: Lean 4 source including `import Mathlib`, written in tactic
                mode with `sorry` at each goal you want to inspect.
        """
        if "sorry" not in code:
            return (
                "No `sorry` in this code, so there is no open goal to inspect. "
                "show_goals is NOT a verifier -- do not call it on a finished "
                "proof. If you believe this proof is complete, call check_lean to "
                "verify it. If check_lean reports an error at some goal, put "
                "`sorry` at THAT goal and call show_goals to see what remains "
                "there. Do not re-call show_goals on code with no `sorry`."
            )

        result = compiler.check(code)

        # A real error (not just the sorry warning) means the skeleton itself
        # does not elaborate -- the engineer must fix that before any goal state
        # exists to show. Relay the first error so it knows what broke.
        if not result.compiled:
            first = result.errors[0]
            loc = f" (line {first.line})" if first.line is not None else ""
            head = first.data.splitlines()[0] if first.data else "error"
            return (
                f"The proof skeleton does not compile{loc}: {head}\n"
                "Fix this structural error first; there is no goal state to show "
                "until the skeleton elaborates. (Common cause: Lean 3 syntax like "
                "`begin`/`end` -- use `by` and newline-separated tactics.)"
            )

        if not result.sorries:
            return "No open goals: the proof compiles with no `sorry`. It is complete."

        # One block per open goal. `s.goal` is the proof state string the REPL
        # reports. PROBE-DEPENDENT: if the probe shows `goal` is the full
        # turnstile (`h : P ⊢ Q`), print it verbatim (below). If it shows only
        # the target with no context, we would instead need proofState threading
        # to recover hypotheses -- the probe's raw-attr dump tells us which.
        lines: list[str] = [f"{len(result.sorries)} open goal(s):"]
        for i, s in enumerate(result.sorries, 1):
            loc = f" (line {s.line})" if s.line is not None else ""
            lines.append(f"\n── goal {i}{loc} ──")
            lines.append(s.goal or "<goal state unavailable>")
        lines.append(
            "\nProve each goal above. Discharge the ones you can; keep `sorry` "
            "only where still stuck, and inspect that goal alone."
        )
        return "\n".join(lines)

    return show_goals
