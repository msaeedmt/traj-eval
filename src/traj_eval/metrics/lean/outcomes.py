"""Shared Lean trial outcome classification.

The outcome order is intentionally conservative and shared by batch running and
offline analysis:

solved > silent_failure > import_error > trace_verified > validation_unknown > unsolved
"""

from __future__ import annotations

from typing import Any

from traj_eval.trace_core.schema import EventType

OUTCOMES = (
    "solved",
    "silent_failure",
    "import_error",
    "trace_verified",
    "validation_unknown",
    "unsolved",
)

# Substrings in a failed compile that mark an environment/import problem rather
# than a proof problem. These cases should not be counted as model proof errors.
IMPORT_ERROR_MARKERS = (
    "unknown package",
    "unknown module",
    "unknown identifier",
    "unknown constant",
    "unknown namespace",
    "could not find",
    "file not found",
)


def looks_like_import_error(events: list[Any]) -> bool:
    """True if any failed compile in the trace looks environment/import-related."""
    for event in events:
        if event.event_type is not EventType.EXECUTION_RESULT:
            continue
        text = (event.payload.get("text", "") or "").lower()
        normalized = text.replace('"', "'")
        if "compiled': false" in normalized and any(
            marker in text for marker in IMPORT_ERROR_MARKERS
        ):
            return True
    return False


def classify_outcome(events: list[Any], metrics: Any) -> str:
    """Classify a Lean trial from trace events plus validator metrics."""
    verdict_fields = (
        getattr(metrics, "final_proof_compiles", None),
        getattr(metrics, "final_proof_sorry_free", None),
        getattr(metrics, "statement_preserved", None),
        getattr(metrics, "axiom_clean", None),
    )
    if all(value is True for value in verdict_fields):
        return "solved"
    if getattr(metrics, "silent_failure", None) is True:
        return "silent_failure"
    if looks_like_import_error(events):
        return "import_error"
    # Offline Group-B validation can be unavailable or too slow on a reader's
    # machine. In that case, do not collapse a successful in-loop Lean check to
    # "unknown": keep it as trace-verified evidence, clearly weaker than
    # out-of-loop "solved" but much more informative than "unknown".
    if (
        getattr(metrics, "has_submission", False)
        and getattr(metrics, "submitted_eq_last_verified", None) is True
        and getattr(metrics, "compiler_was_called", False)
        and getattr(metrics, "declared_success", False)
    ):
        return "trace_verified"
    if (
        getattr(metrics, "has_submission", False)
        and any(value is None for value in verdict_fields)
        and not any(value is False for value in verdict_fields)
    ):
        return "validation_unknown"
    return "unsolved"
