from __future__ import annotations

import json
from pathlib import Path

from .core import repo_relative_path, repo_relative_string, write_text


def build_stargazer_task(repo: Path, output_rel: str) -> str:
    notebook_dir = repo / "notebooks" / "qwen_saeed_stargazer_real1"
    observations_path = notebook_dir / "tasks" / "stargazer_real_real_001_minimal" / "stargazer_observations.json"
    observations = json.loads(observations_path.read_text(encoding="utf-8"))
    obs = observations.get("observations", {})
    summary = {
        "task_id": observations.get("task_id"),
        "observation_count": len(obs.get("times_days", [])),
        "instrument_count": len(set(obs.get("instruments", []))),
        "first_time_days": obs.get("times_days", [None])[0] if obs.get("times_days") else None,
        "last_time_days": obs.get("times_days", [None])[-1] if obs.get("times_days") else None,
    }
    script_rel = f"{output_rel}/stargazer_engineer_script.py"
    run_dir_rel = f"{output_rel}/stargazer_workdir"
    return f"""Build a runnable Stargazer engineer script that makes a real public-data model attempt.

Notebook source: notebooks/qwen_saeed_stargazer_real1/qwen_saeed_agent_stargazer.ipynb
Public observation file: {observations_path.relative_to(repo).as_posix()}
Observation summary: {json.dumps(summary, indent=2)}

Use JSONL tool actions to:
1. Do not call `read_file`; this is a one-shot public-data task and the necessary public paths/schema are already in this prompt.
2. Write a standalone Python script at `{script_rel}`.
3. The script must create `{run_dir_rel}`, copy/read the public observations, and write `{run_dir_rel}/agent_submission.json`.
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
   {{
     "planets": [
       {{
         "P_days": <data-derived positive period>,
         "m_sin_i_mjup": <data-derived positive mass estimate>,
         "e": 0.0,
         "inc_rad": 1.5707963267948966,
         "Omega_rad": 0.0,
         "omega_rad": 0.0,
         "l_rad": 0.0
       }}
     ],
     "noise": {{"sigma_jitter_ms": <data-derived residual jitter>}},
     "metadata": {{"source": "qwen_public_fit", "task_id": "real_001", "fit_method": "..."}}
   }}
   Do not use `predictions` as the main output; it will fail the parser.
9. The script must also write `{run_dir_rel}/fit_diagnostics.json` with the tested period count, best period, amplitude/semi-amplitude, residual RMS, jitter, and parser-ready submission path.
10. Run `python {script_rel}`.
11. Run `python -c "import json, sys; sys.path.insert(0, r'notebooks/qwen_saeed_stargazer_real1/support'); from stargazer.evaluator import _parse_submission_planets; s=json.load(open(r'{run_dir_rel}/agent_submission.json')); print(len(_parse_submission_planets(s, 'params_and_model')))"`.
12. Run `git_status`, `git_diff`, and finish with a short summary of the fitted values.

The generated script must be runnable from the repo root and must leave a visible JSON submission file.
"""


def build_engineer_prompt(task_id: str, task: str) -> str:
    return f"""You are the ENGINEER for traj-eval task_id={task_id}.

You are still the engineer role from the planner -> engineer -> critic setup,
but your output format changes. Your job is to change the real repository by
requesting tools. Do not paste source code as a final chat-only answer. The
critic will read files and git diffs from disk.

Important runtime contract:
- In one-shot mode, return the complete ordered JSONL action list in this single response.
- In interactive tool mode, you may receive tool results in a later message; continue from that evidence.
- Do not stop after read_file. Either continue in the same action list or use the returned tool evidence in the next turn.

Task:
{task.strip()}

Return JSONL. One JSON object per line. No Markdown fences.

Available tools:
{{"tool":"read_file","path":"repo/relative/path"}}
{{"tool":"write_file","path":"repo/relative/path","content":"full new file content"}}
{{"tool":"append_file","path":"repo/relative/path","content":"text to append"}}
{{"tool":"run","command":"python -m pytest tests/trace_core/test_core.py"}}
{{"tool":"git_status"}}
{{"tool":"git_diff"}}
{{"tool":"finish","message":"short summary for critic"}}

Rules:
- Use repo-relative paths only.
- For write_file/append_file, `content` must be one valid JSON string. Escape newlines as `\\n`.
- If the task gives enough concrete file paths and schema details, write and run the script directly.
- Keep changes minimal and tied to task_id={task_id}.
- Prefer editing files over writing code in chat.
- Run a small verification command when possible.
- End with git_status, git_diff, and finish.
"""


def append_context_files(repo: Path, prompt: str, paths: list[str] | None) -> str:
    if not paths:
        return prompt
    chunks = [prompt.rstrip(), "", "Reference files already loaded for this one-shot run:"]
    for raw_path in paths:
        path = repo_relative_path(repo, raw_path)
        text = path.read_text(encoding="utf-8")
        rel = repo_relative_string(repo, path)
        chunks.extend(["", f"--- BEGIN {rel} ---", text.rstrip(), f"--- END {rel} ---"])
    return "\n".join(chunks) + "\n"


def append_version_context(prompt: str, version_index: dict) -> str:
    steps = version_index.get("recommended_engineer_steps") or []
    previous = version_index.get("previous_versions") or []
    best = version_index.get("best_previous") or {}
    chunks = [
        prompt.rstrip(),
        "",
        "Previous run version index for this task_id:",
        f"- schema: {version_index.get('schema')}",
        f"- previous_count: {version_index.get('previous_count', 0)}",
    ]
    if best:
        chunks.extend(
            [
                f"- best_previous_run_id: {best.get('run_id')}",
                f"- best_previous_classification: {best.get('classification')}",
            ]
        )
    if previous:
        latest = previous[-1]
        chunks.extend(
            [
                f"- latest_previous_run_id: {latest.get('run_id')}",
                f"- latest_previous_classification: {latest.get('classification')}",
                f"- latest_previous_tools: {json.dumps(latest.get('tools_requested', []), ensure_ascii=False)}",
            ]
        )
    if steps:
        chunks.append("Recommended next engineer steps:")
        chunks.extend(f"- {step}" for step in steps)
    chunks.append("")
    chunks.append("Read `version_index.json` in the run folder for the full structured previous-version record.")
    return "\n".join(chunks) + "\n"


def write_action_example(run_dir: Path) -> Path:
    path = run_dir / "example_engineer_actions.jsonl"
    write_text(
        path,
        "\n".join(
            [
                json.dumps({"tool": "read_file", "path": "README.md"}),
                json.dumps(
                    {
                        "tool": "write_file",
                        "path": "runs/engineer/tmp/example_from_engineer.txt",
                        "content": "This is an example private engineer artifact.\\n",
                    }
                ),
                json.dumps({"tool": "run", "command": "python --version"}),
                json.dumps({"tool": "git_status"}),
                json.dumps({"tool": "git_diff"}),
                json.dumps({"tool": "finish", "message": "Example only."}),
            ]
        )
        + "\n",
    )
    return path


def write_critic_note(run_dir: Path, task_id: str, trial_id: str) -> Path:
    path = run_dir / "critic_read_me.md"
    write_text(
        path,
        f"""# Critic Review Entry Point

task_id: {task_id}
trial_id: {trial_id}

Read files from disk. Do not extract source from engineer chat.

Start here:

- `run_manifest.json`
- `events.jsonl`
- `after_status.txt`
- `after_diff.patch`
- `changed_files.json`
- `changed_snapshots/`
- `private_artifacts` in `run_manifest.json` for ignored generated outputs

Version rule:

- Same `task_id` plus a later timestamped run folder means a later engineer version.
- The critic compares `after_diff.patch`, `changed_files.json`, and `changed_snapshots/`, not prose.
""",
    )
    return path
