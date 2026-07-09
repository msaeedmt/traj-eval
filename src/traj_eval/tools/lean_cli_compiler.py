"""Direct Lean checker backed by local Lean project artifacts.

This is a simpler runtime alternative to the long-lived LeanInteract server for
batch experiments. It checks each snippet in a fresh temporary file inside the
Lean project and returns the same LeanResult shape consumed by the agents and
offline validator.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path
from typing import Any

from traj_eval.tools.lean_compiler import LeanMessage, LeanResult


class LeanCliCompiler:
    """Check Lean snippets with local Lean artifacts, avoiding Lake downloads."""

    def __init__(self, project_dir: str | Path, *, timeout: int = 120) -> None:
        self.project_dir = Path(project_dir).resolve()
        self.timeout = timeout
        self.tmp_dir = self.project_dir / ".traj_eval_tmp"
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        self.lean_bin = self._find_local_lean()
        self.lean_path = self._build_lean_path()
        if self.lean_bin is None:
            raise FileNotFoundError(
                f"local Lean binary for {self.project_dir / 'lean-toolchain'} was not found"
            )
        if not self.lean_path:
            raise FileNotFoundError(
                f"local Lean build artifacts were not found under {self.project_dir / '.lake'}"
            )

    def _find_local_lean(self) -> Path | None:
        toolchain_file = self.project_dir / "lean-toolchain"
        if not toolchain_file.exists():
            return None
        toolchain = toolchain_file.read_text(encoding="utf-8-sig").strip()
        prefix = "leanprover/lean4:"
        if not toolchain.startswith(prefix):
            return None
        name = "leanprover--lean4---" + toolchain.removeprefix(prefix)
        home = Path.home() / ".elan" / "toolchains" / name / "bin"
        exe = home / ("lean.exe" if os.name == "nt" else "lean")
        return exe if exe.exists() else None

    def _build_lean_path(self) -> list[str]:
        paths: list[str] = []
        own = self.project_dir / ".lake" / "build" / "lib" / "lean"
        if own.exists():
            paths.append(str(own))
        packages = self.project_dir / ".lake" / "packages"
        if packages.exists():
            for package in sorted(p for p in packages.iterdir() if p.is_dir()):
                lib = package / ".lake" / "build" / "lib" / "lean"
                if lib.exists():
                    paths.append(str(lib))
        return paths

    def _command_and_env(self, path: Path) -> tuple[list[str], dict[str, str] | None]:
        env = os.environ.copy()
        existing = env.get("LEAN_PATH")
        parts = [*self.lean_path]
        if existing:
            parts.append(existing)
        env["LEAN_PATH"] = os.pathsep.join(parts)
        return [str(self.lean_bin), str(path)], env

    def check(self, code: str) -> LeanResult:
        path = self.tmp_dir / f"check_{uuid.uuid4().hex}.lean"
        path.write_text(code, encoding="utf-8")
        cmd, env = self._command_and_env(path)
        try:
            proc = subprocess.run(
                cmd,
                cwd=self.project_dir,
                text=True,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            msg = LeanMessage(
                severity="error",
                data=f"lean timed out after {self.timeout}s: {exc}",
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
