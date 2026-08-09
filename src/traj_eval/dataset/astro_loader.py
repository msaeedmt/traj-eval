"""Astro dataset layer: load a prepared RV task, split public view from truth.

The single most dangerous property of the Stargazer task files is that the
ground truth lives in the SAME json as the observations: ``config.planets``
holds the true planetary system, sitting next to ``observations.rvs_ms``. A
trial that leaks it produces a perfectly normal-looking trajectory with a
meaningless pass, and nothing downstream can detect that after the fact.

So the loader refuses to hand back one object. ``load_astro_task`` returns a
pair -- ``(AstroTask, AstroTruth)`` -- and only ``AstroTask`` may reach a
prompt, a tool closure the agent can call, or the observer. ``AstroTruth`` is
consumed exclusively by the out-of-loop anchor, detector and validator layers.
Passing the wrong one into an agent-facing function is then a type error at the
call site rather than a silent scientific bug.

``AstroTask.observation`` mirrors exactly the fields upstream's
``RvEnv._make_observation`` exposes (times, RVs, sigmas, instrument labels, host
star mass, plus optional description / hints / reference on the real-data
tasks), with a few derived conveniences the agent could compute itself anyway
(n_obs, baseline, median sigma) so that prompts, tools and anchors do not each
re-derive them slightly differently.

Tier and budget mapping follows the Stargazer paper (Difficulty Tiers table):
Easy = difficulty 1-2, Medium = 3-6, Hard = 7-10, with 3 / 5 / 10 submission
attempts respectively. NOTE this corrects project proposal section 3, which
stated 12 tasks per difficulty level and tiers of 1-3 / 4-7 / 8-10; the real
bank has 10 tasks per level (100 synthetic) and the tier cuts above.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from traj_eval.dataset.astro_bank import list_task_files, read_task_file, task_file
from traj_eval.vendor.stargazer.config import Task

# Tier boundaries and per-tier submission budgets, from the Stargazer paper.
_TIER_BOUNDS: tuple[tuple[str, int, int], ...] = (
    ("easy", 1, 2),
    ("medium", 3, 6),
    ("hard", 7, 10),
)
# 'real' is our own label for the archival tasks, which are not on the synthetic
# 1-10 difficulty scale. The paper runs them at the Hard budget, so we match it.
MAX_SUBMISSIONS: dict[str, int] = {"easy": 3, "medium": 5, "hard": 10, "real": 10}


def tier_for_difficulty(difficulty: int, *, kind: str = "synthetic") -> str:
    """Map an integer difficulty 1-10 onto Stargazer's three tiers.

    The archival tasks are not scored on the synthetic difficulty rubric, so a
    real task whose ``truth_difficulty`` falls outside 1-10 gets the ``real``
    tier rather than being force-fitted into a synthetic bucket -- keeping the
    two populations separable in every downstream report.
    """
    for name, lo, hi in _TIER_BOUNDS:
        if lo <= difficulty <= hi:
            return name
    if kind == "real":
        return "real"
    raise ValueError(
        f"difficulty {difficulty} is outside the documented range 1-10 " f"for a {kind} task"
    )


@dataclass(frozen=True)
class AstroObservation:
    """Everything the agent is permitted to see. No truth, by construction."""

    times_days: list[float]
    rvs_ms: list[float]
    sigmas_ms: list[float]
    instruments: list[str]
    star_mass_sun: float
    # Derived, so prompts / tools / anchors agree on one definition each.
    n_obs: int
    baseline_days: float
    median_sigma_ms: float
    instrument_labels: list[str] = field(default_factory=list)
    # Present on the real-data tasks; absent on synthetic ones.
    task_description: str | None = None
    hints: dict[str, Any] = field(default_factory=dict)
    reference: str | None = None


@dataclass(frozen=True)
class AstroTask:
    """The agent-facing task. Safe to put in a prompt or a tool closure."""

    task_id: str
    kind: str  # 'synthetic' | 'real'
    difficulty: int
    tier: str
    observation: AstroObservation

    @property
    def max_submissions(self) -> int:
        return MAX_SUBMISSIONS[self.tier]


@dataclass(frozen=True)
class AstroTruth:
    """Ground truth. Out-of-loop consumers only: anchors, detectors, validator.

    ``planets`` holds vendored ``PlanetParams`` instances (not a local mirror)
    so the forward model and Hungarian matcher receive exactly the objects they
    were written for -- any local re-typing risks a silent semantic drift from
    the evaluator we must stay comparable to.
    """

    task_id: str
    planets: list[Any]  # list[vendor.stargazer.config.PlanetParams]
    star_mass_sun: float
    difficulty_details: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def n_planets(self) -> int:
        return len(self.planets)

    @property
    def periods_days(self) -> list[float]:
        return [float(p.P_days) for p in self.planets]


def split_task(task: Task, *, kind: str) -> tuple[AstroTask, AstroTruth]:
    """Split a prepared ``Task`` into (agent-visible view, ground truth)."""
    obs = task.observations
    times = np.asarray(obs.times_days, dtype=float)
    sigmas = np.asarray(obs.sigmas_ms, dtype=float)
    meta = task.meta if isinstance(task.meta, dict) else {}
    difficulty = int(task.truth_difficulty)

    observation = AstroObservation(
        times_days=[float(v) for v in obs.times_days],
        rvs_ms=[float(v) for v in obs.rvs_ms],
        sigmas_ms=[float(v) for v in obs.sigmas_ms],
        instruments=list(obs.instruments),
        star_mass_sun=float(task.config.star.M_star_sun),
        n_obs=int(times.size),
        baseline_days=float(times.max() - times.min()) if times.size else 0.0,
        median_sigma_ms=float(np.median(sigmas)) if sigmas.size else 0.0,
        instrument_labels=[inst.label for inst in task.config.instruments],
        task_description=meta.get("task_description"),
        hints=dict(meta.get("hints") or {}),
        reference=meta.get("reference"),
    )

    public = AstroTask(
        task_id=str(task.task_id),
        kind=kind,
        difficulty=difficulty,
        tier=tier_for_difficulty(difficulty, kind=kind),
        observation=observation,
    )
    truth = AstroTruth(
        task_id=str(task.task_id),
        planets=list(task.config.planets),
        star_mass_sun=float(task.config.star.M_star_sun),
        difficulty_details=dict(task.difficulty_details or {}),
        meta=dict(meta),
    )
    return public, truth


def load_astro_task(
    task_id: str,
    *,
    kind: str = "synthetic",
) -> tuple[AstroTask, AstroTruth]:
    """Load one prepared task by id, returning (agent-visible task, truth)."""
    return split_task(read_task_file(task_file(task_id, kind)), kind=kind)


def list_astro_task_ids(*, kind: str = "synthetic") -> list[str]:
    """All task ids in a bank (``seed22_diff4`` / ``real_012``)."""
    return [p.stem for p in list_task_files(kind)]


def load_astro_tasks(
    *,
    kind: str = "synthetic",
    tier: str | None = None,
    difficulties: set[int] | None = None,
) -> list[tuple[AstroTask, AstroTruth]]:
    """Load a filtered slice of a bank.

    Filtering happens AFTER load because difficulty lives inside the task file,
    not in the filename. Cheap enough at 100-120 tasks; if it ever matters,
    cache an index rather than parsing ids.
    """
    out: list[tuple[AstroTask, AstroTruth]] = []
    for path in list_task_files(kind):
        pair = split_task(read_task_file(path), kind=kind)
        task = pair[0]
        if tier is not None and task.tier != tier:
            continue
        if difficulties is not None and task.difficulty not in difficulties:
            continue
        out.append(pair)
    return out
