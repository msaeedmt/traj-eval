"""Extract the artifacts an offline validator judges, from a completed trace.

Pure trace analysis: no kernel, no LLM, no agent. Given the events of one trial,
this answers the questions the validator needs before it can score anything --
chiefly *what did the agent actually submit, and what did it actually verify* --
which a raw trace does not label.

Two candidate proofs are pulled out, and the difference between them is itself a
signal:

  * submitted   -- the Lean code in the engineer's final FINAL-bearing message
                   (via the 4a extractor). What the agent CLAIMS is the answer.
  * last_verified -- the ``code`` argument of the last *successful* check_lean
                   tool call. What the agent actually ran past the kernel.

When these differ, the agent shipped something it never verified (or verified
something it never shipped) -- the ``submitted_eq_last_verified`` failure. So
locating the artifact and measuring it are the same walk.

Why read the tool ARGUMENTS for last_verified, not the result text: the
TOOL_CALL payload stores ``arguments`` as the clean JSON the LLM emitted, so the
submitted code round-trips exactly. The EXECUTION_RESULT ``text`` is a Python
repr of the result dict (ag2 stringifies with str()), unsuitable for parsing --
we read the result only for its compiled/sorry verdict via the structured
``tool_responses`` mirror, never by parsing that text.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from traj_eval.metrics.lean.extract import lean_code_blocks
from traj_eval.trace_core.schema import AgentRole, EventType, TraceEvent


@dataclass(frozen=True)
class ToolCallRecord:
    """One tool call paired with the result that came back (if any).

    ``tool_name`` names which tool was invoked (check_lean, search_lemmas,
    try_tactic, show_goals, ...). ``arguments`` is the parsed argument dict as
    the LLM emitted it, so a call's payload is inspectable regardless of tool.

    ``code`` / ``compiled`` / ``sorry_free`` are the check_lean-specific fields:
    ``code`` is the ``code`` argument (None for tools that take no code), and
    ``compiled`` / ``sorry_free`` are the compile verdict (None for any tool
    that is not check_lean, since only check_lean returns a compile result). The
    compile-oriented consumers (last_verified, the perseveration detector) read
    these and MUST filter to check_lean records first -- see ``check_lean_calls``
    on TrialArtifacts, which is the check_lean-only view they use.
    """

    call_id: str | None
    code: str | None  # the `code` argument, if any (check_lean / try_tactic / show_goals)
    compiled: bool | None  # check_lean verdict only; None for other tools
    sorry_free: bool | None
    seq: int
    tool_name: str | None = None  # defaults to None == check_lean (backward compat)
    arguments: dict = field(default_factory=dict)


@dataclass(frozen=True)
class TrialArtifacts:
    """Everything the validator reads from a trace, with no kernel involved.

    ``submitted`` / ``last_verified`` are Lean source strings (or None when the
    trace has neither). The booleans summarise process facts the validator turns
    into Group-A metrics.
    """

    submitted: str | None
    last_verified: str | None
    # ``tool_calls`` is the check_lean-ONLY view, kept for backward compatibility:
    # every consumer that reads .code/.compiled (last_verified, the perseveration
    # detector, analyze_batch's got_clean) expects only compile records here, so
    # this list contains exactly the check_lean calls. The full, all-tools list
    # is ``all_tool_calls``.
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    all_tool_calls: list[ToolCallRecord] = field(default_factory=list)
    declared_success: bool = False  # final step ended in critic APPROVE
    n_tool_calls: int = 0  # count of check_lean calls (backward-compatible meaning)
    n_failed_compiles: int = 0  # check_lean results whose verdict was compiled == False
    # Per-tool call counts over ALL tools (check_lean, search_lemmas, try_tactic,
    # show_goals, ...). This is what makes non-compile tool activity measurable:
    # e.g. {"check_lean": 4, "show_goals": 6, "search_lemmas": 3, "try_tactic": 0}.
    tool_call_counts: dict[str, int] = field(default_factory=dict)

    @property
    def compiler_was_called(self) -> bool:
        return self.n_tool_calls > 0

    @property
    def n_all_tool_calls(self) -> int:
        """Total tool calls across every tool, not just check_lean."""
        return len(self.all_tool_calls)

    @property
    def submitted_eq_last_verified(self) -> bool | None:
        """True iff the submitted proof is exactly what was last verified.

        None when one side is missing (no submission, or never verified) -- the
        comparison is undefined rather than False, so the validator can report
        'not applicable' instead of a misleading mismatch.
        """
        if self.submitted is None or self.last_verified is None:
            return None
        return _normalise(self.submitted) == _normalise(self.last_verified)


def _normalise(code: str) -> str:
    """Whitespace-insensitive form for comparing two Lean snippets.

    Collapses runs of whitespace and strips ends. This is only for the
    submitted-vs-verified *string* comparison; the kernel-based checks
    (statement_preserved) never rely on it.
    """
    return " ".join(code.split())


def _call_info(event: TraceEvent) -> tuple[str | None, str | None, str | None, dict]:
    """(call_id, tool_name, code, arguments) from a TOOL_CALL event's first call.

    Generalised over ``_call_code``: reads whichever tool was called, not only
    check_lean. ``code`` is the ``code`` argument when present (check_lean /
    try_tactic / show_goals all take one), else None. ``arguments`` is the full
    parsed argument dict (e.g. ``{"query": ...}`` for search_lemmas), or {} when
    it cannot be parsed -- an unreadable argument is empty, never guessed.
    """
    calls = event.payload.get("tool_calls") or []
    for c in calls:
        name = c.get("name")
        args = c.get("arguments")
        if not args:
            return c.get("id"), name, None, {}
        try:
            parsed = json.loads(args)
        except (json.JSONDecodeError, TypeError):
            return c.get("id"), name, None, {}
        code = parsed.get("code") if isinstance(parsed, dict) else None
        return c.get("id"), name, code, (parsed if isinstance(parsed, dict) else {})
    return None, None, None, {}


def _result_verdict(event: TraceEvent) -> tuple[str | None, bool | None, bool | None]:
    """(call_id, compiled, sorry_free) from an EXECUTION_RESULT event.

    The structured verdict is read from the result's mirrored content. ag2
    stringifies the tool's returned dict with str() (Python repr, not JSON), so
    we parse it leniently with ast.literal_eval rather than json.loads, and fall
    back to None on any failure -- a verdict we cannot read is 'unknown', never a
    guessed pass/fail.
    """
    import ast

    responses = event.payload.get("tool_responses") or []
    for r in responses:
        content = r.get("content")
        if not content:
            return r.get("id"), None, None
        try:
            d = ast.literal_eval(content)
        except (ValueError, SyntaxError):
            return r.get("id"), None, None
        if isinstance(d, dict):
            return r.get("id"), d.get("compiled"), d.get("sorry_free")
    return None, None, None


def extract_artifacts(events: list[TraceEvent]) -> TrialArtifacts:
    """Walk a trial's events and assemble its TrialArtifacts (pure)."""
    events = sorted(events, key=lambda e: e.seq)

    # 1. The submitted proof: the LAST Lean code block in the LAST engineer
    #    message that carried a FINAL marker. Last block, not all blocks
    #    concatenated: a final message often shows a `sorry` scaffold AND the
    #    real proof as separate blocks, and the real answer is conventionally the
    #    last one. Gluing them would produce duplicate declarations that fail to
    #    compile, corrupting every Group-B check downstream.
    submitted: str | None = None
    for e in events:
        if e.agent_role is AgentRole.ENGINEER and e.event_type is EventType.MESSAGE:
            if e.payload.get("has_final"):
                blocks = lean_code_blocks(e.payload.get("text", ""))
                if blocks:
                    submitted = blocks[-1]

    # 2. Pair tool calls with their results by call id, in order.
    results_by_id: dict[str | None, tuple[bool | None, bool | None]] = {}
    for e in events:
        if e.event_type is EventType.EXECUTION_RESULT:
            cid, compiled, sorry_free = _result_verdict(e)
            results_by_id[cid] = (compiled, sorry_free)

    # Record EVERY tool call (check_lean, search_lemmas, try_tactic, show_goals,
    # ...). Compile verdicts only exist for check_lean results, so compiled/
    # sorry_free stay None for every other tool -- their EXECUTION_RESULT text is
    # a suggestion or a lemma list, not a {'compiled': ...} dict, so it simply is
    # not in results_by_id.
    all_tool_calls: list[ToolCallRecord] = []
    tool_call_counts: dict[str, int] = {}
    for e in events:
        if e.event_type is EventType.TOOL_CALL:
            cid, name, code, args = _call_info(e)
            compiled, sorry_free = results_by_id.get(cid, (None, None))
            all_tool_calls.append(
                ToolCallRecord(
                    call_id=cid,
                    tool_name=name,
                    code=code,
                    compiled=compiled,
                    sorry_free=sorry_free,
                    seq=e.seq,
                    arguments=args,
                )
            )
            if name is not None:
                tool_call_counts[name] = tool_call_counts.get(name, 0) + 1

    # The check_lean-only view every compile-oriented consumer expects. A record
    # with tool_name None is treated as check_lean for backward compatibility
    # (older traces did not tag the name; check_lean was the only code-bearing
    # tool then).
    tool_calls: list[ToolCallRecord] = [
        rec for rec in all_tool_calls if rec.tool_name in (None, "check_lean")
    ]

    # 3. last_verified: code of the last check_lean call whose result compiled.
    last_verified: str | None = None
    for rec in tool_calls:
        if rec.compiled and rec.code is not None:
            last_verified = rec.code

    # 3b. Submission fallback. The engineer often verifies via check_lean and
    #     then hands off with a bare `HANDOFF: critic` message that carries NO
    #     code block (the proof lives in the tool-call arguments, not re-pasted
    #     into prose). In that case step 1 found no `submitted`; fall back to
    #     what the agent last successfully verified -- which is the truest
    #     record of what it shipped. When the engineer DID paste a final block,
    #     that explicit submission is kept as primary, so a genuine
    #     submitted-vs-verified discrepancy is still detectable.
    if submitted is None:
        submitted = last_verified

    n_failed = sum(1 for rec in tool_calls if rec.compiled is False)

    # 4. declared_success: the final critic verdict in the trace is APPROVE.
    declared_success = False
    for e in events:
        if e.agent_role is AgentRole.CRITIC and e.payload.get("decision") is not None:
            declared_success = e.payload.get("decision") == "approve"

    return TrialArtifacts(
        submitted=submitted,
        last_verified=last_verified,
        tool_calls=tool_calls,
        all_tool_calls=all_tool_calls,
        declared_success=declared_success,
        n_tool_calls=len(tool_calls),  # check_lean count (backward-compatible)
        n_failed_compiles=n_failed,
        tool_call_counts=tool_call_counts,
    )
