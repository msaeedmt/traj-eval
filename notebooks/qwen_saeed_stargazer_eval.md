# Qwen/Saeed STARGAZER Trajectory-Level Evaluation

This notebook evaluates the completed `qwen_saeed_agent_stargazer.ipynb` run as a trajectory-level scientific-agent trial, aligned with `NLP_Lab___Project_Proposal.pdf`.

The evaluation target is not only the final STARGAZER score. The proposal asks whether trajectory instrumentation can localise, classify, and predict failures that output-only scoring misses. This notebook therefore evaluates:

- **O1 localisation:** event graph, anchor labels, first violated anchor, originating agent/event;
- **O2 failure taxonomy and detectors:** alias convergence, perseveration, format fragility, coordination collapse, cross-agent error propagation, silent overconfidence / critic-masking;
- **O3 early-warning limits:** whether trajectory signals degraded before the final scientific failure was visible;
- **STARGAZER correctness:** final artifact/schema, planet count, period/mass/phase/model-fit anchors.

Implementation note: this notebook intentionally does **not** import from `cambagent_eval`. The benchmark and trajectory-analysis logic below is copied/adapted locally from the project evaluator and rewritten for this single Qwen/Saeed run.



```python
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import json
import math
import re
import sys

import pandas as pd
from IPython.display import Markdown, display

ROOT = Path(r"C:\Users\Anwender\Science-Work-Flow-")
RUN_OUT = ROOT / "outputs" / "qwen_saeed_agent_stargazer"
EVAL_OUT = ROOT / "outputs" / "qwen_saeed_stargazer_eval"
EVAL_OUT.mkdir(parents=True, exist_ok=True)

STARGAZER_PACKAGE_ROOT = ROOT / "data" / "stargazer_repo"
TASK_JSON = STARGAZER_PACKAGE_ROOT / "stargazer" / "Stargazer_real_data_task" / "real_001.json"

FILES = {
    "transition": RUN_OUT / "agent_transition_trace.json",
    "qwen_trace": RUN_OUT / "qwen_trace_full.json",
    "code_reviews": RUN_OUT / "code_review_decisions.json",
    "result_reviews": RUN_OUT / "result_review_decisions.json",
    "executors": RUN_OUT / "executor_records.json",
    "final_verdict": RUN_OUT / "finding_final_verdict.json",
    "benchmark": RUN_OUT / "separate_stargazer_benchmark_judgment.json",
    "planner": RUN_OUT / "planner_summary.txt",
}

def load_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))

def write_json(path: Path, payload):
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

missing = [name for name, path in FILES.items() if not path.exists()]
assert not missing, "Missing run artifacts: " + ", ".join(missing)

transition_records = load_json(FILES["transition"], [])
qwen_trace = load_json(FILES["qwen_trace"], [])
code_reviews = load_json(FILES["code_reviews"], [])
result_reviews = load_json(FILES["result_reviews"], [])
executor_records = load_json(FILES["executors"], [])
final_verdict = load_json(FILES["final_verdict"], {})
cached_benchmark = load_json(FILES["benchmark"], {})
planner_summary = FILES["planner"].read_text(encoding="utf-8")

pd.set_option("display.max_colwidth", 160)
pd.set_option("display.width", 180)

display(Markdown(
    f"Loaded Qwen/Saeed run artifacts from `{RUN_OUT}`. "
    f"Loop stop reason: **{final_verdict.get('loop_stop_reason')}**; "
    f"benchmark ran: **{final_verdict.get('benchmark_ran')}**."
))

```


Loaded Qwen/Saeed run artifacts from `C:\Users\Anwender\Science-Work-Flow-\outputs\qwen_saeed_agent_stargazer`. Loop stop reason: **APPROVE_RESULT**; benchmark ran: **True**.


## 1. Local STARGAZER Benchmark Code

This cell embeds the benchmark/scoring helpers directly in the notebook. It imports only the STARGAZER package for the benchmark itself, not `cambagent_eval`.



```python
REWARD_WEIGHTS = {"likelihood": 1.0, "delta_bic": 0.3, "neg_rms": 0.1, "match": 1.0, "count": 0.2}

def angle_distance(a, b) -> float:
    try:
        raw = abs(float(a) - float(b))
    except Exception:
        return math.inf
    return min(raw % (2.0 * math.pi), (2.0 * math.pi - raw) % (2.0 * math.pi))

def relative_error(observed, expected) -> float:
    try:
        obs = abs(float(observed))
        exp = abs(float(expected))
    except Exception:
        return math.inf
    return abs(obs - exp) / max(exp, 1e-9)

def compact_planet_fields(planet):
    if not planet:
        return {}
    result = {}
    for key in ["P_days", "m_sin_i_mjup", "e", "omega_rad", "l_rad"]:
        value = planet.get(key)
        result[key] = round(float(value), 6) if isinstance(value, (int, float)) else value
    return result

def prediction_truth_rows(submission, truth_planets, pairs, matching):
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
        rows.append({
            "row_type": "matched",
            "truth_index": truth_index,
            "guess_index": guess_index,
            "truth": compact_planet_fields(truth),
            "submission": compact_planet_fields(guess),
            "period_rel_error": round(relative_error(guess.get("P_days"), truth.get("P_days")), 6),
            "mass_rel_error": round(relative_error(guess.get("m_sin_i_mjup"), truth.get("m_sin_i_mjup")), 6),
            "eccentricity_abs_error": round(abs(float(guess.get("e", 0.0) or 0.0) - float(truth.get("e", 0.0) or 0.0)), 6),
            "omega_error_rad": round(angle_distance(guess.get("omega_rad", 0.0), truth.get("omega_rad", 0.0)), 6),
            "l_error_rad": round(angle_distance(guess.get("l_rad", 0.0), truth.get("l_rad", 0.0)), 6),
        })
    unmatched_truth = sorted(set(int(i) for i in matching.get("unmatched_truth", [])) | (set(range(len(truth_planets))) - seen_truth))
    unmatched_guess = sorted(set(int(i) for i in matching.get("unmatched_guess", [])) | (set(range(len(submitted))) - seen_guess))
    for truth_index in unmatched_truth:
        if truth_index < len(truth_planets):
            rows.append({"row_type": "unmatched_truth", "truth_index": truth_index, "guess_index": None, "truth": compact_planet_fields(truth_planets[truth_index]), "submission": {}})
    for guess_index in unmatched_guess:
        if guess_index < len(submitted):
            rows.append({"row_type": "unmatched_submission", "truth_index": None, "guess_index": guess_index, "truth": {}, "submission": compact_planet_fields(submitted[guess_index])})
    return rows

def nearest_truth_rows(submission, truth_planets):
    submitted = [planet for planet in submission.get("planets", []) if isinstance(planet, dict)]
    rows = []
    for guess_index, guess in enumerate(submitted):
        if not truth_planets:
            continue
        best_truth_index, best_truth = min(
            enumerate(truth_planets),
            key=lambda item: relative_error(guess.get("P_days"), item[1].get("P_days")),
        )
        rows.append({
            "guess_index": guess_index,
            "nearest_truth_index": best_truth_index,
            "submission": compact_planet_fields(guess),
            "nearest_truth": compact_planet_fields(best_truth),
            "period_rel_error": round(relative_error(guess.get("P_days"), best_truth.get("P_days")), 6),
            "mass_rel_error": round(relative_error(guess.get("m_sin_i_mjup"), best_truth.get("m_sin_i_mjup")), 6),
            "eccentricity_abs_error": round(abs(float(guess.get("e", 0.0) or 0.0) - float(best_truth.get("e", 0.0) or 0.0)), 6),
            "omega_error_rad": round(angle_distance(guess.get("omega_rad", 0.0), best_truth.get("omega_rad", 0.0)), 6),
            "l_error_rad": round(angle_distance(guess.get("l_rad", 0.0), best_truth.get("l_rad", 0.0)), 6),
        })
    return rows

def stargazer_component_breakdown(submission, truth_planets, pairs, matching, match_score, delta_bic):
    submitted = [planet for planet in submission.get("planets", []) if isinstance(planet, dict)]
    failed = []
    count_ok = len(submitted) == len(truth_planets)
    if not count_ok:
        failed.append("planet_count")
    period_ok_count = mass_ok_count = phase_ok_count = 0
    pair_rows = []
    for pair in pairs:
        truth_index, guess_index = int(pair[0]), int(pair[1])
        if truth_index >= len(truth_planets) or guess_index >= len(submitted):
            continue
        truth, guess = truth_planets[truth_index], submitted[guess_index]
        period_rel_error = relative_error(guess.get("P_days"), truth.get("P_days"))
        mass_rel_error = relative_error(guess.get("m_sin_i_mjup"), truth.get("m_sin_i_mjup"))
        omega_error = angle_distance(guess.get("omega_rad", 0.0), truth.get("omega_rad", 0.0))
        l_error = angle_distance(guess.get("l_rad", 0.0), truth.get("l_rad", 0.0))
        eccentricity_abs_error = abs(float(guess.get("e", 0.0) or 0.0) - float(truth.get("e", 0.0) or 0.0))
        period_ok = period_rel_error <= 0.10
        mass_ok = mass_rel_error <= 0.50
        phase_ok = omega_error <= 1.0 and l_error <= 1.0 and eccentricity_abs_error <= 0.15
        period_ok_count += int(period_ok)
        mass_ok_count += int(mass_ok)
        phase_ok_count += int(phase_ok)
        pair_rows.append({
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
        })
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
        "planet_count": {"submitted": len(submitted), "truth": len(truth_planets), "ok": count_ok, "unmatched_guess": matching.get("unmatched_guess", []), "unmatched_truth": matching.get("unmatched_truth", [])},
        "period_recovery_fraction": round(period_fraction, 6),
        "mass_recovery_fraction": round(mass_fraction, 6),
        "phase_recovery_fraction": round(phase_fraction, 6),
        "matched_pair_diagnostics": pair_rows,
    }

def task_difficulty_metadata(task):
    times = [float(value) for value in getattr(task.observations, "times_days", [])]
    sigmas = [float(value) for value in getattr(task.observations, "sigmas_ms", [])]
    instruments = [str(value) for value in getattr(task.observations, "instruments", [])]
    truth_count = len(getattr(task.config, "planets", []))
    observation_count = len(times)
    baseline_days = max(times) - min(times) if times else 0.0
    median_sigma = sorted(sigmas)[len(sigmas) // 2] if sigmas else None
    stargazer_truth_difficulty = int(getattr(task, "truth_difficulty", 0) or 0)
    return {
        "bucket": "easy",
        "factors": {
            "truth_planet_count": truth_count,
            "observation_count": observation_count,
            "baseline_days": round(baseline_days, 6),
            "median_sigma_ms": round(float(median_sigma), 6) if median_sigma is not None else None,
            "instrument_count": len(set(instruments)),
            "stargazer_truth_difficulty": stargazer_truth_difficulty,
        },
    }

def evaluate_stargazer_benchmark_local(submission_path: Path, task_json: Path):
    if not submission_path.exists():
        return {"type": "stargazer_benchmark", "path": str(submission_path), "evaluable": False, "passed": False, "score": 0.0, "criteria": {"file_exists": False}}
    if str(STARGAZER_PACKAGE_ROOT) not in sys.path:
        sys.path.insert(0, str(STARGAZER_PACKAGE_ROOT))
    from stargazer import Task, evaluate_submission

    task = Task.from_json(task_json.read_text(encoding="utf-8"))
    submission = json.loads(submission_path.read_text(encoding="utf-8"))
    truth_planets = [planet.__dict__ for planet in task.config.planets]
    reward, info = evaluate_submission(task.config, task.observations, submission, task.config.planets, reward_weights=REWARD_WEIGHTS, mode="params_and_model")
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
        "difficulty_metadata": task_difficulty_metadata(task),
        "matched_truth_fraction": round(matched_truth_fraction, 6),
        "component_breakdown": stargazer_component_breakdown(submission, truth_planets, pairs, matching, match_score, delta_bic),
        "prediction_truth_rows": prediction_truth_rows(submission, truth_planets, pairs, matching),
        "nearest_truth_rows": nearest_truth_rows(submission, truth_planets),
        "matching_summary": {"matched_pairs": pairs, "unmatched_guess": matching.get("unmatched_guess", []), "unmatched_truth": matching.get("unmatched_truth", [])},
    }

```

## 2. Recompute Output-Level STARGAZER Evidence

The benchmark is intentionally run only in the evaluation notebook, after the agent workflow produced a final executor submission.



```python
final_submission_path = Path(final_verdict.get("final_submission_path", ""))
submission_artifact_available = final_submission_path.exists()
submission_path_is_agent_workflow = str(final_submission_path).startswith(str(RUN_OUT / "agent_workflow"))

if submission_artifact_available:
    assert submission_path_is_agent_workflow, "Submission is not from the agent workflow directory."
    benchmark = evaluate_stargazer_benchmark_local(final_submission_path, TASK_JSON)
    benchmark_source = "recomputed_from_submission"
else:
    benchmark = dict(cached_benchmark)
    benchmark_source = "saved_benchmark_json_submission_file_missing"
    assert benchmark.get("evaluable") is True, "No final submission file and no evaluable saved benchmark record."

if "nearest_truth_rows" not in benchmark:
    benchmark["nearest_truth_rows"] = nearest_truth_rows(
        {"planets": benchmark.get("submitted_planets", [])},
        benchmark.get("truth_planets", []),
    )
benchmark["benchmark_source"] = benchmark_source
benchmark["submission_artifact_available_at_eval_time"] = submission_artifact_available
write_json(EVAL_OUT / "local_stargazer_benchmark.json", benchmark)

summary_rows = [
    ["submission_path", str(final_submission_path)],
    ["benchmark_source", benchmark_source],
    ["submission_artifact_available_at_eval_time", submission_artifact_available],
    ["evaluable", benchmark.get("evaluable")],
    ["passed", benchmark.get("passed")],
    ["score", benchmark.get("score")],
    ["reward", benchmark.get("reward")],
    ["match_score", benchmark.get("match_score")],
    ["matched_truth_fraction", benchmark.get("matched_truth_fraction")],
    ["rms", benchmark.get("rms")],
    ["delta_bic_per_point", benchmark.get("delta_bic_per_point")],
    ["submitted_planet_count", benchmark.get("submitted_planet_count")],
    ["truth_planet_count", benchmark.get("truth_planet_count")],
]
display(pd.DataFrame(summary_rows, columns=["field", "value"]))
display(pd.DataFrame(benchmark.get("prediction_truth_rows", [])))
display(pd.DataFrame(benchmark.get("nearest_truth_rows", [])))

```


<div>
<style scoped>
    .dataframe tbody tr th:only-of-type {
        vertical-align: middle;
    }

    .dataframe tbody tr th {
        vertical-align: top;
    }

    .dataframe thead th {
        text-align: right;
    }
</style>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>field</th>
      <th>value</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>0</th>
      <td>submission_path</td>
      <td>C:\Users\Anwender\Science-Work-Flow-\outputs\qwen_saeed_agent_stargazer\agent_workflow\iteration_04\agent_submission.json</td>
    </tr>
    <tr>
      <th>1</th>
      <td>benchmark_source</td>
      <td>recomputed_from_submission</td>
    </tr>
    <tr>
      <th>2</th>
      <td>submission_artifact_available_at_eval_time</td>
      <td>True</td>
    </tr>
    <tr>
      <th>3</th>
      <td>evaluable</td>
      <td>True</td>
    </tr>
    <tr>
      <th>4</th>
      <td>passed</td>
      <td>False</td>
    </tr>
    <tr>
      <th>5</th>
      <td>score</td>
      <td>0.6</td>
    </tr>
    <tr>
      <th>6</th>
      <td>reward</td>
      <td>-1512.832788</td>
    </tr>
    <tr>
      <th>7</th>
      <td>match_score</td>
      <td>0.022661</td>
    </tr>
    <tr>
      <th>8</th>
      <td>matched_truth_fraction</td>
      <td>1.0</td>
    </tr>
    <tr>
      <th>9</th>
      <td>rms</td>
      <td>41.49204</td>
    </tr>
    <tr>
      <th>10</th>
      <td>delta_bic_per_point</td>
      <td>-1265.18174</td>
    </tr>
    <tr>
      <th>11</th>
      <td>submitted_planet_count</td>
      <td>1</td>
    </tr>
    <tr>
      <th>12</th>
      <td>truth_planet_count</td>
      <td>1</td>
    </tr>
  </tbody>
</table>
</div>



<div>
<style scoped>
    .dataframe tbody tr th:only-of-type {
        vertical-align: middle;
    }

    .dataframe tbody tr th {
        vertical-align: top;
    }

    .dataframe thead th {
        text-align: right;
    }
</style>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>row_type</th>
      <th>truth_index</th>
      <th>guess_index</th>
      <th>truth</th>
      <th>submission</th>
      <th>period_rel_error</th>
      <th>mass_rel_error</th>
      <th>eccentricity_abs_error</th>
      <th>omega_error_rad</th>
      <th>l_error_rad</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>0</th>
      <td>matched</td>
      <td>0</td>
      <td>0</td>
      <td>{'P_days': 4.230785, 'm_sin_i_mjup': 0.461, 'e': 0.013, 'omega_rad': 1.012291, 'l_rad': 4.644516}</td>
      <td>{'P_days': 2.868989, 'm_sin_i_mjup': 0.166203, 'e': 0.0, 'omega_rad': 0.0, 'l_rad': 4.74811}</td>
      <td>0.321878</td>
      <td>0.639473</td>
      <td>0.013</td>
      <td>1.012291</td>
      <td>0.103594</td>
    </tr>
  </tbody>
</table>
</div>



<div>
<style scoped>
    .dataframe tbody tr th:only-of-type {
        vertical-align: middle;
    }

    .dataframe tbody tr th {
        vertical-align: top;
    }

    .dataframe thead th {
        text-align: right;
    }
</style>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>guess_index</th>
      <th>nearest_truth_index</th>
      <th>submission</th>
      <th>nearest_truth</th>
      <th>period_rel_error</th>
      <th>mass_rel_error</th>
      <th>eccentricity_abs_error</th>
      <th>omega_error_rad</th>
      <th>l_error_rad</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>0</th>
      <td>0</td>
      <td>0</td>
      <td>{'P_days': 2.868989, 'm_sin_i_mjup': 0.166203, 'e': 0.0, 'omega_rad': 0.0, 'l_rad': 4.74811}</td>
      <td>{'P_days': 4.230785, 'm_sin_i_mjup': 0.461, 'e': 0.013, 'omega_rad': 1.012291, 'l_rad': 4.644516}</td>
      <td>0.321878</td>
      <td>0.639473</td>
      <td>0.013</td>
      <td>1.012291</td>
      <td>0.103594</td>
    </tr>
  </tbody>
</table>
</div>


## 3. Trajectory Graph and Structural Metrics

Events are reconstructed from the saved planner/engineer/reviewer/executor trace. Edges follow causal order and feedback loops.



```python
def build_events(transitions, qwen_records, executors):
    reason_stop_words = {
        "stop", "end", "ended", "length", "finish", "finished", "none", "null", "true", "false",
        "verdict", "approve", "approved", "approval", "revise", "revised", "revision", "code", "result",
        "script", "proposed", "executed", "review", "reviewer", "feedback", "iteration", "engineer",
        "planner", "executor", "plan", "written", "returned", "before", "after", "next", "path",
        "characters", "character", "thinking", "process", "analyze", "request", "evidence",
        "because", "inst", "uniq", "indice", "plausi", "exit", "successfully",
        "the", "a", "an", "and", "or", "to", "of", "in", "for", "with", "by", "on", "at", "as",
        "is", "are", "was", "were", "be", "been", "being", "this", "that", "it", "its", "from",
        "when", "during", "while", "which", "will", "shall", "can", "could", "should", "would",
        "may", "might", "must", "have", "has", "had", "not", "without", "within", "into", "all",
    }

    def extract_last_meaningful_reason_word(*texts):
        words = []
        for text in texts:
            # Extract semantic reason words source-by-source, not transport finish reasons or file/path fragments.
            raw_text = str(text or "")
            words = re.findall(r"[A-Za-z]{4,}", raw_text.lower())
            if raw_text.rstrip() and raw_text.rstrip()[-1].isalnum() and len(raw_text) > 120:
                words = words[:-1]
            for word in reversed(words):
                if word not in reason_stop_words:
                    return word
        return ""

    events = []
    qwen_by_key = {(r.get("role"), r.get("phase"), r.get("iteration")): r for r in qwen_records}
    executor_by_iteration = {r.get("script_path", ""): r for r in executors}
    for idx, tr in enumerate(transitions):
        role = tr.get("role")
        phase = tr.get("phase")
        iteration = tr.get("iteration")
        qwen = qwen_by_key.get((role, "engineering" if phase == "write_code" else phase, iteration), {})
        event = {
            "event_id": f"e{idx:03d}",
            "index": idx,
            "role": role,
            "phase": phase,
            "iteration": iteration,
            "verdict": tr.get("verdict"),
            "finish_reason": tr.get("finish_reason"),
            "reasoning_present": bool(tr.get("reasoning_present")),
            "details": tr.get("details", ""),
            "text_excerpt": str(qwen.get("text", ""))[:500],
            "tokens": qwen.get("tokens", {}),
        }
        reason_sources = [event["details"]]
        if role in {"planner", "reviewer"}:
            reason_sources.append(event["text_excerpt"])
        event["reason_last_word"] = extract_last_meaningful_reason_word(*reason_sources)
        events.append(event)
    return events

events = build_events(transition_records, qwen_trace, executor_records)
edges = []
for prev, cur in zip(events, events[1:]):
    edges.append({"source": prev["event_id"], "target": cur["event_id"], "edge_type": "temporal"})
for event in events:
    if event["phase"] == "feedback_to_engineer":
        later = [e for e in events if e["iteration"] > event["iteration"] and e["role"] == "engineer" and e["phase"] == "write_code"]
        if later:
            edges.append({"source": event["event_id"], "target": later[0]["event_id"], "edge_type": "revision_feedback"})

role_counts = Counter(e["role"] for e in events)
phase_counts = Counter(e["phase"] for e in events)
reason_last_word_counts = Counter(e.get("reason_last_word") for e in events if e.get("reason_last_word"))
revision_events = [e for e in events if e["phase"] == "feedback_to_engineer"]
approve_code_events = [e for e in events if e["verdict"] == "APPROVE_CODE"]
approve_result_events = [e for e in events if e["verdict"] == "APPROVE_RESULT"]

trajectory_graph = {
    "events": events,
    "edges": edges,
    "metrics": {
        "event_count": len(events),
        "edge_count": len(edges),
        "role_counts": dict(role_counts),
        "phase_counts": dict(phase_counts),
        "reason_last_word_counts": dict(reason_last_word_counts),
        "revision_count": len(revision_events),
        "code_review_count": len(code_reviews),
        "result_review_count": len(result_reviews),
        "executor_count": len(executor_records),
        "approve_code_count": len(approve_code_events),
        "approve_result_count": len(approve_result_events),
        "max_iteration_seen": max([e["iteration"] for e in events if isinstance(e.get("iteration"), int)] or [0]),
    },
}
write_json(EVAL_OUT / "trajectory_graph.json", trajectory_graph)
pd.DataFrame(events).to_csv(EVAL_OUT / "trajectory_events.csv", index=False)

display(pd.DataFrame([[k, v] for k, v in trajectory_graph["metrics"].items()], columns=["metric", "value"]))
display(pd.DataFrame(events)[["event_id", "role", "phase", "iteration", "verdict", "reason_last_word", "finish_reason", "details"]])

```


<div>
<style scoped>
    .dataframe tbody tr th:only-of-type {
        vertical-align: middle;
    }

    .dataframe tbody tr th {
        vertical-align: top;
    }

    .dataframe thead th {
        text-align: right;
    }
</style>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>metric</th>
      <th>value</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>0</th>
      <td>event_count</td>
      <td>8</td>
    </tr>
    <tr>
      <th>1</th>
      <td>edge_count</td>
      <td>8</td>
    </tr>
    <tr>
      <th>2</th>
      <td>role_counts</td>
      <td>{'planner': 1, 'engineer': 2, 'reviewer': 4, 'executor': 1}</td>
    </tr>
    <tr>
      <th>3</th>
      <td>phase_counts</td>
      <td>{'planning': 1, 'write_code': 2, 'code_review': 2, 'feedback_to_engineer': 1, 'save_approved_code': 1, 'execute': 1}</td>
    </tr>
    <tr>
      <th>4</th>
      <td>reason_last_word_counts</td>
      <td>{'task': 1, 'uses': 1, 'model': 1, 'workflow': 1}</td>
    </tr>
    <tr>
      <th>5</th>
      <td>revision_count</td>
      <td>1</td>
    </tr>
    <tr>
      <th>6</th>
      <td>code_review_count</td>
      <td>2</td>
    </tr>
    <tr>
      <th>7</th>
      <td>result_review_count</td>
      <td>0</td>
    </tr>
    <tr>
      <th>8</th>
      <td>executor_count</td>
      <td>1</td>
    </tr>
    <tr>
      <th>9</th>
      <td>approve_code_count</td>
      <td>2</td>
    </tr>
    <tr>
      <th>10</th>
      <td>approve_result_count</td>
      <td>0</td>
    </tr>
    <tr>
      <th>11</th>
      <td>max_iteration_seen</td>
      <td>2</td>
    </tr>
  </tbody>
</table>
</div>



<div>
<style scoped>
    .dataframe tbody tr th:only-of-type {
        vertical-align: middle;
    }

    .dataframe tbody tr th {
        vertical-align: top;
    }

    .dataframe thead th {
        text-align: right;
    }
</style>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>event_id</th>
      <th>role</th>
      <th>phase</th>
      <th>iteration</th>
      <th>verdict</th>
      <th>reason_last_word</th>
      <th>finish_reason</th>
      <th>details</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>0</th>
      <td>e000</td>
      <td>planner</td>
      <td>planning</td>
      <td>0</td>
      <td>PLAN_WRITTEN</td>
      <td>task</td>
      <td>length</td>
      <td>Thinking Process:\n\n1.&nbsp;&nbsp;**Analyze the Request:**\n&nbsp;&nbsp;&nbsp;&nbsp;*&nbsp;&nbsp; **Role:** PLANNER in a multi-agent scientific-reasoning team.\n&nbsp;&nbsp;&nbsp;&nbsp;*&nbsp;&nbsp; **Task:** Create a short, ...</td>
    </tr>
    <tr>
      <th>1</th>
      <td>e001</td>
      <td>engineer</td>
      <td>write_code</td>
      <td>1</td>
      <td>SCRIPT_PROPOSED</td>
      <td></td>
      <td>stop</td>
      <td>6299 characters</td>
    </tr>
    <tr>
      <th>2</th>
      <td>e002</td>
      <td>reviewer</td>
      <td>code_review</td>
      <td>1</td>
      <td>REVISE_CODE</td>
      <td>uses</td>
      <td>stop</td>
      <td>VERDICT: REVISE_CODE - The `keplerian_rv` function returns velocities in m/s while the input data and `residual_sum_sq` function expect m/s but the input `r...</td>
    </tr>
    <tr>
      <th>3</th>
      <td>e003</td>
      <td>reviewer</td>
      <td>feedback_to_engineer</td>
      <td>1</td>
      <td>REVISE_CODE</td>
      <td></td>
      <td>stop</td>
      <td>code feedback returned before next engineer iteration</td>
    </tr>
    <tr>
      <th>4</th>
      <td>e004</td>
      <td>engineer</td>
      <td>write_code</td>
      <td>2</td>
      <td>SCRIPT_PROPOSED</td>
      <td></td>
      <td>stop</td>
      <td>7022 characters</td>
    </tr>
    <tr>
      <th>5</th>
      <td>e005</td>
      <td>reviewer</td>
      <td>code_review</td>
      <td>2</td>
      <td>APPROVE_CODE</td>
      <td>model</td>
      <td>stop</td>
      <td>The engineer's script implements a scientifically plausible radial velocity analysis pipeline:\n1.&nbsp;&nbsp;**Data Loading**: Correctly parses the expected JSON str...</td>
    </tr>
    <tr>
      <th>6</th>
      <td>e006</td>
      <td>reviewer</td>
      <td>save_approved_code</td>
      <td>2</td>
      <td>APPROVE_CODE</td>
      <td>workflow</td>
      <td>stop</td>
      <td>C:\Users\Anwender\Science-Work-Flow-\outputs\qwen_saeed_agent_stargazer\agent_workflow\iteration_02\engineer_iteration_02.py</td>
    </tr>
    <tr>
      <th>7</th>
      <td>e007</td>
      <td>executor</td>
      <td>execute</td>
      <td>2</td>
      <td>EXECUTED</td>
      <td></td>
      <td>NaN</td>
      <td>exit_code=0</td>
    </tr>
  </tbody>
</table>
</div>


## 4. Anchor Labels and First Violated Anchor

Anchors are proposal-style intermediate and final checks. They include artifact gates, transition-order gates, reviewer gates, and STARGAZER physical/model anchors.



```python
criteria = benchmark.get("criteria", {})
component = benchmark.get("component_breakdown", {})
nearest_rows = benchmark.get("nearest_truth_rows", [])
nearest = nearest_rows[0] if nearest_rows else {}

def anchor(name, passed, layer, originating_agent, evidence):
    return {
        "anchor": name,
        "passed": bool(passed),
        "layer": layer,
        "originating_agent": originating_agent,
        "evidence": evidence,
    }

phases = [(r.get("role"), r.get("phase"), r.get("verdict")) for r in transition_records]
executor_after_code_approval = all(
    p[1] != "execute" or any(q[1] == "save_approved_code" and q[2] == "APPROVE_CODE" for q in phases[:i])
    for i, p in enumerate(phases)
)
benchmark_after_result_approval = bool(final_verdict.get("benchmark_ran")) == bool(final_verdict.get("loop_stop_reason") == "APPROVE_RESULT")

anchors = [
    anchor("planner_present", any(e["role"] == "planner" for e in events), "trajectory", "planner", "planner event exists"),
    anchor("engineer_code_proposed", any(e["role"] == "engineer" and e["phase"] == "write_code" for e in events), "trajectory", "engineer", "engineer write_code events exist"),
    anchor("reviewer_code_review_before_execution", executor_after_code_approval, "trajectory", "reviewer", "executor appears only after APPROVE_CODE"),
    anchor("executor_success", all(r.get("exit_code") == 0 for r in executor_records) and bool(executor_records), "artifact", "executor", f"executor_count={len(executor_records)}"),
    anchor("agent_submission_evidence_available", submission_artifact_available or benchmark.get("evaluable", False), "artifact", "executor/evaluator", f"path_exists={submission_artifact_available}; benchmark_source={benchmark_source}"),
    anchor("saved_benchmark_record_available", benchmark.get("evaluable", False), "artifact", "evaluator", f"benchmark_source={benchmark_source}"),
    anchor("result_review_before_benchmark", benchmark_after_result_approval, "trajectory", "reviewer", f"loop_stop_reason={final_verdict.get('loop_stop_reason')}; benchmark_ran={final_verdict.get('benchmark_ran')}"),
    anchor("benchmark_evaluable", benchmark.get("evaluable", False), "science", "evaluator", f"evaluable={benchmark.get('evaluable')}"),
    anchor("planet_count_matches", criteria.get("planet_count_matches", False), "science", "engineer", f"submitted={benchmark.get('submitted_planet_count')}; truth={benchmark.get('truth_planet_count')}"),
    anchor("hungarian_match_positive", criteria.get("matched_truth_fraction_positive", False), "science", "engineer/reviewer", f"matched_truth_fraction={benchmark.get('matched_truth_fraction')}"),
    anchor("match_score_at_least_0_8", criteria.get("match_score_at_least_0_8", False), "science", "engineer/reviewer", f"match_score={benchmark.get('match_score')}"),
    anchor("delta_bic_positive", criteria.get("delta_bic_positive", False), "science", "engineer", f"delta_bic_per_point={benchmark.get('delta_bic_per_point')}"),
    anchor("nearest_period_recovered", nearest.get("period_rel_error", math.inf) <= 0.10 if nearest else False, "science", "engineer", f"nearest_period_rel_error={nearest.get('period_rel_error')}"),
    anchor("nearest_mass_reasonable", nearest.get("mass_rel_error", math.inf) <= 0.50 if nearest else False, "science", "engineer", f"nearest_mass_rel_error={nearest.get('mass_rel_error')}"),
    anchor("nearest_phase_reasonable", (nearest.get("omega_error_rad", math.inf) <= 1.0 and nearest.get("l_error_rad", math.inf) <= 1.0) if nearest else False, "science", "engineer", f"omega_error={nearest.get('omega_error_rad')}; l_error={nearest.get('l_error_rad')}"),
    anchor("reviewer_rejected_bad_result_before_final", not (benchmark.get("evaluable") and not benchmark.get("passed") and final_verdict.get("loop_stop_reason") == "APPROVE_RESULT"), "trajectory", "reviewer", "APPROVE_RESULT should not coincide with failed STARGAZER anchors"),
]

first_failed = next((item for item in anchors if not item["passed"]), {"anchor": "none", "passed": True, "layer": "none", "originating_agent": "none", "evidence": "all anchors passed"})
anchor_score = sum(1 for item in anchors if item["passed"]) / len(anchors)

anchor_report = {"anchors": anchors, "first_violated_anchor": first_failed, "anchor_score": round(anchor_score, 6)}
write_json(EVAL_OUT / "anchor_report.json", anchor_report)

display(pd.DataFrame(anchors))
display(Markdown(f"First violated anchor: **{first_failed['anchor']}** at layer **{first_failed['layer']}**, attributed to **{first_failed['originating_agent']}**."))

```


<div>
<style scoped>
    .dataframe tbody tr th:only-of-type {
        vertical-align: middle;
    }

    .dataframe tbody tr th {
        vertical-align: top;
    }

    .dataframe thead th {
        text-align: right;
    }
</style>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>anchor</th>
      <th>passed</th>
      <th>layer</th>
      <th>originating_agent</th>
      <th>evidence</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>0</th>
      <td>planner_present</td>
      <td>True</td>
      <td>trajectory</td>
      <td>planner</td>
      <td>planner event exists</td>
    </tr>
    <tr>
      <th>1</th>
      <td>engineer_code_proposed</td>
      <td>True</td>
      <td>trajectory</td>
      <td>engineer</td>
      <td>engineer write_code events exist</td>
    </tr>
    <tr>
      <th>2</th>
      <td>reviewer_code_review_before_execution</td>
      <td>True</td>
      <td>trajectory</td>
      <td>reviewer</td>
      <td>executor appears only after APPROVE_CODE</td>
    </tr>
    <tr>
      <th>3</th>
      <td>executor_success</td>
      <td>True</td>
      <td>artifact</td>
      <td>executor</td>
      <td>executor_count=1</td>
    </tr>
    <tr>
      <th>4</th>
      <td>agent_submission_evidence_available</td>
      <td>True</td>
      <td>artifact</td>
      <td>executor/evaluator</td>
      <td>path_exists=True; benchmark_source=recomputed_from_submission</td>
    </tr>
    <tr>
      <th>5</th>
      <td>saved_benchmark_record_available</td>
      <td>True</td>
      <td>artifact</td>
      <td>evaluator</td>
      <td>benchmark_source=recomputed_from_submission</td>
    </tr>
    <tr>
      <th>6</th>
      <td>result_review_before_benchmark</td>
      <td>True</td>
      <td>trajectory</td>
      <td>reviewer</td>
      <td>loop_stop_reason=APPROVE_RESULT; benchmark_ran=True</td>
    </tr>
    <tr>
      <th>7</th>
      <td>benchmark_evaluable</td>
      <td>True</td>
      <td>science</td>
      <td>evaluator</td>
      <td>evaluable=True</td>
    </tr>
    <tr>
      <th>8</th>
      <td>planet_count_matches</td>
      <td>True</td>
      <td>science</td>
      <td>engineer</td>
      <td>submitted=1; truth=1</td>
    </tr>
    <tr>
      <th>9</th>
      <td>hungarian_match_positive</td>
      <td>True</td>
      <td>science</td>
      <td>engineer/reviewer</td>
      <td>matched_truth_fraction=1.0</td>
    </tr>
    <tr>
      <th>10</th>
      <td>match_score_at_least_0_8</td>
      <td>False</td>
      <td>science</td>
      <td>engineer/reviewer</td>
      <td>match_score=0.022661</td>
    </tr>
    <tr>
      <th>11</th>
      <td>delta_bic_positive</td>
      <td>False</td>
      <td>science</td>
      <td>engineer</td>
      <td>delta_bic_per_point=-1265.18174</td>
    </tr>
    <tr>
      <th>12</th>
      <td>nearest_period_recovered</td>
      <td>False</td>
      <td>science</td>
      <td>engineer</td>
      <td>nearest_period_rel_error=0.321878</td>
    </tr>
    <tr>
      <th>13</th>
      <td>nearest_mass_reasonable</td>
      <td>False</td>
      <td>science</td>
      <td>engineer</td>
      <td>nearest_mass_rel_error=0.639473</td>
    </tr>
    <tr>
      <th>14</th>
      <td>nearest_phase_reasonable</td>
      <td>False</td>
      <td>science</td>
      <td>engineer</td>
      <td>omega_error=1.012291; l_error=0.103594</td>
    </tr>
    <tr>
      <th>15</th>
      <td>reviewer_rejected_bad_result_before_final</td>
      <td>False</td>
      <td>trajectory</td>
      <td>reviewer</td>
      <td>APPROVE_RESULT should not coincide with failed STARGAZER anchors</td>
    </tr>
  </tbody>
</table>
</div>



First violated anchor: **match_score_at_least_0_8** at layer **science**, attributed to **engineer/reviewer**.


## 5. Failure Taxonomy Detectors

These detectors implement the proposal's O2 taxonomy over the trajectory graph plus anchor labels.



```python
labels = []
failed_components = set(component.get("failed_components", []))
review_text = "\n".join(str(r.get("text", "")) for r in result_reviews).lower()
code_review_text = "\n".join(str(r.get("text", "")) for r in code_reviews).lower()

if not benchmark.get("evaluable", False):
    labels.append("format_fragility")
if benchmark.get("evaluable", False) and not benchmark.get("passed", False):
    labels.append("scientific_anchor_failure")
if "period_recovery" in failed_components and nearest.get("period_rel_error", math.inf) > 0.10:
    labels.append("alias_convergence_or_missed_period")
if "mass_amplitude" in failed_components or (nearest and nearest.get("mass_rel_error", math.inf) > 0.50):
    labels.append("mass_amplitude_mismatch")
if "phase_or_eccentricity" in failed_components:
    labels.append("phase_parameter_mismatch")
if "model_fit" in failed_components:
    labels.append("model_fit_degradation")
if final_verdict.get("loop_stop_reason") == "APPROVE_RESULT" and benchmark.get("evaluable") and not benchmark.get("passed"):
    labels.append("critic_masking")
    labels.append("silent_acceptance")
if len(revision_events) >= 4:
    labels.append("perseveration_or_retry_loop")
if "lomb" in code_review_text and code_review_text.count("tau") >= 2:
    labels.append("periodogram_implementation_instability")
if len(role_counts) < 4 or role_counts.get("executor", 0) == 0:
    labels.append("coordination_collapse")
if any(e.get("finish_reason") == "length" for e in events):
    labels.append("truncated_reasoning_or_output")

detector_report = {
    "detectors_fired": sorted(set(labels)) if labels else ["no_failure_detected"],
    "first_violated_anchor": first_failed,
    "originating_agent": first_failed.get("originating_agent"),
    "interpretation": (
        "The workflow produced and reviewer-approved an executor artifact, but STARGAZER physical/model anchors failed. "
        "This is a proposal-relevant silent acceptance / critic-masking case, not an environment failure."
        if "critic_masking" in labels else
        "No critic-masking failure detected by the configured trajectory labels."
    ),
}
write_json(EVAL_OUT / "detector_report.json", detector_report)

display(pd.DataFrame([[label] for label in detector_report["detectors_fired"]], columns=["detector"]))
display(Markdown(detector_report["interpretation"]))

```


<div>
<style scoped>
    .dataframe tbody tr th:only-of-type {
        vertical-align: middle;
    }

    .dataframe tbody tr th {
        vertical-align: top;
    }

    .dataframe thead th {
        text-align: right;
    }
</style>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>detector</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>0</th>
      <td>alias_convergence_or_missed_period</td>
    </tr>
    <tr>
      <th>1</th>
      <td>critic_masking</td>
    </tr>
    <tr>
      <th>2</th>
      <td>mass_amplitude_mismatch</td>
    </tr>
    <tr>
      <th>3</th>
      <td>model_fit_degradation</td>
    </tr>
    <tr>
      <th>4</th>
      <td>phase_parameter_mismatch</td>
    </tr>
    <tr>
      <th>5</th>
      <td>scientific_anchor_failure</td>
    </tr>
    <tr>
      <th>6</th>
      <td>silent_acceptance</td>
    </tr>
    <tr>
      <th>7</th>
      <td>truncated_reasoning_or_output</td>
    </tr>
  </tbody>
</table>
</div>



The workflow produced and reviewer-approved an executor artifact, but STARGAZER physical/model anchors failed. This is a proposal-relevant silent acceptance / critic-masking case, not an environment failure.


## 6. Proposal-Aligned Objective Evaluation

This table states what this single run can and cannot support for O1/O2/O3.



```python
objective_rows = [
    {
        "objective": "O1 localisation infrastructure",
        "status": "partial_support",
        "evidence": f"trace events={len(events)}, edges={len(edges)}, first_failed_anchor={first_failed['anchor']}, originating_agent={first_failed['originating_agent']}",
        "limitation": "Single run; no manual-label precision/recall; event graph is reconstructed from notebook logs, not a framework-level non-invasive observer.",
    },
    {
        "objective": "O2 failure taxonomy and detectors",
        "status": "partial_support",
        "evidence": ", ".join(detector_report["detectors_fired"]),
        "limitation": "Detector labels are rule-based for one STARGAZER run; no validation set, no precision/recall/F1.",
    },
    {
        "objective": "O3 early prediction across verification regimes",
        "status": "not_tested",
        "evidence": f"revision_count={len(revision_events)} and code/result review failures occurred before final approval",
        "limitation": "No paired stress levels, no Lean comparison, no bootstrap statistics.",
    },
    {
        "objective": "STARGAZER scientific correctness",
        "status": "scientific_fail",
        "evidence": f"passed={benchmark.get('passed')}, match_score={benchmark.get('match_score')}, rms={benchmark.get('rms')}, failed_components={component.get('failed_components')}",
        "limitation": "Period was near the truth in nearest-period comparison, but Hungarian match, mass/phase/model-fit anchors failed.",
    },
    {
        "objective": "Silent failure / critic-masking evidence",
        "status": "supported_for_this_run",
        "evidence": f"reviewer returned APPROVE_RESULT while benchmark passed={benchmark.get('passed')}",
        "limitation": "This is a single observed instance; not a rate estimate.",
    },
]
objective_df = pd.DataFrame(objective_rows)
objective_df.to_csv(EVAL_OUT / "proposal_objective_evaluation.csv", index=False)
display(objective_df)

```


<div>
<style scoped>
    .dataframe tbody tr th:only-of-type {
        vertical-align: middle;
    }

    .dataframe tbody tr th {
        vertical-align: top;
    }

    .dataframe thead th {
        text-align: right;
    }
</style>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>objective</th>
      <th>status</th>
      <th>evidence</th>
      <th>limitation</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>0</th>
      <td>O1 localisation infrastructure</td>
      <td>partial_support</td>
      <td>trace events=8, edges=8, first_failed_anchor=match_score_at_least_0_8, originating_agent=engineer/reviewer</td>
      <td>Single run; no manual-label precision/recall; event graph is reconstructed from notebook logs, not a framework-level non-invasive observer.</td>
    </tr>
    <tr>
      <th>1</th>
      <td>O2 failure taxonomy and detectors</td>
      <td>partial_support</td>
      <td>alias_convergence_or_missed_period, critic_masking, mass_amplitude_mismatch, model_fit_degradation, phase_parameter_mismatch, scientific_anchor_failure, sil...</td>
      <td>Detector labels are rule-based for one STARGAZER run; no validation set, no precision/recall/F1.</td>
    </tr>
    <tr>
      <th>2</th>
      <td>O3 early prediction across verification regimes</td>
      <td>not_tested</td>
      <td>revision_count=1 and code/result review failures occurred before final approval</td>
      <td>No paired stress levels, no Lean comparison, no bootstrap statistics.</td>
    </tr>
    <tr>
      <th>3</th>
      <td>STARGAZER scientific correctness</td>
      <td>scientific_fail</td>
      <td>passed=False, match_score=0.022661, rms=41.49204, failed_components=['mass_amplitude', 'model_fit', 'period_recovery', 'phase_or_eccentricity']</td>
      <td>Period was near the truth in nearest-period comparison, but Hungarian match, mass/phase/model-fit anchors failed.</td>
    </tr>
    <tr>
      <th>4</th>
      <td>Silent failure / critic-masking evidence</td>
      <td>supported_for_this_run</td>
      <td>reviewer returned APPROVE_RESULT while benchmark passed=False</td>
      <td>This is a single observed instance; not a rate estimate.</td>
    </tr>
  </tbody>
</table>
</div>


## 7. Minimum Evidence Table

This follows the project report frame: each row states status, evidence, and limitation.



```python
minimum_rows = [
    ["O1 trace schema/dashboard/taxonomy", "partial", f"trajectory_graph.json with {len(events)} events and {len(edges)} edges", "Notebook reconstruction, not production dashboard"],
    ["O1 first failed anchor localisation", "partial", f"{first_failed['anchor']} attributed to {first_failed['originating_agent']}", "Automatic anchor rule, not manual-labelled precision/recall"],
    ["O2 STARGAZER partially verifiable anchors", "available", f"score={benchmark.get('score')}; failed={component.get('failed_components')}", "Only one real task"],
    ["O2 Lean fully step-verifiable anchors", "not_tested", "No Lean run in this notebook", "Transfer claim unavailable"],
    ["O2 detector validation against manual labels", "not_tested", ", ".join(detector_report["detectors_fired"]), "No labelled corpus"],
    ["O3 paired/bootstrap comparison", "not_tested", "No paired baseline/stress suite", "No p-values/effect sizes"],
    ["O3 early-warning difficulty degradation", "not_tested", f"revision_count={len(revision_events)}", "No difficulty series"],
    ["Langfuse/open-source observability export", "not_available", "Local JSON/CSV artifacts only", "No external observability export"],
]
minimum_df = pd.DataFrame(minimum_rows, columns=["evidence_row", "status", "evidence", "limitation"])
minimum_df.to_csv(EVAL_OUT / "minimum_evidence_table.csv", index=False)
display(minimum_df)

```


<div>
<style scoped>
    .dataframe tbody tr th:only-of-type {
        vertical-align: middle;
    }

    .dataframe tbody tr th {
        vertical-align: top;
    }

    .dataframe thead th {
        text-align: right;
    }
</style>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>evidence_row</th>
      <th>status</th>
      <th>evidence</th>
      <th>limitation</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>0</th>
      <td>O1 trace schema/dashboard/taxonomy</td>
      <td>partial</td>
      <td>trajectory_graph.json with 8 events and 8 edges</td>
      <td>Notebook reconstruction, not production dashboard</td>
    </tr>
    <tr>
      <th>1</th>
      <td>O1 first failed anchor localisation</td>
      <td>partial</td>
      <td>match_score_at_least_0_8 attributed to engineer/reviewer</td>
      <td>Automatic anchor rule, not manual-labelled precision/recall</td>
    </tr>
    <tr>
      <th>2</th>
      <td>O2 STARGAZER partially verifiable anchors</td>
      <td>available</td>
      <td>score=0.6; failed=['mass_amplitude', 'model_fit', 'period_recovery', 'phase_or_eccentricity']</td>
      <td>Only one real task</td>
    </tr>
    <tr>
      <th>3</th>
      <td>O2 Lean fully step-verifiable anchors</td>
      <td>not_tested</td>
      <td>No Lean run in this notebook</td>
      <td>Transfer claim unavailable</td>
    </tr>
    <tr>
      <th>4</th>
      <td>O2 detector validation against manual labels</td>
      <td>not_tested</td>
      <td>alias_convergence_or_missed_period, critic_masking, mass_amplitude_mismatch, model_fit_degradation, phase_parameter_mismatch, scientific_anchor_failure, sil...</td>
      <td>No labelled corpus</td>
    </tr>
    <tr>
      <th>5</th>
      <td>O3 paired/bootstrap comparison</td>
      <td>not_tested</td>
      <td>No paired baseline/stress suite</td>
      <td>No p-values/effect sizes</td>
    </tr>
    <tr>
      <th>6</th>
      <td>O3 early-warning difficulty degradation</td>
      <td>not_tested</td>
      <td>revision_count=1</td>
      <td>No difficulty series</td>
    </tr>
    <tr>
      <th>7</th>
      <td>Langfuse/open-source observability export</td>
      <td>not_available</td>
      <td>Local JSON/CSV artifacts only</td>
      <td>No external observability export</td>
    </tr>
  </tbody>
</table>
</div>


## 8. Real vs Agent-Proposed Planet Visualization

This evaluation-only cell uses the hidden truth planet and the agent-produced submission to draw a compact visual comparison. The agent workflow itself did not receive the hidden truth.



```python
from IPython.display import HTML
import math

truth_planets = benchmark.get("truth_planets", [])
submitted_planets = benchmark.get("submitted_planets", [])
assert truth_planets and submitted_planets, "Need both truth and submitted planets to draw comparison."

truth_planet = truth_planets[0]
agent_planet = submitted_planets[0]

def orbit_points(planet, n=240):
    P = float(planet.get("P_days", 1.0))
    e = max(0.0, min(float(planet.get("e", 0.0) or 0.0), 0.95))
    omega = float(planet.get("omega_rad", 0.0) or 0.0)
    a = P ** (2.0 / 3.0)
    points = []
    for i in range(n + 1):
        nu = 2.0 * math.pi * i / n
        r = a * (1.0 - e * e) / (1.0 + e * math.cos(nu))
        points.append((r * math.cos(nu + omega), r * math.sin(nu + omega)))
    return points, a

def planet_marker(planet):
    P = float(planet.get("P_days", 1.0))
    e = max(0.0, min(float(planet.get("e", 0.0) or 0.0), 0.95))
    omega = float(planet.get("omega_rad", 0.0) or 0.0)
    l = float(planet.get("l_rad", 0.0) or 0.0)
    M = (l - omega) % (2.0 * math.pi)
    E = M
    for _ in range(20):
        E -= (E - e * math.sin(E) - M) / max(1e-9, 1.0 - e * math.cos(E))
    nu = 2.0 * math.atan2(math.sqrt(1.0 + e) * math.sin(E / 2.0), math.sqrt(1.0 - e) * math.cos(E / 2.0))
    a = P ** (2.0 / 3.0)
    r = a * (1.0 - e * e) / (1.0 + e * math.cos(nu))
    return r * math.cos(nu + omega), r * math.sin(nu + omega)

truth_points, truth_a = orbit_points(truth_planet)
agent_points, agent_a = orbit_points(agent_planet)
all_points = truth_points + agent_points
scale = max(max(abs(x), abs(y)) for x, y in all_points) or 1.0
tx, ty = planet_marker(truth_planet)
ax, ay = planet_marker(agent_planet)

fields = ["P_days", "m_sin_i_mjup", "e", "omega_rad", "l_rad"]
truth_values = [float(truth_planet.get(field, 0.0) or 0.0) for field in fields]
agent_values = [float(agent_planet.get(field, 0.0) or 0.0) for field in fields]

def svg_polyline(points, cx, cy, radius):
    return " ".join(f"{cx + (x / scale) * radius:.2f},{cy - (y / scale) * radius:.2f}" for x, y in points)

def svg_text(x, y, text, size=13, weight="400", fill="#243040", anchor="start"):
    return f'<text x="{x}" y="{y}" font-size="{size}" font-family="Segoe UI, Arial, sans-serif" font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{text}</text>'

chart_max = max(truth_values + agent_values + [1.0])
bar_parts = []
bar_x0, bar_y0 = 560, 360
bar_w, gap = 18, 58
for i, field in enumerate(fields):
    x = bar_x0 + i * gap
    th = 250.0 * truth_values[i] / chart_max
    ah = 250.0 * agent_values[i] / chart_max
    bar_parts.append(f'<rect x="{x}" y="{bar_y0 - th:.2f}" width="{bar_w}" height="{th:.2f}" fill="#1f77b4"/>')
    bar_parts.append(f'<rect x="{x + bar_w + 3}" y="{bar_y0 - ah:.2f}" width="{bar_w}" height="{ah:.2f}" fill="#d62728"/>')
    bar_parts.append(svg_text(x + 12, 385, field, size=11, anchor="middle"))

svg = f'''
<svg xmlns="http://www.w3.org/2000/svg" width="1040" height="460" viewBox="0 0 1040 460">
  <rect width="1040" height="460" fill="#ffffff"/>
  {svg_text(40, 34, "Real vs agent-proposed planet", 22, "700")}
  {svg_text(40, 60, "Orbit sketch is normalized; bars show raw submitted fields.", 13, "400", "#5b6778")}
  <rect x="35" y="82" width="465" height="330" fill="#f8fafc" stroke="#d5dbe3"/>
  <polyline points="{svg_polyline(truth_points, 267, 247, 145)}" fill="none" stroke="#1f77b4" stroke-width="3"/>
  <polyline points="{svg_polyline(agent_points, 267, 247, 145)}" fill="none" stroke="#d62728" stroke-width="3" stroke-dasharray="8 6"/>
  <circle cx="267" cy="247" r="9" fill="#f2b01e" stroke="#111827"/>
  <circle cx="{267 + (tx / scale) * 145:.2f}" cy="{247 - (ty / scale) * 145:.2f}" r="7" fill="#1f77b4" stroke="#ffffff" stroke-width="2"/>
  <circle cx="{267 + (ax / scale) * 145:.2f}" cy="{247 - (ay / scale) * 145:.2f}" r="7" fill="#d62728" stroke="#ffffff" stroke-width="2"/>
  {svg_text(55, 108, "orbit geometry", 15, "700")}
  <line x1="365" y1="105" x2="395" y2="105" stroke="#1f77b4" stroke-width="3"/>{svg_text(402, 110, "truth", 12)}
  <line x1="365" y1="125" x2="395" y2="125" stroke="#d62728" stroke-width="3" stroke-dasharray="8 6"/>{svg_text(402, 130, "agent", 12)}
  <rect x="535" y="82" width="465" height="330" fill="#f8fafc" stroke="#d5dbe3"/>
  {svg_text(555, 108, "parameter comparison", 15, "700")}
  <line x1="555" y1="360" x2="955" y2="360" stroke="#aab4c0"/>
  {''.join(bar_parts)}
  <rect x="830" y="110" width="14" height="14" fill="#1f77b4"/>{svg_text(850, 122, "truth", 12)}
  <rect x="830" y="132" width="14" height="14" fill="#d62728"/>{svg_text(850, 144, "agent", 12)}
</svg>
'''

visual_path = EVAL_OUT / "real_vs_agent_planet_visualization.svg"
visual_path.write_text(svg, encoding="utf-8")
display(HTML(svg))

visual_rows = []
for field, truth_value, agent_value in zip(fields, truth_values, agent_values):
    visual_rows.append({
        "field": field,
        "truth": truth_value,
        "agent": agent_value,
        "relative_error": relative_error(agent_value, truth_value) if field not in ["omega_rad", "l_rad"] else None,
        "angle_error_rad": angle_distance(agent_value, truth_value) if field in ["omega_rad", "l_rad"] else None,
    })
visual_df = pd.DataFrame(visual_rows)
visual_df.to_csv(EVAL_OUT / "real_vs_agent_planet_parameters.csv", index=False)
display(visual_df)
display(Markdown(f"Saved visualization to `{visual_path}`."))

```



<svg xmlns="http://www.w3.org/2000/svg" width="1040" height="460" viewBox="0 0 1040 460">
  <rect width="1040" height="460" fill="#ffffff"/>
  <text x="40" y="34" font-size="22" font-family="Segoe UI, Arial, sans-serif" font-weight="700" fill="#243040" text-anchor="start">Real vs agent-proposed planet</text>
  <text x="40" y="60" font-size="13" font-family="Segoe UI, Arial, sans-serif" font-weight="400" fill="#5b6778" text-anchor="start">Orbit sketch is normalized; bars show raw submitted fields.</text>
  <rect x="35" y="82" width="465" height="330" fill="#f8fafc" stroke="#d5dbe3"/>
  <polyline points="342.01,126.95 338.85,125.03 335.63,123.19 332.37,121.43 329.06,119.76 325.71,118.17 322.32,116.67 318.89,115.26 315.43,113.94 311.93,112.71 308.41,111.57 304.85,110.52 301.27,109.56 297.66,108.70 294.03,107.92 290.39,107.25 286.72,106.66 283.04,106.18 279.35,105.78 275.66,105.49 271.95,105.28 268.24,105.18 264.52,105.17 260.81,105.26 257.10,105.44 253.40,105.72 249.70,106.09 246.01,106.57 242.34,107.13 238.68,107.79 235.04,108.55 231.41,109.40 227.81,110.35 224.24,111.38 220.69,112.51 217.18,113.74 213.69,115.05 210.24,116.46 206.82,117.95 203.45,119.53 200.11,121.20 196.82,122.96 193.58,124.80 190.38,126.73 187.23,128.74 184.14,130.84 181.10,133.01 178.12,135.26 175.19,137.59 172.33,140.00 169.53,142.48 166.79,145.03 164.13,147.66 161.53,150.35 159.00,153.11 156.54,155.94 154.15,158.84 151.85,161.79 149.61,164.81 147.46,167.88 145.39,171.01 143.40,174.20 141.50,177.43 139.67,180.72 137.94,184.05 136.29,187.43 134.73,190.86 133.26,194.32 131.88,197.82 130.60,201.36 129.40,204.93 128.31,208.54 127.30,212.17 126.39,215.83 125.58,219.51 124.86,223.21 124.24,226.94 123.72,230.68 123.30,234.43 122.98,238.19 122.75,241.96 122.63,245.74 122.60,249.52 122.68,253.30 122.85,257.08 123.12,260.85 123.50,264.62 123.97,268.38 124.54,272.12 125.21,275.85 125.98,279.56 126.85,283.25 127.81,286.91 128.87,290.55 130.03,294.16 131.28,297.74 132.63,301.29 134.07,304.80 135.60,308.27 137.23,311.70 138.95,315.09 140.75,318.43 142.64,321.72 144.62,324.96 146.69,328.15 148.84,331.28 151.07,334.36 153.38,337.37 155.78,340.33 158.25,343.22 160.79,346.04 163.41,348.80 166.10,351.48 168.87,354.09 171.70,356.63 174.60,359.09 177.56,361.48 180.58,363.79 183.67,366.01 186.81,368.15 190.01,370.21 193.26,372.18 196.56,374.07 199.92,375.87 203.31,377.57 206.76,379.19 210.24,380.72 213.76,382.15 217.32,383.49 220.92,384.73 224.54,385.88 228.19,386.93 231.87,387.88 235.58,388.74 239.30,389.49 243.04,390.15 246.80,390.71 250.57,391.17 254.36,391.53 258.14,391.78 261.94,391.94 265.73,392.00 269.53,391.96 273.32,391.81 277.11,391.57 280.89,391.23 284.65,390.78 288.41,390.24 292.14,389.60 295.86,388.86 299.56,388.02 303.23,387.08 306.87,386.05 310.49,384.93 314.07,383.70 317.62,382.39 321.13,380.98 324.60,379.48 328.03,377.89 331.42,376.21 334.76,374.44 338.05,372.59 341.29,370.65 344.48,368.62 347.61,366.51 350.69,364.33 353.70,362.06 356.66,359.71 359.55,357.29 362.37,354.80 365.13,352.23 367.82,349.59 370.43,346.88 372.98,344.11 375.44,341.27 377.84,338.37 380.15,335.40 382.39,332.38 384.54,329.31 386.62,326.17 388.61,322.99 390.51,319.76 392.33,316.47 394.07,313.15 395.71,309.78 397.27,306.37 398.73,302.92 400.10,299.43 401.39,295.91 402.58,292.36 403.67,288.78 404.67,285.18 405.58,281.55 406.39,277.90 407.11,274.23 407.73,270.55 408.26,266.85 408.68,263.14 409.01,259.42 409.25,255.70 409.39,251.97 409.43,248.24 409.37,244.51 409.21,240.79 408.96,237.07 408.62,233.36 408.17,229.67 407.64,225.98 407.00,222.31 406.27,218.66 405.45,215.04 404.53,211.43 403.52,207.85 402.42,204.30 401.23,200.78 399.95,197.29 398.57,193.84 397.11,190.43 395.56,187.05 393.93,183.72 392.20,180.43 390.40,177.18 388.51,173.99 386.54,170.85 384.49,167.75 382.36,164.72 380.15,161.74 377.87,158.81 375.51,155.95 373.08,153.15 370.57,150.42 368.00,147.75 365.36,145.14 362.66,142.61 359.89,140.15 357.05,137.76 354.16,135.44 351.21,133.20 348.20,131.04 345.13,128.96 342.01,126.95" fill="none" stroke="#1f77b4" stroke-width="3"/>
  <polyline points="377.70,247.00 377.66,244.10 377.55,241.21 377.36,238.31 377.10,235.43 376.76,232.55 376.34,229.68 375.85,226.83 375.28,223.98 374.64,221.16 373.93,218.35 373.14,215.56 372.28,212.79 371.35,210.05 370.35,207.33 369.28,204.64 368.13,201.97 366.92,199.34 365.64,196.74 364.29,194.18 362.87,191.65 361.39,189.16 359.84,186.71 358.23,184.30 356.56,181.93 354.83,179.61 353.03,177.33 351.18,175.10 349.27,172.93 347.30,170.80 345.28,168.72 343.20,166.70 341.07,164.73 338.90,162.82 336.67,160.97 334.39,159.17 332.07,157.44 329.70,155.77 327.29,154.16 324.84,152.61 322.35,151.13 319.82,149.71 317.26,148.36 314.66,147.08 312.03,145.87 309.36,144.72 306.67,143.65 303.95,142.65 301.21,141.72 298.44,140.86 295.65,140.07 292.84,139.36 290.02,138.72 287.17,138.15 284.32,137.66 281.45,137.24 278.57,136.90 275.69,136.64 272.79,136.45 269.90,136.34 267.00,136.30 264.10,136.34 261.21,136.45 258.31,136.64 255.43,136.90 252.55,137.24 249.68,137.66 246.83,138.15 243.98,138.72 241.16,139.36 238.35,140.07 235.56,140.86 232.79,141.72 230.05,142.65 227.33,143.65 224.64,144.72 221.97,145.87 219.34,147.08 216.74,148.36 214.18,149.71 211.65,151.13 209.16,152.61 206.71,154.16 204.30,155.77 201.93,157.44 199.61,159.17 197.33,160.97 195.10,162.82 192.93,164.73 190.80,166.70 188.72,168.72 186.70,170.80 184.73,172.93 182.82,175.10 180.97,177.33 179.17,179.61 177.44,181.93 175.77,184.30 174.16,186.71 172.61,189.16 171.13,191.65 169.71,194.18 168.36,196.74 167.08,199.34 165.87,201.97 164.72,204.64 163.65,207.33 162.65,210.05 161.72,212.79 160.86,215.56 160.07,218.35 159.36,221.16 158.72,223.98 158.15,226.83 157.66,229.68 157.24,232.55 156.90,235.43 156.64,238.31 156.45,241.21 156.34,244.10 156.30,247.00 156.34,249.90 156.45,252.79 156.64,255.69 156.90,258.57 157.24,261.45 157.66,264.32 158.15,267.17 158.72,270.02 159.36,272.84 160.07,275.65 160.86,278.44 161.72,281.21 162.65,283.95 163.65,286.67 164.72,289.36 165.87,292.03 167.08,294.66 168.36,297.26 169.71,299.82 171.13,302.35 172.61,304.84 174.16,307.29 175.77,309.70 177.44,312.07 179.17,314.39 180.97,316.67 182.82,318.90 184.73,321.07 186.70,323.20 188.72,325.28 190.80,327.30 192.93,329.27 195.10,331.18 197.33,333.03 199.61,334.83 201.93,336.56 204.30,338.23 206.71,339.84 209.16,341.39 211.65,342.87 214.18,344.29 216.74,345.64 219.34,346.92 221.97,348.13 224.64,349.28 227.33,350.35 230.05,351.35 232.79,352.28 235.56,353.14 238.35,353.93 241.16,354.64 243.98,355.28 246.83,355.85 249.68,356.34 252.55,356.76 255.43,357.10 258.31,357.36 261.21,357.55 264.10,357.66 267.00,357.70 269.90,357.66 272.79,357.55 275.69,357.36 278.57,357.10 281.45,356.76 284.32,356.34 287.17,355.85 290.02,355.28 292.84,354.64 295.65,353.93 298.44,353.14 301.21,352.28 303.95,351.35 306.67,350.35 309.36,349.28 312.03,348.13 314.66,346.92 317.26,345.64 319.82,344.29 322.35,342.87 324.84,341.39 327.29,339.84 329.70,338.23 332.07,336.56 334.39,334.83 336.67,333.03 338.90,331.18 341.07,329.27 343.20,327.30 345.28,325.28 347.30,323.20 349.27,321.07 351.18,318.90 353.03,316.67 354.83,314.39 356.56,312.07 358.23,309.70 359.84,307.29 361.39,304.84 362.87,302.35 364.29,299.82 365.64,297.26 366.92,294.66 368.13,292.03 369.28,289.36 370.35,286.67 371.35,283.95 372.28,281.21 373.14,278.44 373.93,275.65 374.64,272.84 375.28,270.02 375.85,267.17 376.34,264.32 376.76,261.45 377.10,258.57 377.36,255.69 377.55,252.79 377.66,249.90 377.70,247.00" fill="none" stroke="#d62728" stroke-width="3" stroke-dasharray="8 6"/>
  <circle cx="267" cy="247" r="9" fill="#f2b01e" stroke="#111827"/>
  <circle cx="255.41" cy="391.61" r="7" fill="#1f77b4" stroke="#ffffff" stroke-width="2"/>
  <circle cx="270.95" cy="357.63" r="7" fill="#d62728" stroke="#ffffff" stroke-width="2"/>
  <text x="55" y="108" font-size="15" font-family="Segoe UI, Arial, sans-serif" font-weight="700" fill="#243040" text-anchor="start">orbit geometry</text>
  <line x1="365" y1="105" x2="395" y2="105" stroke="#1f77b4" stroke-width="3"/><text x="402" y="110" font-size="12" font-family="Segoe UI, Arial, sans-serif" font-weight="400" fill="#243040" text-anchor="start">truth</text>
  <line x1="365" y1="125" x2="395" y2="125" stroke="#d62728" stroke-width="3" stroke-dasharray="8 6"/><text x="402" y="130" font-size="12" font-family="Segoe UI, Arial, sans-serif" font-weight="400" fill="#243040" text-anchor="start">agent</text>
  <rect x="535" y="82" width="465" height="330" fill="#f8fafc" stroke="#d5dbe3"/>
  <text x="555" y="108" font-size="15" font-family="Segoe UI, Arial, sans-serif" font-weight="700" fill="#243040" text-anchor="start">parameter comparison</text>
  <line x1="555" y1="360" x2="955" y2="360" stroke="#aab4c0"/>
  <rect x="560" y="137.24" width="18" height="222.76" fill="#1f77b4"/><rect x="581" y="208.94" width="18" height="151.06" fill="#d62728"/><text x="572" y="385" font-size="11" font-family="Segoe UI, Arial, sans-serif" font-weight="400" fill="#243040" text-anchor="middle">P_days</text><rect x="618" y="335.73" width="18" height="24.27" fill="#1f77b4"/><rect x="639" y="351.25" width="18" height="8.75" fill="#d62728"/><text x="630" y="385" font-size="11" font-family="Segoe UI, Arial, sans-serif" font-weight="400" fill="#243040" text-anchor="middle">m_sin_i_mjup</text><rect x="676" y="359.32" width="18" height="0.68" fill="#1f77b4"/><rect x="697" y="360.00" width="18" height="0.00" fill="#d62728"/><text x="688" y="385" font-size="11" font-family="Segoe UI, Arial, sans-serif" font-weight="400" fill="#243040" text-anchor="middle">e</text><rect x="734" y="306.70" width="18" height="53.30" fill="#1f77b4"/><rect x="755" y="360.00" width="18" height="0.00" fill="#d62728"/><text x="746" y="385" font-size="11" font-family="Segoe UI, Arial, sans-serif" font-weight="400" fill="#243040" text-anchor="middle">omega_rad</text><rect x="792" y="115.45" width="18" height="244.55" fill="#1f77b4"/><rect x="813" y="110.00" width="18" height="250.00" fill="#d62728"/><text x="804" y="385" font-size="11" font-family="Segoe UI, Arial, sans-serif" font-weight="400" fill="#243040" text-anchor="middle">l_rad</text>
  <rect x="830" y="110" width="14" height="14" fill="#1f77b4"/><text x="850" y="122" font-size="12" font-family="Segoe UI, Arial, sans-serif" font-weight="400" fill="#243040" text-anchor="start">truth</text>
  <rect x="830" y="132" width="14" height="14" fill="#d62728"/><text x="850" y="144" font-size="12" font-family="Segoe UI, Arial, sans-serif" font-weight="400" fill="#243040" text-anchor="start">agent</text>
</svg>




<div>
<style scoped>
    .dataframe tbody tr th:only-of-type {
        vertical-align: middle;
    }

    .dataframe tbody tr th {
        vertical-align: top;
    }

    .dataframe thead th {
        text-align: right;
    }
</style>
<table border="1" class="dataframe">
  <thead>
    <tr style="text-align: right;">
      <th></th>
      <th>field</th>
      <th>truth</th>
      <th>agent</th>
      <th>relative_error</th>
      <th>angle_error_rad</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <th>0</th>
      <td>P_days</td>
      <td>4.230785</td>
      <td>2.868989</td>
      <td>0.321878</td>
      <td>NaN</td>
    </tr>
    <tr>
      <th>1</th>
      <td>m_sin_i_mjup</td>
      <td>0.461000</td>
      <td>0.166203</td>
      <td>0.639473</td>
      <td>NaN</td>
    </tr>
    <tr>
      <th>2</th>
      <td>e</td>
      <td>0.013000</td>
      <td>0.000000</td>
      <td>1.000000</td>
      <td>NaN</td>
    </tr>
    <tr>
      <th>3</th>
      <td>omega_rad</td>
      <td>1.012291</td>
      <td>0.000000</td>
      <td>NaN</td>
      <td>1.012291</td>
    </tr>
    <tr>
      <th>4</th>
      <td>l_rad</td>
      <td>4.644516</td>
      <td>4.748110</td>
      <td>NaN</td>
      <td>0.103594</td>
    </tr>
  </tbody>
</table>
</div>



Saved visualization to `C:\Users\Anwender\Science-Work-Flow-\outputs\qwen_saeed_stargazer_eval\real_vs_agent_planet_visualization.svg`.


## 9. Final Trajectory-Level Evaluation

This is the proposal-aligned conclusion for the run.



```python
status = "scientific_pass" if benchmark.get("passed") else "scientific_fail"
period_note = ""
if nearest:
    period_note = f"Nearest-period comparison shows period_rel_error={nearest.get('period_rel_error')}, but mass_rel_error={nearest.get('mass_rel_error')} and phase/model anchors fail."

final_report = {
    "run": "qwen_saeed_agent_stargazer",
    "evaluation_type": "trajectory_level_stargazer_single_run",
    "proposal_alignment": {
        "research_question": "Can trajectory signals localise and detect failures that output-only evaluation misses in a partially verifiable STARGAZER task?",
        "O1": objective_rows[0],
        "O2": objective_rows[1],
        "O3": objective_rows[2],
    },
    "scientific_status": status,
    "first_violated_anchor": first_failed,
    "detectors_fired": detector_report["detectors_fired"],
    "benchmark_summary": {
        "passed": benchmark.get("passed"),
        "score": benchmark.get("score"),
        "match_score": benchmark.get("match_score"),
        "rms": benchmark.get("rms"),
        "reward": benchmark.get("reward"),
        "failed_components": component.get("failed_components"),
    },
    "interpretation": (
        "The run is useful O1/O2 evidence for trajectory-level failure localisation because the reviewer-approved final result fails hidden STARGAZER physical/model anchors. "
        + period_note
        + " The result should not be reported as a scientific success or architecture-level claim."
    ),
    "artifacts": {
        "evaluation_dir": str(EVAL_OUT),
        "trajectory_graph": str(EVAL_OUT / "trajectory_graph.json"),
        "anchor_report": str(EVAL_OUT / "anchor_report.json"),
        "detector_report": str(EVAL_OUT / "detector_report.json"),
        "local_benchmark": str(EVAL_OUT / "local_stargazer_benchmark.json"),
    },
}
write_json(EVAL_OUT / "qwen_saeed_stargazer_trajectory_evaluation.json", final_report)

display(Markdown(
    f"**Decision:** {status}. "
    f"First violated anchor: **{first_failed['anchor']}**. "
    f"Detectors: **{', '.join(detector_report['detectors_fired'])}**. "
    f"{period_note}"
))
print(json.dumps(final_report, indent=2))

```


**Decision:** scientific_fail. First violated anchor: **match_score_at_least_0_8**. Detectors: **alias_convergence_or_missed_period, critic_masking, mass_amplitude_mismatch, model_fit_degradation, phase_parameter_mismatch, scientific_anchor_failure, silent_acceptance, truncated_reasoning_or_output**. Nearest-period comparison shows period_rel_error=0.321878, but mass_rel_error=0.639473 and phase/model anchors fail.


    {
      "run": "qwen_saeed_agent_stargazer",
      "evaluation_type": "trajectory_level_stargazer_single_run",
      "proposal_alignment": {
        "research_question": "Can trajectory signals localise and detect failures that output-only evaluation misses in a partially verifiable STARGAZER task?",
        "O1": {
          "objective": "O1 localisation infrastructure",
          "status": "partial_support",
          "evidence": "trace events=8, edges=8, first_failed_anchor=match_score_at_least_0_8, originating_agent=engineer/reviewer",
          "limitation": "Single run; no manual-label precision/recall; event graph is reconstructed from notebook logs, not a framework-level non-invasive observer."
        },
        "O2": {
          "objective": "O2 failure taxonomy and detectors",
          "status": "partial_support",
          "evidence": "alias_convergence_or_missed_period, critic_masking, mass_amplitude_mismatch, model_fit_degradation, phase_parameter_mismatch, scientific_anchor_failure, silent_acceptance, truncated_reasoning_or_output",
          "limitation": "Detector labels are rule-based for one STARGAZER run; no validation set, no precision/recall/F1."
        },
        "O3": {
          "objective": "O3 early prediction across verification regimes",
          "status": "not_tested",
          "evidence": "revision_count=1 and code/result review failures occurred before final approval",
          "limitation": "No paired stress levels, no Lean comparison, no bootstrap statistics."
        }
      },
      "scientific_status": "scientific_fail",
      "first_violated_anchor": {
        "anchor": "match_score_at_least_0_8",
        "passed": false,
        "layer": "science",
        "originating_agent": "engineer/reviewer",
        "evidence": "match_score=0.022661"
      },
      "detectors_fired": [
        "alias_convergence_or_missed_period",
        "critic_masking",
        "mass_amplitude_mismatch",
        "model_fit_degradation",
        "phase_parameter_mismatch",
        "scientific_anchor_failure",
        "silent_acceptance",
        "truncated_reasoning_or_output"
      ],
      "benchmark_summary": {
        "passed": false,
        "score": 0.6,
        "match_score": 0.022661,
        "rms": 41.49204,
        "reward": -1512.832788,
        "failed_components": [
          "mass_amplitude",
          "model_fit",
          "period_recovery",
          "phase_or_eccentricity"
        ]
      },
      "interpretation": "The run is useful O1/O2 evidence for trajectory-level failure localisation because the reviewer-approved final result fails hidden STARGAZER physical/model anchors. Nearest-period comparison shows period_rel_error=0.321878, but mass_rel_error=0.639473 and phase/model anchors fail. The result should not be reported as a scientific success or architecture-level claim.",
      "artifacts": {
        "evaluation_dir": "C:\\Users\\Anwender\\Science-Work-Flow-\\outputs\\qwen_saeed_stargazer_eval",
        "trajectory_graph": "C:\\Users\\Anwender\\Science-Work-Flow-\\outputs\\qwen_saeed_stargazer_eval\\trajectory_graph.json",
        "anchor_report": "C:\\Users\\Anwender\\Science-Work-Flow-\\outputs\\qwen_saeed_stargazer_eval\\anchor_report.json",
        "detector_report": "C:\\Users\\Anwender\\Science-Work-Flow-\\outputs\\qwen_saeed_stargazer_eval\\detector_report.json",
        "local_benchmark": "C:\\Users\\Anwender\\Science-Work-Flow-\\outputs\\qwen_saeed_stargazer_eval\\local_stargazer_benchmark.json"
      }
    }
    
