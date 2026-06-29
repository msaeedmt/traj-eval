"""Perseveration detector (objective O2).

Perseveration is one of the trajectory-level failure modes the proposal names
(after Stargazer's "perseveration"): an agent stuck re-submitting the same
failing attempt instead of changing approach or asking for help. Output-level
metrics cannot see it -- the final result is just "failed" -- but the trajectory
shows it plainly as a run of identical, identically-failing tool calls.

Operational definition (deliberately conservative so a normal retry is not
flagged):
  A perseveration episode is a maximal run of >= ``min_repeats`` consecutive
  check_lean calls whose submitted code is identical after whitespace
  normalisation AND whose every result is a failure (compiled is False).

We separate two related-but-distinct signals, because they mean different things:
  * identical perseveration -- byte-identical resubmission (the agent is not even
    changing the code; pure stuckness);
  * the retry-success rate -- of all failed-then-retried attempts, how often a
    retry actually fixed the error (low rate = unproductive retrying).

This is pure trace analysis: it consumes the ToolCallRecords already extracted
by metrics.lean.artifacts, adds no kernel or LLM, and is domain-agnostic in
shape (it reads code+verdict pairs; the same detector would serve astro once
its tool calls carry an analogous failure flag).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from traj_eval.metrics.lean.artifacts import ToolCallRecord


def _norm(code: str | None) -> str:
    return " ".join((code or "").split())


@dataclass(frozen=True)
class PerseverationEpisode:
    """A maximal run of identical, identically-failing submissions."""

    code: str  # the normalised repeated code
    count: int  # how many times it was resubmitted
    start_seq: int  # seq of the first call in the run
    end_seq: int  # seq of the last call in the run


@dataclass(frozen=True)
class PerseverationReport:
    """Per-trial perseveration signals (O2)."""

    episodes: list[PerseverationEpisode] = field(default_factory=list)
    n_tool_calls: int = 0
    n_failed_compiles: int = 0
    retry_success_rate: float | None = None  # None when there were no retries

    @property
    def perseverated(self) -> bool:
        """True if at least one identical-resubmission episode was found."""
        return len(self.episodes) > 0

    @property
    def max_repeat(self) -> int:
        """Longest identical-resubmission run (0 if none)."""
        return max((e.count for e in self.episodes), default=0)

    @property
    def wasted_calls(self) -> int:
        """Tool calls spent inside perseveration episodes beyond the first try.

        An episode of N identical submissions 'wasted' N-1 of them: the first
        was a legitimate attempt, the rest added nothing.
        """
        return sum(e.count - 1 for e in self.episodes)


def detect_perseveration(
    tool_calls: list[ToolCallRecord],
    *,
    min_repeats: int = 3,
) -> PerseverationReport:
    """Find identical-failing-resubmission episodes among check_lean calls.

    ``min_repeats`` is the run length at which we call it perseveration rather
    than ordinary retrying (default 3: two retries of the same failing code).
    """
    n = len(tool_calls)
    n_failed = sum(1 for c in tool_calls if c.compiled is False)

    # Scan for maximal runs of identical code that all failed.
    episodes: list[PerseverationEpisode] = []
    i = 0
    while i < n:
        code_i = _norm(tool_calls[i].code)
        # only consider runs that start on a failing call with non-empty code
        if not code_i or tool_calls[i].compiled is not False:
            i += 1
            continue
        j = i + 1
        while j < n and _norm(tool_calls[j].code) == code_i and tool_calls[j].compiled is False:
            j += 1
        run_len = j - i
        if run_len >= min_repeats:
            episodes.append(
                PerseverationEpisode(
                    code=code_i,
                    count=run_len,
                    start_seq=tool_calls[i].seq,
                    end_seq=tool_calls[j - 1].seq,
                )
            )
        i = j if run_len > 1 else i + 1

    # Retry-success rate: among consecutive (prev failed -> next call) retry
    # pairs, the fraction where the next call compiled. Low rate = unproductive
    # retrying; None when there were no retries to judge.
    retries = 0
    successful_retries = 0
    for prev, nxt in zip(tool_calls, tool_calls[1:], strict=False):
        if prev.compiled is False:
            retries += 1
            if nxt.compiled is True:
                successful_retries += 1
    retry_success_rate = (successful_retries / retries) if retries else None

    return PerseverationReport(
        episodes=episodes,
        n_tool_calls=n,
        n_failed_compiles=n_failed,
        retry_success_rate=retry_success_rate,
    )
