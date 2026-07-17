"""Goal-directed Lean tactic suggestions backed by ``exact?`` / ``apply?``."""

from __future__ import annotations

import re

_TRY_THIS = re.compile(r"Try this:", re.IGNORECASE)
_TAG = re.compile(r"^\s*\[[^\]]*\]\s*")


def _extract_suggestions(warnings) -> list[str]:
    """Return ready-to-paste tactics from Lean's ``Try this:`` messages."""
    suggestions: list[str] = []
    for warning in warnings:
        data = getattr(warning, "data", "") or ""
        if not _TRY_THIS.search(data):
            continue
        after_header = False
        for line in data.splitlines():
            if _TRY_THIS.search(line):
                after_header = True
                continue
            if after_header and line.strip():
                suggestions.append(_TAG.sub("", line.strip()))
    return suggestions


def make_try_tactic(compiler):
    """Build an Engineer tool that runs tactic search through the shared compiler."""

    def try_tactic(code: str) -> str:
        """Run Lean tactic search at an ``exact?`` or ``apply?`` hole.

        Args:
            code: Complete Lean source with ``exact?`` or ``apply?`` at the
                concrete goal that needs a closing lemma.
        """
        if "exact?" not in code and "apply?" not in code:
            return (
                "No `exact?`/`apply?` found. Put one at the concrete open goal "
                "and call try_tactic again."
            )

        result = compiler.check(code)
        if getattr(result, "verification_status", None) == "infrastructure_unknown":
            detail = (
                getattr(result, "infrastructure_error", None)
                or getattr(result, "summary", None)
                or "Lean validation was unavailable"
            )
            return (
                f"Lean infrastructure could not run tactic search: {detail}. "
                "This is not evidence that no lemma exists."
            )

        suggestions = list(dict.fromkeys(_extract_suggestions(result.warnings)))
        if suggestions:
            body = "\n".join(f"  {suggestion}" for suggestion in suggestions[:5])
            return f"exact?/apply? suggests:\n{body}\nPaste the tactic in place of the hole."

        if not result.compiled and result.errors:
            first = result.errors[0].data.splitlines()[0] or "error"
            return f"No lemma found to close the goal. Lean says: {first}"
        return "No single-lemma suggestion found; try a different proof step."

    return try_tactic
