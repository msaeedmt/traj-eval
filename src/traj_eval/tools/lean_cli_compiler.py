"""Direct Lean checker backed by ``lake env lean``.

This is a simpler runtime alternative to the long-lived LeanInteract server for
batch experiments. It checks each snippet in a fresh temporary file inside the
Lean project and returns the same LeanResult shape consumed by the agents and
offline validator.
"""

from __future__ import annotations

import subprocess
import uuid
from pathlib import Path
from typing import Any

from traj_eval.tools.lean_compiler import LeanMessage, LeanResult


class LeanCliCompiler:
    """Check Lean snippets by shelling out to ``lake env lean``."""

    def __init__(self, project_dir: str | Path, *, timeout: int = 120) -> None:
        self.project_dir = Path(project_dir)
        self.timeout = timeout
        self.tmp_dir = self.project_dir / ".traj_eval_tmp"
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    def check(self, code: str) -> LeanResult:
        path = self.tmp_dir / f"check_{uuid.uuid4().hex}.lean"
        path.write_text(code, encoding="utf-8")
        try:
            proc = subprocess.run(
                ["lake", "env", "lean", str(path.relative_to(self.project_dir))],
                cwd=self.project_dir,
                text=True,
                capture_output=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired as exc:
            msg = LeanMessage(
                severity="error",
                data=f"lake env lean timed out after {self.timeout}s: {exc}",
            )
            return LeanResult(
                compiled=False,
                sorry_free=False,
                n_sorries=0,
                n_errors=1,
                errors=[msg],
                summary=msg.data,
            )
        finally:
            path.unlink(missing_ok=True)

        output = "\n".join(part for part in (proc.stdout, proc.stderr) if part)
        compiled = proc.returncode == 0
        sorry_count = output.lower().count("declaration uses 'sorry'")
        sorry_free = sorry_count == 0
        errors = [] if compiled else [LeanMessage(severity="error", data=output.strip())]
        warnings = []
        if compiled and output.strip():
            warnings.append(LeanMessage(severity="warning", data=output.strip()))

        if not compiled:
            first = output.strip().splitlines()[0] if output.strip() else "lean failed"
            summary = f"compiled: false; errors: 1; first error: {first}"
        elif not sorry_free:
            summary = f"compiled: true; sorries: {sorry_count}; errors: 0"
        else:
            summary = "compiled: true; sorries: 0; errors: 0"

        return LeanResult(
            compiled=compiled,
            sorry_free=sorry_free,
            n_sorries=sorry_count,
            n_errors=len(errors),
            errors=errors,
            warnings=warnings,
            summary=summary,
        )

    def as_tool(self):
        def check_lean(code: str) -> dict[str, Any]:
            """Type-check Lean 4 source. Returns compile status, errors, and
            whether the proof is sorry-free. Call before declaring success.

            Args:
                code: Lean 4 source to check (include needed imports).
            """
            return self.check(code).to_dict()

        return check_lean
