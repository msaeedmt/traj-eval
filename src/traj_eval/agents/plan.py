"""Structured plan parsing (Phase 3, Step 3a).

The planner emits an ordered list of sub-tasks delimited by <step>...</step>
tags. This module turns that text into a list of sub-task strings the
controller can walk one at a time.

Why tags rather than "1. 2. 3." line parsing: a sub-task description may wrap
across several lines or contain its own enumerated sub-points; tag delimiters
survive that, whereas line-prefix parsing does not. Tags are also something
LLMs emit reliably. If the endpoint later gains native structured output, only
``parse_plan`` changes (tag-splitting -> json.loads); the controller above it
is unaffected.

Design rule: fail loud. A planner that produces zero parseable steps is a real
failure -- the controller would have nothing to execute -- so ``parse_plan``
raises rather than returning an empty list and letting the run drift.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Captures the text between <step> and </step>, across newlines, non-greedily.
_STEP_RE = re.compile(r"<step>(.*?)</step>", re.DOTALL | re.IGNORECASE)


class PlanParseError(ValueError):
    """Raised when the planner output contains no parseable steps."""


@dataclass(frozen=True)
class Plan:
    """An ordered list of sub-task descriptions produced by the planner."""

    steps: list[str]

    def __len__(self) -> int:
        return len(self.steps)

    def __getitem__(self, i: int) -> str:
        return self.steps[i]


def parse_plan(text: str) -> Plan:
    """Parse planner output into a Plan. Raise PlanParseError if none found.

    Steps are the trimmed contents of each <step>...</step> tag, in order.
    Empty or whitespace-only steps are dropped. If nothing parses, raise.
    """
    raw = _STEP_RE.findall(text or "")
    steps = [s.strip() for s in raw if s and s.strip()]
    if not steps:
        raise PlanParseError(
            "Planner output contained no <step>...</step> blocks. " f"Got: {text[:200]!r}"
        )
    return Plan(steps=steps)
