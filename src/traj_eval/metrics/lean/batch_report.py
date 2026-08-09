"""Shared analysis layer over saved Lean batch logs (data/batch/<config>/*.jsonl).

Both the CLI scripts (analyze_batch.py, compare_offline_kernel.py, tool_usage.py)
and the interactive dashboard call into this module, so every view -- single
batch, multi-batch comparison, single-trial detail -- reads its numbers from the
same functions instead of three separate re-implementations drifting apart.

Everything here is pure: it reads trial JSONL files (and optionally re-runs the
Lean kernel through a caller-supplied ``compiler``), it never decides how to
render or print. Kernel access is always injected, never constructed here, so
callers that only want the offline (Group A) signal pay no Lean startup cost.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from traj_eval.detectors.perseveration import detect_perseveration
from traj_eval.metrics.lean.artifacts import TrialArtifacts, extract_artifacts
from traj_eval.metrics.lean.validator import LeanTask, validate
from traj_eval.trace_core.schema import EventType, TraceEvent
from traj_eval.trace_core.storage import read_trial

# filename like easy_fatem_011_t3.jsonl -> task "easy_fatem_011", trial 3
TRIAL_NAME_RE = re.compile(r"^(?P<task>.+)_t(?P<trial>\d+)\.jsonl$")

# The tool names the current engineer/critic surface actually offers. Anything
# else seen in a tool_call's ``name`` field is a formatting artifact (a model
# stuffed text into the name slot instead of arguments) rather than a real
# tool -- see the codestral/devstral "malformed tool call" pattern.
KNOWN_TOOLS = frozenset({"check_lean", "search_lemmas", "try_tactic", "show_goals"})


def parse_trial_filename(path: Path) -> tuple[str, int] | None:
    """(task_id, trial_index) from a ``<task>_t<N>.jsonl`` filename, or None."""
    m = TRIAL_NAME_RE.match(path.name)
    if not m:
        return None
    return m.group("task"), int(m.group("trial"))


def list_trial_files(folder: Path, *, difficulty: str | None = None) -> list[Path]:
    """Trial JSONL files in ``folder``, sorted, optionally filtered by task prefix."""
    paths = sorted(Path(folder).glob("*.jsonl"))
    out = []
    for p in paths:
        tt = parse_trial_filename(p)
        if not tt:
            continue
        task, _ = tt
        if difficulty and not task.startswith(difficulty):
            continue
        out.append(p)
    return out


# --------------------------------------------------------------------------
# Batch discovery + config metadata
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class BatchMeta:
    """What a batch folder claims to be, read from its own config.json when
    present (data/batch/<config>/config.json) and falling back to a bare
    folder-name label for the historical version_N_trial_traces layout, which
    predates the config schema."""

    path: Path
    name: str
    phase: str | None = None
    arm_id: str | None = None
    models: dict[str, str] = field(default_factory=dict)
    trials_per_task: int | None = None
    n_trial_files: int = 0
    has_config: bool = False

    @property
    def label(self) -> str:
        """Short human label for UI pickers: 'phase/arm' when known, else the
        folder name."""
        if self.phase and self.arm_id:
            return f"{self.name}  ({self.phase} / {self.arm_id})"
        return self.name


def load_batch_meta(folder: Path) -> BatchMeta:
    """Read one batch folder's config.json (if any) plus its trial file count."""
    folder = Path(folder)
    n_files = len(list_trial_files(folder))
    cfg_path = folder / "config.json"
    if not cfg_path.exists():
        return BatchMeta(path=folder, name=folder.name, n_trial_files=n_files)
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    return BatchMeta(
        path=folder,
        name=folder.name,
        phase=cfg.get("phase"),
        arm_id=cfg.get("arm_id"),
        models=dict(cfg.get("models") or {}),
        trials_per_task=cfg.get("trials_per_task"),
        n_trial_files=n_files,
        has_config=True,
    )


def discover_batches(root: Path) -> list[BatchMeta]:
    """Every immediate subfolder of ``root`` that contains at least one trial
    JSONL file, as BatchMeta, sorted by name. ``root`` is typically data/batch."""
    root = Path(root)
    if not root.exists():
        return []
    metas = []
    for sub in sorted(p for p in root.iterdir() if p.is_dir()):
        if list_trial_files(sub) or any(list_trial_files(p) for p in sub.iterdir() if p.is_dir()):
            # Only count the folder itself as a batch if it directly holds
            # trial files (version_2_trial_traces/200_turns is a nested
            # variant, not a batch in its own right -- surfaced separately by
            # callers that want to walk subfolders explicitly).
            if list_trial_files(sub):
                metas.append(load_batch_meta(sub))
    return metas


# --------------------------------------------------------------------------
# Per-task success/failure report (analyze_batch.py)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class TaskRow:
    task: str
    n: int
    success: int
    fail: int
    thrash: int
    silent: int

    @property
    def rate(self) -> float:
        return self.success / self.n if self.n else 0.0


@dataclass(frozen=True)
class BatchReport:
    folder: Path
    validated: bool
    rows: list[TaskRow]
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (filename, error)

    @property
    def total_n(self) -> int:
        return sum(r.n for r in self.rows)

    @property
    def total_success(self) -> int:
        return sum(r.success for r in self.rows)

    @property
    def total_rate(self) -> float:
        n = self.total_n
        return self.total_success / n if n else 0.0


def _offline_success(events: list[TraceEvent]) -> bool:
    art = extract_artifacts(events)
    got_clean = any(c.compiled and c.sorry_free for c in art.tool_calls)
    return bool(got_clean and art.declared_success)


def build_batch_report(
    folder: Path,
    *,
    difficulty: str | None = None,
    compiler=None,
    tasks: dict[str, LeanTask] | None = None,
) -> BatchReport:
    """Per-task success/fail/thrash/(silent) counts for one batch folder.

    Mirrors analyze_batch.py's aggregation exactly. Offline-only (fast) when
    ``compiler`` is None; kernel-validated (Group B, incl. silent-failure
    detection) when a LeanCompiler + task map are supplied.
    """
    validated = compiler is not None and tasks is not None
    success: dict[str, int] = defaultdict(int)
    fail: dict[str, int] = defaultdict(int)
    thrash: dict[str, int] = defaultdict(int)
    silent: dict[str, int] = defaultdict(int)
    total: dict[str, int] = defaultdict(int)
    skipped: list[tuple[str, str]] = []

    for p in list_trial_files(folder, difficulty=difficulty):
        try:
            _, events = read_trial(p)
        except Exception as e:  # noqa: BLE001 -- one bad file must not abort the batch
            skipped.append((p.name, f"{type(e).__name__}: {e}"))
            continue

        task, _ = parse_trial_filename(p)  # type: ignore[misc]
        total[task] += 1
        ok = _offline_success(events)

        if validated and task in tasks:
            try:
                m = validate(events, tasks[task], compiler=compiler)
            except Exception as e:  # noqa: BLE001
                skipped.append((p.name, f"validate {type(e).__name__}: {str(e)[:120]}"))
                fail[task] += 1
                continue
            ok = bool(
                m.final_proof_compiles
                and m.final_proof_sorry_free
                and m.statement_preserved
                and m.axiom_clean
            )
            if m.silent_failure:
                silent[task] += 1

        if ok:
            success[task] += 1
        else:
            fail[task] += 1

        rep = detect_perseveration(extract_artifacts(events).tool_calls)
        if rep.n_failed_compiles > 0 and rep.retry_success_rate == 0.0 and not ok:
            thrash[task] += 1

    rows = [
        TaskRow(
            task=t,
            n=total[t],
            success=success[t],
            fail=fail[t],
            thrash=thrash[t],
            silent=silent[t],
        )
        for t in sorted(total)
    ]
    return BatchReport(folder=Path(folder), validated=validated, rows=rows, skipped=skipped)


# --------------------------------------------------------------------------
# Offline-vs-kernel disagreement report (compare_offline_kernel.py)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DisagreementRow:
    trial: str
    task: str
    reasons: list[str]


@dataclass(frozen=True)
class ComparisonReport:
    folder: Path
    agree_pass: list[str] = field(default_factory=list)
    agree_fail: list[str] = field(default_factory=list)
    silent: list[DisagreementRow] = field(default_factory=list)  # offline PASS, kernel FAIL
    offline_miss: list[DisagreementRow] = field(default_factory=list)  # offline FAIL, kernel PASS
    errors: list[tuple[str, str]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return (
            len(self.agree_pass) + len(self.agree_fail) + len(self.silent) + len(self.offline_miss)
        )

    @property
    def disagreement_rate(self) -> float:
        n = self.total
        return (len(self.silent) + len(self.offline_miss)) / n if n else 0.0


def _kernel_verdict(events: list[TraceEvent], task: LeanTask, compiler):
    m = validate(events, task, compiler=compiler)
    ok = bool(
        m.final_proof_compiles
        and m.final_proof_sorry_free
        and m.statement_preserved
        and m.axiom_clean
    )
    reasons = []
    if m.final_proof_compiles is False:
        reasons.append("not_compiles")
    if m.final_proof_sorry_free is False:
        reasons.append("has_sorry")
    if m.statement_preserved is False:
        reasons.append("statement_not_preserved")
    if m.axiom_clean is False:
        reasons.append(f"extra_axioms={m.extra_axioms}")
    if m.final_proof_compiles is None:
        reasons.append("no_submission")
    return ok, m, reasons


def build_comparison_report(
    folder: Path,
    tasks: dict[str, LeanTask],
    compiler,
    *,
    difficulty: str | None = None,
) -> ComparisonReport:
    """Per-trial offline-vs-kernel verdict, bucketed. Mirrors
    compare_offline_kernel.py's aggregation exactly."""
    report = ComparisonReport(folder=Path(folder))

    for p in list_trial_files(folder, difficulty=difficulty):
        tt = parse_trial_filename(p)
        if not tt:
            continue
        task, trial_idx = tt
        if task not in tasks:
            continue
        trial = f"{task}_t{trial_idx}"
        try:
            _, events = read_trial(p)
            off = _offline_success(events)
            ker, _metrics, reasons = _kernel_verdict(events, tasks[task], compiler)
        except Exception as e:  # noqa: BLE001
            report.errors.append((p.name, f"{type(e).__name__}: {str(e)[:120]}"))
            continue

        if off and ker:
            report.agree_pass.append(trial)
        elif not off and not ker:
            report.agree_fail.append(trial)
        elif off and not ker:
            report.silent.append(DisagreementRow(trial=trial, task=task, reasons=reasons))
        else:
            report.offline_miss.append(DisagreementRow(trial=trial, task=task, reasons=reasons))

    return report


# --------------------------------------------------------------------------
# Tool-usage report: per-role/tool call counts, critic self-verification rate,
# malformed tool-call names.
#
# extract_artifacts() deliberately reads only the FIRST tool call out of a
# TOOL_CALL event's (possibly batched) tool_calls list -- it exists to pair one
# call with one compile verdict. Reasoners/engineers sometimes batch several
# tool calls into a single event (e.g. three parallel search_lemmas), so a
# faithful per-tool-call tally needs its own walk over every call in every
# event; that's what this section does.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolCallSeen:
    role: str
    tool_name: str
    trial: str


@dataclass(frozen=True)
class ToolUsageReport:
    folder: Path
    n_trials: int
    # role -> tool -> total call count
    calls: dict[str, dict[str, int]] = field(default_factory=dict)
    # role -> tool -> number of distinct trials with >=1 call
    trials_with_tool: dict[str, dict[str, int]] = field(default_factory=dict)
    critic_self_check_trials: int = 0  # trials where the critic itself called check_lean
    critic_text_verdict_trials: int = 0  # trials where the critic sent a text VERDICT
    malformed_tool_calls: list[ToolCallSeen] = field(default_factory=list)

    def calls_per_trial(self, role: str) -> float:
        tot = sum(self.calls.get(role, {}).values())
        return tot / self.n_trials if self.n_trials else 0.0

    def tool_rate(self, role: str, tool: str) -> float:
        """Fraction of trials with >=1 call to ``tool`` by ``role``."""
        n = self.trials_with_tool.get(role, {}).get(tool, 0)
        return n / self.n_trials if self.n_trials else 0.0

    @property
    def critic_self_check_rate(self) -> float:
        return self.critic_self_check_trials / self.n_trials if self.n_trials else 0.0


def build_tool_usage_report(folder: Path, *, difficulty: str | None = None) -> ToolUsageReport:
    """Per-role/tool call tallies plus the critic self-verification and
    malformed-tool-call signals surfaced during the model-matrix analysis."""
    calls: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    trials_with_tool: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    critic_self_check_trials = 0
    critic_text_verdict_trials = 0
    malformed: list[ToolCallSeen] = []

    n_trials = 0
    for p in list_trial_files(folder, difficulty=difficulty):
        try:
            _, events = read_trial(p)
        except Exception:  # noqa: BLE001
            continue
        n_trials += 1
        trial = p.name
        seen_this_trial: dict[str, set[str]] = defaultdict(set)
        critic_checked = False
        critic_text_verdict = False

        for e in sorted(events, key=lambda ev: ev.seq):
            if e.event_type is EventType.TOOL_CALL:
                role = str(e.agent_role)
                for tc in e.payload.get("tool_calls") or []:
                    name = tc.get("name") or ""
                    if name.upper().startswith("VERDICT"):
                        # A verdict emitted as a (malformed) tool call rather
                        # than the expected text message.
                        malformed.append(ToolCallSeen(role=role, tool_name=name, trial=trial))
                        continue
                    if name not in KNOWN_TOOLS:
                        malformed.append(ToolCallSeen(role=role, tool_name=name, trial=trial))
                        continue
                    calls[role][name] += 1
                    seen_this_trial[role].add(name)
                    if role == "critic" and name == "check_lean":
                        critic_checked = True
            elif e.event_type is EventType.MESSAGE and str(e.agent_role) == "critic":
                text = str(e.payload.get("text") or "")
                if "VERDICT" in text.upper():
                    critic_text_verdict = True

        for role, tools in seen_this_trial.items():
            for t in tools:
                trials_with_tool[role][t] += 1
        if critic_checked:
            critic_self_check_trials += 1
        if critic_text_verdict:
            critic_text_verdict_trials += 1

    return ToolUsageReport(
        folder=Path(folder),
        n_trials=n_trials,
        calls={r: dict(t) for r, t in calls.items()},
        trials_with_tool={r: dict(t) for r, t in trials_with_tool.items()},
        critic_self_check_trials=critic_self_check_trials,
        critic_text_verdict_trials=critic_text_verdict_trials,
        malformed_tool_calls=malformed,
    )


# --------------------------------------------------------------------------
# Single-trial detail (trace viewer)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class TrialDetail:
    path: Path
    task: str
    trial_index: int
    meta: dict
    events: list[TraceEvent]
    artifacts: TrialArtifacts
    offline_success: bool


def load_trial_detail(path: Path) -> TrialDetail:
    tt = parse_trial_filename(Path(path))
    task, idx = tt if tt else (path.stem, -1)
    meta, events = read_trial(path)
    art = extract_artifacts(events)
    return TrialDetail(
        path=Path(path),
        task=task,
        trial_index=idx,
        meta=meta.model_dump(mode="json"),
        events=events,
        artifacts=art,
        offline_success=_offline_success(events),
    )
