from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

from traj_eval.tools.lean_cli_compiler import LeanCliCompiler


def _compiler(tmp_path: Path) -> LeanCliCompiler:
    compiler = object.__new__(LeanCliCompiler)
    compiler.project_dir = tmp_path
    compiler.timeout = 7
    compiler.lean_bin = Path("lean")
    compiler.lean_path = []
    return compiler


def test_init_does_not_create_a_project_temp_directory(monkeypatch, tmp_path):
    def fail_mkdir(*args, **kwargs):
        raise AssertionError("LeanCliCompiler must not create project directories")

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)
    monkeypatch.setattr(
        LeanCliCompiler, "_find_local_lean", lambda self: Path("lean")
    )
    monkeypatch.setattr(
        LeanCliCompiler, "_build_lean_path", lambda self: ["cached-lean-path"]
    )

    compiler = LeanCliCompiler(tmp_path)

    assert compiler.project_dir == tmp_path.resolve()
    assert not hasattr(compiler, "tmp_dir")


def test_check_uses_stdin_without_project_file_mutation(monkeypatch, tmp_path):
    calls: list[tuple[list[str], dict]] = []

    def fail_file_operation(*args, **kwargs):
        raise AssertionError("LeanCliCompiler must not write or unlink project files")

    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(Path, "write_text", fail_file_operation)
    monkeypatch.setattr(Path, "unlink", fail_file_operation)
    monkeypatch.setattr(subprocess, "run", run)
    code = "theorem target : True := trivial"

    result = _compiler(tmp_path).check(code)

    assert result.compiled is True
    assert len(calls) == 1
    cmd, kwargs = calls[0]
    assert cmd == ["lean", "--stdin"]
    assert kwargs["input"] == code
    assert kwargs["cwd"] == tmp_path
    assert kwargs["text"] is True
    assert kwargs["capture_output"] is True
    assert kwargs["timeout"] == 7


def test_timeout_is_an_infrastructure_unknown(monkeypatch, tmp_path):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="lean", timeout=7)

    monkeypatch.setattr(subprocess, "run", timeout)
    result = _compiler(tmp_path).check("theorem target : True := trivial")

    assert result.verification_status == "infrastructure_unknown"
    assert result.infrastructure_error is not None
    assert result.n_errors == 0
    assert result.to_dict()["verification_status"] == "infrastructure_unknown"


def test_empty_nonzero_exit_is_not_a_lean_rejection(monkeypatch, tmp_path):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr=""),
    )
    result = _compiler(tmp_path).check("theorem target : True := trivial")
    assert result.verification_status == "infrastructure_unknown"
    assert result.n_errors == 0


def test_opaque_lean_failed_output_is_not_a_rejection(monkeypatch, tmp_path):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1, stdout="lean failed", stderr=""
        ),
    )
    result = _compiler(tmp_path).check("theorem target : True := trivial")
    assert result.verification_status == "infrastructure_unknown"


def test_lean_diagnostic_is_a_rejection(monkeypatch, tmp_path):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stdout="check.lean:1:1: error: unknown identifier 'bad'",
            stderr="",
        ),
    )
    result = _compiler(tmp_path).check("theorem target : True := bad")
    assert result.verification_status == "rejected"
    assert result.compiled is False
    assert result.n_errors == 1


def test_backtick_warning_and_source_admit_are_not_sorry_free(monkeypatch, tmp_path):
    outputs = iter(
        [
            SimpleNamespace(
                returncode=0,
                stdout="warning: declaration uses `sorry`",
                stderr="",
            ),
            SimpleNamespace(returncode=0, stdout="", stderr=""),
        ]
    )
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: next(outputs))
    compiler = _compiler(tmp_path)

    warned = compiler.check("theorem target : True := trivial")
    source_admit = compiler.check("theorem target : True := by admit")

    assert warned.compiled is True and warned.sorry_free is False
    assert source_admit.compiled is True and source_admit.sorry_free is False


def test_placeholder_words_in_comments_and_strings_are_ignored(monkeypatch, tmp_path):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    code = '-- sorry\n#check "admit"\ntheorem target : True := trivial'
    result = _compiler(tmp_path).check(code)
    assert result.sorry_free is True
