"""Build the reviewed, proposal-grounded analysis of the 100 Lean traces.

The raw JSONL files are immutable evidence.  This module joins three different
layers without conflating them:

* trace facts (tool calls, compiler responses, routing, and approvals),
* agent-reviewed multi-label diagnoses in ``lean_easy_failure_reviews.jsonl``,
* optional out-of-loop Lean kernel validation.

Canonical generation is deliberately fail-closed: ``--kernel required`` is the
default.  ``auto`` and ``off`` are explicit trace-only modes and every emitted
row remains visibly provisional when Group-B validation did not run.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import re
import shutil
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from traj_eval.dataset.loader import ProblemRecord, load_dataset
from traj_eval.metrics.lean.artifacts import (
    contains_prohibited_placeholder,
    prohibited_placeholders,
    target_proof_body,
)
from traj_eval.metrics.lean.validator import STANDARD_AXIOMS, _axiom_diff
from traj_eval.trace_core.graph import build_graph, causal_order
from traj_eval.trace_core.schema import AgentRole, EventType, TraceEvent
from traj_eval.trace_core.storage import read_trial

DEFAULT_INPUT_DIR = Path("data/batch/version_1_trial_traces")
DEFAULT_DATASET_ROOT = Path("dataset/Lean")
DEFAULT_REVIEWS = Path("data/analysis/lean_easy_failure_reviews.jsonl")
DEFAULT_OUT_CSV = Path("data/analysis/lean_easy_failure_patterns.csv")
DEFAULT_REPORT_CSV = Path(
    "docs/lean_easy_failure_report/public/data/lean_easy_failure_patterns.csv"
)
DEFAULT_REPORT_JSON = Path(
    "docs/lean_easy_failure_report/public/data/lean_easy_failure_traces.json"
)
PUBLIC_REPO_ROOT = Path(__file__).resolve().parents[1]

CSV_FIELDS = [
    "task_id",
    "trial_id",
    "trial_number",
    "source",
    "difficulty",
    "source_sha256",
    "analysis_snapshot_sha256",
    "review_status",
    "review_confidence",
    "math_question",
    "naive_human_strategy",
    "domain_specific_LLM_strategy",
    "reasoner_strategy_label",
    "engineer_failure_label",
    "critic_label",
    "global_graph_pattern",
    "validator_outcome",
    "verification_level",
    "kernel_status",
    "validation_status",
    "validation_error",
    "claim_status",
    "candidate_kind",
    "candidate_event_seq",
    "statement_match",
    "workflow_outcome",
    "submission_source",
    "submission_accepted",
    "symptom_codes",
    "error_labels",
    "incident_count",
    "critical_failure_seq",
    "critical_failure_label",
    "critical_failure_role",
    "recovered_failure_count",
    "first_failure_stage",
    "n_tool_calls",
    "n_check_lean_calls",
    "n_search_lemma_calls",
    "n_failed_compiles",
    "n_infrastructure_unknown_checks",
    "retry_success_rate",
    "perseverated",
    "declared_success",
    "final_proof_compiles",
    "final_proof_sorry_free",
    "statement_preserved",
    "axiom_clean",
    "prohibited_placeholders",
    "anchor_coverage",
    "presentation_takeaway",
]

PROPOSAL_GROUNDING = (
    "Proposal mapping: O1 localization is partial because raw anchors are absent; "
    "O2 labels are agent-reviewed and detector precision/recall is untested; "
    "O3 is not tested on this single configuration."
)
MD_GROUNDING = "Taxonomy: docs/guides/LEAN_FAILURE_ANALYSIS_GUIDE.md."

CONFIDENCE_LEVELS = frozenset({"confirmed", "strong", "tentative", "not_observable"})
CANDIDATE_KINDS = frozenset({"exact_target", "statement_drift", "helper_or_probe", "none"})
STATEMENT_MATCHES = frozenset({"exact", "changed", "not_target", "none"})
WORKFLOW_OUTCOMES = frozenset(
    {
        "approved_direct",
        "approved_after_productive_revision",
        "approved_statement_drift",
        "approved_after_failed_recheck",
        "target_verified_unapproved",
        "statement_drift_unapproved",
        "regressed_after_success",
        "terminated_with_compile_failures",
        "terminated_with_unresolved_checks",
        "terminated_without_target_check",
    }
)
SYMPTOM_CODES = frozenset(
    {
        "application_type_mismatch",
        "critic_approval_after_failed_recheck",
        "invalid_field_projection",
        "invalid_import_path",
        "opaque_compiler_failure",
        "other_lean_diagnostic",
        "parser_or_syntax_error",
        "regression_after_success",
        "sorry_pseudo_pass",
        "statement_drift",
        "tactic_failure",
        "target_not_attempted",
        "target_unreviewed",
        "type_mismatch",
        "typeclass_resolution",
        "unknown_symbol",
        "unsolved_goals",
    }
)
CAUSAL_LABELS = frozenset(
    {
        "api_or_library_hallucination",
        "critic_masking",
        "helper_substitution",
        "incomplete_verification",
        "incorrect_verification",
        "invalid_import_path",
        "lean_elaboration_failure",
        "lean_tactic_failure",
        "lean_type_failure",
        "missed_statement_drift",
        "missing_critic_review",
        "no_actionable_plan",
        "perseveration",
        "premature_termination",
        "regression_after_success",
        "sorry_pseudo_pass",
        "statement_drift",
        "tooling_diagnostic_unknown",
    }
)


@dataclass(frozen=True)
class TaskReference:
    naive_human_strategy: str
    domain_specific_llm_strategy: str
    key_objects: tuple[str, ...]


TASK_REFERENCES: dict[str, TaskReference] = {
    "easy_fatem_011": TaskReference(
        "Expand the ring expression, split the conjunction, and use distributivity.",
        "Use mul_sub and sub_mul, preserve the statement, then check the target.",
        ("mul_sub", "sub_mul", "And.intro"),
    ),
    "easy_fatem_012": TaskReference(
        "Use uniqueness of the integer-to-ring homomorphism.",
        "Use RingHom extensionality and Int.cast lemmas instead of inventing a map API.",
        ("RingHom.ext", "Int.cast", "existsUnique"),
    ),
    "easy_fatem_019": TaskReference(
        "Connect the field structure of ZMod n with primality of n.",
        "Find the current ZMod field/primality API and keep both iff directions faithful.",
        ("ZMod", "IsField", "Nat.Prime"),
    ),
    "easy_fatem_020": TaskReference(
        "In a field every ideal is bottom or top; use an inverse for a nonzero element.",
        "Use the Ideal/field API without demanding a nonexistent IsField instance.",
        ("Ideal", "Field", "inv_mul_cancel"),
    ),
    "easy_fatem_041": TaskReference(
        "Relate the order of a product to the lcm of component orders.",
        "Use orderOf/product lemmas and discharge their commutativity hypotheses.",
        ("orderOf", "Nat.lcm", "Commute"),
    ),
    "easy_fatem_109": TaskReference(
        "Use no-zero-divisor cancellation to recover equality of the factors.",
        "Use cancellation lemmas valid for rings without zero divisors; do not assume a field.",
        ("NoZeroDivisors", "mul_left_cancel", "mul_right_cancel"),
    ),
    "easy_fatem_111": TaskReference(
        "Expand both products and rewrite a^2 to zero in the noncommutative ring.",
        "Unfold Commute and normalize with mul_add, add_mul, mul_assoc, and pow_two.",
        ("Commute", "mul_add", "add_mul", "mul_assoc", "pow_two"),
    ),
    "easy_fatem_115": TaskReference(
        "Unpack transitivity and apply it in reverse order for the inverse relation.",
        "Prove the exact Transitive target; an IsTrans reformulation is statement drift.",
        ("Transitive", "IsTrans", "swap"),
    ),
    "easy_leancat_001": TaskReference(
        "Use extensionality and componentwise naturality for natural transformations.",
        "Use NatTrans.ext/naturality while preserving universes and category variables.",
        ("NatTrans.ext", "naturality", "Category.assoc"),
    ),
    "easy_leancat_002": TaskReference(
        "Cancel through the known monic factors of the composition.",
        "Use Mono and categorical cancellation lemmas for composition.",
        ("Mono", "cancel_mono", "Category.comp"),
    ),
}

TASK_DIAGNOSES = {
    "easy_fatem_011": "Direct distributivity proof; the observed runs provide a low-friction control.",
    "easy_fatem_012": "Most runs recover from concrete elaboration/API errors before approval.",
    "easy_fatem_019": "The main obstacle is the ZMod field/primality API; helper checks must not count as target proofs.",
    "easy_fatem_020": "Repeated failures center on typeclass/API use for ideals over a Field.",
    "easy_fatem_041": "Direct Mathlib reuse succeeds without an observed compile-failure phase.",
    "easy_fatem_109": "Successful runs find cancellation; incomplete runs often stop during search without a target check.",
    "easy_fatem_111": "Noncommutative normalization remains unresolved; a helper theorem about a*a=0 is not the target.",
    "easy_fatem_115": "The key fidelity risk is changing deprecated Transitive to IsTrans instead of proving the supplied header.",
    "easy_leancat_001": "Category-theory elaboration is fragile; probe success and unreviewed target success are separated.",
    "easy_leancat_002": "Most runs reach a short cancellation proof; failed early drafts are usually recovered.",
}

_THEOREM_NAME_RE = re.compile(r"\b(?:theorem|lemma)\s+([A-Za-z_][A-Za-z0-9_'.]*)")


@dataclass(frozen=True)
class CheckEvidence:
    call_id: str | None
    call_seq: int
    result_seq: int | None
    role: str
    code: str
    compiled: bool | None
    sorry_free: bool | None
    verification_status: str
    diagnostic: str
    candidate_kind: str
    statement_match: str


@dataclass(frozen=True)
class CandidateValidation:
    status: str
    final_proof_compiles: bool | None
    final_proof_sorry_free: bool | None
    statement_preserved: bool | None
    axiom_clean: bool | None
    extra_axioms: tuple[str, ...] = ()
    error: str | None = None
    prohibited_placeholders: tuple[str, ...] = ()


def parse_trial_number(path: Path | str) -> int:
    match = re.search(r"_t(\d+)\.jsonl$", Path(path).name)
    if not match:
        raise ValueError(f"Cannot parse trial number from {path}")
    return int(match.group(1))


def _compact(text: str | None, *, limit: int | None = None) -> str:
    value = " ".join((text or "").split())
    if limit is not None and len(value) > limit:
        return value[: limit - 3].rstrip() + "..."
    return value


def _public_text(text: str | None) -> str:
    """Remove absolute local Windows paths from shareable diagnostics.

    Known roots retain a useful ``<repo>``/``<home>`` prefix. Any other drive
    path is reduced to ``<local-path>/<basename>`` so the diagnostic keeps the
    relevant file without publishing a workstation layout. Both decoded
    backslashes and doubled backslashes inside Python-repr trace text are
    handled deterministically.
    """
    value = text or ""
    replacements = (
        (str(PUBLIC_REPO_ROOT), "<repo>"),
        (str(PUBLIC_REPO_ROOT).replace("\\", "\\\\"), "<repo>"),
        (PUBLIC_REPO_ROOT.as_posix(), "<repo>"),
        (str(Path.home()), "<home>"),
        (str(Path.home()).replace("\\", "\\\\"), "<home>"),
        (Path.home().as_posix(), "<home>"),
    )
    for root, replacement in replacements:
        if root:
            value = re.sub(
                re.escape(root), replacement, value, flags=re.IGNORECASE
            )
    value = re.sub(
        r"(?i)(?:\.traj_eval_tmp(?:\\{1,2}|/))check_[0-9a-f]+\.lean",
        "<lean-temp>.lean",
        value,
    )

    def replacement(match: re.Match[str]) -> str:
        path = match.group("path")
        basename = re.split(r"\\+|/", path)[-1].strip()
        redacted = f"<local-path>/{basename}" if basename else "<local-path>"
        quote = match.groupdict().get("quote")
        return f"{quote}{redacted}{quote}" if quote else redacted

    value = re.sub(
        r"(?i)(?P<quote>['\"])(?P<path>[a-z]:(?:\\{1,2}|/)[^'\"\r\n]+)(?P=quote)",
        replacement,
        value,
    )
    return re.sub(
        r"(?i)(?<![a-z0-9_])(?P<path>[a-z]:(?:\\{1,2}|/)[^\s'\"<>|:]+)",
        replacement,
        value,
    )


def _public_value(value: Any) -> Any:
    """Recursively sanitize every string in a public report payload."""
    if isinstance(value, str):
        return _public_text(value)
    if isinstance(value, list):
        return [_public_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_public_value(item) for item in value)
    if isinstance(value, dict):
        return {key: _public_value(item) for key, item in value.items()}
    return value


def _bool(value: bool | None) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return "none"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def analysis_snapshot_sha256(trace_paths: list[Path]) -> str:
    manifest = "\n".join(f"{path.name}:{_sha256(path)}" for path in sorted(trace_paths))
    return hashlib.sha256(manifest.encode("utf-8")).hexdigest()


def _review_sha256(review: dict[str, Any]) -> str:
    raw = json.dumps(review, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _json_loads_or_none(text: str | None) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def _normalise_header(text: str) -> str:
    text = re.sub(r"/-.*?-/", " ", text, flags=re.DOTALL)
    text = re.sub(r"--[^\n]*", " ", text)
    # Whitespace and comments are presentation, not theorem-type changes.
    return "".join(text.split())


def _contains_sorry(code: str) -> bool:
    return contains_prohibited_placeholder(code)


def _theorem_name(statement: str) -> str | None:
    match = _THEOREM_NAME_RE.search(statement)
    return match.group(1) if match else None


def _declaration_headers(code: str) -> list[tuple[str, str]]:
    pattern = re.compile(
        r"\b(?:theorem|lemma)\s+([A-Za-z_][A-Za-z0-9_'.]*)\b(.*?)(?=:=)", re.DOTALL
    )
    return [(match.group(1), match.group(2)) for match in pattern.finditer(code)]


def _candidate_class(code: str, record: ProblemRecord) -> tuple[str, str]:
    name = _theorem_name(record.statement)
    if not name:
        return "helper_or_probe", "not_target"
    target_type = re.sub(
        rf"^\s*(?:theorem|lemma)\s+{re.escape(name)}\b",
        "",
        record.statement,
        count=1,
    )
    declarations = _declaration_headers(code)
    for declared_name, header_type in declarations:
        if declared_name != name:
            continue
        if _normalise_header(header_type) == _normalise_header(target_type):
            return "exact_target", "exact"
        return "statement_drift", "changed"
    task_prefix = record.id.removeprefix("easy_")
    if any(declared_name.startswith(task_prefix) for declared_name, _ in declarations):
        return "statement_drift", "changed"
    if not declarations:
        return "helper_or_probe", "not_target"
    return "helper_or_probe", "not_target"


def _result_map(events: list[TraceEvent]) -> dict[str | None, tuple[int, dict[str, Any]]]:
    results: dict[str | None, tuple[int, dict[str, Any]]] = {}
    for event in events:
        if event.event_type is not EventType.EXECUTION_RESULT:
            continue
        for response in event.payload.get("tool_responses") or []:
            parsed: dict[str, Any] = {}
            content = response.get("content")
            if content:
                try:
                    value = ast.literal_eval(content)
                except (ValueError, SyntaxError):
                    value = None
                if isinstance(value, dict):
                    parsed = value
            results[response.get("id")] = (event.seq, parsed)
    return results


def _diagnostic(result: dict[str, Any]) -> str:
    chunks: list[str] = []
    for item in result.get("errors") or []:
        if isinstance(item, dict):
            data = item.get("data")
        else:
            data = getattr(item, "data", None) or str(item)
        if data:
            chunks.append(str(data))
    if not chunks and result.get("error"):
        chunks.append(str(result["error"]))
    return _public_text("\n".join(chunks).strip())


def _trace_verification_status(result: dict[str, Any]) -> str:
    status = result.get("verification_status")
    if status in {"accepted", "rejected", "infrastructure_unknown"}:
        return status
    if result.get("infrastructure_error"):
        return "infrastructure_unknown"
    if result.get("compiled") is True:
        return "accepted"
    if result.get("compiled") is False:
        return "rejected" if _diagnostic(result) else "infrastructure_unknown"
    return "infrastructure_unknown"


def check_evidence(events: list[TraceEvent], record: ProblemRecord) -> list[CheckEvidence]:
    results = _result_map(events)
    checks: list[CheckEvidence] = []
    for event in events:
        if event.event_type is not EventType.TOOL_CALL:
            continue
        for call in event.payload.get("tool_calls") or []:
            if call.get("name") != "check_lean":
                continue
            args = _json_loads_or_none(call.get("arguments"))
            code = args.get("code") if isinstance(args, dict) else None
            code = code if isinstance(code, str) else ""
            result_seq, result = results.get(call.get("id"), (None, {}))
            kind, match = _candidate_class(code, record)
            verification_status = _trace_verification_status(result)
            checks.append(
                CheckEvidence(
                    call_id=call.get("id"),
                    call_seq=event.seq,
                    result_seq=result_seq,
                    role=event.agent_role.value,
                    code=code,
                    compiled=(
                        result.get("compiled")
                        if verification_status != "infrastructure_unknown"
                        else None
                    ),
                    sorry_free=(
                        result.get("sorry_free")
                        if verification_status != "infrastructure_unknown"
                        else None
                    ),
                    verification_status=verification_status,
                    diagnostic=_diagnostic(result),
                    candidate_kind=kind,
                    statement_match=match,
                )
            )
    return checks


def _tool_counts(events: list[TraceEvent]) -> tuple[int, int]:
    checks = searches = 0
    for event in events:
        if event.event_type is not EventType.TOOL_CALL:
            continue
        for call in event.payload.get("tool_calls") or []:
            checks += call.get("name") == "check_lean"
            searches += call.get("name") == "search_lemmas"
    return checks, searches


def _final_critic_decision(events: list[TraceEvent]) -> tuple[str | None, int | None]:
    decisions = [
        (event.payload.get("decision"), event.seq)
        for event in events
        if event.agent_role is AgentRole.CRITIC and event.payload.get("decision")
    ]
    return decisions[-1] if decisions else (None, None)


def _successful(check: CheckEvidence) -> bool:
    return (
        check.verification_status == "accepted"
        and
        check.compiled is True
        and check.sorry_free is not False
        and not _contains_sorry(check.code)
    )


def select_candidate(
    checks: list[CheckEvidence], events: list[TraceEvent]
) -> CheckEvidence | None:
    decision, decision_seq = _final_critic_decision(events)
    limit = decision_seq if decision == "approve" else None
    eligible = [
        check
        for check in checks
        if _successful(check)
        and check.candidate_kind in {"exact_target", "statement_drift"}
        and (limit is None or check.call_seq < limit)
    ]
    if eligible:
        return eligible[-1]
    helpers = [check for check in checks if _successful(check) and (limit is None or check.call_seq < limit)]
    return helpers[-1] if helpers else None


def workflow_outcome(
    checks: list[CheckEvidence], events: list[TraceEvent], candidate: CheckEvidence | None
) -> str:
    decision, decision_seq = _final_critic_decision(events)
    approved = decision == "approve"
    exact_successes = [c for c in checks if _successful(c) and c.candidate_kind == "exact_target"]
    drift_successes = [c for c in checks if _successful(c) and c.candidate_kind == "statement_drift"]
    failed = [c for c in checks if c.verification_status == "rejected"]
    unknown = [c for c in checks if c.verification_status == "infrastructure_unknown"]
    if approved:
        if candidate and candidate.candidate_kind == "statement_drift":
            failed_critic_recheck = any(
                c.role == AgentRole.CRITIC.value
                and c.verification_status == "rejected"
                and c.call_seq > candidate.call_seq
                and (decision_seq is None or c.call_seq < decision_seq)
                for c in checks
            )
            return "approved_after_failed_recheck" if failed_critic_recheck else "approved_statement_drift"
        if candidate and any(c.call_seq < candidate.call_seq for c in failed):
            return "approved_after_productive_revision"
        return "approved_direct"
    if exact_successes:
        last_success = exact_successes[-1]
        if any(
            c.verification_status in {"rejected", "infrastructure_unknown"}
            and c.call_seq > last_success.call_seq
            for c in checks
        ):
            return "regressed_after_success"
        return "target_verified_unapproved"
    if drift_successes:
        return "statement_drift_unapproved"
    if failed:
        return "terminated_with_compile_failures"
    if unknown:
        return "terminated_with_unresolved_checks"
    return "terminated_without_target_check"


def _symptom_for_failure(diagnostic: str) -> tuple[str, list[str], str]:
    text = diagnostic.lower()
    if not text.strip():
        return "opaque_compiler_failure", ["tooling_diagnostic_unknown"], "not_observable"
    if ("object file" in text and "does not exist" in text) or "unknown module" in text:
        return (
            "invalid_import_path",
            ["invalid_import_path", "api_or_library_hallucination"],
            "confirmed",
        )
    if any(marker in text for marker in ("unknown identifier", "unknown constant", "unknown namespace")):
        return "unknown_symbol", ["api_or_library_hallucination", "lean_elaboration_failure"], "confirmed"
    if "application type mismatch" in text or "function expected" in text:
        return "application_type_mismatch", ["lean_type_failure"], "confirmed"
    if "failed to synthesize" in text or "type class" in text or "synthinstance" in text:
        return "typeclass_resolution", ["lean_type_failure"], "confirmed"
    if "type mismatch" in text:
        return "type_mismatch", ["lean_type_failure"], "confirmed"
    if "invalid field" in text or "invalid field notation" in text:
        return "invalid_field_projection", ["lean_elaboration_failure"], "confirmed"
    if "unsolved goals" in text:
        return "unsolved_goals", ["lean_tactic_failure"], "confirmed"
    if any(marker in text for marker in ("tactic", "made no progress", "no goals to be solved")):
        return "tactic_failure", ["lean_tactic_failure"], "confirmed"
    if any(marker in text for marker in ("parser", "unexpected token", "invalid syntax")):
        return "parser_or_syntax_error", ["lean_elaboration_failure"], "confirmed"
    return "other_lean_diagnostic", ["lean_elaboration_failure"], "strong"


def _retry_success_rate(checks: list[CheckEvidence]) -> float | None:
    retry_pairs = [
        (a, b)
        for a, b in zip(checks, checks[1:], strict=False)
        if a.verification_status == "rejected"
    ]
    if not retry_pairs:
        return None
    return sum(1 for _, nxt in retry_pairs if nxt.compiled is True) / len(retry_pairs)


def _perseveration_episode(checks: list[CheckEvidence]) -> tuple[int, int] | None:
    i = 0
    while i < len(checks):
        current = " ".join(checks[i].code.split())
        if not current or checks[i].verification_status != "rejected":
            i += 1
            continue
        j = i + 1
        while (
            j < len(checks)
            and checks[j].verification_status == "rejected"
            and " ".join(checks[j].code.split()) == current
        ):
            j += 1
        if j - i >= 3:
            return checks[i].call_seq, checks[j - 1].call_seq
        i = max(i + 1, j)
    return None


def label_reasoner(events: list[TraceEvent], reference: TaskReference) -> str:
    text = "\n".join(
        event.payload.get("text", "") or ""
        for event in events
        if event.agent_role is AgentRole.REASONER and event.event_type is EventType.MESSAGE
    ).lower()
    if not text:
        return "no_real_strategy"
    key_hits = sum(1 for key in reference.key_objects if key.lower() in text)
    if key_hits >= 2:
        return "valid_strategy"
    if key_hits == 1 or "strategy" in text or "plan" in text:
        return "partially_valid_strategy"
    return "no_real_strategy"


def derive_review_record(
    path: Path, record: ProblemRecord, events: list[TraceEvent]
) -> dict[str, Any]:
    """Derive the evidence skeleton reviewed for one immutable raw trial."""
    checks = check_evidence(events, record)
    candidate = select_candidate(checks, events)
    outcome = workflow_outcome(checks, events, candidate)
    decision, decision_seq = _final_critic_decision(events)
    approved = decision == "approve"
    submission_accepted = bool(
        approved
        and candidate
        and candidate.candidate_kind in {"exact_target", "statement_drift"}
        and _successful(candidate)
    )

    target_successes = [
        check
        for check in checks
        if _successful(check) and check.candidate_kind in {"exact_target", "statement_drift"}
    ]
    incidents: list[dict[str, Any]] = []
    for check in checks:
        if check.verification_status not in {"rejected", "infrastructure_unknown"}:
            continue
        if check.verification_status == "infrastructure_unknown":
            symptom, labels, confidence = (
                "opaque_compiler_failure",
                ["tooling_diagnostic_unknown"],
                "not_observable",
            )
        else:
            symptom, labels, confidence = _symptom_for_failure(check.diagnostic)
        later_target_success = any(c.call_seq > check.call_seq for c in target_successes)
        incidents.append(
            {
                "event_seq": check.call_seq,
                "result_event_seq": check.result_seq,
                "role": check.role,
                "symptom_code": symptom,
                "causal_labels": labels,
                "recovered": later_target_success,
                "confidence": confidence,
                "evidence": _compact(check.diagnostic, limit=240) or "Lean returned no diagnostic text.",
            }
        )

    for check in checks:
        has_sorry = check.sorry_free is False or _contains_sorry(check.code)
        if check.compiled is True and has_sorry:
            incidents.append(
                {
                    "event_seq": check.call_seq,
                    "result_event_seq": check.result_seq,
                    "role": check.role,
                    "symptom_code": "sorry_pseudo_pass",
                    "causal_labels": ["sorry_pseudo_pass", "incomplete_verification"],
                    "recovered": False,
                    "confidence": "confirmed",
                    "evidence": "Compiled candidate contains sorry/admit or was not reported sorry-free.",
                }
            )

    if candidate and candidate.candidate_kind == "statement_drift":
        drift_labels = ["statement_drift"]
        if submission_accepted:
            drift_labels.extend(["incorrect_verification", "missed_statement_drift"])
        incidents.append(
            {
                "event_seq": candidate.call_seq,
                "result_event_seq": candidate.result_seq,
                "role": candidate.role,
                "symptom_code": "statement_drift",
                "causal_labels": drift_labels,
                "recovered": False,
                "confidence": "confirmed",
                "evidence": (
                    "The approved compiled theorem declaration does not preserve the supplied target header."
                    if submission_accepted
                    else "The compiled theorem declaration does not preserve the supplied target header."
                ),
            }
        )

    if outcome == "approved_after_failed_recheck":
        incidents.append(
            {
                "event_seq": decision_seq,
                "result_event_seq": None,
                "role": AgentRole.CRITIC.value,
                "symptom_code": "critic_approval_after_failed_recheck",
                "causal_labels": ["incorrect_verification", "critic_masking", "missed_statement_drift"],
                "recovered": False,
                "confidence": "confirmed",
                "evidence": "Critic approved after its later relevant check failed.",
            }
        )

    if outcome == "target_verified_unapproved":
        incidents.append(
            {
                "event_seq": events[-1].seq,
                "result_event_seq": None,
                "role": events[-1].agent_role.value,
                "symptom_code": "target_unreviewed",
                "causal_labels": ["missing_critic_review", "incomplete_verification"],
                "recovered": False,
                "confidence": "strong",
                "evidence": "An exact-target check succeeded, but no critic approval was logged.",
            }
        )

    if outcome == "regressed_after_success":
        last_exact = max(
            c.call_seq for c in checks if _successful(c) and c.candidate_kind == "exact_target"
        )
        regressed = next(
            c
            for c in checks
            if c.verification_status in {"rejected", "infrastructure_unknown"}
            and c.call_seq > last_exact
        )
        incidents.append(
            {
                "event_seq": regressed.call_seq,
                "result_event_seq": regressed.result_seq,
                "role": regressed.role,
                "symptom_code": "regression_after_success",
                "causal_labels": ["regression_after_success"],
                "recovered": False,
                "confidence": "confirmed",
                "evidence": "A later target attempt failed after an exact-target check had succeeded.",
            }
        )

    if outcome == "terminated_without_target_check":
        incidents.append(
            {
                "event_seq": events[-1].seq,
                "result_event_seq": None,
                "role": events[-1].agent_role.value,
                "symptom_code": "target_not_attempted",
                "causal_labels": ["premature_termination", "no_actionable_plan"],
                "recovered": False,
                "confidence": "tentative",
                "evidence": "The trace ended without a check_lean call for the supplied theorem.",
            }
        )

    episode = _perseveration_episode(checks)
    if episode:
        incidents.append(
            {
                "event_seq": episode[0],
                "result_event_seq": None,
                "role": AgentRole.ENGINEER.value,
                "symptom_code": "other_lean_diagnostic",
                "causal_labels": ["perseveration"],
                "recovered": False,
                "confidence": "confirmed",
                "evidence": f"Identical failing code was submitted at least three times through seq {episode[1]}.",
            }
        )

    incidents.sort(key=lambda item: (item["event_seq"], item["symptom_code"]))
    critical = next((item for item in incidents if not item["recovered"]), None)
    recovered_seqs = sorted({item["event_seq"] for item in incidents if item["recovered"]})
    symptom_codes = sorted({item["symptom_code"] for item in incidents})
    labels = sorted({label for item in incidents for label in item["causal_labels"]})

    if critical is None:
        review_confidence = "strong"
    elif critical["confidence"] == "not_observable":
        review_confidence = "tentative"
    else:
        review_confidence = critical["confidence"]

    failed_count = sum(check.verification_status == "rejected" for check in checks)
    reasoner_label = label_reasoner(events, TASK_REFERENCES[record.id])
    critic_checks = [check for check in checks if check.role == AgentRole.CRITIC.value]
    graph = build_graph(events)
    remaining = set(graph.nodes)
    component_count = 0
    while remaining:
        component_count += 1
        stack = [remaining.pop()]
        while stack:
            node = stack.pop()
            neighbours = set(graph.predecessors(node)) | set(graph.successors(node))
            unseen = neighbours & remaining
            remaining -= unseen
            stack.extend(unseen)
    result_ids = set(_result_map(events))
    unpaired_tool_call_seqs = []
    for event in events:
        if event.event_type is not EventType.TOOL_CALL:
            continue
        if any(call.get("id") not in result_ids for call in event.payload.get("tool_calls") or []):
            unpaired_tool_call_seqs.append(event.seq)
    downstream: list[str] = []
    if not approved:
        downstream.append("workflow_ended_without_critic_approval")
    if candidate is None or candidate.candidate_kind == "helper_or_probe":
        downstream.append("no_verified_target_candidate")
    if candidate and candidate.candidate_kind == "statement_drift":
        downstream.append("compiled_changed_statement_not_original_contract")

    return {
        "schema_version": "1.0.0",
        "trial_id": path.stem,
        "task_id": record.id,
        "source_file": path.as_posix(),
        "source_sha256": _sha256(path),
        "review_status": "agent_reviewed",
        "review_confidence": review_confidence,
        "candidate": {
            "kind": candidate.candidate_kind if candidate else "none",
            "event_seq": candidate.call_seq if candidate else None,
            "result_event_seq": candidate.result_seq if candidate else None,
            "trace_compiled": candidate.compiled if candidate else None,
            "trace_sorry_free": candidate.sorry_free if candidate else None,
            "statement_match": candidate.statement_match if candidate else "none",
            "workflow_approved": approved,
            "submission_accepted": submission_accepted,
            "kernel_status": "not_run",
        },
        "workflow": {
            "outcome": outcome,
            "declared_success": approved,
            "approval_event_seq": decision_seq if approved else None,
            "critic_check_count": len(critic_checks),
        },
        "symptom_codes": symptom_codes,
        "causal_labels": labels,
        "incidents": incidents,
        "critical_failure": critical,
        "recovered_failure_seqs": recovered_seqs,
        "downstream_effects": downstream,
        "assessments": {
            "reasoner": f"{reasoner_label}: compared against the task-specific mathematical strategy.",
            "engineer": (
                f"{failed_count} failed target/probe checks; candidate="
                f"{candidate.candidate_kind if candidate else 'none'}."
            ),
            "critic": (
                f"approval={approved}; independent check_lean calls by critic={len(critic_checks)}."
            ),
        },
        "trace_evidence": {
            "event_count": len(events),
            "graph_component_count": component_count,
            "graph_interpretation": (
                "disconnected_event_timeline" if component_count > 1 else "linear_event_timeline"
            ),
            "anchor_count": sum(event.anchor is not None for event in events),
            "unpaired_tool_call_seqs": unpaired_tool_call_seqs,
        },
        "task_diagnosis": TASK_DIAGNOSES[record.id],
    }


def _validate_review(
    review: dict[str, Any],
    path: Path,
    meta_trial_id: str,
    meta_task_id: str,
    event_seqs: set[int],
    result_event_seqs: set[int],
) -> None:
    def require_event_seq(seq: Any, field: str, *, result: bool = False) -> None:
        allowed = result_event_seqs if result else event_seqs
        if seq is not None and (
            not isinstance(seq, int) or isinstance(seq, bool) or seq not in allowed
        ):
            raise ValueError(f"{meta_trial_id}: {field} references missing event seq {seq}")

    def checked_codes(field: str, allowed: frozenset[str]) -> set[str]:
        values = review.get(field)
        if not isinstance(values, list):
            raise ValueError(f"{meta_trial_id}: {field} must be a list")
        bad = set(values) - allowed
        if bad:
            raise ValueError(f"{meta_trial_id}: invalid {field} {sorted(bad)}")
        return set(values)

    if review.get("schema_version") != "1.0.0":
        raise ValueError(f"{meta_trial_id}: unsupported review schema")
    if review.get("trial_id") != meta_trial_id:
        raise ValueError(f"{meta_trial_id}: review trial_id mismatch")
    if review.get("task_id") != meta_task_id:
        raise ValueError(f"{meta_trial_id}: review task_id mismatch")
    source_file = review.get("source_file")
    if not isinstance(source_file, str) or Path(source_file).name != path.name:
        raise ValueError(f"{meta_trial_id}: review source_file mismatch")
    if review.get("source_sha256") != _sha256(path):
        raise ValueError(f"{meta_trial_id}: raw trace hash changed since review")
    if review.get("review_status") != "agent_reviewed":
        raise ValueError(f"{meta_trial_id}: review_status must be agent_reviewed")
    if review.get("review_confidence") not in CONFIDENCE_LEVELS:
        raise ValueError(f"{meta_trial_id}: invalid review confidence")
    candidate = review.get("candidate") or {}
    if candidate.get("kind") not in CANDIDATE_KINDS:
        raise ValueError(f"{meta_trial_id}: invalid candidate kind")
    if candidate.get("statement_match") not in STATEMENT_MATCHES:
        raise ValueError(f"{meta_trial_id}: invalid statement match")
    workflow = review.get("workflow") or {}
    if workflow.get("outcome") not in WORKFLOW_OUTCOMES:
        raise ValueError(f"{meta_trial_id}: invalid workflow outcome")
    require_event_seq(candidate.get("event_seq"), "candidate.event_seq")
    require_event_seq(
        candidate.get("result_event_seq"), "candidate.result_event_seq", result=True
    )
    require_event_seq(workflow.get("approval_event_seq"), "workflow.approval_event_seq")
    if not isinstance(candidate.get("submission_accepted"), bool):
        raise ValueError(f"{meta_trial_id}: submission_accepted must be boolean")

    top_symptoms = checked_codes("symptom_codes", SYMPTOM_CODES)
    top_causes = checked_codes("causal_labels", CAUSAL_LABELS)
    incidents = review.get("incidents")
    if not isinstance(incidents, list):
        raise ValueError(f"{meta_trial_id}: incidents must be a list")
    valid_roles = {role.value for role in AgentRole}
    for incident in incidents:
        if not isinstance(incident, dict):
            raise ValueError(f"{meta_trial_id}: incident must be an object")
        if incident.get("symptom_code") not in SYMPTOM_CODES:
            raise ValueError(f"{meta_trial_id}: invalid symptom code")
        if incident.get("confidence") not in CONFIDENCE_LEVELS:
            raise ValueError(f"{meta_trial_id}: invalid incident confidence")
        if incident.get("role") not in valid_roles:
            raise ValueError(f"{meta_trial_id}: invalid incident role")
        require_event_seq(incident.get("event_seq"), "incident.event_seq")
        require_event_seq(
            incident.get("result_event_seq"), "incident.result_event_seq", result=True
        )
        bad = set(incident.get("causal_labels") or []) - CAUSAL_LABELS
        if bad:
            raise ValueError(f"{meta_trial_id}: invalid causal labels {sorted(bad)}")

    incident_symptoms = {incident["symptom_code"] for incident in incidents}
    incident_causes = {
        label for incident in incidents for label in incident.get("causal_labels") or []
    }
    if top_symptoms != incident_symptoms:
        raise ValueError(f"{meta_trial_id}: top-level symptom_codes do not match incidents")
    if top_causes != incident_causes:
        raise ValueError(f"{meta_trial_id}: top-level causal_labels do not match incidents")

    critical = review.get("critical_failure")
    expected_critical = next(
        (incident for incident in incidents if incident.get("recovered") is False), None
    )
    if critical != expected_critical:
        raise ValueError(f"{meta_trial_id}: critical_failure is not the first unrecovered incident")
    if critical is not None:
        require_event_seq(critical.get("event_seq"), "critical_failure.event_seq")
        require_event_seq(
            critical.get("result_event_seq"),
            "critical_failure.result_event_seq",
            result=True,
        )
        if critical.get("symptom_code") not in SYMPTOM_CODES:
            raise ValueError(f"{meta_trial_id}: invalid critical_failure symptom code")
        if set(critical.get("causal_labels") or []) - CAUSAL_LABELS:
            raise ValueError(f"{meta_trial_id}: invalid critical_failure causal labels")

    recovered = review.get("recovered_failure_seqs")
    if not isinstance(recovered, list):
        raise ValueError(f"{meta_trial_id}: recovered_failure_seqs must be a list")
    for seq in recovered:
        require_event_seq(seq, "recovered_failure_seqs")
    expected_recovered = sorted(
        {incident["event_seq"] for incident in incidents if incident.get("recovered") is True}
    )
    if recovered != expected_recovered:
        raise ValueError(f"{meta_trial_id}: recovered_failure_seqs do not match incidents")


def load_reviews(
    review_path: Path, trace_paths: list[Path], *, allow_partial: bool = False
) -> dict[str, dict[str, Any]]:
    if not review_path.exists():
        raise FileNotFoundError(f"Required review source not found: {review_path}")
    reviews: dict[str, dict[str, Any]] = {}
    for line_no, line in enumerate(review_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        review = json.loads(line)
        trial_id = review.get("trial_id")
        if not trial_id or trial_id in reviews:
            raise ValueError(f"{review_path}:{line_no}: duplicate or missing trial_id")
        reviews[trial_id] = review

    trace_ids = {path.stem for path in trace_paths}
    review_ids = set(reviews)
    if allow_partial:
        missing = trace_ids - review_ids
        if missing:
            raise ValueError(f"Reviews missing selected trials: {sorted(missing)}")
    elif trace_ids != review_ids:
        raise ValueError(
            f"Review/trace ID mismatch: missing={sorted(trace_ids-review_ids)}, "
            f"extra={sorted(review_ids-trace_ids)}"
        )
    for path in trace_paths:
        meta, events = read_trial(path)
        _validate_review(
            reviews[meta.trial_id],
            path,
            meta.trial_id,
            meta.task_id,
            {event.seq for event in events},
            {
                event.seq
                for event in events
                if event.event_type is EventType.EXECUTION_RESULT
            },
        )
    return {trial_id: reviews[trial_id] for trial_id in trace_ids}


class _MemoizingCompiler:
    """Reuse deterministic kernel verdicts for identical Lean source.

    The 100-trial batch contains many repeated proof candidates.  A fresh Lean
    process is still used for every *distinct* source string, while exact
    duplicates reuse the verdict already obtained in this analyzer run.
    """

    def __init__(self, compiler: Any) -> None:
        self._compiler = compiler
        self._cache: dict[str, Any] = {}

    def check(self, code: str) -> Any:
        if code not in self._cache:
            self._cache[code] = self._compiler.check(code)
        return self._cache[code]


def _try_compiler(dataset_root: Path, kernel: str):
    if kernel == "off":
        return None, "off"
    try:
        from traj_eval.tools.lean_cli_compiler import LeanCliCompiler

        return _MemoizingCompiler(LeanCliCompiler(dataset_root)), "available"
    except Exception as exc:  # noqa: BLE001 - converted to an explicit claim gate
        status = f"unavailable:{type(exc).__name__}"
        if kernel == "required":
            raise SystemExit(
                "Kernel validation is required but the pinned Lean toolchain/build is unavailable "
                f"({status}). Install the dataset toolchain/cache or explicitly choose --kernel auto/off."
            ) from exc
        return None, status


def _kernel_result_status(result: Any) -> str:
    status = getattr(result, "verification_status", None)
    if status in {"accepted", "rejected", "infrastructure_unknown"}:
        return status
    return "accepted" if result.compiled else "rejected"


def _safe_kernel_check(compiler: Any, code: str) -> tuple[Any | None, str | None]:
    try:
        result = compiler.check(code)
    except (TimeoutError, subprocess.TimeoutExpired, OSError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if _kernel_result_status(result) == "infrastructure_unknown":
        error = getattr(result, "infrastructure_error", None) or getattr(result, "summary", None)
        return None, str(error or "Lean validation infrastructure returned no verdict")
    return result, None


def _target_declaration_name(code: str, record: ProblemRecord) -> str | None:
    target_name = _theorem_name(record.statement)
    if target_name is None:
        return None
    return target_name if any(name == target_name for name, _ in _declaration_headers(code)) else None


def _exact_target_body(code: str, record: ProblemRecord) -> str | None:
    return target_proof_body(code, record.statement)


def _exact_target_probe(code: str, record: ProblemRecord) -> str | None:
    """Replay the proof body under the dataset header in its checked prelude.

    Imports are proof dependencies, not part of the theorem statement.  Keep
    the candidate's already-compiled imports and helper declarations, while
    replacing only the target declaration header with the exact dataset one.
    """
    target_name = _theorem_name(record.statement)
    body = _exact_target_body(code, record)
    if target_name is None or body is None:
        return None
    declaration = re.search(
        rf"\b(?:theorem|lemma)\s+{re.escape(target_name)}(?=\s|\(|\{{|\[|:)",
        code,
    )
    if declaration is None:
        return None
    return f"{code[: declaration.start()]}{record.statement} := {body}"


def _infrastructure_validation(
    error: str,
    *,
    record: ProblemRecord,
    fail_closed: bool,
    placeholders: tuple[str, ...],
) -> CandidateValidation:
    if fail_closed:
        raise RuntimeError(f"Kernel validation failed for {record.id}: {error}")
    return CandidateValidation(
        "infrastructure_unknown",
        None,
        False if placeholders else None,
        None,
        None,
        error=error,
        prohibited_placeholders=placeholders,
    )


def _candidate_validation(
    candidate: CheckEvidence | None,
    record: ProblemRecord,
    compiler,
    *,
    kernel_status: str,
    fail_closed: bool,
) -> CandidateValidation:
    if compiler is None:
        return CandidateValidation("not_evaluated", None, None, None, None)
    if candidate is None or candidate.candidate_kind == "helper_or_probe":
        return CandidateValidation("not_evaluated", None, None, None, None)
    placeholders = tuple(prohibited_placeholders(candidate.code))
    direct, error = _safe_kernel_check(compiler, candidate.code)
    if direct is None:
        return _infrastructure_validation(
            error or "candidate check returned no verdict",
            record=record,
            fail_closed=fail_closed,
            placeholders=placeholders,
        )

    final_compiles = _kernel_result_status(direct) == "accepted"
    final_sorry_free = False if placeholders else direct.sorry_free
    statement_preserved: bool | None = False
    axiom_clean: bool | None = None
    extra_axioms: tuple[str, ...] = ()
    errors: list[str] = []

    if candidate.statement_match == "exact" and not placeholders:
        target_source = _exact_target_probe(candidate.code, record)
        if target_source is None:
            statement_preserved = False
        else:
            target_probe, target_error = _safe_kernel_check(
                compiler, target_source
            )
            if target_probe is None:
                return _infrastructure_validation(
                    target_error or "target statement check returned no verdict",
                    record=record,
                    fail_closed=fail_closed,
                    placeholders=placeholders,
                )
            statement_preserved = bool(
                _kernel_result_status(target_probe) == "accepted" and target_probe.sorry_free
            )

    declaration_name = _target_declaration_name(candidate.code, record)
    if final_compiles and declaration_name:
        extra, audit_error = _axiom_diff(
            candidate.code,
            declaration_name,
            STANDARD_AXIOMS,
            compiler,
        )
        if extra is None:
            return _infrastructure_validation(
                audit_error or "axiom audit returned no verdict",
                record=record,
                fail_closed=fail_closed,
                placeholders=placeholders,
            )
        extra_axioms = tuple(extra)
        axiom_clean = not extra_axioms
    elif final_compiles:
        errors.append("target theorem declaration was not found for axiom audit")

    verdicts = (final_compiles, final_sorry_free, statement_preserved, axiom_clean)
    status = "accepted" if all(value is True for value in verdicts) else "rejected"
    return CandidateValidation(
        status,
        final_compiles,
        final_sorry_free,
        statement_preserved,
        axiom_clean,
        extra_axioms,
        "; ".join(errors) or None,
        placeholders,
    )


def _validator_outcome(
    review: dict[str, Any], validation: CandidateValidation
) -> tuple[str, str, str]:
    candidate = review["candidate"]
    approved = candidate["submission_accepted"]
    kind = candidate["kind"]
    verdicts = (
        validation.final_proof_compiles,
        validation.final_proof_sorry_free,
        validation.statement_preserved,
        validation.axiom_clean,
    )
    if validation.status in {"accepted", "rejected"}:
        if all(value is True for value in verdicts):
            return "solved", "kernel_verified", "kernel_confirmed"
        if approved and any(value is False for value in verdicts):
            return "silent_failure", "kernel_rejected", "kernel_rejected"
        return "unsolved", "kernel_rejected", "kernel_rejected"
    if validation.status == "infrastructure_unknown":
        return "validation_unknown", "infrastructure_unknown", "unresolved"
    if kind == "statement_drift":
        return "statement_drift", "trace_changed_statement", "provisional_trace_only"
    if kind == "exact_target" and approved:
        return "trace_verified", "trace_exact_target_approved", "provisional_trace_only"
    if kind == "exact_target":
        return "trace_verified_unreviewed", "trace_exact_target_unreviewed", "provisional_trace_only"
    if kind == "helper_or_probe":
        return "unsolved", "trace_helper_only", "provisional_trace_only"
    return "unsolved", "no_target_evidence", "provisional_trace_only"


def _legacy_labels(review: dict[str, Any], events: list[TraceEvent]) -> tuple[str, str, str, str]:
    critical = review.get("critical_failure")
    incidents = review.get("incidents") or []
    if critical and critical.get("role") == AgentRole.ENGINEER.value:
        engineer = critical["symptom_code"]
    elif any(item.get("role") == AgentRole.ENGINEER.value for item in incidents):
        engineer = "recovered_errors"
    else:
        engineer = "no_unrecovered_engineer_failure"

    labels = set(review.get("causal_labels") or [])
    submission_accepted = review["candidate"]["submission_accepted"]
    if "incorrect_verification" in labels and submission_accepted:
        critic = "critic_false_accept"
    elif "missing_critic_review" in labels or not review["workflow"]["declared_success"]:
        critic = "critic_missing"
    elif submission_accepted and review["workflow"]["critic_check_count"]:
        critic = "critic_compile_checked"
    elif submission_accepted:
        critic = "critic_approval_without_recheck"
    else:
        critic = "critic_missing"

    outcome = review["workflow"]["outcome"]
    if "critic_masking" in labels:
        global_pattern = "critic_masking"
    elif "perseveration" in labels:
        global_pattern = "perseveration"
    elif outcome == "regressed_after_success":
        global_pattern = "regression_after_success"
    elif outcome == "approved_after_productive_revision":
        global_pattern = "productive_revision"
    elif outcome == "approved_direct":
        global_pattern = "direct_success"
    elif outcome == "target_verified_unapproved":
        global_pattern = "incomplete_verification"
    elif outcome.startswith("approved_"):
        global_pattern = "statement_fidelity_failure"
    else:
        global_pattern = "incomplete_workflow"
    stage = critical.get("role", "global") if critical else "none"
    return engineer, critic, global_pattern, stage


def _presentation_takeaway(
    outcome: str, verification_level: str, claim_status: str, review: dict[str, Any]
) -> str:
    if claim_status == "kernel_confirmed":
        finding = "Kernel-confirmed exact-target, sorry-free, axiom-clean proof."
    elif claim_status == "kernel_rejected":
        finding = "Independent kernel validation rejected at least one correctness requirement."
    elif outcome == "statement_drift":
        finding = "Trace-only evidence confirms a compiled changed statement, not the original contract."
    elif outcome == "trace_verified":
        finding = "Provisional trace-only exact-target approval; independent kernel validation did not run."
    elif outcome == "trace_verified_unreviewed":
        finding = "Provisional exact-target trace check without a completed critic review."
    else:
        finding = "No accepted exact-target proof is established by this trace."
    critical = review.get("critical_failure")
    detail = f" Critical unrecovered incident: {critical['symptom_code']} at seq {critical['event_seq']}." if critical else ""
    return f"{finding}{detail} {PROPOSAL_GROUNDING} {MD_GROUNDING} verification={verification_level}."


def build_rows(
    trace_paths: list[Path],
    *,
    dataset_root: Path,
    reviews_by_trial: dict[str, dict[str, Any]],
    compiler=None,
    kernel_status: str = "off",
    fail_closed: bool = False,
) -> list[dict[str, str]]:
    records = {record.id: record for record in load_dataset(dataset_root, difficulty="easy")}
    snapshot = analysis_snapshot_sha256(trace_paths)
    rows: list[dict[str, str]] = []
    for path in trace_paths:
        meta, events = read_trial(path)
        record = records.get(meta.task_id)
        if record is None:
            raise KeyError(f"Trace {path} references unknown task_id {meta.task_id}")
        review = reviews_by_trial[meta.trial_id]
        derived = derive_review_record(path, record, events)
        for section, fields in {
            "candidate": (
                "kind",
                "event_seq",
                "statement_match",
                "workflow_approved",
                "submission_accepted",
            ),
            "workflow": ("outcome", "declared_success", "approval_event_seq"),
        }.items():
            for field in fields:
                if review[section].get(field) != derived[section].get(field):
                    raise ValueError(
                        f"{meta.trial_id}: reviewed {section}.{field} no longer matches raw evidence"
                    )
        checks = check_evidence(events, record)
        candidate = select_candidate(checks, events)
        validation = _candidate_validation(
            candidate,
            record,
            compiler,
            kernel_status=kernel_status,
            fail_closed=fail_closed,
        )
        outcome, verification_level, claim_status = _validator_outcome(review, validation)
        engineer, critic, global_pattern, stage = _legacy_labels(review, events)
        reference = TASK_REFERENCES[record.id]
        check_count, search_count = _tool_counts(events)
        retry_rate = _retry_success_rate(checks)
        graph = build_graph(events)
        _ = causal_order(events)
        if graph.number_of_nodes() != len(events):
            raise RuntimeError(f"Graph/event mismatch in {path}")
        anchored = sum(event.anchor is not None for event in events)
        critical = review.get("critical_failure") or {}
        has_explicit_final = any(
            event.agent_role is AgentRole.ENGINEER
            and event.event_type is EventType.MESSAGE
            and event.payload.get("has_final")
            for event in events
        )
        submission_source = (
            "approved_verified_target"
            if review["candidate"]["submission_accepted"]
            else "explicit_final"
            if has_explicit_final
            else "none"
        )
        rows.append(
            {
                "task_id": record.id,
                "trial_id": meta.trial_id,
                "trial_number": str(parse_trial_number(path)),
                "source": record.source,
                "difficulty": record.difficulty,
                "source_sha256": review["source_sha256"],
                "analysis_snapshot_sha256": snapshot,
                "review_status": review["review_status"],
                "review_confidence": review["review_confidence"],
                "math_question": _compact(record.informal, limit=220),
                "naive_human_strategy": reference.naive_human_strategy,
                "domain_specific_LLM_strategy": reference.domain_specific_llm_strategy,
                "reasoner_strategy_label": label_reasoner(events, reference),
                "engineer_failure_label": engineer,
                "critic_label": critic,
                "global_graph_pattern": global_pattern,
                "validator_outcome": outcome,
                "verification_level": verification_level,
                "kernel_status": kernel_status,
                "validation_status": validation.status,
                "validation_error": validation.error or "",
                "claim_status": claim_status,
                "candidate_kind": review["candidate"]["kind"],
                "candidate_event_seq": str(review["candidate"]["event_seq"] or ""),
                "statement_match": review["candidate"]["statement_match"],
                "workflow_outcome": review["workflow"]["outcome"],
                "submission_source": submission_source,
                "submission_accepted": _bool(review["candidate"]["submission_accepted"]),
                "symptom_codes": "|".join(review["symptom_codes"]),
                "error_labels": "|".join(review["causal_labels"]),
                "incident_count": str(len(review["incidents"])),
                "critical_failure_seq": str(critical.get("event_seq", "")),
                "critical_failure_label": critical.get("symptom_code", "none"),
                "critical_failure_role": critical.get("role", "none"),
                "recovered_failure_count": str(len(review["recovered_failure_seqs"])),
                "first_failure_stage": stage,
                "n_tool_calls": str(check_count + search_count),
                "n_check_lean_calls": str(check_count),
                "n_search_lemma_calls": str(search_count),
                "n_failed_compiles": str(
                    sum(check.verification_status == "rejected" for check in checks)
                ),
                "n_infrastructure_unknown_checks": str(
                    sum(check.verification_status == "infrastructure_unknown" for check in checks)
                ),
                "retry_success_rate": "none" if retry_rate is None else f"{retry_rate:.6f}",
                "perseverated": _bool("perseveration" in review["causal_labels"]),
                "declared_success": _bool(review["workflow"]["declared_success"]),
                "final_proof_compiles": _bool(validation.final_proof_compiles),
                "final_proof_sorry_free": _bool(validation.final_proof_sorry_free),
                "statement_preserved": _bool(validation.statement_preserved),
                "axiom_clean": _bool(validation.axiom_clean),
                "prohibited_placeholders": (
                    "|".join(validation.prohibited_placeholders)
                    or ("sorry_or_admit" if "sorry_pseudo_pass" in review["symptom_codes"] else "none")
                ),
                "anchor_coverage": f"{anchored}/{len(events)}",
                "presentation_takeaway": _presentation_takeaway(
                    outcome, verification_level, claim_status, review
                ),
            }
        )
    return rows


def _tool_name(event: TraceEvent) -> str | None:
    calls = event.payload.get("tool_calls") or []
    return calls[0].get("name") if calls else None


def _code_from_tool_call(event: TraceEvent) -> str | None:
    for call in event.payload.get("tool_calls") or []:
        if call.get("name") != "check_lean":
            continue
        parsed = _json_loads_or_none(call.get("arguments"))
        return parsed.get("code") if isinstance(parsed, dict) else None
    return None


def _event_snippet(event: TraceEvent) -> str:
    code = _code_from_tool_call(event)
    if code:
        return code
    if event.event_type is EventType.TOOL_CALL:
        calls = event.payload.get("tool_calls") or []
        return (calls[0].get("arguments") if calls else "") or ""
    return event.payload.get("text", "") or ""


def _compiled_by_seq(events: list[TraceEvent]) -> dict[int, bool | None]:
    verdicts: dict[int, bool | None] = {}
    for result_seq, parsed in _result_map(events).values():
        verdicts[result_seq] = parsed.get("compiled")
    return verdicts


def _graph_payload(events: list[TraceEvent]) -> dict[str, Any]:
    graph = build_graph(events)
    compiled_by_seq = _compiled_by_seq(events)
    nodes = []
    for event in events:
        compiled = compiled_by_seq.get(event.seq)
        status = "pass" if compiled is True else "fail" if compiled is False else "neutral"
        if event.payload.get("decision") == "approve":
            status = "approve"
        elif event.payload.get("decision") == "reject":
            status = "reject"
        nodes.append(
            {
                "id": event.event_id,
                "seq": event.seq,
                "role": event.agent_role.value,
                "type": event.event_type.value,
                "tool": _tool_name(event),
                "decision": event.payload.get("decision"),
                "handoff_target": event.payload.get("handoff_target"),
                "status": status,
                "anchor": event.anchor.model_dump(mode="json") if event.anchor else None,
                "label": f"{event.seq}: {event.agent_role.value}",
            }
        )
    return {
        "kind": "event_timeline_with_declared_causal_edges",
        "causal_claim": "descriptive_only",
        "nodes": nodes,
        "edges": [{"source": source, "target": target} for source, target in graph.edges()],
    }


def build_trace_documents(
    trace_paths: list[Path],
    *,
    dataset_root: Path,
    rows_by_trial: dict[str, dict[str, str]],
    reviews_by_trial: dict[str, dict[str, Any]],
    expected_count: int | None = None,
) -> list[dict[str, Any]]:
    records = {record.id: record for record in load_dataset(dataset_root, difficulty="easy")}
    docs: list[dict[str, Any]] = []
    for path in trace_paths:
        meta, events = read_trial(path)
        record = records.get(meta.task_id)
        if record is None:
            continue
        row = rows_by_trial[meta.trial_id]
        review = reviews_by_trial[meta.trial_id]
        checks = check_evidence(events, record)
        candidate = select_candidate(checks, events)
        timeline = [
            {
                "event_id": event.event_id,
                "seq": event.seq,
                "role": event.agent_role.value,
                "type": event.event_type.value,
                "caused_by": event.caused_by,
                "tool": _tool_name(event),
                "decision": event.payload.get("decision"),
                "handoff_target": event.payload.get("handoff_target"),
                "anchor": event.anchor.model_dump(mode="json") if event.anchor else None,
                "text": _compact(_public_text(_event_snippet(event)), limit=5000),
                "lean_code": _code_from_tool_call(event),
            }
            for event in events
        ]
        doc = {
                "task_id": record.id,
                "trial_id": meta.trial_id,
                "trial_number": parse_trial_number(path),
                "source": record.source,
                "difficulty": record.difficulty,
                "source_sha256": review["source_sha256"],
                "analysis_snapshot_sha256": row["analysis_snapshot_sha256"],
                "review_sha256": _review_sha256(review),
                "informal": record.informal,
                "formal_statement": record.statement,
                "submitted_code": candidate.code if candidate and review["candidate"]["workflow_approved"] else None,
                "accepted_candidate_code": candidate.code if candidate else None,
                "declared_success": review["workflow"]["declared_success"],
                "n_tool_calls": int(row["n_tool_calls"]),
                "n_check_lean_calls": int(row["n_check_lean_calls"]),
                "n_search_lemma_calls": int(row["n_search_lemma_calls"]),
                "n_failed_compiles": int(row["n_failed_compiles"]),
                "n_infrastructure_unknown_checks": int(
                    row["n_infrastructure_unknown_checks"]
                ),
                "tool_calls": [
                    {
                        "seq": check.call_seq,
                        "result_seq": check.result_seq,
                        "role": check.role,
                        "compiled": check.compiled,
                        "sorry_free": check.sorry_free,
                        "verification_status": check.verification_status,
                        "candidate_kind": check.candidate_kind,
                        "statement_match": check.statement_match,
                        "diagnostic": check.diagnostic,
                        "code": check.code,
                    }
                    for check in checks
                ],
                "graph": _graph_payload(events),
                "diagnosis": {
                    "headline": row["presentation_takeaway"],
                    "status": row["claim_status"],
                    "verification": {
                        "validator_outcome": row["validator_outcome"],
                        "verification_level": row["verification_level"],
                        "kernel_status": row["kernel_status"],
                        "validation_status": row["validation_status"],
                        "validation_error": row["validation_error"] or None,
                        "final_proof_compiles": row["final_proof_compiles"],
                        "final_proof_sorry_free": row["final_proof_sorry_free"],
                        "statement_preserved": row["statement_preserved"],
                        "axiom_clean": row["axiom_clean"],
                        "prohibited_placeholders": (
                            []
                            if row["prohibited_placeholders"] in {"", "none"}
                            else row["prohibited_placeholders"].split("|")
                        ),
                    },
                    "candidate": {
                        **review["candidate"],
                        "kernel_status": row["kernel_status"],
                        "validation_status": row["validation_status"],
                        "submission_source": row["submission_source"],
                    },
                    "workflow": review["workflow"],
                    "symptom_codes": review["symptom_codes"],
                    "causal_labels": review["causal_labels"],
                    "incidents": review["incidents"],
                    "critical_failure": review["critical_failure"],
                    "recovered_failure_seqs": review["recovered_failure_seqs"],
                    "downstream_effects": review["downstream_effects"],
                    "assessments": review["assessments"],
                    "task_diagnosis": review["task_diagnosis"],
                    "trace_evidence": review["trace_evidence"],
                    "review_status": review["review_status"],
                    "review_confidence": review["review_confidence"],
                },
                "timeline": timeline,
            }
        docs.append(_public_value(doc))
    if expected_count is not None and len(docs) != expected_count:
        raise RuntimeError(f"Expected {expected_count} trace documents, built {len(docs)}")
    return docs


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(_public_value(row) for row in rows)


def _copy_for_report(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)


def _write_json(path: Path, docs: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_public_value(docs), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _summarize(rows: list[dict[str, str]]) -> str:
    outcomes = Counter(row["validator_outcome"] for row in rows)
    workflows = Counter(row["workflow_outcome"] for row in rows)
    outcome_text = ", ".join(f"{key}={value}" for key, value in sorted(outcomes.items()))
    workflow_text = ", ".join(f"{key}={value}" for key, value in sorted(workflows.items()))
    return f"wrote {len(rows)} rows; outcomes: {outcome_text}; workflows: {workflow_text}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--reviews", type=Path, default=DEFAULT_REVIEWS)
    parser.add_argument("--out-csv", type=Path, default=DEFAULT_OUT_CSV)
    parser.add_argument("--report-public-csv", type=Path, default=DEFAULT_REPORT_CSV)
    parser.add_argument("--report-public-json", type=Path, default=DEFAULT_REPORT_JSON)
    parser.add_argument("--expect-count", type=int, default=100)
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--kernel", choices=["required", "auto", "off"], default="required")
    args = parser.parse_args(argv)

    trace_paths = sorted(args.input_dir.glob("*.jsonl"))
    if len(trace_paths) != args.expect_count and not args.allow_partial:
        raise SystemExit(
            f"Expected {args.expect_count} traces in {args.input_dir}, found {len(trace_paths)}. "
            "Use --allow-partial for smoke tests."
        )
    reviews = load_reviews(args.reviews, trace_paths, allow_partial=args.allow_partial)
    compiler, compiler_status = _try_compiler(args.dataset_root, args.kernel)
    rows = build_rows(
        trace_paths,
        dataset_root=args.dataset_root,
        reviews_by_trial=reviews,
        compiler=compiler,
        kernel_status=compiler_status,
        fail_closed=args.kernel == "required",
    )
    rows_by_trial = {row["trial_id"]: row for row in rows}
    docs = build_trace_documents(
        trace_paths,
        dataset_root=args.dataset_root,
        rows_by_trial=rows_by_trial,
        reviews_by_trial=reviews,
        expected_count=None if args.allow_partial else args.expect_count,
    )
    if set(rows_by_trial) != {doc["trial_id"] for doc in docs}:
        raise RuntimeError("CSV/JSON trial IDs disagree")
    if len({row["analysis_snapshot_sha256"] for row in rows}) != (1 if rows else 0):
        raise RuntimeError("Rows do not share one analysis snapshot hash")

    _write_csv(args.out_csv, rows)
    _copy_for_report(args.out_csv, args.report_public_csv)
    _write_json(args.report_public_json, docs)
    print(f"{_summarize(rows)}; compiler={compiler_status}; csv={args.out_csv}")
    print(f"copied report CSV to {args.report_public_csv}")
    print(f"wrote trace JSON to {args.report_public_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
