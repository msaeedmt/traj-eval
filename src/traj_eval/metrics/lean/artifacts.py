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
import re
from dataclasses import dataclass, field

from traj_eval.metrics.lean.extract import lean_code_blocks
from traj_eval.trace_core.schema import AgentRole, EventType, TraceEvent


@dataclass(frozen=True)
class ToolCallRecord:
    """One check_lean call paired with the verdict that came back (if any)."""

    call_id: str | None
    code: str | None  # the `code` argument, parsed from the call's JSON arguments
    compiled: bool | None  # from the matching result, if one was logged
    sorry_free: bool | None
    seq: int
    verification_status: str | None = None
    result_seq: int | None = None


@dataclass(frozen=True)
class TrialArtifacts:
    """Everything the validator reads from a trace, with no kernel involved.

    ``submitted`` / ``last_verified`` are Lean source strings (or None when the
    trace has neither). The booleans summarise process facts the validator turns
    into Group-A metrics.
    """

    submitted: str | None
    last_verified: str | None
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    declared_success: bool = False  # final step ended in critic APPROVE
    n_tool_calls: int = 0
    n_failed_compiles: int = 0  # tool results carrying a real Lean rejection
    submission_source: str = "none"
    submitted_kind: str = "none"
    last_verified_kind: str = "none"
    submission_accepted: bool = False

    @property
    def compiler_was_called(self) -> bool:
        return self.n_tool_calls > 0

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


def _normalise_header(header: str) -> str:
    """Whitespace-insensitive Lean header without merging identifiers.

    Lean permits either ``{R :Type*}`` or ``{R : Type*}``.  A plain
    ``split``/``join`` still considers those different, while deleting every
    space would incorrectly equate ``a b`` with the identifier ``ab``.  Keep a
    separator only where two identifier-like characters need one.
    """
    chars: list[str] = []
    i = 0
    while i < len(header):
        if not header[i].isspace():
            chars.append(header[i])
            i += 1
            continue
        while i < len(header) and header[i].isspace():
            i += 1
        previous = chars[-1] if chars else ""
        following = header[i] if i < len(header) else ""
        previous_is_word = previous.isalnum() or previous in {"_", "'"}
        following_is_word = following.isalnum() or following in {"_", "'"}
        if previous_is_word and following_is_word:
            chars.append(" ")
    return "".join(chars)


def _source_without_comments_and_strings(code: str) -> str:
    """Return Lean source with comments and strings blanked out.

    Newlines are retained so this is also safe for later diagnostic/location
    work. Lean block comments can nest, so a small scanner is more reliable
    than a regular expression here.
    """
    out: list[str] = []
    i = 0
    block_depth = 0
    in_string = False
    while i < len(code):
        pair = code[i : i + 2]
        char = code[i]
        if block_depth:
            if pair == "/-":
                block_depth += 1
                out.extend("  ")
                i += 2
            elif pair == "-/":
                block_depth -= 1
                out.extend("  ")
                i += 2
            else:
                out.append("\n" if char == "\n" else " ")
                i += 1
            continue
        if in_string:
            if char == "\\" and i + 1 < len(code):
                out.extend("  ")
                i += 2
            else:
                if char == '"':
                    in_string = False
                out.append("\n" if char == "\n" else " ")
                i += 1
            continue
        if pair == "--":
            end = code.find("\n", i)
            if end < 0:
                out.extend(" " * (len(code) - i))
                break
            out.extend(" " * (end - i))
            out.append("\n")
            i = end + 1
        elif pair == "/-":
            block_depth = 1
            out.extend("  ")
            i += 2
        elif char == '"':
            in_string = True
            out.append(" ")
            i += 1
        else:
            out.append(char)
            i += 1
    return "".join(out)


_PROHIBITED_PLACEHOLDER_RE = re.compile(
    r"(?<![A-Za-z0-9_'])\b(?:sorry|admit|sorryAx)\b"
)


def prohibited_placeholders(code: str) -> tuple[str, ...]:
    """Source-level ``sorry``/``admit``/``sorryAx`` occurrences.

    Compiler warnings are useful evidence, but they vary between Lean versions
    and quote the word ``sorry`` with either apostrophes or backticks. The source
    is authoritative, while comments and strings are intentionally ignored.
    """
    source = _source_without_comments_and_strings(code)
    return tuple(match.group(0) for match in _PROHIBITED_PLACEHOLDER_RE.finditer(source))


def contains_prohibited_placeholder(code: str) -> bool:
    return bool(prohibited_placeholders(code))


_DECL_RE = re.compile(r"\b(theorem|lemma)\s+([A-Za-z_][A-Za-z0-9_'.]*)")
_HELPER_OR_PROBE_RE = re.compile(r"\b(?:theorem|lemma|example|def)\b|#check\b")


def _declaration_header(code: str, name: str) -> str | None:
    source = _source_without_comments_and_strings(code)
    pattern = re.compile(
        rf"\b(?:theorem|lemma)\s+{re.escape(name)}(?=\s|\(|\{{|\[|:)"
    )
    match = pattern.search(source)
    if match is None:
        return None
    body_start = source.find(":=", match.start())
    if body_start < 0:
        return None
    return source[match.start() : body_start].strip()


def candidate_kind(code: str | None, target_statement: str | None) -> str:
    """Classify a checked/submitted snippet against the exact target header."""
    if code is None:
        return "none"
    if not target_statement:
        return "unknown"
    target_match = _DECL_RE.search(_source_without_comments_and_strings(target_statement))
    if target_match is None:
        return "unknown"
    target_name = target_match.group(2)
    candidate_header = _declaration_header(code, target_name)
    if candidate_header is not None:
        target_header = _declaration_header(f"{target_statement} := by trivial", target_name)
        if (
            target_header is not None
            and _normalise_header(candidate_header) == _normalise_header(target_header)
        ):
            return "exact_target"
        return "statement_drift"
    source = _source_without_comments_and_strings(code)
    declarations = _DECL_RE.findall(source)
    # A common target mutation keeps the descriptive theorem-name prefix but
    # drops a suffix (for example ``..._transitive_iff`` ->
    # ``..._transitive``).  Preserve that as statement drift so an approved
    # renamed target cannot disappear as a harmless helper theorem.
    if len(declarations) == 1:
        candidate_name = declarations[0][1]
        if target_name.startswith(f"{candidate_name}_") or candidate_name.startswith(
            f"{target_name}_"
        ):
            return "statement_drift"
    if _HELPER_OR_PROBE_RE.search(source):
        return "helper_or_probe"
    return "unknown"


def target_proof_body(code: str, target_statement: str) -> str | None:
    """Proof body for the target-named declaration, never a preceding helper."""
    target_match = _DECL_RE.search(_source_without_comments_and_strings(target_statement))
    if target_match is None:
        return None
    target_name = target_match.group(2)
    source = _source_without_comments_and_strings(code)
    pattern = re.compile(
        rf"\b(?:theorem|lemma)\s+{re.escape(target_name)}(?=\s|\(|\{{|\[|:)"
    )
    declaration = pattern.search(source)
    if declaration is None:
        return None
    body_start = source.find(":=", declaration.start())
    if body_start < 0:
        return None
    return code[body_start + 2 :].strip()


def _call_code(event: TraceEvent) -> tuple[str | None, str | None]:
    """(call_id, code) from a TOOL_CALL event's first check_lean call.

    Returns (None, None) if the arguments cannot be parsed or carry no code.
    """
    calls = event.payload.get("tool_calls") or []
    for c in calls:
        name = c.get("name")
        if name not in (None, "check_lean"):
            continue
        args = c.get("arguments")
        if not args:
            if name == "check_lean":
                return c.get("id"), None
            continue
        try:
            parsed = json.loads(args)
        except (json.JSONDecodeError, TypeError):
            if name == "check_lean":
                return c.get("id"), None
            continue
        if not isinstance(parsed, dict):
            return c.get("id"), None
        if name is None and "code" not in parsed:
            continue
        return c.get("id"), parsed.get("code")
    return None, None


def _result_verdict(
    event: TraceEvent,
) -> tuple[str | None, bool | None, bool | None, str | None]:
    """(call_id, compiled, sorry_free, status) from an execution result.

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
            return r.get("id"), None, None, "infrastructure_unknown"
        try:
            d = ast.literal_eval(content)
        except (ValueError, SyntaxError):
            return r.get("id"), None, None, "infrastructure_unknown"
        if isinstance(d, dict):
            compiled = d.get("compiled")
            sorry_free = d.get("sorry_free")
            status = d.get("verification_status")
            if status not in {"accepted", "rejected", "infrastructure_unknown"}:
                if d.get("infrastructure_error"):
                    status = "infrastructure_unknown"
                elif compiled is True:
                    status = "accepted"
                elif compiled is False:
                    summary = str(d.get("summary") or "").strip().lower()
                    errors = d.get("errors") or []
                    useful_errors = [
                        str(item.get("data") or "").strip()
                        for item in errors
                        if isinstance(item, dict) and str(item.get("data") or "").strip()
                    ]
                    status = (
                        "infrastructure_unknown"
                        if not useful_errors and (not summary or "lean failed" in summary)
                        else "rejected"
                    )
            if status == "infrastructure_unknown":
                return r.get("id"), None, None, status
            return r.get("id"), compiled, sorry_free, status
    return None, None, None, "infrastructure_unknown"


def extract_artifacts(
    events: list[TraceEvent], *, target_statement: str | None = None
) -> TrialArtifacts:
    """Walk a trial's events and assemble its TrialArtifacts (pure)."""
    events = sorted(events, key=lambda e: e.seq)

    # 1. The submitted proof: the LAST Lean code block in the LAST engineer
    #    message that carried a FINAL marker. Last block, not all blocks
    #    concatenated: a final message often shows a `sorry` scaffold AND the
    #    real proof as separate blocks, and the real answer is conventionally the
    #    last one. Gluing them would produce duplicate declarations that fail to
    #    compile, corrupting every Group-B check downstream.
    submitted: str | None = None
    submitted_seq: int | None = None
    submission_source = "none"
    for e in events:
        if e.agent_role is AgentRole.ENGINEER and e.event_type is EventType.MESSAGE:
            if e.payload.get("has_final"):
                blocks = lean_code_blocks(e.payload.get("text", ""))
                if blocks:
                    submitted = blocks[-1]
                    submitted_seq = e.seq
                    submission_source = "explicit_final"

    # 2. Pair tool calls with their results by call id, in order.
    results_by_id: dict[
        str | None, tuple[bool | None, bool | None, str | None, int | None]
    ] = {}
    for e in events:
        if e.event_type is EventType.EXECUTION_RESULT:
            cid, compiled, sorry_free, status = _result_verdict(e)
            results_by_id[cid] = (compiled, sorry_free, status, e.seq)

    tool_calls: list[ToolCallRecord] = []
    for e in events:
        if e.event_type is EventType.TOOL_CALL:
            cid, code = _call_code(e)
            # ``TrialArtifacts.tool_calls`` is deliberately the Lean compiler
            # attempt stream, not every agent tool invocation.  Search calls
            # are reported separately by the trajectory analyzer and must not
            # inflate compiler/retry metrics here.
            if cid is None and code is None:
                continue
            compiled, sorry_free, status, result_seq = results_by_id.get(
                cid, (None, None, None, None)
            )
            tool_calls.append(
                ToolCallRecord(
                    call_id=cid,
                    code=code,
                    compiled=compiled,
                    sorry_free=sorry_free,
                    seq=e.seq,
                    verification_status=status,
                    result_seq=result_seq,
                )
            )

    # 3. last_verified: code of the last call whose result compiled successfully.
    last_verified: str | None = None
    last_verified_seq: int | None = None
    for rec in tool_calls:
        if (
            rec.verification_status == "accepted"
            and rec.compiled is True
            and rec.sorry_free is True
            and rec.code is not None
            and not contains_prohibited_placeholder(rec.code)
        ):
            last_verified = rec.code
            last_verified_seq = rec.result_seq

    # 4. declared_success: the final critic verdict in the trace is APPROVE.
    declared_success = False
    critic_decision_seq: int | None = None
    for e in events:
        if e.agent_role is AgentRole.CRITIC and e.payload.get("decision") is not None:
            declared_success = e.payload.get("decision") == "approve"
            critic_decision_seq = e.seq

    last_verified_kind = candidate_kind(last_verified, target_statement)

    # 3b. An approved, verified target (including an approved statement drift)
    #     may be inferred when the final handoff contains no code. A helper,
    #     `example`, or `#check` success is process evidence only and can never
    #     silently become the submitted theorem.
    if (
        submitted is None
        and declared_success
        and last_verified is not None
        and last_verified_kind in {"exact_target", "statement_drift"}
        and critic_decision_seq is not None
        and last_verified_seq is not None
        and critic_decision_seq > last_verified_seq
    ):
        submitted = last_verified
        submitted_seq = last_verified_seq
        submission_source = "approved_verified_target"

    n_failed = sum(1 for rec in tool_calls if rec.verification_status == "rejected")
    submitted_kind = candidate_kind(submitted, target_statement)
    submission_accepted = bool(
        declared_success
        and submitted_seq is not None
        and critic_decision_seq is not None
        and critic_decision_seq > submitted_seq
    )

    return TrialArtifacts(
        submitted=submitted,
        last_verified=last_verified,
        tool_calls=tool_calls,
        declared_success=declared_success,
        n_tool_calls=len(tool_calls),
        n_failed_compiles=n_failed,
        submission_source=submission_source,
        submitted_kind=submitted_kind,
        last_verified_kind=last_verified_kind,
        submission_accepted=submission_accepted,
    )
