# Engineer Agent

The engineer agent is the public, file-backed version of the local Codex-style
prototype. It turns a task contract into JSONL tool actions, executes those
actions, and writes trace evidence to disk.

## Flow

```text
task / plan.md
  -> build engineer prompt
  -> Qwen returns JSONL actions
  -> execute tools
  -> write files / run commands / check git
  -> save events, stdout, stderr, run_manifest.json, trace_validation.json
```

## Code Map

```text
src/traj_eval/engineer/cli.py          CLI arguments
src/traj_eval/engineer/session.py      main engineer loop
src/traj_eval/engineer/qwen_client.py  Qwen request and JSONL parsing
src/traj_eval/engineer/tools.py        tool handlers
src/traj_eval/engineer/evidence.py     git snapshots, diagnosis, version index
src/traj_eval/engineer/prompts.py      prompt and context-file construction
scripts/engineer_agent.py              command-line entrypoint
```

Generated run artifacts are written under `runs/engineer/`, which is ignored by
Git.

## Example

```powershell
python scripts\engineer_agent.py --task-id demo --task "Explain the prompt only." --write-prompt-only
```

Stargazer task evidence:

```powershell
python -m pytest tests\engineer\test_stargazer_task.py
```

This public test validates the committed
`tests/engineer/evidence/stargazer_true_task/` bundle. The bundle is a scrubbed
full artifact from a real Qwen-based Stargazer engineer run through the public
package: prompt, Qwen response, JSONL actions, monitor log, tool outputs,
manifest, trace validation, generated fitting script, fit diagnostics, and
submission. The test rejects placeholder constants and requires data-derived
fit diagnostics.
On Windows worktrees where pytest cache/temp permissions are restricted, run:

```powershell
python -m pytest tests\engineer\test_stargazer_task.py --basetemp runs\pytest-temp -p no:cacheprovider
```

For a live Qwen run, provide a local env file with `OPENAI_BASE_URL`,
`OPENAI_API_KEY`, and model settings, then pass `--qwen --execute-qwen-actions`.
