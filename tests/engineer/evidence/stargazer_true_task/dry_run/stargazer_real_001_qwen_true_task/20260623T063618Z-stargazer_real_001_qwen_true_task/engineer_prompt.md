You are the ENGINEER for traj-eval task_id=stargazer_real_001_qwen_true_task.

You are still the engineer role from the planner -> engineer -> critic setup,
but your output format changes. Your job is to change the real repository by
requesting tools. Do not paste source code as a final chat-only answer. The
critic will read files and git diffs from disk.

Important runtime contract:
- In one-shot mode, return the complete ordered JSONL action list in this single response.
- In interactive tool mode, you may receive tool results in a later message; continue from that evidence.
- Do not stop after read_file. Either continue in the same action list or use the returned tool evidence in the next turn.

Task:
Build a runnable Stargazer engineer script that makes a real public-data model attempt.

Notebook source: notebooks/qwen_saeed_stargazer_real1/qwen_saeed_agent_stargazer.ipynb
Public observation file: notebooks/qwen_saeed_stargazer_real1/tasks/stargazer_real_real_001_minimal/stargazer_observations.json
Observation summary: {
  "task_id": "real_001",
  "observation_count": 639,
  "instrument_count": 6,
  "first_time_days": 2449610.532755,
  "last_time_days": 2456847.926159
}

Use JSONL tool actions to:
1. Do not call `read_file`; this is a one-shot public-data task and the necessary public paths/schema are already in this prompt.
2. Write a standalone Python script at `tests/engineer/evidence/stargazer_true_task/workdir/stargazer_engineer_script.py`.
3. The script must create `tests/engineer/evidence/stargazer_true_task/workdir/stargazer_workdir`, copy/read the public observations, and write `tests/engineer/evidence/stargazer_true_task/workdir/stargazer_workdir/agent_submission.json`.
4. The script must not read hidden truth, benchmark answer files, or real_001 hidden task files.
5. The public observation JSON has top-level key `observations`. `observations` is one dictionary of parallel arrays, not a list of row dictionaries:
   - `obs = data["observations"]`
   - `times = obs["times_days"]`
   - `rvs = obs["rvs_ms"]`
   - `sigmas = obs["sigmas_ms"]`
   - `instruments = obs["instruments"]`
   Loop by array index, not by iterating `for row in obs`.
6. Fit or estimate parameters from the observations. A valid attempt must use the observation arrays to derive period, amplitude/mass, and jitter; for example, detrend per-instrument radial velocities, search candidate periods with sinusoidal least squares, and convert the best semi-amplitude into `m_sin_i_mjup`.
7. Do not submit placeholder constants such as `P_days=100.0`, `m_sin_i_mjup=0.1`, and `sigma_jitter_ms=1.0` unless those exact values are derived by the script from the data and the script writes fit diagnostics proving it.
8. The submission JSON must match the public Stargazer parser contract:
   {
     "planets": [
       {
         "P_days": <data-derived positive period>,
         "m_sin_i_mjup": <data-derived positive mass estimate>,
         "e": 0.0,
         "inc_rad": 1.5707963267948966,
         "Omega_rad": 0.0,
         "omega_rad": 0.0,
         "l_rad": 0.0
       }
     ],
     "noise": {"sigma_jitter_ms": <data-derived residual jitter>},
     "metadata": {"source": "qwen_public_fit", "task_id": "real_001", "fit_method": "..."}
   }
   Do not use `predictions` as the main output; it will fail the parser.
9. The script must also write `tests/engineer/evidence/stargazer_true_task/workdir/stargazer_workdir/fit_diagnostics.json` with the tested period count, best period, amplitude/semi-amplitude, residual RMS, jitter, and parser-ready submission path.
10. Run `python tests/engineer/evidence/stargazer_true_task/workdir/stargazer_engineer_script.py`.
11. Run `python -c "import json, sys; sys.path.insert(0, r'notebooks/qwen_saeed_stargazer_real1/support'); from stargazer.evaluator import _parse_submission_planets; s=json.load(open(r'tests/engineer/evidence/stargazer_true_task/workdir/stargazer_workdir/agent_submission.json')); print(len(_parse_submission_planets(s, 'params_and_model')))"`.
12. Run `git_status`, `git_diff`, and finish with a short summary of the fitted values.

The generated script must be runnable from the repo root and must leave a visible JSON submission file.

Return JSONL. One JSON object per line. No Markdown fences.

Available tools:
{"tool":"read_file","path":"repo/relative/path"}
{"tool":"write_file","path":"repo/relative/path","content":"full new file content"}
{"tool":"append_file","path":"repo/relative/path","content":"text to append"}
{"tool":"run","command":"python -m pytest tests/trace_core/test_core.py"}
{"tool":"git_status"}
{"tool":"git_diff"}
{"tool":"finish","message":"short summary for critic"}

Rules:
- Use repo-relative paths only.
- For write_file/append_file, `content` must be one valid JSON string. Escape newlines as `\n`.
- If the task gives enough concrete file paths and schema details, write and run the script directly.
- Keep changes minimal and tied to task_id=stargazer_real_001_qwen_true_task.
- Prefer editing files over writing code in chat.
- Run a small verification command when possible.
- End with git_status, git_diff, and finish.

Previous run version index for this task_id:
- schema: traj_eval_engineer_version_index_v1
- previous_count: 0
Recommended next engineer steps:
- No previous version found for this task_id; produce a complete action list.
- Prefer write/run/git_status/git_diff/finish when the task has enough context.

Read `version_index.json` in the run folder for the full structured previous-version record.
