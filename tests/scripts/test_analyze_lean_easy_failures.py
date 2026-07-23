from __future__ import annotations

import copy
import csv
import hashlib
import json
import re
import shutil
from collections import Counter
from functools import lru_cache
from pathlib import Path

import pytest

from scripts import analyze_lean_easy_failures as analyzer
from traj_eval.dataset.loader import load_dataset
from traj_eval.trace_core.storage import read_trial

TRACE_DIR = Path("data/batch/version_1_trial_traces")
REVIEW_PATH = Path("data/analysis/lean_easy_failure_reviews.jsonl")
DATASET_ROOT = Path("dataset/Lean")


@lru_cache(maxsize=1)
def _records():
    return {record.id: record for record in load_dataset(DATASET_ROOT, difficulty="easy")}


@lru_cache(maxsize=1)
def _reviews():
    paths = sorted(TRACE_DIR.glob("*.jsonl"))
    return analyzer.load_reviews(REVIEW_PATH, paths)


def _review(trial_id: str):
    return _reviews()[trial_id]


def _hashes(paths):
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _strings(item)


def _has_windows_absolute_path(text):
    return re.search(r"(?i)(?<![a-z0-9_])[a-z]:(?:\\+|/)", text) is not None


def test_parse_trial_number():
    assert analyzer.parse_trial_number("easy_fatem_111_t7.jsonl") == 7
    assert analyzer.parse_trial_number(TRACE_DIR / "easy_leancat_002_t0.jsonl") == 0


def test_public_text_redacts_workstation_and_temp_paths():
    raw = (
        f"{analyzer.PUBLIC_REPO_ROOT}\\dataset\\Lean\\.lake\\module.olean "
        f"'{str(analyzer.PUBLIC_REPO_ROOT).replace(chr(92), chr(92) * 2)}"
        "\\\\dataset\\\\Lean\\\\escaped.olean' "
        "'D:\\private workspace\\Other.olean' "
        ".traj_eval_tmp\\\\check_0123456789abcdef.lean"
    )
    public = analyzer._public_text(raw)

    assert not _has_windows_absolute_path(public)
    assert "<repo>" in public
    assert "<lean-temp>.lean" in public
    assert "<local-path>/Other.olean" in public
    assert "module.olean" in public


def test_review_source_has_exactly_100_hash_bound_trials():
    reviews = _reviews()
    assert len(reviews) == 100
    assert len({review["source_sha256"] for review in reviews.values()}) == 100
    assert {review["review_status"] for review in reviews.values()} == {"agent_reviewed"}
    assert all(review["trace_evidence"]["anchor_count"] == 0 for review in reviews.values())
    assert not any(
        _has_windows_absolute_path(text) for review in reviews.values() for text in _strings(review)
    )


def test_strict_header_partition_is_preserved():
    reviews = _reviews().values()
    approved = [review for review in reviews if review["candidate"]["submission_accepted"]]
    assert Counter(review["candidate"]["kind"] for review in approved) == {
        "exact_target": 55,
        "statement_drift": 4,
    }
    unreviewed_exact = [
        review
        for review in reviews
        if review["candidate"]["kind"] == "exact_target"
        and not review["candidate"]["submission_accepted"]
    ]
    assert [review["trial_id"] for review in unreviewed_exact] == ["easy_leancat_001_t1"]
    assert len(approved) + 1 + sum(
        not review["candidate"]["submission_accepted"]
        and review["trial_id"] != "easy_leancat_001_t1"
        for review in reviews
    ) == 100


@pytest.mark.parametrize(
    ("trial_id", "expected"),
    [
        ("easy_fatem_115_t2", "approved_after_failed_recheck"),
        ("easy_fatem_115_t4", "approved_statement_drift"),
        ("easy_fatem_115_t5", "approved_statement_drift"),
        ("easy_fatem_115_t8", "approved_statement_drift"),
    ],
)
def test_fatem115_statement_drift_is_strictly_labeled(trial_id, expected):
    review = _review(trial_id)
    assert review["candidate"]["kind"] == "statement_drift"
    assert review["candidate"]["statement_match"] == "changed"
    assert review["workflow"]["outcome"] == expected
    assert "statement_drift" in review["causal_labels"]
    assert "incorrect_verification" in review["causal_labels"]
    assert "missed_statement_drift" in review["causal_labels"]
    assert review["critical_failure"]["symptom_code"] == "statement_drift"


def test_unapproved_statement_drift_is_not_a_false_accept():
    review = _review("easy_fatem_115_t3")
    assert review["candidate"]["kind"] == "statement_drift"
    assert review["candidate"]["submission_accepted"] is False
    assert "incorrect_verification" not in review["causal_labels"]
    assert "missed_statement_drift" not in review["causal_labels"]


def test_fatem019_t8_sorry_pseudopass_is_not_a_target_candidate():
    review = _review("easy_fatem_019_t8")
    assert review["candidate"]["kind"] == "none"
    assert "sorry_pseudo_pass" in review["symptom_codes"]
    assert "sorry_pseudo_pass" in review["causal_labels"]


def test_recovered_errors_do_not_become_terminal_failure():
    review = _review("easy_fatem_020_t0")
    assert review["workflow"]["outcome"] == "approved_after_productive_revision"
    assert review["critical_failure"] is None
    assert review["recovered_failure_seqs"]
    assert "invalid_import_path" not in review["causal_labels"]


def test_helper_success_is_not_target_success():
    review = _review("easy_fatem_111_t0")
    assert review["candidate"]["kind"] == "helper_or_probe"
    assert not review["candidate"]["submission_accepted"]
    assert review["workflow"]["outcome"] == "terminated_with_compile_failures"


def test_unknown_constant_is_agent_api_error_not_environment_error():
    symptom, labels, confidence = analyzer._symptom_for_failure(
        "error(lean.unknownIdentifier): Unknown constant Foo.bar"
    )
    assert symptom == "unknown_symbol"
    assert "api_or_library_hallucination" in labels
    assert "invalid_import_path" not in labels
    assert confidence == "confirmed"


def test_unpaired_search_and_disconnected_components_are_explicit():
    assert _review("easy_fatem_109_t3")["trace_evidence"]["unpaired_tool_call_seqs"] == [23]
    assert _review("easy_leancat_002_t1")["trace_evidence"]["unpaired_tool_call_seqs"] == [11]
    for trial_id in ("easy_fatem_111_t5", "easy_fatem_111_t9", "easy_fatem_115_t7"):
        evidence = _review(trial_id)["trace_evidence"]
        assert evidence["graph_component_count"] == 2
        assert evidence["graph_interpretation"] == "disconnected_event_timeline"


def test_review_hash_mismatch_fails_closed(tmp_path):
    source = TRACE_DIR / "easy_fatem_011_t0.jsonl"
    copied = tmp_path / source.name
    data = source.read_bytes().replace(b"\n", b" \n", 1)
    copied.write_bytes(data)
    with pytest.raises(ValueError, match="raw trace hash changed"):
        analyzer.load_reviews(REVIEW_PATH, [copied], allow_partial=True)


def test_review_validation_closes_top_level_and_event_reference_gaps():
    trial_id = "easy_fatem_111_t0"
    path = TRACE_DIR / f"{trial_id}.jsonl"
    meta, events = read_trial(path)
    event_seqs = {event.seq for event in events}
    result_seqs = {
        event.seq
        for event in events
        if event.event_type.value == "execution_result"
    }

    def validate(review):
        analyzer._validate_review(
            review,
            path,
            meta.trial_id,
            meta.task_id,
            event_seqs,
            result_seqs,
        )

    base = _review(trial_id)
    validate(copy.deepcopy(base))
    cases = [
        (
            lambda review: review["symptom_codes"].append("not_a_symptom"),
            "invalid symptom_codes",
        ),
        (
            lambda review: review["causal_labels"].append("not_a_cause"),
            "invalid causal_labels",
        ),
        (
            lambda review: review.__setitem__("symptom_codes", []),
            "top-level symptom_codes",
        ),
        (
            lambda review: review["candidate"].__setitem__("result_event_seq", 999),
            "candidate.result_event_seq",
        ),
        (
            lambda review: review["incidents"][0].__setitem__("result_event_seq", 999),
            "incident.result_event_seq",
        ),
        (
            lambda review: review.__setitem__("recovered_failure_seqs", [999]),
            "recovered_failure_seqs",
        ),
        (
            lambda review: review["critical_failure"].__setitem__("event_seq", 999),
            "critical_failure",
        ),
        (
            lambda review: review.__setitem__("task_id", "wrong_task"),
            "task_id mismatch",
        ),
        (
            lambda review: review.__setitem__("source_file", "data/batch/wrong.jsonl"),
            "source_file mismatch",
        ),
    ]
    for mutate, message in cases:
        review = copy.deepcopy(base)
        mutate(review)
        with pytest.raises(ValueError, match=message):
            validate(review)


def test_count_mismatch_fails_without_allow_partial(tmp_path):
    input_dir = tmp_path / "batch"
    input_dir.mkdir()
    with pytest.raises(SystemExit, match="Expected 100 traces"):
        analyzer.main(
            [
                "--input-dir",
                str(input_dir),
                "--dataset-root",
                str(DATASET_ROOT),
                "--out-csv",
                str(tmp_path / "out.csv"),
                "--report-public-csv",
                str(tmp_path / "public.csv"),
                "--kernel",
                "off",
            ]
        )


def test_kernel_required_is_default_and_fails_before_outputs(tmp_path):
    input_dir = tmp_path / "batch"
    input_dir.mkdir()
    source = TRACE_DIR / "easy_fatem_011_t0.jsonl"
    shutil.copyfile(source, input_dir / source.name)
    out = tmp_path / "out.csv"
    with pytest.raises(SystemExit, match="Kernel validation is required"):
        analyzer.main(
            [
                "--input-dir",
                str(input_dir),
                "--dataset-root",
                str(tmp_path / "missing-lean-project"),
                "--reviews",
                str(REVIEW_PATH),
                "--out-csv",
                str(out),
                "--report-public-csv",
                str(tmp_path / "public.csv"),
                "--report-public-json",
                str(tmp_path / "public.json"),
                "--expect-count",
                "1",
                "--allow-partial",
            ]
        )
    assert not out.exists()


def test_writes_structured_trace_only_bundle_without_mutating_raw_traces(tmp_path):
    before = _hashes(TRACE_DIR.glob("*.jsonl"))
    input_dir = tmp_path / "batch"
    input_dir.mkdir()
    source = TRACE_DIR / "easy_fatem_111_t0.jsonl"
    shutil.copyfile(source, input_dir / source.name)

    out_csv = tmp_path / "analysis" / "patterns.csv"
    public_csv = tmp_path / "report" / "patterns.csv"
    public_json = tmp_path / "report" / "traces.json"
    rc = analyzer.main(
        [
            "--input-dir",
            str(input_dir),
            "--dataset-root",
            str(DATASET_ROOT),
            "--reviews",
            str(REVIEW_PATH),
            "--out-csv",
            str(out_csv),
            "--report-public-csv",
            str(public_csv),
            "--report-public-json",
            str(public_json),
            "--expect-count",
            "1",
            "--allow-partial",
            "--kernel",
            "off",
        ]
    )

    assert rc == 0
    assert public_csv.read_text(encoding="utf-8") == out_csv.read_text(encoding="utf-8")
    rows = list(csv.DictReader(out_csv.open(encoding="utf-8")))
    assert len(rows) == 1
    assert list(rows[0]) == analyzer.CSV_FIELDS
    assert rows[0]["kernel_status"] == "off"
    assert rows[0]["validation_status"] == "not_evaluated"
    assert rows[0]["claim_status"] == "provisional_trace_only"
    assert rows[0]["candidate_kind"] == "helper_or_probe"
    assert rows[0]["n_check_lean_calls"] == "9"
    assert rows[0]["n_search_lemma_calls"] == "5"
    assert "precision/recall is untested" in rows[0]["presentation_takeaway"]

    docs = json.loads(public_json.read_text(encoding="utf-8"))
    assert len(docs) == 1
    doc = docs[0]
    assert doc["trial_id"] == "easy_fatem_111_t0"
    assert len(doc["graph"]["nodes"]) == len(doc["timeline"])
    assert doc["graph"]["causal_claim"] == "descriptive_only"
    diagnosis = doc["diagnosis"]
    assert isinstance(diagnosis["incidents"], list)
    assert isinstance(diagnosis["causal_labels"], list)
    assert diagnosis["critical_failure"]["event_seq"] == 12
    assert diagnosis["verification"]["validation_status"] == "not_evaluated"
    assert isinstance(diagnosis["verification"]["prohibited_placeholders"], list)
    assert before == _hashes(TRACE_DIR.glob("*.jsonl"))


def test_full_trace_only_bundle_has_consistent_ids_hashes_and_claim_gate(tmp_path):
    out_csv = tmp_path / "analysis" / "patterns.csv"
    public_csv = tmp_path / "report" / "patterns.csv"
    public_json = tmp_path / "report" / "traces.json"
    rc = analyzer.main(
        [
            "--input-dir",
            str(TRACE_DIR),
            "--dataset-root",
            str(DATASET_ROOT),
            "--reviews",
            str(REVIEW_PATH),
            "--out-csv",
            str(out_csv),
            "--report-public-csv",
            str(public_csv),
            "--report-public-json",
            str(public_json),
            "--expect-count",
            "100",
            "--kernel",
            "off",
        ]
    )
    assert rc == 0
    rows = list(csv.DictReader(out_csv.open(encoding="utf-8")))
    docs = json.loads(public_json.read_text(encoding="utf-8"))
    assert len(rows) == len(docs) == 100
    assert {row["trial_id"] for row in rows} == {doc["trial_id"] for doc in docs}
    assert len({row["analysis_snapshot_sha256"] for row in rows}) == 1
    assert all(row["review_status"] == "agent_reviewed" for row in rows)
    assert all(row["claim_status"] == "provisional_trace_only" for row in rows)
    assert sum(int(row["n_check_lean_calls"]) for row in rows) == 341
    assert sum(int(row["n_failed_compiles"]) for row in rows) == 132
    assert sum(int(row["n_infrastructure_unknown_checks"]) for row in rows) == 86
    assert all("precision/recall is untested" in row["presentation_takeaway"] for row in rows)
    assert not any("O1/O2 evidence:" in row["presentation_takeaway"] for row in rows)
    assert not any(_has_windows_absolute_path(text) for text in _strings(rows))
    assert not any(_has_windows_absolute_path(text) for text in _strings(docs))


class _ExplodingCompiler:
    def check(self, _code):
        raise TimeoutError("synthetic timeout")


class _InfrastructureResult:
    compiled = False
    sorry_free = False
    verification_status = "infrastructure_unknown"
    infrastructure_error = "synthetic opaque process exit"
    summary = infrastructure_error


class _InfrastructureResultCompiler:
    def check(self, _code):
        return _InfrastructureResult()


def test_validation_infrastructure_failure_is_tri_state_and_can_fail_closed():
    path = TRACE_DIR / "easy_fatem_011_t0.jsonl"
    meta, events = read_trial(path)
    checks = analyzer.check_evidence(events, _records()[meta.task_id])
    candidate = analyzer.select_candidate(checks, events)
    result = analyzer._candidate_validation(
        candidate,
        _records()[meta.task_id],
        _ExplodingCompiler(),
        kernel_status="available",
        fail_closed=False,
    )
    assert result.status == "infrastructure_unknown"
    assert result.final_proof_compiles is None
    assert "TimeoutError" in result.error
    with pytest.raises(RuntimeError, match="Kernel validation failed"):
        analyzer._candidate_validation(
            candidate,
            _records()[meta.task_id],
            _ExplodingCompiler(),
            kernel_status="available",
            fail_closed=True,
        )


def test_structured_infrastructure_unknown_is_not_a_kernel_rejection():
    path = TRACE_DIR / "easy_fatem_011_t0.jsonl"
    meta, events = read_trial(path)
    record = _records()[meta.task_id]
    candidate = analyzer.select_candidate(analyzer.check_evidence(events, record), events)
    result = analyzer._candidate_validation(
        candidate,
        record,
        _InfrastructureResultCompiler(),
        kernel_status="available",
        fail_closed=False,
    )
    assert result.status == "infrastructure_unknown"
    assert result.final_proof_compiles is None
    with pytest.raises(RuntimeError, match="synthetic opaque process exit"):
        analyzer._candidate_validation(
            candidate,
            record,
            _InfrastructureResultCompiler(),
            kernel_status="available",
            fail_closed=True,
        )


class _AcceptedResult:
    compiled = True
    sorry_free = True
    verification_status = "accepted"
    infrastructure_error = None
    summary = "accepted"
    warnings = []
    errors = []


class _RecordingCompiler:
    def __init__(self):
        self.codes = []

    def check(self, code):
        self.codes.append(code)
        result = _AcceptedResult()
        if "#print axioms" in code:
            result.warnings = [type("Message", (), {"data": "does not depend on any axioms"})()]
        return result


class _AlwaysAcceptedWithoutAuditOutput:
    def check(self, _code):
        return _AcceptedResult()


def test_memoizing_compiler_reuses_only_identical_source():
    inner = _RecordingCompiler()
    compiler = analyzer._MemoizingCompiler(inner)

    first = compiler.check("import Mathlib\n#check Nat")
    second = compiler.check("import Mathlib\n#check Nat")
    compiler.check("import Mathlib\n#check Int")

    assert first is second
    assert inner.codes == ["import Mathlib\n#check Nat", "import Mathlib\n#check Int"]


def test_target_body_and_axiom_audit_ignore_preceding_helper_declaration():
    record = _records()["easy_fatem_011"]
    code = f"import Mathlib\ntheorem helper : True := by trivial\n{record.statement} := by simp"
    candidate = analyzer.CheckEvidence(
        call_id="c",
        call_seq=1,
        result_seq=2,
        role="engineer",
        code=code,
        compiled=True,
        sorry_free=True,
        verification_status="accepted",
        diagnostic="",
        candidate_kind="exact_target",
        statement_match="exact",
    )
    assert analyzer._exact_target_body(code, record) == "by simp"
    compiler = _RecordingCompiler()
    result = analyzer._candidate_validation(
        candidate,
        record,
        compiler,
        kernel_status="available",
        fail_closed=True,
    )
    assert result.status == "accepted"
    assert compiler.codes[-1].endswith("#print axioms fatem_011_mul_sub_and_sub_mul")


def test_exact_target_probe_keeps_the_checked_candidate_prelude():
    path = TRACE_DIR / "easy_fatem_012_t0.jsonl"
    meta, events = read_trial(path)
    record = _records()[meta.task_id]
    candidate = analyzer.select_candidate(analyzer.check_evidence(events, record), events)

    assert candidate is not None
    probe = analyzer._exact_target_probe(candidate.code, record)
    assert probe is not None
    assert probe.startswith("import Mathlib")
    assert record.statement in probe


def test_empty_axiom_output_is_infrastructure_unknown_not_clean():
    path = TRACE_DIR / "easy_fatem_011_t0.jsonl"
    meta, events = read_trial(path)
    record = _records()[meta.task_id]
    candidate = analyzer.select_candidate(analyzer.check_evidence(events, record), events)
    result = analyzer._candidate_validation(
        candidate,
        record,
        _AlwaysAcceptedWithoutAuditOutput(),
        kernel_status="available",
        fail_closed=False,
    )
    assert result.status == "infrastructure_unknown"
    assert result.axiom_clean is None
    with pytest.raises(RuntimeError, match="no parseable #print axioms output"):
        analyzer._candidate_validation(
            candidate,
            record,
            _AlwaysAcceptedWithoutAuditOutput(),
            kernel_status="available",
            fail_closed=True,
        )
