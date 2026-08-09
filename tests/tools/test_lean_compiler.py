"""Step 4e: the CommandResponse -> LeanResult mapping.

Drives ``_build_result`` with fake response objects shaped exactly like the
lean_interact CommandResponse the probe printed (clean / sorry / error). Pure:
no lean_interact, no Lean toolchain, no REPL -- so this runs in plain CI.
"""

from __future__ import annotations

from types import SimpleNamespace

from traj_eval.tools.lean_compiler import LeanResult, _build_result


def _pos(line, column):
    return SimpleNamespace(line=line, column=column)


def _msg(severity, data, line=1, column=0):
    return SimpleNamespace(severity=severity, data=data, start_pos=_pos(line, column))


def _sorry(goal, line=1, column=48):
    return SimpleNamespace(goal=goal, start_pos=_pos(line, column))


def _response(messages=None, sorries=None):
    return SimpleNamespace(messages=messages or [], sorries=sorries or [])


# --- clean: no messages, no sorries (probe 'clean') ------------------------


def test_clean_proof():
    r = _build_result(_response())
    assert isinstance(r, LeanResult)
    assert r.compiled is True
    assert r.sorry_free is True
    assert r.n_errors == 0 and r.n_sorries == 0
    assert r.summary == "compiled: true; sorries: 0; errors: 0"


# --- sorry: a sorries entry + a 'sorry' warning (probe 'sorry') ------------


def test_sorry_detected():
    resp = _response(
        messages=[_msg("warning", "declaration uses `sorry`", line=1, column=8)],
        sorries=[_sorry("n : Nat\n\u22a2 n + 0 = n")],
    )
    r = _build_result(resp)
    assert r.compiled is True  # a sorry still type-checks
    assert r.sorry_free is False
    assert r.n_sorries == 1
    assert r.sorries[0].goal.startswith("n : Nat")
    assert r.n_errors == 0
    assert len(r.warnings) == 1
    assert "incomplete" in r.summary


# --- error: an error-severity message, no sorries (probe 'error') ----------


def test_error_detected():
    resp = _response(
        messages=[
            _msg("error", "numerals are data in Lean...\n  n + 0 = n : Prop", line=1, column=54)
        ]
    )
    r = _build_result(resp)
    assert r.compiled is False
    assert r.n_errors == 1
    assert r.errors[0].line == 1
    assert "compiled: false" in r.summary
    # summary uses only the first line of the error text
    assert "\n" not in r.summary


# --- cheat: looks identical to clean (probe 'cheat') -----------------------


def test_cheat_looks_like_clean():
    # A weakened statement that type-checks returns an empty response, exactly
    # like a real proof. The tool CANNOT distinguish it -- documents why the
    # statement-faithfulness check must live in the offline validator.
    r = _build_result(_response())
    assert r.compiled is True and r.sorry_free is True


# --- mixed: error takes precedence over a stray warning --------------------


def test_error_and_warning_classified_separately():
    resp = _response(
        messages=[
            _msg("warning", "unused variable", line=1, column=4),
            _msg("error", "type mismatch", line=2, column=2),
        ]
    )
    r = _build_result(resp)
    assert r.compiled is False
    assert r.n_errors == 1
    assert len(r.warnings) == 1


def test_to_dict_has_summary_and_detail():
    r = _build_result(_response(sorries=[_sorry("g")]))
    d = r.to_dict()
    assert "summary" in d
    assert d["n_sorries"] == 1
    assert d["sorries"][0]["goal"] == "g"


def test_check_survives_server_crash():
    # A REPL panic (e.g. Nat.pow exponent too big) must become a failed result,
    # not a raised exception that aborts a whole batch.
    import pytest

    pytest.importorskip("lean_interact")
    from traj_eval.tools.lean_compiler import LeanCompiler

    comp = LeanCompiler.__new__(LeanCompiler)  # bypass __init__ (no real server)
    comp._timeout = 5

    class _BoomServer:
        def run(self, *a, **k):
            raise ConnectionAbortedError("The Lean server closed unexpectedly.")

    comp._server = _BoomServer()
    res = comp.check("import Mathlib\nexample : True := by native_decide")
    assert res.compiled is False
    assert res.n_errors == 1
    assert "lean server error" in res.summary
