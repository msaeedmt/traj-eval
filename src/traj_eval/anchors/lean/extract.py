"""Extract Lean source from an engineer event's message text (Step 1).

The anchor pass replays the engineer's Lean code through the kernel, but the
observer logs an engineer turn as a MESSAGE event whose ``payload["text"]`` is
the agent's *whole* reply -- prose, a fenced code block, the FINAL marker, all
mixed together. This module is the one place that turns that free text into a
clean Lean source string (or reports that the step contained no code).

It is deliberately pure: no kernel, no I/O, no schema mutation. It takes the
text (or an event) and returns an ``Extracted`` result. That keeps the brittle
part -- LLMs format messages inconsistently -- isolated and unit-testable on
its own, separate from everything the kernel touches downstream.

Extraction strategy, in priority order:
  1. Fenced ```lean ... ``` blocks. The canonical case once the Lean role
     prompts are in use. If several appear, they are concatenated in order
     (a step may show a lemma then the theorem that uses it).
  2. A generic fenced ``` ... ``` block with no language tag, but only if its
     body *looks* like Lean (contains a Lean declaration keyword). This catches
     engineers that drop the ``lean`` tag without scooping up, say, a stray
     shell snippet.
  3. Nothing -> ``Extracted(code=None, ...)``. A step with no code is a normal
     outcome (e.g. a planning-ish engineer turn, or the toy arithmetic task
     that emits ``FINAL: <number>`` and no code). Callers decide what an empty
     step means for anchoring; this module never raises on "no code".

The FINAL: marker (markers.FINAL) is stripped if it lands inside a block, and
used only as a fallback boundary, never as code itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from traj_eval.trace_core.schema import AgentRole, EventType, TraceEvent

# Lean declaration keywords -- enough to tell "this generic block is Lean" from
# "this is a bash snippet". Kept small and conservative on purpose.
_LEAN_DECL_KEYWORDS = (
    "theorem",
    "lemma",
    "def",
    "example",
    "instance",
    "structure",
    "inductive",
    "abbrev",
)

# A fenced block whose info-string starts with `lean` (```lean, ```lean4).
_LEAN_FENCE_RE = re.compile(
    r"```[ \t]*lean[0-9]*[ \t]*\r?\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)

# Any fenced block, capturing the info-string and the body separately, so we
# can decide whether an untagged block looks like Lean.
_ANY_FENCE_RE = re.compile(
    r"```([^\n`]*)\r?\n(.*?)```",
    re.DOTALL,
)


@dataclass(frozen=True)
class Extracted:
    """Result of pulling Lean source out of one engineer turn.

    ``code`` is None when the step carried no Lean. ``method`` records how the
    code was found ('lean_fence' | 'generic_fence' | 'none'); it is handy for
    debugging trace quality and for later reporting which steps were anchorable.
    """

    code: str | None
    method: str

    @property
    def has_code(self) -> bool:
        return self.code is not None


def _looks_like_lean(body: str) -> bool:
    """True if a code body contains a Lean declaration keyword as a word."""
    for kw in _LEAN_DECL_KEYWORDS:
        if re.search(rf"\b{kw}\b", body):
            return True
    return False


def _clean(body: str) -> str:
    """Trim trailing whitespace and a stray FINAL: line if it slipped inside."""
    lines = body.splitlines()
    # Drop a lone FINAL: marker line if the engineer put it inside the block.
    lines = [ln for ln in lines if not ln.strip().upper().startswith("FINAL:")]
    return "\n".join(lines).strip()


def extract_lean_code(text: str) -> Extracted:
    """Pull Lean source from one engineer message's text. Never raises.

    See module docstring for the priority order. Returns ``Extracted`` with
    ``code=None`` when the text contains no Lean.
    """
    text = text or ""

    # 1. Explicit ```lean blocks (concatenate in document order).
    lean_blocks = [_clean(m.group(1)) for m in _LEAN_FENCE_RE.finditer(text)]
    lean_blocks = [b for b in lean_blocks if b]
    if lean_blocks:
        return Extracted(code="\n\n".join(lean_blocks), method="lean_fence")

    # 2. Generic fenced blocks that look like Lean (untagged ``` ... ```).
    generic_blocks: list[str] = []
    for m in _ANY_FENCE_RE.finditer(text):
        info, body = m.group(1).strip().lower(), _clean(m.group(2))
        # Skip blocks explicitly tagged as another language.
        if info and not info.startswith("lean"):
            continue
        if body and _looks_like_lean(body):
            generic_blocks.append(body)
    if generic_blocks:
        return Extracted(code="\n\n".join(generic_blocks), method="generic_fence")

    # 3. No Lean in this step.
    return Extracted(code=None, method="none")


def extract_from_event(event: TraceEvent) -> Extracted:
    """Extract Lean code from a TraceEvent, guarding role/type.

    Only engineer MESSAGE events can carry proposal code. Anything else yields
    an empty result, so a caller can map over a whole trajectory without first
    filtering by role.
    """
    if event.agent_role is not AgentRole.ENGINEER:
        return Extracted(code=None, method="none")
    if event.event_type is not EventType.MESSAGE:
        return Extracted(code=None, method="none")
    text = event.payload.get("text", "") if event.payload else ""
    return extract_lean_code(text)
