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

It reuses the run's existing compiler boundary. When structured sorry goals are
available, it presents them directly. With the CLI compiler, it inserts
`trace_state` in memory and extracts the kernel's printed goal states. It does
not create project files or add a second Lean runtime. (Contrast check_lean,
which reports sorries as "proof incomplete" -- a failure signal, not a
next-step signal.)

Pairs with try_tactic: use show_goals to SEE the goal, then exact?/apply? (via
try_tactic) to find the lemma that closes it. show_goals answers "what do I need
to prove here?"; try_tactic answers "what closes it?".
"""

from __future__ import annotations


def _instrument_sorries(code: str) -> tuple[str, int]:
    """Insert `trace_state` before standalone tactic-mode `sorry` lines."""
    lines: list[str] = []
    count = 0
    for line in code.splitlines():
        stripped = line.strip()
        if stripped in {"sorry", "· sorry"}:
            count += 1
            indent = line[: len(line) - len(line.lstrip())]
            if stripped == "· sorry":
                lines.extend([f"{indent}· trace_state", f"{indent}  sorry"])
                continue
            lines.append(f"{indent}trace_state")
        lines.append(line)
    return "\n".join(lines), count


def _extract_traced_goals(warnings, count: int) -> list[str]:
    """Extract ordered trace_state blocks, each ending at its turnstile line."""
    data = "\n".join((getattr(w, "data", "") or "") for w in warnings)
    goals: list[str] = []
    block: list[str] = []
    for line in data.splitlines():
        if line.startswith("<stdin>:"):
            break
        if not line.strip():
            continue
        block.append(line)
        if line.lstrip().startswith("⊢"):
            goals.append("\n".join(block))
            block = []
            if len(goals) == count:
                break
    return goals


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

        instrumented, marker_count = _instrument_sorries(code)
        result = compiler.check(instrumented)

        if getattr(result, "verification_status", None) == "infrastructure_unknown":
            detail = (
                getattr(result, "infrastructure_error", None)
                or getattr(result, "summary", None)
                or "Lean validation was unavailable"
            )
            return (
                f"Lean infrastructure could not inspect the goals: {detail}. "
                "Do not treat this proof as complete; retry after the validator "
                "is available."
            )

        # A real error (not just the sorry warning) means the skeleton itself
        # does not elaborate -- the engineer must fix that before any goal state
        # exists to show. Relay the first error so it knows what broke.
        if not result.compiled:
            first = result.errors[0] if result.errors else None
            loc = f" (line {first.line})" if first and first.line is not None else ""
            head = (
                first.data.splitlines()[0]
                if first and first.data
                else "Lean rejected the proof skeleton without a diagnostic"
            )
            return (
                f"The proof skeleton does not compile{loc}: {head}\n"
                "Fix this structural error first; there is no goal state to show "
                "until the skeleton elaborates. (Common cause: Lean 3 syntax like "
                "`begin`/`end` -- use `by` and newline-separated tactics.)"
            )

        goal_states = [
            (s.goal or "<goal state unavailable>", s.line) for s in result.sorries
        ]
        if not goal_states and getattr(result, "n_sorries", 0):
            goal_states = [
                (goal, None)
                for goal in _extract_traced_goals(result.warnings, marker_count)
            ]

        if not goal_states and getattr(result, "n_sorries", 0):
            return (
                "Lean reports unresolved `sorry` goals, but structured goal "
                "states are unavailable. Do not treat this proof as complete; "
                "put each tactic-mode `sorry` on its own line and try again, or "
                "call check_lean."
            )

        if not goal_states:
            return "No open goals: the proof compiles with no `sorry`. It is complete."

        # One block per open goal. `s.goal` is the proof state string the REPL
        # reports. PROBE-DEPENDENT: if the probe shows `goal` is the full
        # turnstile (`h : P ⊢ Q`), print it verbatim (below). If it shows only
        # the target with no context, we would instead need proofState threading
        # to recover hypotheses -- the probe's raw-attr dump tells us which.
        lines: list[str] = [f"{len(goal_states)} open goal(s):"]
        for i, (goal, line) in enumerate(goal_states, 1):
            loc = f" (line {line})" if line is not None else ""
            lines.append(f"\n── goal {i}{loc} ──")
            lines.append(goal)
        lines.append(
            "\nProve each goal above. Discharge the ones you can; keep `sorry` "
            "only where still stuck, and inspect that goal alone."
        )
        return "\n".join(lines)

    return show_goals
