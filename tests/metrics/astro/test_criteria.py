"""Tests for the astro criteria gate. No Stargazer, no rebound, no network.

These pin the thresholds against the values read out of
``stargazer.env.RvEnv._evaluate_success``. If upstream ever changes them, the
intent is that THESE tests fail loudly rather than our pass rates drifting
silently away from the published baseline.
"""

from __future__ import annotations

from traj_eval.metrics.astro.criteria import (
    DEFAULT_MAX_RMS_FACTOR,
    DEFAULT_MIN_MATCH_SCORE,
    best_criteria,
    evaluate_criteria,
)


def _info(*, delta_bic_pp: float, rms: float, match: float, count: float) -> dict:
    """Minimal stand-in for an evaluate_submission info dict."""
    return {
        "residuals": {"rms": rms, "mae": rms * 0.8},
        "components": {
            "delta_bic": delta_bic_pp,
            "neg_rms": -rms,
            "match": match,
            "count": count,
        },
    }


def test_all_four_pass() -> None:
    c = evaluate_criteria(
        _info(delta_bic_pp=12.0, rms=1.0, match=0.93, count=0.0),
        median_sigma_ms=1.0,
    )
    assert (c.ok_delta_bic, c.ok_rms, c.ok_match, c.ok_count) == (True, True, True, True)
    assert c.solved and c.statistical_pass and c.physical_pass
    assert not c.stat_phys_gap
    assert c.failed_criteria() == []


def test_rms_threshold_is_1p5_times_median_sigma() -> None:
    # Exactly on the boundary passes (upstream uses <=).
    on = evaluate_criteria(
        _info(delta_bic_pp=1.0, rms=DEFAULT_MAX_RMS_FACTOR * 2.0, match=0.9, count=0.0),
        median_sigma_ms=2.0,
    )
    assert on.ok_rms
    just_over = evaluate_criteria(
        _info(delta_bic_pp=1.0, rms=DEFAULT_MAX_RMS_FACTOR * 2.0 + 1e-6, match=0.9, count=0.0),
        median_sigma_ms=2.0,
    )
    assert not just_over.ok_rms


def test_delta_bic_must_be_strictly_positive_per_point() -> None:
    zero = evaluate_criteria(
        _info(delta_bic_pp=0.0, rms=1.0, match=0.9, count=0.0), median_sigma_ms=1.0
    )
    assert not zero.ok_delta_bic  # strict >, not >=
    tiny = evaluate_criteria(
        _info(delta_bic_pp=1e-9, rms=1.0, match=0.9, count=0.0), median_sigma_ms=1.0
    )
    assert tiny.ok_delta_bic


def test_match_threshold_default_and_boundary() -> None:
    at = evaluate_criteria(
        _info(delta_bic_pp=1.0, rms=1.0, match=DEFAULT_MIN_MATCH_SCORE, count=0.0),
        median_sigma_ms=1.0,
    )
    assert at.ok_match  # >=
    below = evaluate_criteria(
        _info(delta_bic_pp=1.0, rms=1.0, match=DEFAULT_MIN_MATCH_SCORE - 1e-6, count=0.0),
        median_sigma_ms=1.0,
    )
    assert not below.ok_match


def test_count_term_must_be_exactly_zero() -> None:
    off_by_one = evaluate_criteria(
        _info(delta_bic_pp=1.0, rms=1.0, match=0.9, count=-1.0), median_sigma_ms=1.0
    )
    assert not off_by_one.ok_count
    assert not off_by_one.physical_pass


def test_statistical_physical_dissociation() -> None:
    """The signal the whole astro testbed exists to measure."""
    c = evaluate_criteria(
        _info(delta_bic_pp=500.0, rms=0.9, match=-0.008, count=0.0),
        median_sigma_ms=1.0,
    )
    assert c.statistical_pass
    assert not c.physical_pass
    assert c.stat_phys_gap
    assert not c.solved
    assert c.failed_criteria() == ["ok_match"]


def test_hints_override_rms_threshold() -> None:
    """Real-data tasks carry per-task threshold overrides in meta.hints."""
    base = _info(delta_bic_pp=1.0, rms=4.0, match=0.9, count=0.0)
    without = evaluate_criteria(base, median_sigma_ms=1.0)
    assert not without.ok_rms  # 4.0 > 1.5
    with_hint = evaluate_criteria(base, median_sigma_ms=1.0, hints={"max_rms_ms": 5.0})
    assert with_hint.ok_rms
    assert with_hint.max_rms_ms == 5.0


def test_hints_override_match_threshold() -> None:
    base = _info(delta_bic_pp=1.0, rms=1.0, match=0.6, count=0.0)
    assert not evaluate_criteria(base, median_sigma_ms=1.0).ok_match
    relaxed = evaluate_criteria(base, median_sigma_ms=1.0, hints={"target_match_score": 0.5})
    assert relaxed.ok_match
    assert relaxed.min_match_score == 0.5


def test_malformed_hints_fall_back_to_defaults() -> None:
    for bad in ({"max_rms_ms": "abc"}, {"max_rms_ms": None}, {"max_rms_ms": 0.0}, {}):
        c = evaluate_criteria(
            _info(delta_bic_pp=1.0, rms=1.4, match=0.9, count=0.0),
            median_sigma_ms=1.0,
            hints=bad,
        )
        assert c.max_rms_ms == DEFAULT_MAX_RMS_FACTOR * 1.0


def test_missing_components_do_not_crash_and_do_not_pass() -> None:
    c = evaluate_criteria({}, median_sigma_ms=1.0)
    assert not any((c.ok_delta_bic, c.ok_rms, c.ok_match, c.ok_count))
    assert not c.solved
    assert set(c.failed_criteria()) == {"ok_delta_bic", "ok_rms", "ok_match", "ok_count"}


def test_best_criteria_prefers_solved_then_physical() -> None:
    """Stargazer scores only the BEST submission of an episode."""
    stat_only = evaluate_criteria(
        _info(delta_bic_pp=500.0, rms=0.9, match=0.1, count=0.0), median_sigma_ms=1.0
    )
    solved = evaluate_criteria(
        _info(delta_bic_pp=300.0, rms=1.0, match=0.95, count=0.0), median_sigma_ms=1.0
    )
    nothing = evaluate_criteria(
        _info(delta_bic_pp=-5.0, rms=9.0, match=-0.5, count=-1.0), median_sigma_ms=1.0
    )
    assert best_criteria([stat_only, solved, nothing]) is solved
    assert best_criteria([stat_only, nothing]) is stat_only
    assert best_criteria([]) is None


def test_best_criteria_breaks_ties_on_match_score() -> None:
    lo = evaluate_criteria(
        _info(delta_bic_pp=10.0, rms=1.0, match=0.2, count=0.0), median_sigma_ms=1.0
    )
    hi = evaluate_criteria(
        _info(delta_bic_pp=10.0, rms=1.0, match=0.7, count=0.0), median_sigma_ms=1.0
    )
    assert best_criteria([lo, hi]) is hi
