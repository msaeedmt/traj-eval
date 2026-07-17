"""Inspect tactic-mode Lean goals through the shared kernel-backed compiler."""

from __future__ import annotations


def _instrument_sorries(code: str) -> tuple[str, int]:
    """Insert ``trace_state`` before standalone tactic-mode ``sorry`` lines."""
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
    """Extract ordered ``trace_state`` blocks ending at their turnstile line."""
    data = "\n".join((getattr(warning, "data", "") or "") for warning in warnings)
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
    """Build an Engineer tool that reports hypotheses and targets at ``sorry``."""

    def show_goals(code: str) -> str:
        """Show the Lean proof state at each tactic-mode ``sorry``.

        Args:
            code: Complete Lean source with ``sorry`` only at currently open
                goals. This tool inspects goals; it does not verify completion.
        """
        if "sorry" not in code:
            return (
                "No `sorry` is present. show_goals is NOT a verifier; call "
                "check_lean for a proof you believe is complete."
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
                "Do not treat this proof as complete."
            )

        if not result.compiled:
            first = result.errors[0] if result.errors else None
            location = f" (line {first.line})" if first and first.line is not None else ""
            diagnostic = (
                first.data.splitlines()[0]
                if first and first.data
                else "Lean rejected the proof skeleton without a diagnostic"
            )
            return (
                f"The proof skeleton does not compile{location}: {diagnostic}\n"
                "Fix the structural error before inspecting open goals."
            )

        goal_states = [
            (sorry.goal or "<goal state unavailable>", sorry.line)
            for sorry in result.sorries
        ]
        if not goal_states and getattr(result, "n_sorries", 0):
            goal_states = [
                (goal, None)
                for goal in _extract_traced_goals(result.warnings, marker_count)
            ]
        if not goal_states and getattr(result, "n_sorries", 0):
            return (
                "Lean reports unresolved `sorry` goals, but their states are "
                "unavailable. Do not treat this proof as complete."
            )
        if not goal_states:
            return "No open goals: the proof compiles with no `sorry`. It is complete."

        lines = [f"{len(goal_states)} open goal(s):"]
        for index, (goal, line) in enumerate(goal_states, 1):
            location = f" (line {line})" if line is not None else ""
            lines.extend([f"\n── goal {index}{location} ──", goal])
        lines.append("\nProve each goal, then verify the completed proof with check_lean.")
        return "\n".join(lines)

    return show_goals
