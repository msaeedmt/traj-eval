"""Tests for the dataset loader, run against the REAL benchmark files shipped in
dataset/Lean. These are pure-text parsing checks (no Lean, no network).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from traj_eval.dataset.loader import (
    ProblemRecord,
    load_dataset,
    parse_problem_file,
    to_lean_task,
)

ROOT = Path(__file__).resolve().parents[2] / "dataset" / "Lean"

pytestmark = pytest.mark.skipif(
    not (ROOT / "metadata.json").exists(),
    reason="benchmark dataset not present",
)


def test_loads_all_thirty():
    recs = load_dataset(ROOT)
    assert len(recs) == 30
    assert all(isinstance(r, ProblemRecord) for r in recs)


def test_difficulty_split():
    for diff, n in [("easy", 10), ("medium", 10), ("hard", 10)]:
        recs = load_dataset(ROOT, difficulty=diff)
        assert len(recs) == n
        assert all(r.difficulty == diff for r in recs)


def test_source_filter():
    fatem = load_dataset(ROOT, source="FATE-M")
    assert len(fatem) == 8
    assert all(r.source == "FATE-M" for r in fatem)


def test_statement_has_no_proof_body():
    recs = load_dataset(ROOT)
    for r in recs:
        assert r.statement, f"{r.id} has empty statement"
        assert "sorry" not in r.statement, f"{r.id} statement leaked sorry"
        assert ":= by" not in r.statement, f"{r.id} statement leaked body start"
        assert "theorem" in r.statement, f"{r.id} statement missing theorem kw"


def test_namespace_wrapper_stripped():
    # FATE-X (hard) files wrap the theorem in `namespace ... end`; the extracted
    # statement should start at `theorem`, not at `namespace`.
    hard = load_dataset(ROOT, difficulty="hard")
    for r in hard:
        assert not r.statement.startswith("namespace")
        assert "end MiniFATELeanCat" not in r.statement


def test_informal_extracted():
    recs = load_dataset(ROOT)
    # every file has an "Informal statement:" block
    assert all(r.informal for r in recs)


def test_imports_from_metadata():
    fatem011 = next(r for r in load_dataset(ROOT) if r.id == "easy_fatem_011")
    assert "Mathlib.Algebra.Ring.Basic" in fatem011.imports
    assert fatem011.import_block.startswith("import Mathlib.Algebra.Ring.Basic")


def test_to_lean_task_bridge():
    fatem011 = next(r for r in load_dataset(ROOT) if r.id == "easy_fatem_011")
    task = to_lean_task(fatem011)
    assert task.task_id == "easy_fatem_011"
    assert "theorem" in task.statement
    assert "import Mathlib.Algebra.Ring.Basic" in task.imports


def test_parse_file_directly():
    p = ROOT / "MiniFATELeanCat" / "Easy" / "FATEM011.lean"
    statement, informal, imports = parse_problem_file(p)
    assert statement.startswith("theorem fatem_011")
    assert "distribute over subtraction" in informal
    assert imports == ["Mathlib.Algebra.Ring.Basic"]
