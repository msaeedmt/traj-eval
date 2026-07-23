"""Goal-directed tactic search via Lean's `exact?` / `apply?` (Step: try_tactic).

Unlike search_lemmas (semantic TEXT search over lemma descriptions, goal-free),
this is GOAL-DIRECTED: the engineer submits a proof with `exact?` (or `apply?`)
at the goal it is stuck on, and Lean searches its library for a term that
actually CLOSES that goal, returning a concrete tactic. Because it is grounded
in the real goal state, it does not suffer the reword-loop that plagues text
search (the engineer re-issuing near-identical search_lemmas queries).

Contract (confirmed against the live Lean kernel): `exact?`
emits a single info-severity message of the form

    Try this:
      [apply] exact <term>

The suggestion is the line after "Try this:", with the leading "[apply]" (or
similar bracket tag) stripped -> a ready-to-paste tactic like "exact Nat.add_comm a b".
When no term is found, `exact?` reports an error instead and we return a
"no suggestion" message. Note (honest caveat): `exact?` sometimes returns a
correct-but-ugly term rather than the cleanest one -- it guarantees closure, not
elegance.

The tool reuses the run's existing compiler boundary; it parses the suggestion
out of the compiler messages rather than reading only a pass/fail verdict.
"""

from __future__ import annotations

import re

# The suggestion line looks like "  [apply] exact foo" or "  [rw] rw [foo]".
# Strip an optional leading "[tag]" then keep the tactic.
_TRY_THIS = re.compile(r"Try this:", re.IGNORECASE)
_TAG = re.compile(r"^\s*\[[^\]]*\]\s*")


def _extract_suggestions(warnings) -> list[str]:
    """Pull suggested tactics from the compiler warnings (where info messages
    land). Each `Try this:` block's following non-empty lines are suggestions."""
    out: list[str] = []
    for w in warnings:
        data = getattr(w, "data", "") or ""
        if not _TRY_THIS.search(data):
            continue
        lines = data.splitlines()
        # collect lines after the "Try this:" line
        started = False
        for ln in lines:
            if _TRY_THIS.search(ln):
                started = True
                continue
            if started and ln.strip():
                out.append(_TAG.sub("", ln.strip()))
    return out


def make_try_tactic(compiler):
    """Return the try_tactic tool. ``compiler`` is a LeanCompiler (or anything
    with a ``check(code) -> LeanResult`` method exposing ``.warnings``)."""

    def try_tactic(code: str) -> str:
        """Ask Lean to find a lemma that closes the current goal, using its
        built-in `exact?` tactic search. Provide your Lean proof with `exact?`
        (or `apply?`) written at the goal you are stuck on; this returns a
        concrete tactic (e.g. `exact Nat.add_comm a b`) that closes it, if one
        exists. Prefer this over search_lemmas when you already have a formalised
        goal and just need the lemma that finishes it.

        Args:
            code: Lean source including `import Mathlib` and your proof with
                `exact?` or `apply?` placed at the stuck goal.
        """
        if "exact?" not in code and "apply?" not in code:
            return (
                "No `exact?`/`apply?` found in the code. Put `exact?` at the goal "
                "you are stuck on, then call this tool."
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
                "This is not evidence that no lemma exists; retry "
                "after the validator is available."
            )
        suggestions = _extract_suggestions(result.warnings)
        if suggestions:
            uniq = list(dict.fromkeys(suggestions))  # dedupe, keep order
            body = "\n".join(f"  {s}" for s in uniq[:5])
            return f"exact?/apply? suggests:\n{body}\nPaste the tactic in place of `exact?`."
        # no suggestion: relay the compiler's own message so the agent learns why
        if not result.compiled and result.errors:
            first = result.errors[0].data.splitlines()[0] if result.errors[0].data else "error"
            return f"No lemma found to close the goal. Lean says: {first}"
        return (
            "No suggestion found. The goal may not be closable by a single "
            "lemma; try a different approach."
        )

    return try_tactic
