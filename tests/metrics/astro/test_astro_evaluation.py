"""Tests for the offline astro evaluation layer.

Everything here is trace-in / numbers-out: no LLM, no network, and (except for
the oracle tests) no evaluator. The fixtures are hand-built event lists rather
than recorded runs, so each test pins one behaviour without depending on a
particular model's output.
"""

from __future__ import annotations

import json
import uuid

import pytest

from traj_eval.metrics.astro.artifacts import (
    extract_astro_artifacts,
)
from traj_eval.metrics.astro.sequence import (
    Transition,
    analyse_self_signal,
    build_sequence,
)
from traj_eval.metrics.astro.validator import (
    detect_noise_absorbing_planet,
    detect_rubber_stamp,
    detect_stat_phys_gap,
    detect_unverifiable_claim,
    detect_wrong_direction_escalation,
    validate_astro_trial,
)
from traj_eval.trace_core.schema import AgentRole, EventType, TraceEvent

# --------------------------------------------------------------------------
# fixture helpers
# --------------------------------------------------------------------------


class TraceBuilder:
    """Assemble a plausible astro trace event by event."""

    def __init__(self) -> None:
        self.events: list[TraceEvent] = []
        self._seq = 0
        self._call = 0

    def _add(self, event_type: EventType, role: AgentRole, payload: dict) -> None:
        self.events.append(
            TraceEvent(
                event_id=str(uuid.uuid4()),
                trial_id="t",
                seq=self._seq,
                timestamp="2026-01-01T00:00:00Z",
                event_type=event_type,
                agent_role=role,
                caused_by=[],
                payload=payload,
            )
        )
        self._seq += 1

    def message(
        self, role: AgentRole, text: str, *, handoff: str | None = None, decision: str | None = None
    ) -> TraceBuilder:
        payload: dict = {"sender": role.value, "text": text}
        if handoff:
            payload["handoff_target"] = handoff
        if decision:
            payload["decision"] = decision
        self._add(EventType.MESSAGE, role, payload)
        return self

    def tool(self, role: AgentRole, name: str, arguments: dict, result: dict) -> TraceBuilder:
        self._call += 1
        call_id = f"call_{self._call}"
        self._add(
            EventType.TOOL_CALL,
            role,
            {"tool_calls": [{"id": call_id, "name": name, "arguments": json.dumps(arguments)}]},
        )
        self._add(
            EventType.EXECUTION_RESULT,
            AgentRole.EXECUTOR,
            {"tool_responses": [{"id": call_id, "content": repr(result)}], "text": repr(result)},
        )
        return self


def planet(period: float, *, ecc: float = 0.1) -> dict:
    return {
        "P_days": period,
        "m_sin_i_mjup": 0.5,
        "e": ecc,
        "inc_rad": 0.0,
        "Omega_rad": 0.0,
        "omega_rad": 1.0,
        "l_rad": 2.0,
    }


def fit_result(
    planets: list[dict], *, rms: float = 1.0, chi2: float = 1.1, ok: bool = True
) -> dict:
    return {
        "ok": ok,
        "planets": planets,
        "rms_ms": rms,
        "delta_bic_per_point": 100.0,
        "chi2_reduced": chi2,
        "n_starts_tried": 8,
        "n_starts_converged": 7,
    }


def submit_result(
    *,
    attempt: int,
    solved: bool,
    bic: bool = True,
    rms_ok: bool = True,
    match_ok: bool = True,
    count_ok: bool = True,
    rms: float = 1.0,
    match: float = 0.9,
) -> dict:
    criteria = {
        "ok_delta_bic": bic,
        "ok_rms": rms_ok,
        "ok_match": match_ok,
        "ok_count": count_ok,
    }
    return {
        "ok": True,
        "attempt": attempt,
        "attempts_remaining": 5 - attempt,
        "solved": solved,
        "criteria": criteria,
        "failed_criteria": [k for k, v in criteria.items() if not v],
        "measured": {"rms_ms": rms, "match_score": match},
        "shape_warnings": [],
    }


# --------------------------------------------------------------------------
# artifacts
# --------------------------------------------------------------------------


def test_extractor_pairs_calls_with_their_results() -> None:
    b = TraceBuilder()
    b.tool(
        AgentRole.ENGINEER,
        "rv_fit",
        {"period_guesses": [11.2]},
        fit_result([planet(11.2)], rms=1.4),
    )
    art = extract_astro_artifacts(b.events)
    assert art.n_tool_calls == 1
    assert art.tool_call_counts == {"rv_fit": 1}
    fit = art.fits[0]
    assert fit.ok and fit.rms_ms == 1.4
    assert fit.period_guesses == [11.2]
    assert fit.periods == [11.2]


def test_exploratory_tools_report_no_progress_verdict() -> None:
    """rv_periodogram and rv_residual omit ``ok`` so exploration is not thrashing."""
    b = TraceBuilder()
    b.tool(AgentRole.PLANNER, "rv_periodogram", {}, {"peaks": [], "spectral_window_peaks_days": []})
    b.tool(AgentRole.ENGINEER, "rv_residual", {"planets": []}, {"residual_rms_ms": 3.0})
    art = extract_astro_artifacts(b.events)
    assert all(c.ok is None for c in art.tool_calls)


def test_a_call_without_a_result_is_kept_not_dropped() -> None:
    """A truncated trace must stay analysable, with the gap visible."""
    b = TraceBuilder()
    b._add(  # noqa: SLF001 - deliberately builds a call with no matching result
        EventType.TOOL_CALL,
        AgentRole.ENGINEER,
        {"tool_calls": [{"id": "orphan", "name": "rv_fit", "arguments": "{}"}]},
    )
    art = extract_astro_artifacts(b.events)
    assert art.n_tool_calls == 1
    assert art.tool_calls[0].result is None
    assert art.fits[0].ok is False


def test_malformed_submission_does_not_count_as_scored() -> None:
    b = TraceBuilder()
    b.tool(
        AgentRole.CRITIC,
        "rv_submit",
        {"planets": []},
        {"ok": False, "error": "malformed submission: planets[0] must include 'P_days'"},
    )
    art = extract_astro_artifacts(b.events)
    assert art.n_accepted_submissions == 0
    assert art.n_malformed_submissions == 1
    assert not art.has_submission


def test_submitted_eq_last_fitted_detects_a_mismatch() -> None:
    """Shipping a system that was never measured invalidates every quoted number."""
    b = TraceBuilder()
    b.tool(AgentRole.ENGINEER, "rv_fit", {"period_guesses": [11.2]}, fit_result([planet(11.2)]))
    b.tool(
        AgentRole.CRITIC,
        "rv_submit",
        {"planets": [planet(57.9)]},
        submit_result(attempt=1, solved=False, match_ok=False, match=0.1),
    )
    assert extract_astro_artifacts(b.events).submitted_eq_last_fitted is False


def test_declared_success_reads_the_approve_decision() -> None:
    b = TraceBuilder().message(AgentRole.CRITIC, "All good.", decision="approve")
    assert extract_astro_artifacts(b.events).declared_success


# --------------------------------------------------------------------------
# sequence
# --------------------------------------------------------------------------


def test_fit_then_submit_of_the_same_system_is_a_commit_not_a_repeat() -> None:
    """The intended handoff must not score as thrashing.

    Counting it as a repeat made a clean single-shot success report
    revision_ratio 0.0, which inverted the metric's meaning.
    """
    b = TraceBuilder()
    b.tool(AgentRole.ENGINEER, "rv_fit", {"period_guesses": [11.2]}, fit_result([planet(11.2)]))
    b.tool(
        AgentRole.CRITIC,
        "rv_submit",
        {"planets": [planet(11.2)]},
        submit_result(attempt=1, solved=True),
    )
    seq = build_sequence(extract_astro_artifacts(b.events))
    assert [t.kind for t in seq.transitions] == [Transition.COMMIT]
    assert seq.count(Transition.REPEAT) == 0
    # Undefined, not zero: a single-shot success has no repetition to measure.
    assert seq.revision_ratio is None


def test_adding_a_planet_is_an_escalation() -> None:
    b = TraceBuilder()
    b.tool(AgentRole.ENGINEER, "rv_fit", {}, fit_result([planet(20.8)], rms=6.4))
    b.tool(AgentRole.ENGINEER, "rv_fit", {}, fit_result([planet(15.9), planet(21.7)], rms=0.8))
    seq = build_sequence(extract_astro_artifacts(b.events))
    assert seq.count(Transition.ESCALATE) == 1
    assert seq.planet_count_path == [1, 2]
    assert seq.revision_ratio == 1.0


def test_resubmitting_the_same_system_is_a_repeat() -> None:
    """Stargazer's documented pathology: the same wrong answer, again."""
    b = TraceBuilder()
    for attempt in (1, 2, 3):
        b.tool(
            AgentRole.CRITIC,
            "rv_submit",
            {"planets": [planet(111.7), planet(164.5)]},
            submit_result(attempt=attempt, solved=False, match_ok=False, match=-0.008),
        )
    seq = build_sequence(extract_astro_artifacts(b.events))
    assert seq.count(Transition.REPEAT) == 2
    assert seq.max_consecutive_repeats == 2
    assert seq.revision_ratio == 0.0


def test_same_count_different_periods_is_exploration() -> None:
    b = TraceBuilder()
    b.tool(AgentRole.ENGINEER, "rv_fit", {}, fit_result([planet(11.2)]))
    b.tool(AgentRole.ENGINEER, "rv_fit", {}, fit_result([planet(57.9)]))
    seq = build_sequence(extract_astro_artifacts(b.events))
    assert seq.count(Transition.EXPLORE) == 1
    assert seq.distinct_systems == 2


def test_periods_within_grid_resolution_are_the_same_system() -> None:
    """A 1% difference is periodogram quantisation, not a new hypothesis."""
    b = TraceBuilder()
    b.tool(AgentRole.ENGINEER, "rv_fit", {}, fit_result([planet(11.20)]))
    b.tool(AgentRole.ENGINEER, "rv_fit", {}, fit_result([planet(11.29)]))
    seq = build_sequence(extract_astro_artifacts(b.events))
    assert seq.count(Transition.EXPLORE) == 0
    assert seq.distinct_systems == 1


def test_failed_fits_are_not_model_states() -> None:
    b = TraceBuilder()
    b.tool(AgentRole.ENGINEER, "rv_fit", {}, {"ok": False, "error": "no start converged"})
    b.tool(AgentRole.ENGINEER, "rv_fit", {}, fit_result([planet(11.2)]))
    seq = build_sequence(extract_astro_artifacts(b.events))
    assert len(seq.states) == 1


# --------------------------------------------------------------------------
# self-signal
# --------------------------------------------------------------------------


def test_misleading_self_signal_fires_when_rms_improves_and_match_worsens() -> None:
    """The team's visible feedback endorsed a change that made the answer worse.

    Stargazer measured the statistical/physical dissociation across models; this
    is the same dissociation inside one trajectory, over time.
    """
    b = TraceBuilder()
    b.tool(
        AgentRole.CRITIC,
        "rv_submit",
        {"planets": [planet(11.2)]},
        submit_result(attempt=1, solved=False, match_ok=False, rms=2.27, match=0.72),
    )
    b.tool(
        AgentRole.CRITIC,
        "rv_submit",
        {"planets": [planet(11.2), planet(4.4)]},
        submit_result(
            attempt=2, solved=False, match_ok=False, count_ok=False, rms=1.97, match=0.42
        ),
    )
    signal = analyse_self_signal(extract_astro_artifacts(b.events))
    assert signal.misleading
    assert signal.n_misleading_steps == 1
    assert signal.agreement == 0.0


def test_self_signal_agrees_when_both_improve() -> None:
    b = TraceBuilder()
    b.tool(
        AgentRole.CRITIC,
        "rv_submit",
        {"planets": [planet(11.2)]},
        submit_result(attempt=1, solved=False, match_ok=False, rms=3.0, match=0.4),
    )
    b.tool(
        AgentRole.CRITIC,
        "rv_submit",
        {"planets": [planet(11.2), planet(57.9)]},
        submit_result(attempt=2, solved=True, rms=1.0, match=0.95),
    )
    signal = analyse_self_signal(extract_astro_artifacts(b.events))
    assert not signal.misleading
    assert signal.agreement == 1.0


def test_self_signal_undefined_with_one_submission() -> None:
    b = TraceBuilder()
    b.tool(
        AgentRole.CRITIC,
        "rv_submit",
        {"planets": [planet(11.2)]},
        submit_result(attempt=1, solved=True),
    )
    assert analyse_self_signal(extract_astro_artifacts(b.events)).agreement is None


# --------------------------------------------------------------------------
# detectors
# --------------------------------------------------------------------------


def test_rubber_stamp_fires_when_the_critic_never_checks() -> None:
    b = TraceBuilder()
    b.tool(
        AgentRole.CRITIC,
        "rv_submit",
        {"planets": [planet(11.2)]},
        submit_result(attempt=1, solved=True),
    )
    b.message(AgentRole.CRITIC, "Passed.", decision="approve")
    assert detect_rubber_stamp(extract_astro_artifacts(b.events))


def test_rubber_stamp_does_not_fire_when_the_critic_verifies() -> None:
    b = TraceBuilder()
    b.tool(
        AgentRole.CRITIC,
        "rv_residual",
        {"planets": [planet(11.2)]},
        {"residual_rms_ms": 1.0, "rms_within_threshold": True},
    )
    b.tool(
        AgentRole.CRITIC,
        "rv_submit",
        {"planets": [planet(11.2)]},
        submit_result(attempt=1, solved=True),
    )
    assert not detect_rubber_stamp(extract_astro_artifacts(b.events))


def test_rubber_stamp_does_not_fire_when_the_critic_never_acted() -> None:
    """An episode that ended before the critic did anything is not a rubber stamp."""
    b = TraceBuilder().message(AgentRole.PLANNER, "Two planets.", handoff="engineer")
    assert not detect_rubber_stamp(extract_astro_artifacts(b.events))


def test_unverifiable_claim_fires_on_a_pre_submission_match_assertion() -> None:
    b = TraceBuilder()
    b.message(
        AgentRole.ENGINEER,
        "The orbits match the underlying system based on the fitted parameters.",
        handoff="critic",
    )
    b.tool(
        AgentRole.CRITIC,
        "rv_submit",
        {"planets": [planet(11.2)]},
        submit_result(attempt=1, solved=False, match_ok=False),
    )
    assert detect_unverifiable_claim(extract_astro_artifacts(b.events))


def test_the_same_sentence_after_a_submission_is_a_legitimate_report() -> None:
    b = TraceBuilder()
    b.tool(
        AgentRole.CRITIC,
        "rv_submit",
        {"planets": [planet(11.2)]},
        submit_result(attempt=1, solved=True),
    )
    b.message(AgentRole.ENGINEER, "The orbits match the underlying system.", handoff="critic")
    assert not detect_unverifiable_claim(extract_astro_artifacts(b.events))


def test_noise_absorbing_planet_fires_at_the_eccentricity_clip() -> None:
    """A planet pinned exactly to 0.95 is the optimiser hitting the bound."""
    b = TraceBuilder()
    b.tool(AgentRole.ENGINEER, "rv_fit", {}, fit_result([planet(2.41, ecc=0.95)]))
    assert detect_noise_absorbing_planet(extract_astro_artifacts(b.events))


def test_noise_absorbing_planet_fires_on_sub_unity_chi_square() -> None:
    b = TraceBuilder()
    b.tool(AgentRole.ENGINEER, "rv_fit", {}, fit_result([planet(11.2)], chi2=0.74))
    assert detect_noise_absorbing_planet(extract_astro_artifacts(b.events))


def test_a_healthy_fit_is_not_flagged() -> None:
    b = TraceBuilder()
    b.tool(AgentRole.ENGINEER, "rv_fit", {}, fit_result([planet(11.2, ecc=0.2)], chi2=1.07))
    assert not detect_noise_absorbing_planet(extract_astro_artifacts(b.events))


def test_wrong_direction_escalation_needs_two_count_failures() -> None:
    b = TraceBuilder()
    b.tool(
        AgentRole.CRITIC,
        "rv_submit",
        {"planets": [planet(11.2), planet(2.4)]},
        submit_result(attempt=1, solved=False, match_ok=False, count_ok=False),
    )
    b.tool(
        AgentRole.CRITIC,
        "rv_submit",
        {"planets": [planet(11.2), planet(2.4), planet(4.4)]},
        submit_result(attempt=2, solved=False, match_ok=False, count_ok=False),
    )
    assert detect_wrong_direction_escalation(extract_astro_artifacts(b.events))


def test_a_count_fix_that_works_is_not_flagged() -> None:
    b = TraceBuilder()
    b.tool(
        AgentRole.CRITIC,
        "rv_submit",
        {"planets": [planet(11.2), planet(2.4)]},
        submit_result(attempt=1, solved=False, match_ok=False, count_ok=False),
    )
    b.tool(
        AgentRole.CRITIC,
        "rv_submit",
        {"planets": [planet(11.2)]},
        submit_result(attempt=2, solved=True),
    )
    assert not detect_wrong_direction_escalation(extract_astro_artifacts(b.events))


def test_stat_phys_gap_is_the_operational_silent_failure_signal() -> None:
    """Good statistics, wrong physics -- the dissociation this testbed targets."""
    b = TraceBuilder()
    b.tool(
        AgentRole.CRITIC,
        "rv_submit",
        {"planets": [planet(111.7)]},
        submit_result(
            attempt=1,
            solved=False,
            bic=True,
            rms_ok=True,
            match_ok=False,
            count_ok=False,
            match=-0.008,
        ),
    )
    art = extract_astro_artifacts(b.events)
    assert detect_stat_phys_gap(art)
    assert art.submissions[0].statistical_pass
    assert not art.submissions[0].physical_pass


# --------------------------------------------------------------------------
# the validator
# --------------------------------------------------------------------------


def test_group_b_is_none_without_task_and_truth() -> None:
    """Trace-only analysis must work with no dataset present."""
    b = TraceBuilder()
    b.tool(AgentRole.ENGINEER, "rv_fit", {}, fit_result([planet(11.2)]))
    b.tool(
        AgentRole.CRITIC,
        "rv_submit",
        {"planets": [planet(11.2)]},
        submit_result(attempt=1, solved=True),
    )
    m = validate_astro_trial(b.events, trial_id="t", task_id="task")
    assert m.reachable_solved is None
    assert m.had_it_and_lost_it is None
    assert m.flags.discarded_passing_solution is None
    assert m.solved is True


def test_silent_failure_requires_an_unsolved_trial() -> None:
    """A solved trial with a fired mode is worth reporting, but is not a silent failure."""
    b = TraceBuilder()
    b.tool(
        AgentRole.CRITIC,
        "rv_submit",
        {"planets": [planet(11.2)]},
        submit_result(attempt=1, solved=True),
    )
    b.message(AgentRole.CRITIC, "Passed.", decision="approve")
    m = validate_astro_trial(b.events, trial_id="t", task_id="task")
    assert "rubber_stamp_approval" in m.flags.fired
    assert m.solved and not m.silent_failure


def test_best_of_episode_scoring_matches_stargazer() -> None:
    """Only the best submission counts, so a later worse one must not overwrite it."""
    b = TraceBuilder()
    b.tool(
        AgentRole.CRITIC,
        "rv_submit",
        {"planets": [planet(11.2)]},
        submit_result(attempt=1, solved=True, match=0.95),
    )
    b.tool(
        AgentRole.CRITIC,
        "rv_submit",
        {"planets": [planet(3.3)]},
        submit_result(attempt=2, solved=False, match_ok=False, match=0.1),
    )
    m = validate_astro_trial(b.events, trial_id="t", task_id="task")
    assert m.solved
    assert m.best_match_score == pytest.approx(0.95)
