"""Dataset layer: load the MiniFATELeanCat benchmark (FATE-M/H/X + LeanCat) into
task objects the rest of the pipeline consumes.

The benchmark ships as one .lean file per problem plus a metadata.json index.
Each file has a uniform shape (verified across all 30):

    /- Source: ... / Difficulty: ... / Informal statement: ... -/
    import Mathlib....
    [optional]  namespace ...
    theorem <name> (...) : <goal> := by
      sorry
    [optional]  end ...

This module reads metadata.json, joins each record to its file, extracts the
informal statement, the imports, and the theorem SIGNATURE (everything up to
``:= by``, with the sorry body dropped), and exposes them as ProblemRecords.
``to_lean_task`` bridges a record to the LeanTask the validator already expects,
so nothing downstream changes.

The parser is deliberately format-specific (the benchmark is uniform) but
defensive about the namespace wrapper and about the ``:= by`` / ``:= by sorry``
terminator. Nothing here touches Lean or the network -- it is pure text.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from traj_eval.metrics.lean.validator import STANDARD_AXIOMS, LeanTask

# The statement ends where the proof body begins. All 30 files use ':= by'.
_BODY_START = re.compile(r":=\s*by\b")
_INFORMAL = re.compile(r"Informal statement:\s*(.*?)\s*-/", re.DOTALL)
_IMPORT = re.compile(r"^\s*import\s+.+$", re.MULTILINE)
_THEOREM = re.compile(r"\btheorem\b")


@dataclass(frozen=True)
class ProblemRecord:
    """One benchmark problem, parsed from its file + metadata row."""

    id: str
    source: str  # 'FATE-M' | 'FATE-H' | 'FATE-X' | 'LeanCat'
    difficulty: str  # 'easy' | 'medium' | 'hard'
    imports: list[str] = field(default_factory=list)
    statement: str = ""  # theorem signature, no proof body
    informal: str = ""  # natural-language problem description
    module: str = ""
    source_id: str = ""
    path: Path | None = None

    @property
    def import_block(self) -> str:
        """The imports as a Lean prelude (falls back to plain Mathlib)."""
        return "\n".join(f"import {m}" for m in self.imports) if self.imports else "import Mathlib"


def _extract_informal(text: str) -> str:
    m = _INFORMAL.search(text)
    return " ".join(m.group(1).split()) if m else ""


def _extract_statement(text: str) -> str:
    """Signature from the first ``theorem`` keyword up to ``:= by`` (exclusive).

    Drops the namespace wrapper (only lines before the theorem could contain it)
    and the sorry body. Whitespace is preserved as written except leading/
    trailing trim, so the multi-line signature stays readable.
    """
    tm = _THEOREM.search(text)
    if not tm:
        return ""
    after = text[tm.start() :]
    bm = _BODY_START.search(after)
    sig = after[: bm.start()] if bm else after
    return sig.strip()


def parse_problem_file(path: Path) -> tuple[str, str, list[str]]:
    """Parse a benchmark .lean file -> (statement, informal, imports).

    Imports here are read from the FILE; the metadata also carries them and is
    treated as authoritative by load_dataset (the file is the fallback).
    """
    text = path.read_text(encoding="utf-8")
    statement = _extract_statement(text)
    informal = _extract_informal(text)
    imports = [line.split("import", 1)[1].strip() for line in _IMPORT.findall(text)]
    return statement, informal, imports


def load_dataset(
    root: Path,
    *,
    difficulty: str | None = None,
    source: str | None = None,
) -> list[ProblemRecord]:
    """Load all problems under ``root`` (the dataset/Lean directory).

    ``root`` must contain metadata.json and the module .lean files. Optional
    ``difficulty`` ('easy'|'medium'|'hard') and ``source`` filters let callers
    grab a slice (e.g. just easy problems for first runs).
    """
    root = Path(root)
    meta = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
    records: list[ProblemRecord] = []
    for row in meta:
        if difficulty and row.get("difficulty") != difficulty:
            continue
        if source and row.get("source") != source:
            continue
        # module 'MiniFATELeanCat.Easy.FATEM011' -> path under root
        rel = Path(*row["module"].split(".")).with_suffix(".lean")
        path = root / rel
        statement, informal, file_imports = ("", "", [])
        if path.exists():
            statement, informal, file_imports = parse_problem_file(path)
        records.append(
            ProblemRecord(
                id=row["id"],
                source=row.get("source", ""),
                difficulty=row.get("difficulty", ""),
                # metadata imports are authoritative; file imports are fallback
                imports=row.get("imports") or file_imports,
                statement=statement,
                informal=informal,
                module=row.get("module", ""),
                source_id=str(row.get("source_id", "")),
                path=path if path.exists() else None,
            )
        )
    return records


def to_lean_task(record: ProblemRecord) -> LeanTask:
    """Bridge a ProblemRecord to the LeanTask the validator consumes."""
    return LeanTask(
        task_id=record.id,
        statement=record.statement,
        imports=record.import_block,
        allowed_axioms=STANDARD_AXIOMS,
    )
