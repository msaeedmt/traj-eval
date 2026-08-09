"""A0 integration probe: prove we call the vendored evaluator correctly.

Costs nothing -- no LLM, no API key, no agents. Run it before writing a single
astro tool, and re-run it after any change to the bridge, loader, or criteria
layer. Everything downstream (anchors, detectors, the whole silent-failure
definition) assumes the gate behaves as characterised here; if this probe is
red, later disagreements between an anchor and the gate are unattributable.

Four assertions, in increasing sharpness:

  1. TRUTH IN -> ALL FOUR PASS. Submitting the ground-truth planetary system
     must satisfy ok_delta_bic, ok_rms, ok_match and ok_count. This is the
     cheapest possible end-to-end check of field names, angle conventions,
     the rv-only compat conversion, the per-instrument MLE gamma fit, and the
     Hungarian matcher all at once. If it fails, nothing else is worth doing.

  2. PHASE BROKEN -> STATISTICS SURVIVE, PHYSICS COLLAPSES. Zero out l_rad on
     every planet, keeping every other parameter exact. The RV curve is now
     phase-shifted, so ok_match should collapse while the model may still beat a
     flat line. This is the paper's documented format-fragility failure (§4.4:
     an internal fit at RMS 1.08 evaluating at 7.71 purely from an l_rad
     convention error) and it is the premise of the submission_consistency
     anchor. It also demonstrates the statistical/physical dissociation on a
     case where we KNOW the cause.

  3. PLANET DROPPED -> ok_count FAILS. On a multi-planet task, submit all but
     the last truth planet. Confirms the count term is exactly
     -|n_truth - n_guess| and that a wrong count also depresses the match score
     (the -0.25 penalty is folded into components['match']).

  4. SPURIOUS EXTRA PLANET -> ok_count FAILS. Duplicate a planet at a shifted
     period. Guards the over-parameterisation direction, which the delta-BIC
     criterion is supposed to penalise.

Usage:
    uv run python scripts/probe_astro_eval.py                    # first synthetic task
    uv run python scripts/probe_astro_eval.py --task-id seed22_diff4
    uv run python scripts/probe_astro_eval.py --kind real --task-id real_012
    uv run python scripts/probe_astro_eval.py --all-easy         # sweep a tier
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import replace

from traj_eval.dataset.astro_loader import (
    AstroTask,
    AstroTruth,
    list_astro_task_ids,
    load_astro_task,
    load_astro_tasks,
)
from traj_eval.metrics.astro.criteria import AstroCriteria
from traj_eval.metrics.astro.evaluate import score_submission, submission_from_planets


def _fmt(criteria: AstroCriteria) -> str:
    def mark(ok: bool) -> str:
        return "PASS" if ok else "FAIL"

    return (
        f"bic={mark(criteria.ok_delta_bic)} "
        f"rms={mark(criteria.ok_rms)} "
        f"match={mark(criteria.ok_match)} "
        f"count={mark(criteria.ok_count)}  "
        f"| dBIC/N={criteria.delta_bic_per_point:+.3g} "
        f"rms={criteria.rms_ms:.3g}/{criteria.max_rms_ms:.3g} "
        f"match={criteria.match_score:+.3f}>={criteria.min_match_score:.2f}"
    )


def probe_task(task: AstroTask, truth: AstroTruth) -> list[str]:
    """Run the four checks on one task. Returns a list of failure messages."""
    failures: list[str] = []
    o = task.observation
    print(
        f"\n=== {task.task_id}  ({task.kind}, difficulty {task.difficulty}, {task.tier}) ===\n"
        f"    n_obs={o.n_obs}  baseline={o.baseline_days:.1f} d  "
        f"median_sigma={o.median_sigma_ms:.3g} m/s  "
        f"n_inst={len(set(o.instruments))}  n_truth_planets={truth.n_planets}\n"
        f"    truth periods (d): {', '.join(f'{p:.4g}' for p in truth.periods_days)}\n"
        f"    truth l_rad (rad):  {', '.join(f'{p.l_rad:.4g}' for p in truth.planets)}"
    )
    if o.hints:
        print(f"    task hints (threshold overrides): {o.hints}")

    # --- 1. truth in -> all four pass ---------------------------------
    criteria, _ = score_submission(submission_from_planets(truth.planets), task=task, truth=truth)
    label = "truth submitted" if task.kind == "synthetic" else "truth (ceiling)"
    print(f"  [1] {label:<24s} {_fmt(criteria)}")
    # On the archival tasks the "truth" is a literature fit, not a generative
    # ground truth: real RVs carry stellar activity, unmodelled companions and
    # instrumental systematics that no Keplerian model can absorb, so even the
    # published solution cannot clear the gate. Those tasks ship relaxed
    # thresholds in meta.hints for exactly this reason. So check 1 is a hard
    # assertion for synthetic tasks only; for real ones the score is the CEILING
    # -- the best any agent could achieve -- and is reported, not judged.
    if task.kind != "synthetic":
        print(
            "      (real task: not asserted. This is the achievable ceiling -- "
            "an agent scoring near it is doing well.)"
        )
    elif not criteria.solved:
        failures.append(
            f"{task.task_id}: ground truth did NOT pass the gate "
            f"(failed: {', '.join(criteria.failed_criteria())}). "
            f"Integration is wrong -- suspect the rv-only compat conversion, the "
            f"l_rad/Omega convention, or the median-sigma used for the RMS threshold."
        )

    # --- 2. phase inverted -> physics collapses -----------------------
    # A pi shift, NOT l_rad=0. Zeroing only breaks the fit when the true phase
    # happens to be far from zero: on a task whose true l_rad is already ~0
    # (seed1108_diff2 is one) zeroing is a no-op and the check fires spuriously.
    # Adding pi inverts the RV curve whatever the true value, so the perturbation
    # is maximally wrong by construction and the assertion is task-independent.
    broken_phase = [
        replace(p, l_rad=float((float(p.l_rad) + math.pi) % (2.0 * math.pi))) for p in truth.planets
    ]
    criteria_phase, _ = score_submission(
        submission_from_planets(broken_phase), task=task, truth=truth
    )
    print(f"  [2] {'phase shifted by pi':<24s} {_fmt(criteria_phase)}")
    if criteria_phase.ok_match:
        failures.append(
            f"{task.task_id}: inverting the orbital phase still passed ok_match. "
            f"The matcher is not seeing phase -- check that times_days reaches "
            f"match_planets (without it it silently falls back to _LEGACY_WEIGHTS "
            f"and drops the dominant rv_curve term)."
        )

    # --- 3. planet dropped -> ok_count fails --------------------------
    if truth.n_planets >= 2:
        criteria_short, _ = score_submission(
            submission_from_planets(truth.planets[:-1]), task=task, truth=truth
        )
        print(f"  [3] {'one planet dropped':<24s} {_fmt(criteria_short)}")
        if criteria_short.ok_count:
            failures.append(
                f"{task.task_id}: dropping a planet still passed ok_count; the count "
                f"term is not -|n_truth - n_guess|."
            )
    else:
        print(f"  [3] {'one planet dropped':<24s} skipped (single-planet task)")

    # --- 4. spurious extra planet -> ok_count fails -------------------
    extra = list(truth.planets) + [replace(truth.planets[0], P_days=truth.planets[0].P_days * 1.7)]
    criteria_extra, _ = score_submission(submission_from_planets(extra), task=task, truth=truth)
    print(f"  [4] {'spurious extra planet':<24s} {_fmt(criteria_extra)}")
    if criteria_extra.ok_count:
        failures.append(f"{task.task_id}: an extra planet still passed ok_count.")

    return failures


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--task-id", default=None, help="task id, e.g. seed22_diff4 / real_012")
    ap.add_argument("--kind", default="synthetic", choices=("synthetic", "real"))
    ap.add_argument("--all-easy", action="store_true", help="sweep every easy-tier task")
    ap.add_argument("--list", action="store_true", help="list task ids and exit")
    args = ap.parse_args(argv)

    if args.list:
        for task_id in list_astro_task_ids(kind=args.kind):
            print(task_id)
        return 0

    if args.all_easy:
        pairs = load_astro_tasks(kind=args.kind, tier="easy")
        if not pairs:
            print("No easy-tier tasks found; is the bank populated?")
            return 1
    elif args.task_id:
        pairs = [load_astro_task(args.task_id, kind=args.kind)]
    else:
        ids = list_astro_task_ids(kind=args.kind)
        if not ids:
            print("Task bank is empty. Did you init the submodule?")
            return 1
        pairs = [load_astro_task(ids[0], kind=args.kind)]

    failures: list[str] = []
    for task, truth in pairs:
        failures.extend(probe_task(task, truth))

    print("\n" + "=" * 70)
    if failures:
        print(f"PROBE FAILED ({len(failures)} problem(s)):")
        for f in failures:
            print(f"  * {f}")
        return 1
    print(f"PROBE PASSED on {len(pairs)} task(s). The evaluator integration is sound.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
