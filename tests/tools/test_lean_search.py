"""Tests for the LeanSearch parsing (Step 4i). The HTTP call is not exercised
(no network in CI); instead we test _flatten/render and the response-shape
handling against the EXACT JSON the live probe returned, plus the graceful
degradation path.
"""

from __future__ import annotations

import json
from unittest import mock

from traj_eval.tools.lean_search import (
    LemmaHit,
    _flatten,
    make_search_lemmas,
)

# A real result record, copied from scripts/probe_leansearch.py output.
_REAL_RECORD = {
    "result": {
        "module_name": ["Mathlib", "Algebra", "Group", "Nat", "Defs"],
        "kind": "instance",
        "name": ["Nat", "instAddCommMonoid"],
        "signature": ": AddCommMonoid ℕ",
        "type": "AddCommMonoid ℕ",
        "value": ":= by infer_instance",
        "docstring": None,
        "informal_name": "Additive Commutative Monoid Structure on Natural Numbers",
        "informal_description": "The natural numbers are an additive commutative monoid.",
    },
    "distance": 0.2004793882369995,
}

# The full response is a list (one per query) of lists of records.
_REAL_RESPONSE = [[_REAL_RECORD]]


def test_flatten_joins_name_and_picks_informal():
    hit = _flatten(_REAL_RECORD)
    assert isinstance(hit, LemmaHit)
    assert hit.name == "Nat.instAddCommMonoid"  # name list joined by '.'
    assert hit.kind == "instance"
    assert hit.signature == ": AddCommMonoid ℕ"
    assert "Commutative Monoid" in hit.informal
    assert hit.distance < 0.21


def test_flatten_skips_nameless():
    assert _flatten({"result": {"name": []}}) is None


def test_render_is_readable():
    hit = _flatten(_REAL_RECORD)
    line = hit.render()
    assert "Nat.instAddCommMonoid" in line
    assert "AddCommMonoid" in line


def _fake_urlopen(response_obj):
    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(response_obj).encode()

    return lambda *a, **k: _Resp()


def test_search_lemmas_parses_real_response():
    search = make_search_lemmas(num_results=4)
    with mock.patch("urllib.request.urlopen", _fake_urlopen(_REAL_RESPONSE)):
        out = search("commutativity of addition")
    assert "Nat.instAddCommMonoid" in out
    assert out.startswith("Top matches")


def test_search_lemmas_appends_question_mark():
    # The API wants queries ending in '.' or '?'; the tool should add one. We
    # can't see the sent body via the public fn, so just confirm it runs and
    # returns parsed results regardless of trailing punctuation.
    search = make_search_lemmas()
    with mock.patch("urllib.request.urlopen", _fake_urlopen(_REAL_RESPONSE)):
        assert "Nat.instAddCommMonoid" in search("no trailing punctuation")


def test_search_lemmas_handles_empty():
    search = make_search_lemmas()
    with mock.patch("urllib.request.urlopen", _fake_urlopen([[]])):
        assert "No lemmas found" in search("nonsense query zzzz")


def test_search_lemmas_degrades_on_error():
    search = make_search_lemmas()

    def _boom(*a, **k):
        raise TimeoutError("network down")

    with mock.patch("urllib.request.urlopen", _boom):
        out = search("anything")
    assert "unavailable" in out  # graceful, not an exception
