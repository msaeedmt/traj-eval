"""Build the proposal/MD-grounded CSV for the 100 Lean easy traces.

The CSV is the canonical analysis artifact. The Vite report consumes a copied
version from ``docs/lean_easy_failure_report/public/data``.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from traj_eval.dataset.loader import ProblemRecord, load_dataset, to_lean_task
from traj_eval.detectors.perseveration import detect_perseveration
from traj_eval.metrics.lean.artifacts import TrialArtifacts, extract_artifacts
from traj_eval.metrics.lean.outcomes import classify_outcome
from traj_eval.metrics.lean.validator import TrialMetrics, validate
from traj_eval.trace_core.graph import build_graph, causal_order
from traj_eval.trace_core.schema import AgentRole, EventType, TraceEvent
from traj_eval.trace_core.storage import read_trial

DEFAULT_INPUT_DIR = Path("data/batch")
DEFAULT_DATASET_ROOT = Path("dataset/Lean")
DEFAULT_OUT_CSV = Path("data/analysis/lean_easy_failure_patterns.csv")
DEFAULT_REPORT_CSV = Path(
    "docs/lean_easy_failure_report/public/data/lean_easy_failure_patterns.csv"
)
DEFAULT_REPORT_JSON = Path(
    "docs/lean_easy_failure_report/public/data/lean_easy_failure_traces.json"
)

CSV_FIELDS = [
    "task_id",
    "trial_id",
    "trial_number",
    "source",
    "difficulty",
    "math_question",
    "naive_human_strategy",
    "domain_specific_LLM_strategy",
    "reasoner_strategy_label",
    "engineer_failure_label",
    "critic_label",
    "global_graph_pattern",
    "validator_outcome",
    "first_failure_stage",
    "n_tool_calls",
    "n_failed_compiles",
    "perseverated",
    "declared_success",
    "final_proof_compiles",
    "statement_preserved",
    "axiom_clean",
    "presentation_takeaway",
]

PROPOSAL_GROUNDING = (
    "Proposal grounding: README/NLP Lab O1 localization, O2 failure taxonomy, "
    "O3 early prediction. O3 is not claimed for this 100-trace slice."
)
MD_GROUNDING = (
    "MD grounding: docs/LEAN_FAILURE_ANALYSIS_GUIDE.md and "
    "docs/REPO_LAYOUT_RULES.md."
)


@dataclass(frozen=True)
class TaskReference:
    naive_human_strategy: str
    domain_specific_llm_strategy: str
    key_objects: tuple[str, ...]


TASK_REFERENCES: dict[str, TaskReference] = {
    "easy_fatem_011": TaskReference(
        "Expand the ring expression, split the conjunction, and use distributivity.",
        "Use ring/distributivity lemmas such as mul_sub and sub_mul; avoid changing the statement.",
        ("mul_sub", "sub_mul", "And.intro"),
    ),
    "easy_fatem_012": TaskReference(
        "Use the uniqueness of the integer-to-ring homomorphism.",
        "Use RingHom extensionality and Int.cast-style lemmas rather than inventing a new map API.",
        ("RingHom.ext", "Int.cast", "existsUnique"),
    ),
    "easy_fatem_019": TaskReference(
        "Connect the field structure of ZMod n with primality of n.",
        "Search for ZMod field/primality theorems and keep the iff direction faithful.",
        ("ZMod", "IsField", "Nat.Prime"),
    ),
    "easy_fatem_020": TaskReference(
        "In a field, every ideal is bottom or top; use an inverse for any nonzero element.",
        "Use Ideal and field inverse lemmas; do not weaken the ideal statement.",
        ("Ideal", "Field", "inv_mul_cancel"),
    ),
    "easy_fatem_041": TaskReference(
        "Relate the order of a product to the lcm of component orders.",
        "Use orderOf/product lemmas and check required commutativity hypotheses.",
        ("orderOf", "Nat.lcm", "Commute"),
    ),
    "easy_fatem_109": TaskReference(
        "Use no-zero-divisor cancellation to move from an equality of products to equality of factors.",
        "Use cancellation lemmas for rings without zero divisors; avoid assuming a field.",
        ("NoZeroDivisors", "mul_left_cancel", "mul_right_cancel"),
    ),
    "easy_fatem_111": TaskReference(
        "Convert Commute to a multiplication equality, expand both sides, and rewrite a^2 to zero.",
        "Use commute_iff_eq, mul_add/add_mul, mul_assoc, and simp/ring normalization with h.",
        ("Commute", "commute_iff_eq", "mul_add", "add_mul", "mul_assoc", "pow_two"),
    ),
    "easy_fatem_115": TaskReference(
        "Unpack transitivity for the inverse relation and apply the original transitivity in reversed order.",
        "Use Transitive/IsTrans definitions directly; avoid searching for a nonexistent special inverse lemma.",
        ("Transitive", "IsTrans", "swap", "inverse relation"),
    ),
    "easy_leancat_001": TaskReference(
        "Show two natural transformations are equal by extensionality and componentwise naturality.",
        "Use NatTrans.ext and naturality; keep category variables and universe context intact.",
        ("NatTrans.ext", "naturality", "Category.assoc"),
    ),
    "easy_leancat_002": TaskReference(
        "To prove a composed morphism is monic, cancel through the known monic factors.",
        "Use the Mono definition and cancellation lemmas for composition.",
        ("Mono", "cancel_mono", "Category.comp"),
    ),
}

WRONG_API_MARKERS = (
    "unknown identifier",
    "unknown constant",
    "unknown namespace",
    "does not exist",
    "nonexistent",
)


def parse_trial_number(path: Path | str) -> int:
    """Parse ``*_tN.jsonl`` trial filenames."""
    match = re.search(r"_t(\d+)\.jsonl$", Path(path).name)
    if not match:
        raise ValueError(f"Cannot parse trial number from {path}")
    return int(match.group(1))


def _compact(text: str | None, *, limit: int | None = None) -> str:
    value = " ".join((text or "").split())
    if limit is not None and len(value) > limit:
        return value[: limit - 3].rstrip() + "..."
    return value


def _bool(value: bool | None) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return "none"


def _role_text(events: Iterable[TraceEvent], role: AgentRole) -> str:
    parts = []
    for event in events:
        if event.agent_role is role and event.event_type is EventType.MESSAGE:
            parts.append(event.payload.get("text", "") or "")
    return "\n".join(parts)


def _result_text(events: Iterable[TraceEvent]) -> str:
    return "\n".join(
        (event.payload.get("text", "") or "")
        for event in events
        if event.event_type is EventType.EXECUTION_RESULT
    )


def _tool_names(events: Iterable[TraceEvent]) -> list[str]:
    names: list[str] = []
    for event in events:
        if event.event_type is not EventType.TOOL_CALL:
            continue
        for call in event.payload.get("tool_calls") or []:
            names.append(call.get("name") or "")
    return names


def _json_loads_or_none(text: str | None):
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _code_from_tool_call(event: TraceEvent) -> str | None:
    calls = event.payload.get("tool_calls") or []
    for call in calls:
        if call.get("name") != "check_lean":
            continue
        parsed = _json_loads_or_none(call.get("arguments"))
        if isinstance(parsed, dict):
            return parsed.get("code")
    return None


def _tool_name(event: TraceEvent) -> str | None:
    calls = event.payload.get("tool_calls") or []
    return calls[0].get("name") if calls else None


def _event_snippet(event: TraceEvent) -> str:
    if event.event_type is EventType.TOOL_CALL:
        code = _code_from_tool_call(event)
        if code:
            return code
        calls = event.payload.get("tool_calls") or []
        return (calls[0].get("arguments") if calls else "") or ""
    return event.payload.get("text", "") or ""


def _graph_payload(events: list[TraceEvent]) -> dict:
    graph = build_graph(events)
    compiled_by_seq = _compiled_by_seq(events)
    nodes = []
    for event in events:
        tool = _tool_name(event)
        compiled = compiled_by_seq.get(event.seq)
        status = "neutral"
        if compiled is True:
            status = "pass"
        elif compiled is False:
            status = "fail"
        elif event.payload.get("decision") == "approve":
            status = "approve"
        elif event.payload.get("decision") == "reject":
            status = "reject"
        nodes.append(
            {
                "id": event.event_id,
                "seq": event.seq,
                "role": event.agent_role.value,
                "type": event.event_type.value,
                "tool": tool,
                "decision": event.payload.get("decision"),
                "handoff_target": event.payload.get("handoff_target"),
                "status": status,
                "label": f"{event.seq}: {event.agent_role.value}",
            }
        )
    return {
        "nodes": nodes,
        "edges": [{"source": source, "target": target} for source, target in graph.edges()],
    }


def _compiled_by_seq(events: list[TraceEvent]) -> dict[int, bool | None]:
    """Best-effort compile verdict by result event seq for UI coloring."""
    import ast

    verdicts: dict[int, bool | None] = {}
    for event in events:
        if event.event_type is not EventType.EXECUTION_RESULT:
            continue
        verdict = None
        for response in event.payload.get("tool_responses") or []:
            content = response.get("content")
            if not content:
                continue
            try:
                parsed = ast.literal_eval(content)
            except (ValueError, SyntaxError):
                continue
            if isinstance(parsed, dict) and "compiled" in parsed:
                verdict = parsed.get("compiled")
                break
        verdicts[event.seq] = verdict
    return verdicts


def _evidence_seqs(events: list[TraceEvent], *, role: AgentRole | None = None) -> list[int]:
    seqs = []
    for event in events:
        if role is not None and event.agent_role is not role:
            continue
        if event.event_type in {EventType.MESSAGE, EventType.TOOL_CALL, EventType.EXECUTION_RESULT}:
            seqs.append(event.seq)
    return seqs[:8]


def _diagnosis_payload(row: dict[str, str], events: list[TraceEvent]) -> dict:
    outcome = row["validator_outcome"]
    engineer = row["engineer_failure_label"]
    critic = row["critic_label"]
    global_pattern = row["global_graph_pattern"]
    if outcome in {"solved", "trace_verified"}:
        status = "verified"
        headline = "Trace has positive Lean evidence; offline validation may still be unavailable."
    elif critic == "critic_false_accept":
        status = "critic_masking"
        headline = "Critic approval does not match the proof evidence."
    elif engineer in {"compile_loop", "application_type_mismatch", "typeclass_failure", "hallucinated_lemma"}:
        status = "engineer_failure"
        headline = "Engineer failed at the Lean coding layer."
    elif global_pattern in {"perseveration", "tool_overuse", "tool_underuse"}:
        status = "coordination_failure"
        headline = "Global routing/tool behavior explains the failure pattern."
    else:
        status = "unresolved"
        headline = "Trace remains unresolved under deterministic labels."

    return {
        "headline": headline,
        "status": status,
        "reasoner": f"Reasoner label: {row['reasoner_strategy_label']}. Human reference: {row['naive_human_strategy']}",
        "engineer": f"Engineer label: {engineer}. Failed compiles: {row['n_failed_compiles']}; tool calls: {row['n_tool_calls']}.",
        "critic": f"Critic label: {critic}. Declared success: {row['declared_success']}.",
        "global": f"Global graph pattern: {global_pattern}. First failure stage: {row['first_failure_stage']}.",
        "artifact": (
            f"Outcome: {outcome}. final_proof_compiles={row['final_proof_compiles']}, "
            f"statement_preserved={row['statement_preserved']}, axiom_clean={row['axiom_clean']}."
        ),
        "takeaway": row["presentation_takeaway"],
        "evidence_seqs": {
            "reasoner": _evidence_seqs(events, role=AgentRole.REASONER),
            "engineer": _evidence_seqs(events, role=AgentRole.ENGINEER),
            "critic": _evidence_seqs(events, role=AgentRole.CRITIC),
            "global": _evidence_seqs(events, role=None),
        },
    }


def build_trace_documents(
    trace_paths: list[Path],
    *,
    dataset_root: Path,
    rows_by_trial: dict[str, dict[str, str]],
    expected_count: int | None = None,
) -> list[dict]:
    """Build the interactive report payload from raw JSONL traces."""
    records = {record.id: record for record in load_dataset(dataset_root, difficulty="easy")}
    docs: list[dict] = []
    for path in trace_paths:
        meta, events = read_trial(path)
        record = records.get(meta.task_id)
        if record is None:
            continue
        row = rows_by_trial.get(meta.trial_id)
        if row is None:
            raise KeyError(f"Missing CSV row for trace {meta.trial_id}")
        artifacts = extract_artifacts(events)
        timeline = []
        for event in events:
            timeline.append(
                {
                    "event_id": event.event_id,
                    "seq": event.seq,
                    "role": event.agent_role.value,
                    "type": event.event_type.value,
                    "caused_by": event.caused_by,
                    "tool": _tool_name(event),
                    "decision": event.payload.get("decision"),
                    "handoff_target": event.payload.get("handoff_target"),
                    "text": _compact(_event_snippet(event), limit=5000),
                    "lean_code": _code_from_tool_call(event),
                }
            )
        docs.append(
            {
                "task_id": record.id,
                "trial_id": meta.trial_id,
                "trial_number": parse_trial_number(path),
                "source": record.source,
                "difficulty": record.difficulty,
                "informal": record.informal,
                "formal_statement": record.statement,
                "submitted_code": artifacts.submitted,
                "last_verified_code": artifacts.last_verified,
                "submitted_eq_last_verified": artifacts.submitted_eq_last_verified,
                "declared_success": artifacts.declared_success,
                "n_tool_calls": artifacts.n_tool_calls,
                "n_failed_compiles": artifacts.n_failed_compiles,
                "tool_calls": [
                    {
                        "seq": call.seq,
                        "compiled": call.compiled,
                        "sorry_free": call.sorry_free,
                        "code": call.code,
                    }
                    for call in artifacts.tool_calls
                    if call.code is not None or call.compiled is not None
                ],
                "graph": _graph_payload(events),
                "diagnosis": _diagnosis_payload(row, events),
                "timeline": timeline,
            }
        )
    if expected_count is not None and len(docs) != expected_count:
        raise RuntimeError(f"Expected {expected_count} trace documents, built {len(docs)}")
    return docs


def label_reasoner(events: list[TraceEvent], reference: TaskReference) -> str:
    text = _role_text(events, AgentRole.REASONER).lower()
    if not text and "search_lemmas" not in _tool_names(events):
        return "no_real_strategy"
    if any(marker in text for marker in WRONG_API_MARKERS):
        return "wrong_api_strategy"

    key_hits = sum(1 for key in reference.key_objects if key.lower() in text)
    if key_hits >= 2:
        return "valid_strategy"
    if key_hits == 1:
        return "partially_valid_strategy"
    if "strategy" in text or "plan" in text or "handoff: engineer" in text:
        return "partially_valid_strategy"
    return "no_real_strategy"


def label_engineer(
    events: list[TraceEvent],
    artifacts: TrialArtifacts,
    metrics: TrialMetrics,
    validator_outcome: str,
) -> str:
    if artifacts.submitted is None and artifacts.last_verified is None:
        return "no_submission"
    if validator_outcome == "import_error":
        return "import_failure"
    if artifacts.submitted_eq_last_verified is False:
        return "verified_then_changed"
    if metrics.statement_preserved is False:
        return "wrong_statement"

    text = _result_text(events).lower()
    if "application type mismatch" in text or "function expected" in text:
        return "application_type_mismatch"
    if "failed to synthesize" in text or "typeclass" in text or "instance" in text:
        return "typeclass_failure"
    if any(marker in text for marker in ("unknown constant", "unknown identifier", "unknown namespace")):
        return "hallucinated_lemma"
    if artifacts.n_failed_compiles >= 3:
        return "compile_loop"
    if "unsolved goals" in text or "tactic" in text or "made no progress" in text:
        return "api_confusion"
    if validator_outcome == "solved":
        return "no_engineer_failure"
    return "compile_loop" if artifacts.n_failed_compiles else "no_submission"


def label_critic(events: list[TraceEvent], metrics: TrialMetrics, validator_outcome: str) -> str:
    critic_events = [
        event
        for event in events
        if event.agent_role is AgentRole.CRITIC and event.event_type is EventType.MESSAGE
    ]
    if not critic_events:
        return "critic_missing"

    decisions = [event.payload.get("decision") for event in critic_events if event.payload.get("decision")]
    if "reject" in decisions:
        return "critic_sent_back"
    if metrics.declared_success and validator_outcome != "solved":
        return "critic_false_accept"
    if metrics.declared_success and metrics.final_proof_compiles is True:
        return "critic_compile_checked"
    if metrics.declared_success:
        return "critic_shallow_approval"

    critic_text = _role_text(events, AgentRole.CRITIC).lower()
    if "check_lean" in critic_text or "compile" in critic_text:
        return "critic_compile_checked"
    if "statement" in critic_text or "faithful" in critic_text:
        return "critic_statement_checked"
    return "critic_no_compile_check"


def label_global(
    artifacts: TrialArtifacts,
    perseverated: bool,
    validator_outcome: str,
    engineer_label: str,
    critic_label: str,
) -> str:
    if perseverated:
        return "perseveration"
    if critic_label == "critic_false_accept":
        return "critic_masking"
    if artifacts.n_tool_calls == 0:
        return "tool_underuse"
    if artifacts.n_tool_calls >= 8 and validator_outcome != "solved":
        return "tool_overuse"
    if engineer_label in {"compile_loop", "api_confusion"} and validator_outcome != "solved":
        return "reasoner_engineer_mismatch"
    if critic_label in {"critic_no_compile_check", "critic_shallow_approval"} and validator_outcome != "solved":
        return "engineer_critic_mismatch"
    if artifacts.n_failed_compiles and validator_outcome == "solved":
        return "productive_revision"
    return "productive_revision" if validator_outcome == "solved" else "free_routing_failure"


def first_failure_stage(
    validator_outcome: str,
    reasoner_label: str,
    engineer_label: str,
    critic_label: str,
) -> str:
    if validator_outcome == "solved":
        return "none"
    if reasoner_label in {"wrong_api_strategy", "wrong_statement_strategy", "strategy_drift", "no_real_strategy"}:
        return "reasoner"
    if engineer_label not in {"no_engineer_failure"}:
        return "engineer"
    if critic_label in {"critic_false_accept", "critic_shallow_approval", "critic_no_compile_check"}:
        return "critic"
    if validator_outcome in {"import_error", "validation_unknown"}:
        return "validator_or_environment"
    return "global"


def presentation_takeaway(
    validator_outcome: str,
    engineer_label: str,
    critic_label: str,
    global_label: str,
) -> str:
    if validator_outcome == "solved":
        return "O1/O2 evidence: trace graph shows a completed proof path; O3 is not claimed."
    if validator_outcome == "trace_verified":
        return "O1/O2 evidence: in-loop Lean check verified the submitted code; offline kernel recheck is not claimed."
    if critic_label == "critic_false_accept":
        return "O1/O2 evidence: critic approval masked a validator-visible proof failure; O3 is not claimed."
    if global_label in {"perseveration", "tool_overuse", "tool_underuse"}:
        return f"O2 evidence: global behavior label {global_label} explains failure beyond final accuracy; O3 is not claimed."
    if engineer_label not in {"no_engineer_failure"}:
        return f"O2 evidence: engineer label {engineer_label} localizes a concrete Lean failure mode; O3 is not claimed."
    return "O1/O2 evidence: causal trace localizes failure stage; O3 is not claimed."


def _try_compiler(dataset_root: Path, kernel: str):
    if kernel == "off":
        return None, "off"
    try:
        from traj_eval.tools.lean_cli_compiler import LeanCliCompiler

        return LeanCliCompiler(dataset_root), "available"
    except Exception as exc:  # noqa: BLE001 -- report generation must degrade cleanly
        return None, f"unavailable:{type(exc).__name__}"


def _validate_safely(
    events: list[TraceEvent],
    record: ProblemRecord,
    compiler,
) -> tuple[TrialMetrics, str]:
    task = to_lean_task(record)
    if compiler is None:
        return validate(events, task, compiler=None), "off"
    try:
        return validate(events, task, compiler=compiler), "available"
    except Exception as exc:  # noqa: BLE001 -- infrastructure failure becomes None fields
        return validate(events, task, compiler=None), f"validation_error:{type(exc).__name__}"


def build_rows(
    trace_paths: list[Path],
    *,
    dataset_root: Path,
    compiler=None,
) -> list[dict[str, str]]:
    records = {record.id: record for record in load_dataset(dataset_root, difficulty="easy")}
    rows: list[dict[str, str]] = []

    for path in trace_paths:
        meta, events = read_trial(path)
        record = records.get(meta.task_id)
        if record is None:
            raise KeyError(f"Trace {path} references unknown task_id {meta.task_id}")
        reference = TASK_REFERENCES.get(
            record.id,
            TaskReference(
                "Read the formal statement and prove the mathematical claim directly.",
                "Search for exact Mathlib lemmas and verify each Lean edit with check_lean.",
                tuple(),
            ),
        )

        graph = build_graph(events)
        _ = causal_order(events)
        metrics, kernel_status = _validate_safely(events, record, compiler)
        artifacts = extract_artifacts(events)
        perseverance = detect_perseveration(artifacts.tool_calls)
        validator_outcome = classify_outcome(events, metrics)
        reasoner = label_reasoner(events, reference)
        engineer = label_engineer(events, artifacts, metrics, validator_outcome)
        critic = label_critic(events, metrics, validator_outcome)
        global_label = label_global(
            artifacts, perseverance.perseverated, validator_outcome, engineer, critic
        )
        stage = first_failure_stage(validator_outcome, reasoner, engineer, critic)

        # ``graph`` is built for O1 grounding. It is intentionally not exposed as
        # a separate CSV column to keep the report compact.
        _graph_node_count = graph.number_of_nodes()
        if _graph_node_count != len(events):
            raise RuntimeError(f"Graph/event mismatch in {path}")

        rows.append(
            {
                "task_id": record.id,
                "trial_id": meta.trial_id,
                "trial_number": str(parse_trial_number(path)),
                "source": record.source,
                "difficulty": record.difficulty,
                "math_question": _compact(record.informal, limit=220),
                "naive_human_strategy": reference.naive_human_strategy,
                "domain_specific_LLM_strategy": reference.domain_specific_llm_strategy,
                "reasoner_strategy_label": reasoner,
                "engineer_failure_label": engineer,
                "critic_label": critic,
                "global_graph_pattern": global_label,
                "validator_outcome": validator_outcome,
                "first_failure_stage": stage,
                "n_tool_calls": str(metrics.n_tool_calls),
                "n_failed_compiles": str(metrics.n_failed_compiles),
                "perseverated": _bool(perseverance.perseverated),
                "declared_success": _bool(metrics.declared_success),
                "final_proof_compiles": _bool(metrics.final_proof_compiles),
                "statement_preserved": _bool(metrics.statement_preserved),
                "axiom_clean": _bool(metrics.axiom_clean),
                "presentation_takeaway": (
                    presentation_takeaway(validator_outcome, engineer, critic, global_label)
                    + f" {PROPOSAL_GROUNDING} {MD_GROUNDING} Kernel={kernel_status}."
                ),
            }
        )
    return rows


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _copy_for_report(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)


def _write_json(path: Path, docs: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(docs, ensure_ascii=False, indent=2), encoding="utf-8")


def _summarize(rows: list[dict[str, str]]) -> str:
    outcomes = Counter(row["validator_outcome"] for row in rows)
    tasks = len({row["task_id"] for row in rows})
    pieces = ", ".join(f"{key}={value}" for key, value in sorted(outcomes.items()))
    return f"wrote {len(rows)} rows across {tasks} tasks; outcomes: {pieces}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--out-csv", type=Path, default=DEFAULT_OUT_CSV)
    parser.add_argument("--report-public-csv", type=Path, default=DEFAULT_REPORT_CSV)
    parser.add_argument("--report-public-json", type=Path, default=DEFAULT_REPORT_JSON)
    parser.add_argument("--expect-count", type=int, default=100)
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--kernel", choices=["auto", "off"], default="auto")
    args = parser.parse_args(argv)

    trace_paths = sorted(args.input_dir.glob("*.jsonl"))
    if len(trace_paths) != args.expect_count and not args.allow_partial:
        raise SystemExit(
            f"Expected {args.expect_count} traces in {args.input_dir}, found {len(trace_paths)}. "
            "Use --allow-partial for smoke tests."
        )

    compiler, compiler_status = _try_compiler(args.dataset_root, args.kernel)
    rows = build_rows(trace_paths, dataset_root=args.dataset_root, compiler=compiler)
    rows_by_trial = {row["trial_id"]: row for row in rows}
    _write_csv(args.out_csv, rows)
    _copy_for_report(args.out_csv, args.report_public_csv)
    _write_json(
        args.report_public_json,
        build_trace_documents(
            trace_paths,
            dataset_root=args.dataset_root,
            rows_by_trial=rows_by_trial,
            expected_count=None if args.allow_partial else args.expect_count,
        ),
    )

    print(f"{_summarize(rows)}; compiler={compiler_status}; csv={args.out_csv}")
    print(f"copied report CSV to {args.report_public_csv}")
    print(f"wrote trace JSON to {args.report_public_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
