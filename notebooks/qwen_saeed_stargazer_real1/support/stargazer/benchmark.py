from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict

from .config import Task
from .evaluator import evaluate_submission

REWARD_WEIGHTS = {
    "likelihood": 1.0,
    "delta_bic": 0.3,
    "neg_rms": 0.1,
    "match": 1.0,
    "count": 0.2,
}


def _angle_distance(a: Any, b: Any) -> float:
    try:
        raw = abs(float(a) - float(b))
    except Exception:
        return math.inf
    return min(raw % (2.0 * math.pi), (2.0 * math.pi - raw) % (2.0 * math.pi))


def _relative_error(observed: Any, expected: Any) -> float:
    try:
        obs = abs(float(observed))
        exp = abs(float(expected))
    except Exception:
        return math.inf
    return abs(obs - exp) / max(exp, 1e-9)


def _compact_planet_fields(planet: Dict[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key in ["P_days", "m_sin_i_mjup", "e", "omega_rad", "l_rad"]:
        value = planet.get(key)
        result[key] = round(float(value), 6) if isinstance(value, (int, float)) else value
    return result


def _prediction_truth_rows(submission, truth_planets, pairs, matching):
    submitted = [planet for planet in submission.get("planets", []) if isinstance(planet, dict)]
    rows = []
    seen_truth, seen_guess = set(), set()
    for pair in pairs:
        truth_index, guess_index = int(pair[0]), int(pair[1])
        if truth_index >= len(truth_planets) or guess_index >= len(submitted):
            continue
        truth = truth_planets[truth_index]
        guess = submitted[guess_index]
        seen_truth.add(truth_index)
        seen_guess.add(guess_index)
        rows.append(
            {
                "row_type": "matched",
                "truth_index": truth_index,
                "guess_index": guess_index,
                "truth": _compact_planet_fields(truth),
                "submission": _compact_planet_fields(guess),
                "period_rel_error": round(_relative_error(guess.get("P_days"), truth.get("P_days")), 6),
                "mass_rel_error": round(_relative_error(guess.get("m_sin_i_mjup"), truth.get("m_sin_i_mjup")), 6),
                "eccentricity_abs_error": round(abs(float(guess.get("e", 0.0) or 0.0) - float(truth.get("e", 0.0) or 0.0)), 6),
                "omega_error_rad": round(_angle_distance(guess.get("omega_rad", 0.0), truth.get("omega_rad", 0.0)), 6),
                "l_error_rad": round(_angle_distance(guess.get("l_rad", 0.0), truth.get("l_rad", 0.0)), 6),
            }
        )
    unmatched_truth = sorted(set(int(i) for i in matching.get("unmatched_truth", [])) | (set(range(len(truth_planets))) - seen_truth))
    unmatched_guess = sorted(set(int(i) for i in matching.get("unmatched_guess", [])) | (set(range(len(submitted))) - seen_guess))
    for truth_index in unmatched_truth:
        if truth_index < len(truth_planets):
            rows.append({"row_type": "unmatched_truth", "truth_index": truth_index, "guess_index": None, "truth": _compact_planet_fields(truth_planets[truth_index]), "submission": {}})
    for guess_index in unmatched_guess:
        if guess_index < len(submitted):
            rows.append({"row_type": "unmatched_submission", "truth_index": None, "guess_index": guess_index, "truth": {}, "submission": _compact_planet_fields(submitted[guess_index])})
    return rows


def _nearest_truth_rows(submission, truth_planets):
    submitted = [planet for planet in submission.get("planets", []) if isinstance(planet, dict)]
    rows = []
    for guess_index, guess in enumerate(submitted):
        if not truth_planets:
            continue
        best_truth_index, best_truth = min(
            enumerate(truth_planets),
            key=lambda item: _relative_error(guess.get("P_days"), item[1].get("P_days")),
        )
        rows.append(
            {
                "guess_index": guess_index,
                "nearest_truth_index": best_truth_index,
                "submission": _compact_planet_fields(guess),
                "nearest_truth": _compact_planet_fields(best_truth),
                "period_rel_error": round(_relative_error(guess.get("P_days"), best_truth.get("P_days")), 6),
                "mass_rel_error": round(_relative_error(guess.get("m_sin_i_mjup"), best_truth.get("m_sin_i_mjup")), 6),
                "eccentricity_abs_error": round(abs(float(guess.get("e", 0.0) or 0.0) - float(best_truth.get("e", 0.0) or 0.0)), 6),
                "omega_error_rad": round(_angle_distance(guess.get("omega_rad", 0.0), best_truth.get("omega_rad", 0.0)), 6),
                "l_error_rad": round(_angle_distance(guess.get("l_rad", 0.0), best_truth.get("l_rad", 0.0)), 6),
            }
        )
    return rows


def _component_breakdown(submission, truth_planets, pairs, matching, match_score, delta_bic):
    submitted = [planet for planet in submission.get("planets", []) if isinstance(planet, dict)]
    failed = []
    if len(submitted) != len(truth_planets):
        failed.append("planet_count")
    period_ok_count = mass_ok_count = phase_ok_count = 0
    pair_rows = []
    for pair in pairs:
        truth_index, guess_index = int(pair[0]), int(pair[1])
        if truth_index >= len(truth_planets) or guess_index >= len(submitted):
            continue
        truth, guess = truth_planets[truth_index], submitted[guess_index]
        period_rel_error = _relative_error(guess.get("P_days"), truth.get("P_days"))
        mass_rel_error = _relative_error(guess.get("m_sin_i_mjup"), truth.get("m_sin_i_mjup"))
        omega_error = _angle_distance(guess.get("omega_rad", 0.0), truth.get("omega_rad", 0.0))
        l_error = _angle_distance(guess.get("l_rad", 0.0), truth.get("l_rad", 0.0))
        eccentricity_abs_error = abs(float(guess.get("e", 0.0) or 0.0) - float(truth.get("e", 0.0) or 0.0))
        period_ok = period_rel_error <= 0.10
        mass_ok = mass_rel_error <= 0.50
        phase_ok = omega_error <= 1.0 and l_error <= 1.0 and eccentricity_abs_error <= 0.15
        period_ok_count += int(period_ok)
        mass_ok_count += int(mass_ok)
        phase_ok_count += int(phase_ok)
        pair_rows.append(
            {
                "truth_index": truth_index,
                "guess_index": guess_index,
                "period_rel_error": round(period_rel_error, 6),
                "mass_rel_error": round(mass_rel_error, 6),
                "omega_error_rad": round(omega_error, 6),
                "l_error_rad": round(l_error, 6),
                "eccentricity_abs_error": round(eccentricity_abs_error, 6),
                "period_ok": period_ok,
                "mass_ok": mass_ok,
                "phase_or_eccentricity_ok": phase_ok,
            }
        )
    truth_count = len(truth_planets)
    period_fraction = period_ok_count / truth_count if truth_count else 1.0
    mass_fraction = mass_ok_count / truth_count if truth_count else 1.0
    phase_fraction = phase_ok_count / truth_count if truth_count else 1.0
    if period_fraction < 1.0:
        failed.append("period_recovery")
    if mass_fraction < 1.0:
        failed.append("mass_amplitude")
    if phase_fraction < 1.0:
        failed.append("phase_or_eccentricity")
    if match_score < 0.8 or delta_bic <= 0.0:
        failed.append("model_fit")
    return {
        "failed_components": sorted(set(failed)),
        "planet_count": {
            "submitted": len(submitted),
            "truth": len(truth_planets),
            "ok": len(submitted) == len(truth_planets),
            "unmatched_guess": matching.get("unmatched_guess", []),
            "unmatched_truth": matching.get("unmatched_truth", []),
        },
        "period_recovery_fraction": round(period_fraction, 6),
        "mass_recovery_fraction": round(mass_fraction, 6),
        "phase_recovery_fraction": round(phase_fraction, 6),
        "matched_pair_diagnostics": pair_rows,
    }


def _difficulty_metadata(task: Task) -> Dict[str, Any]:
    times = [float(value) for value in task.observations.times_days]
    sigmas = [float(value) for value in task.observations.sigmas_ms]
    instruments = [str(value) for value in task.observations.instruments]
    baseline_days = max(times) - min(times) if times else 0.0
    median_sigma = sorted(sigmas)[len(sigmas) // 2] if sigmas else None
    return {
        "bucket": "easy",
        "factors": {
            "truth_planet_count": len(task.config.planets),
            "observation_count": len(times),
            "baseline_days": round(baseline_days, 6),
            "median_sigma_ms": round(float(median_sigma), 6) if median_sigma is not None else None,
            "instrument_count": len(set(instruments)),
            "stargazer_truth_difficulty": int(task.truth_difficulty or 0),
        },
    }


def evaluate_stargazer_benchmark(submission_path: Path | str, task_json: Path | str) -> Dict[str, Any]:
    submission_path = Path(submission_path)
    task_json = Path(task_json)
    if not submission_path.exists():
        return {
            "type": "stargazer_benchmark",
            "path": str(submission_path),
            "evaluable": False,
            "passed": False,
            "score": 0.0,
            "criteria": {"file_exists": False},
        }

    task = Task.from_json(task_json.read_text(encoding="utf-8"))
    submission = json.loads(submission_path.read_text(encoding="utf-8"))
    truth_planets = [planet.__dict__ for planet in task.config.planets]
    reward, info = evaluate_submission(
        task.config,
        task.observations,
        submission,
        task.config.planets,
        reward_weights=REWARD_WEIGHTS,
        mode="params_and_model",
    )
    matching = info.get("matching", {}).get("assignment", {})
    pairs = matching.get("pairs", [])
    truth_count = len(task.config.planets)
    guess_count = len(submission.get("planets", []))
    matched_truth_fraction = len(pairs) / truth_count if truth_count else 1.0
    match_score = float(info.get("components", {}).get("match", 0.0))
    delta_bic = float(info.get("components", {}).get("delta_bic", 0.0))
    rms = float(info.get("residuals", {}).get("rms", float("nan")))
    criteria = {
        "file_exists": True,
        "planet_count_matches": guess_count == truth_count,
        "matched_truth_fraction_positive": matched_truth_fraction > 0.0,
        "match_score_at_least_0_8": match_score >= 0.8,
        "delta_bic_positive": delta_bic > 0.0,
    }
    return {
        "type": "stargazer_benchmark",
        "path": str(submission_path),
        "evaluable": True,
        "passed": all(criteria.values()),
        "score": round(sum(1 for ok in criteria.values() if ok) / len(criteria), 6),
        "criteria": criteria,
        "reward": round(float(reward), 6),
        "match_score": round(match_score, 6),
        "rms": round(rms, 6) if math.isfinite(rms) else None,
        "delta_bic_per_point": round(delta_bic, 6),
        "submitted_planets": submission.get("planets", []),
        "truth_planets": truth_planets,
        "submitted_planet_count": guess_count,
        "truth_planet_count": truth_count,
        "difficulty_metadata": _difficulty_metadata(task),
        "matched_truth_fraction": round(matched_truth_fraction, 6),
        "component_breakdown": _component_breakdown(submission, truth_planets, pairs, matching, match_score, delta_bic),
        "prediction_truth_rows": _prediction_truth_rows(submission, truth_planets, pairs, matching),
        "nearest_truth_rows": _nearest_truth_rows(submission, truth_planets),
        "matching_summary": {
            "matched_pairs": pairs,
            "unmatched_guess": matching.get("unmatched_guess", []),
            "unmatched_truth": matching.get("unmatched_truth", []),
        },
    }
