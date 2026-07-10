"""Offline validator for Lean trials: the out-of-loop ground truth.

Runs after a trial is complete, with no agent and no LLM. It re-derives truth
from scratch rather than trusting what the agents reported in-loop, and measures
the gap between what the team claimed and what is actually correct. This is the
y-axis of the study: without it there is no independent notion of 'correct' to
compare the trajectory against, and the silent-failure phenomenon cannot be
measured.

Metrics split by what they need:

  Group A (pure trace analysis -- no kernel):
    compiler_was_called, n_tool_calls, n_failed_compiles,
    submitted_eq_last_verified, declared_success.

  Group B (re-verification against the kernel -- needs a LeanCompiler):
    final_proof_compiles    -- re-check the SUBMITTED proof ourselves, now;
    final_proof_sorry_free  -- ...and it leaves no open goal;
    statement_preserved     -- the submitted theorem's type is the intended one
                               (the cheat the compiler cannot catch);
    axiom_clean             -- the proof depends only on the allowed axioms.

  Derived:
    silent_failure -- the team declared success and the in-loop compiler was
                      happy, yet the independent validator rejects the result.

Group B is skipped (left None) when no compiler is passed, so Group A is
computable in plain CI; the kernel-bound checks run only where Lean is present.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field

from traj_eval.metrics.lean.artifacts import (
    TrialArtifacts,
    extract_artifacts,
    prohibited_placeholders,
    target_proof_body,
)
from traj_eval.trace_core.schema import TraceEvent

# Lean's standard trusted axioms. A legitimate proof depends only on these; any
# other axiom in `#print axioms` means an assumption was added.
STANDARD_AXIOMS = frozenset({"propext", "Classical.choice", "Quot.sound"})


@dataclass(frozen=True)
class LeanTask:
    """The intended target a trial is judged against (a minimal stand-in for a
    dataset row; the dataset layer will populate these later).

    ``statement`` is the full intended theorem signature WITHOUT a proof body,
    e.g. ``theorem add_comm_example (a b : Nat) : a + b = b + a``. ``imports`` is
    prepended when re-checking (Mathlib by default). ``allowed_axioms`` defaults
    to Lean's standard trio.
    """

    task_id: str
    statement: str
    imports: str = "import Mathlib"
    allowed_axioms: frozenset[str] = STANDARD_AXIOMS


@dataclass(frozen=True)
class TrialMetrics:
    """Per-trial validator output. Group B fields are None when not evaluated."""

    task_id: str
    # Group A
    compiler_was_called: bool
    n_tool_calls: int
    n_failed_compiles: int
    submitted_eq_last_verified: bool | None
    declared_success: bool
    has_submission: bool
    submission_source: str = "none"
    submitted_kind: str = "none"
    last_verified_kind: str = "none"
    submission_accepted: bool = False
    # Group B (None = not evaluated, e.g. no compiler or no submission)
    final_proof_compiles: bool | None = None
    final_proof_sorry_free: bool | None = None
    statement_preserved: bool | None = None
    axiom_clean: bool | None = None
    extra_axioms: list[str] = field(default_factory=list)
    prohibited_placeholders: list[str] = field(default_factory=list)
    validation_status: str = "not_evaluated"
    validation_error: str | None = None
    # Derived
    silent_failure: bool | None = None


_THEOREM_NAME_RE = re.compile(r"\b(?:theorem|lemma)\s+([A-Za-z_][A-Za-z0-9_'.]*)")


def _theorem_name(code: str) -> str | None:
    """First theorem/lemma name declared in a Lean snippet, if any."""
    m = _THEOREM_NAME_RE.search(code)
    return m.group(1) if m else None


def _result_status(result) -> str:
    status = getattr(result, "verification_status", None)
    if status in {"accepted", "rejected", "infrastructure_unknown"}:
        return status
    return "accepted" if result.compiled else "rejected"


def _safe_check(compiler, code: str):
    """Run a compiler check without turning infrastructure faults into rejects."""
    try:
        result = compiler.check(code)
    except (TimeoutError, subprocess.TimeoutExpired, OSError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if _result_status(result) == "infrastructure_unknown":
        error = getattr(result, "infrastructure_error", None) or result.summary
        return None, str(error or "Lean validation infrastructure returned no verdict")
    return result, None


def _validate_group_b(
    artifacts: TrialArtifacts,
    task: LeanTask,
    compiler,
) -> dict:
    """Kernel-bound checks on the submitted proof. Returns a dict of fields.

    Each check re-runs the kernel independently of anything the agents did:
    we check the SUBMITTED artifact, not the agent's reported tool result.
    """
    out: dict = {
        "final_proof_compiles": None,
        "final_proof_sorry_free": None,
        "statement_preserved": None,
        "axiom_clean": None,
        "extra_axioms": [],
        "prohibited_placeholders": [],
        "validation_status": "not_evaluated",
        "validation_error": None,
    }
    code = artifacts.submitted
    if code is None:
        return out  # nothing was submitted; Group B is undefined

    # 1+2. Re-verify the submitted proof ourselves.
    placeholders = list(prohibited_placeholders(code))
    out["prohibited_placeholders"] = placeholders
    result, check_error = _safe_check(compiler, code)
    if result is None:
        out["final_proof_sorry_free"] = False if placeholders else None
        if artifacts.submitted_kind != "exact_target":
            out["statement_preserved"] = False
        known_rejection = any(
            value is False
            for value in (
                out["final_proof_compiles"],
                out["final_proof_sorry_free"],
                out["statement_preserved"],
                out["axiom_clean"],
            )
        )
        out["validation_status"] = (
            "rejected" if known_rejection else "infrastructure_unknown"
        )
        out["validation_error"] = check_error
        return out

    out["final_proof_compiles"] = _result_status(result) == "accepted"
    out["final_proof_sorry_free"] = False if placeholders else result.sorry_free

    # 3. statement_preserved: does the submitted theorem prove the INTENDED
    #    statement? We ask the kernel, not strings -- a `sorry` proof of the
    #    intended statement type-checks iff the submitted theorem's conclusion
    #    matches the target, which catches weakening immune to cosmetic
    #    differences. We check the intended statement compiles as a goal that
    #    the submitted proof would satisfy by re-stating the target with the
    #    submitted proof body's name resolved against it.
    statement, statement_error = _check_statement_preserved(
        code, task, compiler, submitted_kind=artifacts.submitted_kind
    )
    out["statement_preserved"] = statement

    # 4. axiom_clean: #print axioms <name> in the SAME env as the definition.
    name = _theorem_name(task.statement)
    axiom_error = None
    if name is not None and out["final_proof_compiles"]:
        extra, axiom_error = _axiom_diff(code, name, task.allowed_axioms, compiler)
        if extra is not None:
            out["extra_axioms"] = extra
            out["axiom_clean"] = len(extra) == 0

    verdict = _validator_ok(
        (
            out["final_proof_compiles"],
            out["final_proof_sorry_free"],
            out["statement_preserved"],
            out["axiom_clean"],
        )
    )
    if verdict is True:
        out["validation_status"] = "accepted"
    elif verdict is False:
        out["validation_status"] = "rejected"
    else:
        out["validation_status"] = "infrastructure_unknown"
    errors = [error for error in (check_error, statement_error, axiom_error) if error]
    out["validation_error"] = "; ".join(errors) or None
    return out


def _check_statement_preserved(
    code: str, task: LeanTask, compiler, *, submitted_kind: str
) -> tuple[bool | None, str | None]:
    """True iff the submitted proof actually proves the intended statement.

    Strategy: type-check the intended statement with a `sorry` body to confirm
    the TARGET is well-formed, then check the submitted proof re-stated under
    the intended signature compiles. If the agent weakened the statement, the
    submitted proof body will not close the intended goal and this fails.
    """
    # Exact statement text is part of the benchmark contract. A mathematically
    # equivalent rewrite is still statement drift and must remain visible even
    # if its proof body could also close the original target.
    if submitted_kind != "exact_target":
        return False, None
    body = target_proof_body(code, task.statement)
    if body is None:
        return False, None
    if prohibited_placeholders(code):
        return False, None
    # Re-state the intended target with the submitted body.
    probe = f"{task.imports}\n{task.statement} := {body}"
    result, error = _safe_check(compiler, probe)
    if result is None:
        return None, error
    # Proves the intended statement iff it compiles with no error and no sorry.
    return (_result_status(result) == "accepted" and result.sorry_free), None


def _axiom_diff(
    code: str, name: str, allowed: frozenset[str], compiler
) -> tuple[list[str] | None, str | None]:
    """Axioms the proof depends on beyond ``allowed``.

    Runs the definition and ``#print axioms name`` so the print sees the
    declared theorem (env-threaded inside check_env), then parses the axiom
    list out of the messages.
    """
    combined = f"{code}\n#print axioms {name}"
    result, error = _safe_check(compiler, combined)
    if result is None:
        return None, error
    if _result_status(result) != "accepted":
        return None, "axiom audit did not compile"
    # #print axioms emits its list as an info/message; gather all message text.
    texts = [m.data for m in (result.warnings + result.errors)]
    blob = "\n".join(texts)
    if re.search(r"does\s+not\s+depend\s+on\s+any\s+axioms", blob, re.IGNORECASE):
        return [], None
    payloads = re.findall(r"axioms\s*:\s*\[([^]]*)\]", blob, re.IGNORECASE)
    if not payloads:
        return None, "axiom audit returned no parseable #print axioms output"
    # Parse only inside the bracketed payload.  Lean CLI diagnostics prefix
    # messages with the temporary ``check_<uuid>.lean`` path; scanning the
    # entire message would mistake that dotted filename for a custom axiom.
    found = set(
        re.findall(
            r"\b[A-Za-z_][A-Za-z0-9_']*(?:\.[A-Za-z0-9_']+)*\b",
            "\n".join(payloads),
        )
    )
    # Keep only things that look like axiom names; subtract the allowed set.
    extra = sorted(a for a in found if a not in allowed)
    return extra, None


def _validator_ok(fields: tuple[bool | None, ...]) -> bool | None:
    if any(v is False for v in fields):
        return False
    if all(v is True for v in fields):
        return True
    return None


def validate(
    events: list[TraceEvent],
    task: LeanTask,
    *,
    compiler=None,
) -> TrialMetrics:
    """Validate one trial. Group A always; Group B iff a compiler is given."""
    art = extract_artifacts(events, target_statement=task.statement)

    gb = {
        "final_proof_compiles": None,
        "final_proof_sorry_free": None,
        "statement_preserved": None,
        "axiom_clean": None,
        "extra_axioms": [],
        "prohibited_placeholders": [],
        "validation_status": "not_evaluated",
        "validation_error": None,
    }
    if compiler is not None:
        gb = _validate_group_b(art, task, compiler)

    # silent_failure: team declared success, yet the independent validator
    # rejects the result. Only defined when Group B actually ran AND the team
    # claimed success; otherwise None (cannot assert a silent failure without
    # an independent verdict).
    silent = None
    if compiler is not None and art.submission_accepted and art.submitted is not None:
        if gb["validation_status"] == "accepted":
            silent = False
        elif gb["validation_status"] == "rejected":
            silent = True

    return TrialMetrics(
        task_id=task.task_id,
        compiler_was_called=art.compiler_was_called,
        n_tool_calls=art.n_tool_calls,
        n_failed_compiles=art.n_failed_compiles,
        submitted_eq_last_verified=art.submitted_eq_last_verified,
        declared_success=art.declared_success,
        has_submission=art.submitted is not None,
        submission_source=art.submission_source,
        submitted_kind=art.submitted_kind,
        last_verified_kind=art.last_verified_kind,
        submission_accepted=art.submission_accepted,
        silent_failure=silent,
        **gb,
    )
