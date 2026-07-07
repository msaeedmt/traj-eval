"""Tests for the perseveration detector (O2). Fixtures mirror the real cap-runs:
the gpt-4o-mini induction loop (identical `rw [...]` resubmitted ~14x) and the
clean gpt-4o success (one call, no perseveration).
"""

from __future__ import annotations

from traj_eval.detectors.perseveration import detect_perseveration
from traj_eval.metrics.lean.artifacts import ToolCallRecord


def _tc(seq, code, compiled):
    return ToolCallRecord(
        call_id=f"c{seq}", code=code, compiled=compiled, sorry_free=False, seq=seq
    )


def test_identical_failing_loop_is_perseveration():
    # 14 identical failing submissions, like the real gpt-4o-mini run.
    bad = "import Mathlib\ntheorem t : a + b = b + a := by rw [Nat.add_succ, ih]"
    calls = [_tc(2 + 2 * i, bad, False) for i in range(14)]
    rep = detect_perseveration(calls)
    assert rep.perseverated is True
    assert len(rep.episodes) == 1
    assert rep.episodes[0].count == 14
    assert rep.max_repeat == 14
    assert rep.wasted_calls == 13  # all but the first attempt


def test_whitespace_differences_still_count_as_identical():
    a = "theorem t := by simp"
    b = "theorem t   :=   by   simp"  # same after normalisation
    calls = [_tc(2, a, False), _tc(4, b, False), _tc(6, a, False)]
    rep = detect_perseveration(calls)
    assert rep.perseverated is True
    assert rep.episodes[0].count == 3


def test_genuine_iteration_is_not_perseveration():
    # different code each time (real error-driven iteration) -> no episode
    calls = [
        _tc(2, "attempt one", False),
        _tc(4, "attempt two different", False),
        _tc(6, "attempt three also different", False),
    ]
    rep = detect_perseveration(calls)
    assert rep.perseverated is False
    assert rep.max_repeat == 0


def test_two_identical_below_threshold():
    # only 2 identical failures: below default min_repeats=3, not flagged
    bad = "theorem t := bad"
    calls = [_tc(2, bad, False), _tc(4, bad, False)]
    rep = detect_perseveration(calls)
    assert rep.perseverated is False


def test_clean_single_success_no_perseveration():
    # the gpt-4o run: one call, compiled -> nothing to flag
    calls = [_tc(4, "theorem t := Nat.add_comm a b", True)]
    rep = detect_perseveration(calls)
    assert rep.perseverated is False
    assert rep.n_failed_compiles == 0
    assert rep.retry_success_rate is None  # no retries


def test_retry_success_rate_counts_recoveries():
    # fail, then a DIFFERENT call succeeds -> retry that fixed it
    calls = [
        _tc(2, "bad", False),
        _tc(4, "good", True),
    ]
    rep = detect_perseveration(calls)
    assert rep.retry_success_rate == 1.0  # the one retry succeeded


def test_retry_success_rate_low_when_stuck():
    bad = "same bad"
    calls = [_tc(2 + 2 * i, bad, False) for i in range(5)]
    rep = detect_perseveration(calls)
    # 4 retry pairs (fail->fail), none succeeded
    assert rep.retry_success_rate == 0.0


def test_episode_records_span():
    bad = "loop"
    calls = [_tc(10, bad, False), _tc(12, bad, False), _tc(14, bad, False)]
    rep = detect_perseveration(calls)
    ep = rep.episodes[0]
    assert ep.start_seq == 10 and ep.end_seq == 14
