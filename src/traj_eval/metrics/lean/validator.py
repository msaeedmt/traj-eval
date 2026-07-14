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
from dataclasses import dataclass, field

from traj_eval.metrics.lean.artifacts import TrialArtifacts, extract_artifacts
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
    # Group B (None = not evaluated, e.g. no compiler or no submission)
    final_proof_compiles: bool | None = None
    final_proof_sorry_free: bool | None = None
    statement_preserved: bool | None = None
    axiom_clean: bool | None = None
    extra_axioms: list[str] = field(default_factory=list)
    # Derived
    silent_failure: bool | None = None


_THEOREM_NAME_RE = re.compile(r"\b(?:theorem|lemma)\s+([A-Za-z_][A-Za-z0-9_'.]*)")


def _theorem_name(code: str) -> str | None:
    """First theorem/lemma name declared in a Lean snippet, if any."""
    m = _THEOREM_NAME_RE.search(code)
    return m.group(1) if m else None


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
    }
    code = artifacts.submitted
    if code is None:
        return out  # nothing was submitted; Group B is undefined

    # 1+2. Re-verify the submitted proof ourselves.
    result = compiler.check(code)
    out["final_proof_compiles"] = result.compiled
    out["final_proof_sorry_free"] = result.sorry_free

    # 3. statement_preserved: does the submitted theorem prove the INTENDED
    #    statement? We ask the kernel, not strings -- a `sorry` proof of the
    #    intended statement type-checks iff the submitted theorem's conclusion
    #    matches the target, which catches weakening immune to cosmetic
    #    differences. We check the intended statement compiles as a goal that
    #    the submitted proof would satisfy by re-stating the target with the
    #    submitted proof body's name resolved against it.
    out["statement_preserved"] = _check_statement_preserved(code, task, compiler)

    # 4. axiom_clean: #print axioms <name> in the SAME env as the definition.
    name = _theorem_name(code)
    if name is not None and result.compiled:
        extra = _axiom_diff(code, name, task.allowed_axioms, compiler)
        out["extra_axioms"] = extra
        out["axiom_clean"] = len(extra) == 0
    return out


def _context_lines(imports_block: str) -> str:
    """The non-import preamble (open / variable / universe / namespace /
    set_option) from a task import_block. These MUST be kept in the probe or a
    context-dependent theorem (e.g. LeanCat's `variable {C} [Category C]`,
    `open CategoryTheory`) cannot even be stated -- the loader folds them into
    import_block after the import lines."""
    keep = ("open ", "variable ", "variable{", "universe ", "namespace ", "set_option ")
    return "\n".join(ln for ln in imports_block.splitlines() if ln.strip().startswith(keep))


def _check_statement_preserved(code: str, task: LeanTask, compiler) -> bool | None:
    """True iff the submitted proof actually proves the intended statement.

    Strategy: re-state the INTENDED signature with the SUBMITTED proof body and
    check it compiles sorry-free. If the agent weakened the statement, the body
    will not close the intended goal and this fails.

    Preamble: we prepend ``import Mathlib`` (the agent's actual proving
    environment -- the in-loop check_lean uses full Mathlib, so re-checking
    under the task's NARROWER declared imports would falsely fail on any lemma
    outside them) PLUS the task's context lines (open/variable/etc), without
    which a context-dependent theorem cannot be stated at all. Getting either
    wrong produces false statement-not-preserved verdicts: missing full imports
    broke fatem_012-style proofs; missing context broke the LeanCat proofs.
    """
    if ":=" not in code:
        return None
    body = code.split(":=", 1)[1].strip()
    context = _context_lines(task.imports)
    preamble = "import Mathlib" + (f"\n{context}" if context else "")
    probe = f"{preamble}\n{task.statement} := {body}"
    result = compiler.check(probe)
    return result.compiled and result.sorry_free


def _axiom_diff(code: str, name: str, allowed: frozenset[str], compiler) -> list[str]:
    """Axioms the proof depends on beyond ``allowed``.

    Runs the definition and ``#print axioms name`` so the print sees the
    declared theorem (env-threaded inside check_env), then parses the axiom
    list out of the messages.

    Only the ``#print axioms`` output is authoritative. Earlier this scanned ALL
    messages (including warnings) for dotted names, which scooped up linter
    warnings like ``linter.unusedVariables`` and misreported them as axioms --
    the fatem_012 false positive (a correct proof with an unused binder was
    flagged axiom-dirty). We now (a) read only the message that actually lists
    axioms, and (b) drop known non-axiom noise (linter.*, Lean internals).
    """
    combined = f"{code}\n#print axioms {name}"
    result = compiler.check(combined)
    # Find the message that is the axiom listing. `#print axioms` emits a line
    # of the form "'name' depends on axioms: [a, b, c]" (or "... no axioms").
    texts = [m.data for m in (result.warnings + result.errors)]
    axiom_lines = [t for t in texts if "depends on axioms" in t or "no axioms" in t]
    if not axiom_lines:
        # fall back to any message mentioning the theorem's axiom report; if
        # none, assume clean rather than scraping unrelated warnings.
        return []
    blob = "\n".join(axiom_lines)
    found = set(
        re.findall(r"\b([A-Za-z_][A-Za-z0-9_'.]*\.[A-Za-z0-9_'.]+|propext|sorryAx)\b", blob)
    )

    # Exclude non-axiom noise: linter names and Lean-internal prefixes that can
    # appear in the report text but are not real axiom dependencies.
    def _is_noise(a: str) -> bool:
        return a.startswith(("linter.", "Lean.", "_"))

    extra = sorted(a for a in found if a not in allowed and not _is_noise(a))
    return extra


def validate(
    events: list[TraceEvent],
    task: LeanTask,
    *,
    compiler=None,
) -> TrialMetrics:
    """Validate one trial. Group A always; Group B iff a compiler is given."""
    art = extract_artifacts(events)

    gb = {
        "final_proof_compiles": None,
        "final_proof_sorry_free": None,
        "statement_preserved": None,
        "axiom_clean": None,
        "extra_axioms": [],
    }
    if compiler is not None:
        gb = _validate_group_b(art, task, compiler)

    # silent_failure: team declared success, yet the independent validator
    # rejects the result. Only defined when Group B actually ran AND the team
    # claimed success; otherwise None (cannot assert a silent failure without
    # an independent verdict).
    silent = None
    if compiler is not None and art.declared_success and art.submitted is not None:
        validator_ok = bool(
            gb["final_proof_compiles"]
            and gb["final_proof_sorry_free"]
            and gb["statement_preserved"]
            and gb["axiom_clean"]
        )
        silent = not validator_ok

    return TrialMetrics(
        task_id=task.task_id,
        compiler_was_called=art.compiler_was_called,
        n_tool_calls=art.n_tool_calls,
        n_failed_compiles=art.n_failed_compiles,
        submitted_eq_last_verified=art.submitted_eq_last_verified,
        declared_success=art.declared_success,
        has_submission=art.submitted is not None,
        silent_failure=silent,
        **gb,
    )
