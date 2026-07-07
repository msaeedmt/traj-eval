"""Deterministic Lean compiler tool for the in-loop engineer (Step 4e).

Wraps LeanInteract's REPL so the engineer can type-check a Lean snippet during a
proof step. The verdict is deterministic: the same ``code`` in always yields the
same result out (a property the whole trace's gradability depends on). The tool
is the IN-LOOP signal only -- it reports the bottom rungs of correctness the
agent needs to iterate:

  * compiled  -- no error-severity message from the kernel;
  * sorry-free -- the REPL's ``sorries`` list is empty;
  * errors    -- error messages with positions and text;
  * sorries   -- each remaining open goal (text + position), useful for the
                 engineer and logged for trajectory analysis.

It deliberately does NOT judge the top rungs -- whether the statement is the
intended one (weakening cheat) or whether the proof rests on a bogus axiom.
Those are faithfulness questions the kernel cannot answer (the probe confirmed a
weakened statement type-checks identically to the real one); they belong to the
offline validator, not a tool the agent could otherwise game.

Statelessness: each ``check`` runs in a FRESH REPL environment. We do not thread
the ``env`` id between calls, so a check is a clean verdict on exactly the code
passed, with no carry-over from a previous call -- this is what makes it
deterministic and independent. (The offline axiom check, a later step, is the
one place that opts into env-threading, because ``#print axioms`` must run in
the env where the theorem was defined.)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class LeanMessage:
    """One diagnostic from the kernel (error or warning) with its position."""

    severity: str
    data: str
    line: int | None = None
    column: int | None = None


@dataclass
class LeanSorry:
    """One remaining open goal left by a ``sorry``, with its position."""

    goal: str
    line: int | None = None
    column: int | None = None


@dataclass
class LeanResult:
    """Structured result of type-checking one Lean snippet.

    ``summary`` is the short human-readable line handed to the agent; the rest
    is the full structured detail, logged in the trace. Both come from the same
    check -- one call, two consumers.
    """

    compiled: bool
    sorry_free: bool
    n_sorries: int
    n_errors: int
    errors: list[LeanMessage] = field(default_factory=list)
    sorries: list[LeanSorry] = field(default_factory=list)
    warnings: list[LeanMessage] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Rich dict the tool returns: summary line + all structured detail."""
        d = asdict(self)
        return d


def _pos(obj: Any) -> tuple[int | None, int | None]:
    """Pull (line, column) from a lean_interact Pos-bearing object, if present."""
    p = getattr(obj, "start_pos", None)
    if p is None:
        return None, None
    return getattr(p, "line", None), getattr(p, "column", None)


def _build_result(response: Any) -> LeanResult:
    """Map a lean_interact CommandResponse onto our LeanResult.

    Pure given a response object, so it is unit-testable against a fake response
    without a live REPL (the kernel-free half of Step 4e).
    """
    raw_messages = list(getattr(response, "messages", None) or [])
    raw_sorries = list(getattr(response, "sorries", None) or [])

    errors: list[LeanMessage] = []
    warnings: list[LeanMessage] = []
    for m in raw_messages:
        line, col = _pos(m)
        lm = LeanMessage(
            severity=getattr(m, "severity", "") or "",
            data=getattr(m, "data", "") or "",
            line=line,
            column=col,
        )
        if lm.severity == "error":
            errors.append(lm)
        else:
            warnings.append(lm)

    sorries: list[LeanSorry] = []
    for s in raw_sorries:
        line, col = _pos(s)
        sorries.append(LeanSorry(goal=getattr(s, "goal", "") or "", line=line, column=col))

    compiled = len(errors) == 0
    sorry_free = len(sorries) == 0
    n_errors = len(errors)
    n_sorries = len(sorries)

    # Short readable summary for the agent.
    if not compiled:
        first = errors[0]
        loc = f" at line {first.line}" if first.line is not None else ""
        head = first.data.splitlines()[0] if first.data else "error"
        summary = f"compiled: false; errors: {n_errors}; first error{loc}: {head}"
    elif not sorry_free:
        summary = f"compiled: true; sorries: {n_sorries} (proof incomplete); errors: 0"
    else:
        summary = "compiled: true; sorries: 0; errors: 0"

    return LeanResult(
        compiled=compiled,
        sorry_free=sorry_free,
        n_sorries=n_sorries,
        n_errors=n_errors,
        errors=errors,
        sorries=sorries,
        warnings=warnings,
        summary=summary,
    )


class LeanCompiler:
    """Holds a LeanInteract server (created once) and checks snippets.

    The server is expensive to start, so build ONE LeanCompiler per run and
    reuse it across tool calls. ``project_dir`` points at a built Lean project
    (e.g. ~/lean_anchor) so ``import Mathlib`` resolves against its cache.
    """

    def __init__(self, project_dir: str | Path, *, timeout: int = 120) -> None:
        # Imported lazily so the rest of the package (and its tests) does not
        # require lean_interact or a Lean toolchain to be installed.
        from lean_interact import AutoLeanServer, LeanREPLConfig, LocalProject

        self._timeout = timeout
        config = LeanREPLConfig(project=LocalProject(directory=str(project_dir)))
        # AutoLeanServer recovers from crashes/timeouts -- safer across many
        # trials than the bare LeanServer.
        self._server = AutoLeanServer(config)

    def check(self, code: str) -> LeanResult:
        """Type-check ``code`` in a fresh env; return the structured result."""
        from lean_interact import Command

        response = self._server.run(Command(cmd=code), timeout=self._timeout)
        return _build_result(response)

    def as_tool(self):
        """Return the function to register with AG2 (rich dict for the agent).

        The returned closure is what ``build_stepped_team(lean_tool=...)``
        registers. It hands the agent the full dict (summary + detail); AG2
        serialises it into the tool-response message, which the observer logs as
        an EXECUTION_RESULT. The docstring/annotation drive the tool schema the
        LLM sees, so they are written for the engineer, not for us.
        """

        def check_lean(code: str) -> dict[str, Any]:
            """Type-check Lean 4 source. Returns compile status, errors, and any
            remaining `sorry` goals. Call this before declaring a proof done.

            Args:
                code: Lean 4 source to check (include needed imports).
            """
            return self.check(code).to_dict()

        return check_lean
