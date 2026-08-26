"""Turn a completed astro trace into the structured records the validator reads.

Pure trace analysis: no evaluator, no truth, no LLM, no network. Given the events
of one trial, this answers *what did the team actually do* -- which tools it
called with which arguments, what came back, what it submitted, and how the roles
handed work to each other -- none of which a raw event list labels.

Why this layer is cheap for astro and was expensive for Stargazer
-----------------------------------------------------------------
Stargazer's agent had a bare PythonREPL, so its intermediate quantities
(periodogram peaks, fitted parameters, residual scatter) existed only as stdout
inside code blocks; recovering them meant reading logs by hand, which is why
their trajectory-level findings are two hand-written case studies. Our typed
tools return structured JSON, so every intermediate is a field. That is the whole
reason the trajectory metrics in ``sequence.py`` and ``oracle.py`` can be
computed automatically rather than by eye.

Parsing notes
-------------
Tool CALLS are read from the ``tool_calls`` payload of a TOOL_CALL event, where
the observer stores them flattened as ``{id, name, arguments}`` (NOT nested under
``function`` as in the live ag2 message). ``arguments`` is the clean JSON the
model emitted, so it round-trips exactly.

Tool RESULTS are read from the ``tool_responses`` of the following
EXECUTION_RESULT event and paired to their call by ``id``. Their ``content`` is a
Python ``repr`` of the result dict (ag2 stringifies with ``str()``), so it is
parsed with ``ast.literal_eval`` -- never ``json.loads``, which would fail on
``True``/``None``, and never a regex.

A call whose result is missing (truncated trace, crash) keeps ``result=None``
rather than being dropped, so a partial trace is still analysable and the gap is
visible instead of silently changing the counts.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from typing import Any

from traj_eval.trace_core.schema import EventType, TraceEvent

TOOL_PERIODOGRAM = "rv_periodogram"
TOOL_FIT = "rv_fit"
TOOL_RESIDUAL = "rv_residual"
TOOL_SUBMIT = "rv_submit"
ASTRO_TOOLS = frozenset({TOOL_PERIODOGRAM, TOOL_FIT, TOOL_RESIDUAL, TOOL_SUBMIT})

# The fitter clips eccentricity here; a planet sitting exactly on the boundary is
# the optimiser absorbing noise, not a physical orbit (see rv_model.MAX_ECC).
ECC_CLIP = 0.95
ECC_CLIP_TOL = 1e-6


def _parse_result(content: str | None) -> dict[str, Any] | None:
    """Parse a tool result payload. Tries repr first, then JSON, then gives up."""
    if not content:
        return None
    try:
        parsed = ast.literal_eval(content)
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        try:
            parsed = json.loads(content)
        except (ValueError, TypeError):
            return None
    return parsed if isinstance(parsed, dict) else None


def _parse_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        try:
            parsed = ast.literal_eval(raw)
        except (ValueError, SyntaxError):
            return {}
    return parsed if isinstance(parsed, dict) else {}


@dataclass(frozen=True)
class AstroToolCall:
    """One tool invocation paired with the result that came back, if any."""

    seq: int
    role: str
    tool_name: str
    call_id: str | None
    arguments: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    result_seq: int | None = None

    @property
    def ok(self) -> bool | None:
        """The tool's own progress verdict. None for the exploratory tools.

        ``rv_periodogram`` and ``rv_residual`` deliberately omit ``ok`` so that
        exploration does not count toward the controller's no-progress bound;
        that same absence is meaningful here.
        """
        if self.result is None:
            return None
        value = self.result.get("ok")
        return bool(value) if value is not None else None


@dataclass(frozen=True)
class FitRecord:
    """One ``rv_fit`` call: what was requested, and what came back."""

    seq: int
    role: str
    period_guesses: list[float]
    sigma_jitter_ms: float
    ok: bool
    planets: list[dict[str, Any]] = field(default_factory=list)
    rms_ms: float | None = None
    delta_bic_per_point: float | None = None
    chi2_reduced: float | None = None
    n_starts_tried: int | None = None
    n_starts_converged: int | None = None
    error: str | None = None

    @property
    def n_planets(self) -> int:
        return len(self.planets)

    @property
    def periods(self) -> list[float]:
        return [float(p.get("P_days", float("nan"))) for p in self.planets]

    @property
    def n_at_ecc_clip(self) -> int:
        """Planets pinned to the eccentricity bound -- a noise-absorption tell."""
        return sum(
            1 for p in self.planets if abs(float(p.get("e", 0.0)) - ECC_CLIP) <= ECC_CLIP_TOL
        )


@dataclass(frozen=True)
class ResidualRecord:
    """One ``rv_residual`` call: the escalate-or-stop evidence at that moment."""

    seq: int
    role: str
    n_planets_removed: int
    residual_rms_ms: float | None
    residual_rms_in_sigma: float | None
    rms_within_threshold: bool | None
    chi2_reduced: float | None
    top_peak_days: float | None
    top_peak_power: float | None
    top_peak_fap: float | None


@dataclass(frozen=True)
class PeriodogramRecord:
    """One ``rv_periodogram`` call and the peaks it returned."""

    seq: int
    role: str
    searched_range_days: tuple[float, float] | None
    peaks: list[dict[str, Any]] = field(default_factory=list)
    window_peaks_days: list[float] = field(default_factory=list)
    arguments: dict[str, Any] = field(default_factory=dict)

    @property
    def peak_periods(self) -> list[float]:
        return [float(p.get("period_days", float("nan"))) for p in self.peaks]


@dataclass(frozen=True)
class SubmissionRecord:
    """One ``rv_submit`` call and the evaluator's verdict.

    ``criteria`` mirrors the in-loop verdict as the agent saw it. The validator
    does not re-score it: the in-loop tool and any offline re-scoring call the
    same ``evaluate_submission``, so re-running would be a tautology. The
    independent judgement lives in ``oracle.py`` instead, which scores
    submissions the team could have made but did not.
    """

    seq: int
    role: str
    index: int | None
    planets: list[dict[str, Any]]
    accepted: bool
    solved: bool | None
    criteria: dict[str, bool] = field(default_factory=dict)
    failed_criteria: list[str] = field(default_factory=list)
    measured: dict[str, float] = field(default_factory=dict)
    shape_warnings: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def n_planets(self) -> int:
        return len(self.planets)

    @property
    def periods(self) -> list[float]:
        return [float(p.get("P_days", float("nan"))) for p in self.planets]

    @property
    def statistical_pass(self) -> bool:
        return bool(self.criteria.get("ok_delta_bic")) and bool(self.criteria.get("ok_rms"))

    @property
    def physical_pass(self) -> bool:
        return bool(self.criteria.get("ok_match")) and bool(self.criteria.get("ok_count"))

    @property
    def stat_phys_gap(self) -> bool:
        """Good statistics, wrong physics -- the dissociation this testbed targets."""
        return self.statistical_pass and not self.physical_pass


@dataclass(frozen=True)
class Handoff:
    seq: int
    from_role: str
    to_role: str


@dataclass(frozen=True)
class AstroTrialArtifacts:
    """Everything the validator reads from a trace, with no evaluator involved."""

    trial_id: str | None
    task_id: str | None
    tool_calls: list[AstroToolCall] = field(default_factory=list)
    fits: list[FitRecord] = field(default_factory=list)
    residuals: list[ResidualRecord] = field(default_factory=list)
    periodograms: list[PeriodogramRecord] = field(default_factory=list)
    submissions: list[SubmissionRecord] = field(default_factory=list)
    handoffs: list[Handoff] = field(default_factory=list)
    declared_success: bool = False
    messages: list[tuple[int, str, str]] = field(default_factory=list)  # (seq, role, text)

    # ---- counts -------------------------------------------------------

    @property
    def n_tool_calls(self) -> int:
        return len(self.tool_calls)

    @property
    def tool_call_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for call in self.tool_calls:
            counts[call.tool_name] = counts.get(call.tool_name, 0) + 1
        return counts

    def calls_by_role(self, role: str) -> list[AstroToolCall]:
        return [c for c in self.tool_calls if c.role == role]

    @property
    def n_failed_fits(self) -> int:
        return sum(1 for f in self.fits if not f.ok)

    @property
    def n_accepted_submissions(self) -> int:
        return sum(1 for s in self.submissions if s.accepted)

    @property
    def n_malformed_submissions(self) -> int:
        return sum(1 for s in self.submissions if not s.accepted)

    @property
    def has_submission(self) -> bool:
        return self.n_accepted_submissions > 0

    @property
    def solved(self) -> bool:
        """Best-of-episode, matching Stargazer's scoring rule."""
        return any(s.solved for s in self.submissions if s.accepted)

    # ---- the artifacts the oracle and detectors key on -----------------

    @property
    def last_fit(self) -> FitRecord | None:
        successful = [f for f in self.fits if f.ok]
        return successful[-1] if successful else None

    @property
    def last_submission(self) -> SubmissionRecord | None:
        accepted = [s for s in self.submissions if s.accepted]
        return accepted[-1] if accepted else None

    @property
    def submitted_eq_last_fitted(self) -> bool | None:
        """Did the critic submit exactly what the engineer last fitted?

        The astro analogue of Lean's ``submitted_eq_last_verified``: when these
        differ the team shipped a system it never measured, and any fit-quality
        number it quoted describes a different model than the one scored.
        None when either artifact is missing.
        """
        fit, sub = self.last_fit, self.last_submission
        if fit is None or sub is None:
            return None
        return _same_system(fit.planets, sub.planets)


def _same_system(a: list[dict[str, Any]], b: list[dict[str, Any]], *, rtol: float = 1e-6) -> bool:
    """Two planet lists describe the same system (period-sorted, within rtol)."""
    if len(a) != len(b):
        return False
    pa = sorted(float(p.get("P_days", float("nan"))) for p in a)
    pb = sorted(float(p.get("P_days", float("nan"))) for p in b)
    return all(abs(x - y) <= rtol * max(abs(x), abs(y), 1e-12) for x, y in zip(pa, pb, strict=True))


def _result_index(events: list[TraceEvent]) -> dict[str, tuple[int, dict[str, Any]]]:
    """Map tool_call id -> (result event seq, parsed result dict)."""
    out: dict[str, tuple[int, dict[str, Any]]] = {}
    for event in events:
        if event.event_type is not EventType.EXECUTION_RESULT:
            continue
        for response in event.payload.get("tool_responses") or []:
            call_id = response.get("id")
            parsed = _parse_result(response.get("content"))
            if call_id is not None and parsed is not None:
                out[str(call_id)] = (event.seq, parsed)
    return out


def _fit_record(call: AstroToolCall) -> FitRecord:
    result = call.result or {}
    guesses = call.arguments.get("period_guesses") or result.get("period_guesses_days") or []
    return FitRecord(
        seq=call.seq,
        role=call.role,
        period_guesses=[float(g) for g in guesses if isinstance(g, int | float)],
        sigma_jitter_ms=float(call.arguments.get("sigma_jitter_ms") or 0.0),
        ok=bool(result.get("ok")),
        planets=list(result.get("planets") or []),
        rms_ms=_maybe_float(result.get("rms_ms")),
        delta_bic_per_point=_maybe_float(result.get("delta_bic_per_point")),
        chi2_reduced=_maybe_float(result.get("chi2_reduced")),
        n_starts_tried=_maybe_int(result.get("n_starts_tried")),
        n_starts_converged=_maybe_int(result.get("n_starts_converged")),
        error=result.get("error"),
    )


def _residual_record(call: AstroToolCall) -> ResidualRecord:
    result = call.result or {}
    peaks = ((result.get("residual_periodogram") or {}).get("peaks")) or []
    top = peaks[0] if peaks else {}
    return ResidualRecord(
        seq=call.seq,
        role=call.role,
        n_planets_removed=_maybe_int(result.get("n_planets_removed")) or 0,
        residual_rms_ms=_maybe_float(result.get("residual_rms_ms")),
        residual_rms_in_sigma=_maybe_float(result.get("residual_rms_in_sigma")),
        rms_within_threshold=result.get("rms_within_threshold"),
        chi2_reduced=_maybe_float(result.get("chi2_reduced")),
        top_peak_days=_maybe_float(top.get("period_days")),
        top_peak_power=_maybe_float(top.get("power")),
        top_peak_fap=_maybe_float(top.get("false_alarm_probability_approx")),
    )


def _periodogram_record(call: AstroToolCall) -> PeriodogramRecord:
    result = call.result or {}
    rng = result.get("searched_period_range_days")
    return PeriodogramRecord(
        seq=call.seq,
        role=call.role,
        searched_range_days=(float(rng[0]), float(rng[1]))
        if isinstance(rng, list | tuple) and len(rng) == 2
        else None,
        peaks=list(result.get("peaks") or []),
        window_peaks_days=[float(x) for x in (result.get("spectral_window_peaks_days") or [])],
        arguments=dict(call.arguments),
    )


def _submission_record(call: AstroToolCall) -> SubmissionRecord:
    result = call.result or {}
    accepted = bool(result.get("ok"))
    return SubmissionRecord(
        seq=call.seq,
        role=call.role,
        index=_maybe_int(result.get("attempt")),
        planets=list(call.arguments.get("planets") or []),
        accepted=accepted,
        solved=bool(result.get("solved")) if accepted else None,
        criteria=dict(result.get("criteria") or {}),
        failed_criteria=list(result.get("failed_criteria") or []),
        measured={
            k: float(v)
            for k, v in (result.get("measured") or {}).items()
            if isinstance(v, int | float)
        },
        shape_warnings=list(result.get("shape_warnings") or []),
        error=result.get("error"),
    )


def _maybe_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _maybe_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def extract_astro_artifacts(
    events: list[TraceEvent],
    *,
    trial_id: str | None = None,
    task_id: str | None = None,
) -> AstroTrialArtifacts:
    """Build the structured view of one astro trial from its trace events."""
    results = _result_index(events)

    tool_calls: list[AstroToolCall] = []
    handoffs: list[Handoff] = []
    messages: list[tuple[int, str, str]] = []
    declared_success = False

    for event in events:
        role = getattr(event.agent_role, "value", str(event.agent_role))
        payload = event.payload

        if event.event_type is EventType.TOOL_CALL:
            for raw in payload.get("tool_calls") or []:
                # The observer flattens to {id, name, arguments}; tolerate the
                # nested ag2 shape too so this works on either.
                fn = raw.get("function") if isinstance(raw.get("function"), dict) else raw
                name = fn.get("name")
                if not name:
                    continue
                call_id = raw.get("id")
                seq_and_result = results.get(str(call_id)) if call_id is not None else None
                tool_calls.append(
                    AstroToolCall(
                        seq=event.seq,
                        role=role,
                        tool_name=str(name),
                        call_id=str(call_id) if call_id is not None else None,
                        arguments=_parse_arguments(fn.get("arguments")),
                        result=seq_and_result[1] if seq_and_result else None,
                        result_seq=seq_and_result[0] if seq_and_result else None,
                    )
                )
            continue

        if event.event_type is EventType.MESSAGE:
            text = payload.get("text") or ""
            if text:
                messages.append((event.seq, role, text))
            target = payload.get("handoff_target")
            if target:
                handoffs.append(Handoff(seq=event.seq, from_role=role, to_role=str(target)))
            if str(payload.get("decision") or "").lower() == "approve":
                declared_success = True

    return AstroTrialArtifacts(
        trial_id=trial_id,
        task_id=task_id,
        tool_calls=tool_calls,
        fits=[_fit_record(c) for c in tool_calls if c.tool_name == TOOL_FIT],
        residuals=[_residual_record(c) for c in tool_calls if c.tool_name == TOOL_RESIDUAL],
        periodograms=[
            _periodogram_record(c) for c in tool_calls if c.tool_name == TOOL_PERIODOGRAM
        ],
        submissions=[_submission_record(c) for c in tool_calls if c.tool_name == TOOL_SUBMIT],
        handoffs=handoffs,
        declared_success=declared_success,
        messages=messages,
    )
