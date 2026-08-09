"""Reading prepared astro task files from our own dataset directory.

This module replaces the former ``stargazer_bridge``. There is no external
Stargazer checkout any more: the five scoring modules are vendored under
``traj_eval/vendor/stargazer`` and the task files live under ``dataset/Astro/``,
so nothing here touches ``sys.path`` and nothing imports ``rebound``.

Why validation and not computation
----------------------------------
Upstream applies ``bank._apply_rv_only_compat`` on EVERY task load (both
``TaskBank.load_task`` and ``RvEnv.reset``), so an agent never sees an
unconverted task. That conversion is therefore part of what the task *is*, not
an optional preprocessing step we may skip.

But the conversion itself needs an N-body simulation (``engine_rebound
.simulate_clean_rv``) to reconstruct the original REBOUND signal before
replacing it. Rather than carry ``rebound`` as a runtime dependency for
something that produces the same answer every time, we do the conversion ONCE,
offline, via ``scripts/prepare_astro_dataset.py``, and commit the converted
files. That is exactly equivalent to what upstream computes at load time, so
comparability with the published baseline is preserved.

This module's job is then only to CHECK that a file was prepared, and to refuse
to load one that was not -- because an unconverted task would score subtly
wrong rather than fail: the ground truth itself would not reach match 1.0, and
every anchor built on the forward model would inherit that offset. A loud error
is much better than plausible numbers.

Accepted ``meta.rv_semantics`` values:
  * ``rv_only``        -- generated analytically; no conversion was ever needed.
  * ``rv_only_compat`` -- conversion applied and baked in by the prepare script.
Anything else (including a missing key) means the file is raw upstream output.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from traj_eval.vendor.stargazer.config import Task

# The two values that mean "this file is safe to score against".
ACCEPTED_RV_SEMANTICS = frozenset({"rv_only", "rv_only_compat"})

# Where prepared tasks live, mirroring dataset/Lean/ for the Lean benchmark.
DATASET_SUBDIR = Path("dataset") / "Astro"
KINDS = ("synthetic", "real")


class AstroDatasetError(RuntimeError):
    """A task file is missing, unreadable, or not prepared for scoring."""


def _repo_root() -> Path:
    """Walk up from this file to the project root (the dir holding pyproject)."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return here.parents[3]  # src/traj_eval/dataset/ -> repo root


def dataset_root() -> Path:
    return _repo_root() / DATASET_SUBDIR


def bank_dir(kind: str) -> Path:
    """Directory holding the prepared task files for one bank."""
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}, got {kind!r}")
    return dataset_root() / kind


def rv_semantics(task_or_meta: Any) -> str | None:
    """Read the ``rv_semantics`` label off a Task or a raw meta dict."""
    meta = getattr(task_or_meta, "meta", task_or_meta)
    if not isinstance(meta, dict):
        return None
    value = meta.get("rv_semantics")
    return str(value) if value is not None else None


def is_prepared(task_or_meta: Any) -> bool:
    return rv_semantics(task_or_meta) in ACCEPTED_RV_SEMANTICS


def assert_prepared(task: Task, *, path: Path | None = None) -> None:
    """Raise unless the task has been converted to RV-only semantics.

    The error names the one command that fixes it, because the failure is not
    something a reader can be expected to diagnose from the symptom.
    """
    if is_prepared(task):
        return
    where = f" ({path})" if path is not None else ""
    found = rv_semantics(task)
    raise AstroDatasetError(
        f"Task {task.task_id!r}{where} has rv_semantics={found!r}, which is raw "
        f"upstream output. It must be converted to RV-only semantics before it "
        f"can be scored -- otherwise the ground truth itself will not reach "
        f"match 1.0 and every forward-model anchor inherits the offset.\n"
        f"Run the one-time preparation step:\n"
        f"    uv run --with rebound python scripts/prepare_astro_dataset.py \\\n"
        f"        --stargazer-root /path/to/Stargazer"
    )


def read_task_file(path: str | Path) -> Task:
    """Load and validate one prepared task JSON.

    Uses the vendored ``Task.from_json``, so the parsed dataclasses are exactly
    the ones the vendored evaluator expects.
    """
    path = Path(path)
    if not path.is_file():
        raise AstroDatasetError(f"No such task file: {path}")
    try:
        task = Task.from_json(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise AstroDatasetError(f"Could not parse task file {path}: {exc}") from exc
    assert_prepared(task, path=path)
    return task


def list_task_files(kind: str = "synthetic") -> list[Path]:
    """All task files in a bank, sorted by name."""
    directory = bank_dir(kind)
    if not directory.is_dir():
        raise AstroDatasetError(
            f"Astro task bank not found at {directory}. Run the one-time "
            f"preparation step (scripts/prepare_astro_dataset.py) to populate it."
        )
    return sorted(directory.glob("*.json"))


def task_file(task_id: str, kind: str = "synthetic") -> Path:
    """Path to one task file by id (ids look like ``seed22_diff4`` / ``real_012``)."""
    safe = task_id.replace("/", "_").replace("\\", "_")
    return bank_dir(kind) / f"{safe}.json"
