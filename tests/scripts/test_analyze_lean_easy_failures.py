from __future__ import annotations

import csv
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest

from scripts import analyze_lean_easy_failures as analyzer
from traj_eval.metrics.lean.validator import TrialMetrics
from traj_eval.trace_core.schema import AgentRole, EventType


@dataclass
class _FakeEvent:
    agent_role: AgentRole
    event_type: EventType
    payload: dict


def test_parse_trial_number():
    assert analyzer.parse_trial_number("easy_fatem_111_t7.jsonl") == 7
    assert analyzer.parse_trial_number(Path("data/batch/easy_leancat_002_t0.jsonl")) == 0


def test_count_mismatch_fails_without_allow_partial(tmp_path):
    input_dir = tmp_path / "batch"
    input_dir.mkdir()
    with pytest.raises(SystemExit, match="Expected 100 traces"):
        analyzer.main(
            [
                "--input-dir",
                str(input_dir),
                "--dataset-root",
                "dataset/Lean",
                "--out-csv",
                str(tmp_path / "out.csv"),
                "--report-public-csv",
                str(tmp_path / "public.csv"),
                "--kernel",
                "off",
            ]
        )


def test_writes_one_csv_row_per_trace_and_public_copy(tmp_path):
    input_dir = tmp_path / "batch"
    input_dir.mkdir()
    src = Path("data/batch/easy_fatem_111_t0.jsonl")
    shutil.copyfile(src, input_dir / src.name)

    out_csv = tmp_path / "analysis" / "lean_easy_failure_patterns.csv"
    public_csv = tmp_path / "report" / "public" / "data" / "lean_easy_failure_patterns.csv"
    public_json = tmp_path / "report" / "public" / "data" / "lean_easy_failure_traces.json"

    rc = analyzer.main(
        [
            "--input-dir",
            str(input_dir),
            "--dataset-root",
            "dataset/Lean",
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
    assert public_json.exists()
    docs = json.loads(public_json.read_text(encoding="utf-8"))
    assert len(docs) == 1
    assert docs[0]["trial_id"] == "easy_fatem_111_t0"
    assert len(docs[0]["graph"]["nodes"]) == len(docs[0]["timeline"])
    assert "edges" in docs[0]["graph"]
    assert docs[0]["diagnosis"]["headline"]
    assert docs[0]["diagnosis"]["evidence_seqs"]["global"]
    rows = list(csv.DictReader(out_csv.open(encoding="utf-8")))
    assert len(rows) == 1
    assert list(rows[0].keys()) == analyzer.CSV_FIELDS
    assert rows[0]["task_id"] == "easy_fatem_111"
    assert "O3 is not claimed" in rows[0]["presentation_takeaway"]
    assert "docs/LEAN_FAILURE_ANALYSIS_GUIDE.md" in rows[0]["presentation_takeaway"]


def test_full_trace_bundle_matches_csv_trial_ids_for_batch_data(tmp_path):
    out_csv = tmp_path / "analysis" / "lean_easy_failure_patterns.csv"
    public_csv = tmp_path / "report" / "public" / "data" / "lean_easy_failure_patterns.csv"
    public_json = tmp_path / "report" / "public" / "data" / "lean_easy_failure_traces.json"

    rc = analyzer.main(
        [
            "--input-dir",
            "data/batch",
            "--dataset-root",
            "dataset/Lean",
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
    assert len(rows) == 100
    assert len(docs) == 100
    assert {row["trial_id"] for row in rows} == {doc["trial_id"] for doc in docs}


def test_critic_false_accept_when_declared_success_but_validator_rejects():
    event = _FakeEvent(
        agent_role=AgentRole.CRITIC,
        event_type=EventType.MESSAGE,
        payload={"decision": "approve", "text": "VERDICT: APPROVE"},
    )
    metrics = TrialMetrics(
        task_id="task",
        compiler_was_called=True,
        n_tool_calls=1,
        n_failed_compiles=1,
        submitted_eq_last_verified=True,
        declared_success=True,
        has_submission=True,
        final_proof_compiles=False,
        final_proof_sorry_free=True,
        statement_preserved=True,
        axiom_clean=True,
        silent_failure=True,
    )

    assert analyzer.label_critic([event], metrics, "silent_failure") == "critic_false_accept"
