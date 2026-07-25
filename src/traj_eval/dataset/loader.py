"""Dataset layer: load the MiniFATELeanCat benchmark (FATE-M/H/X + LeanCat) into
task objects the rest of the pipeline consumes.

The benchmark ships as one .lean file per problem plus a metadata.json index.
Each file has a uniform shape (verified across all 30):

    /- Source: ... / Difficulty: ... / Informal statement: ... -/
    import Mathlib....
    [optional]  preamble declarations (`open`, `namespace`, `structure`, ...)
    theorem <name> (...) : <goal> := by
      sorry
    [optional]  end ...

This module reads metadata.json, joins each record to its file, extracts the
informal statement, the imports, and the theorem SIGNATURE (everything up to
``:= by``, with the sorry body dropped), and the complete preamble between the
imports and theorem. It exposes them as ProblemRecords. ``to_lean_task`` bridges
a record to the LeanTask the validator already expects, so nothing downstream
changes.

The parser is deliberately format-specific (the benchmark is uniform) but keeps
local declarations required by the target and is defensive about the ``:= by``
/ ``:= by sorry`` terminator. Nothing here touches Lean or the network -- it is
pure text.
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
_THEOREM = re.compile(r"^[ \t]*theorem\b", re.MULTILINE)


@dataclass(frozen=True)
class ProblemRecord:
    """One benchmark problem, parsed from its file + metadata row."""

    id: str
    source: str  # 'FATE-M' | 'FATE-H' | 'FATE-X' | 'LeanCat'
    difficulty: str  # 'easy' | 'medium' | 'hard'
    imports: list[str] = field(default_factory=list)
    statement: str = ""  # theorem signature, no proof body
    context: str = ""  # complete source preamble between imports and theorem
    informal: str = ""  # natural-language problem description
    module: str = ""
    source_id: str = ""
    path: Path | None = None

    @property
    def import_block(self) -> str:
        """The full prelude a re-check needs: imports THEN the source preamble.

        The preamble must follow imports and precede the theorem, which is
        exactly where the validator prepends this block. Falls back to plain
        Mathlib when no imports are listed.
        """
        imp = "\n".join(f"import {m}" for m in self.imports) if self.imports else "import Mathlib"
        return f"{imp}\n{self.context}" if self.context else imp


def _extract_informal(text: str) -> str:
    m = _INFORMAL.search(text)
    return " ".join(m.group(1).split()) if m else ""


def _preamble_start(text: str) -> int:
    imports = list(_IMPORT.finditer(text))
    return imports[-1].end() if imports else 0


def _extract_context(text: str) -> str:
    """The complete source preamble between the imports and target theorem.

    Keeping the source region verbatim preserves local declarations such as
    structures and classes, as well as comments and attributes attached to
    them. Empty when the theorem immediately follows the imports.
    """
    start = _preamble_start(text)
    tm = _THEOREM.search(text, start)
    end = tm.start() if tm else len(text)
    return text[start:end].strip()


def _extract_statement(text: str) -> str:
    """Signature from the target ``theorem`` up to ``:= by`` (exclusive).

    The target is the first theorem declaration after the imports. The preamble
    and sorry body are excluded. Whitespace is preserved as written except
    leading/trailing trim, so the multi-line signature stays readable.
    """
    tm = _THEOREM.search(text, _preamble_start(text))
    if not tm:
        return ""
    after = text[tm.start() :]
    bm = _BODY_START.search(after)
    sig = after[: bm.start()] if bm else after
    return sig.strip()


def parse_problem_file(path: Path) -> tuple[str, str, list[str], str]:
    """Parse a benchmark .lean file -> (statement, informal, imports, context).

    Imports here are read from the FILE; the metadata also carries them and is
    treated as authoritative by load_dataset (the file is the fallback).
    ``context`` is the complete source preamble the theorem needs.
    """
    text = path.read_text(encoding="utf-8")
    statement = _extract_statement(text)
    informal = _extract_informal(text)
    imports = [line.split("import", 1)[1].strip() for line in _IMPORT.findall(text)]
    context = _extract_context(text)
    return statement, informal, imports, context


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
        statement, informal, file_imports, context = ("", "", [], "")
        if path.exists():
            statement, informal, file_imports, context = parse_problem_file(path)
        records.append(
            ProblemRecord(
                id=row["id"],
                source=row.get("source", ""),
                difficulty=row.get("difficulty", ""),
                # metadata imports are authoritative; file imports are fallback
                imports=row.get("imports") or file_imports,
                statement=statement,
                context=context,
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
