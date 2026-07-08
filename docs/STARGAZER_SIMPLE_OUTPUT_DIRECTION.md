# Stargazer Simple Output Direction

This is a future-direction note. Do not treat it as an implementation plan for
the current merge unless explicitly requested.

## Goal

Make future Stargazer agent runs use the same simple output shape as the
Lean-anchor runs:

```text
data/stargazer/<task_id>_t<trial>.jsonl
```

The JSONL file should be enough:

```text
line 0    TrialMeta
line 1..n TraceEvent
```

No default `run_manifest.json`, `artifact_index.json`, git snapshots,
version-index files, nested run folders, or copied prompt bundles.

## Why

The research object is the trajectory, not the packaging around the trajectory.
Lean-anchor already keeps this clean: one trial log, validated by the shared
trace schema, then offline analysis reads the log.

For Stargazer, the future direction is the same:

- record messages, tool calls, code events, execution results, and verdicts as
  `TraceEvent`s
- put task id, model/backend, architecture, and benchmark metadata in
  `TrialMeta.config`
- keep generated science artifacts only when they are actual task outputs
- reference any artifact path inside the relevant event payload

## Notable Paths

Lean-anchor simple output:

```text
scripts/run_batch.py
scripts/run_dataset_task.py
src/traj_eval/trace_core/schema.py
src/traj_eval/trace_core/storage.py
schema/trace_event.schema.json
schema/trial_meta.schema.json
data/batch/
data/runs/
```

Current Stargazer heavy-output path to simplify later:

```text
src/traj_eval/agents/engineer/session.py
src/traj_eval/agents/engineer/core.py
src/traj_eval/agents/engineer/evidence.py
tests/engineer/evidence/stargazer_true_task/
notebooks/qwen_saeed_stargazer_real1/
```

Qwen provider contract to keep separate from output design:

```text
configs/qwen.remote.example.env
configs/qwen.remote.local.env
```

## Future Shape

Prefer this:

```text
data/stargazer/stargazer_real_001_t0.jsonl
data/stargazer/stargazer_real_002_t0.jsonl
```

Avoid this as the default:

```text
runs/engineer/<task_id>/<run_id>/run_manifest.json
runs/engineer/<task_id>/<run_id>/version_index.json
runs/engineer/<task_id>/<run_id>/before_diff.patch
runs/engineer/<task_id>/<run_id>/after_diff.patch
runs/engineer/<task_id>/<run_id>/engineer_prompt.md
```

The heavy folder can remain as old evidence or optional debugging output. It
should not be the default output style for scientific trajectory comparison.

## Karpathy/YAGNI Rule

Keep the future change surgical:

1. Add a simple Stargazer runner only if a run needs it.
2. Reuse `TrialLogWriter`, `TrialMeta`, and `TraceEvent`.
3. Do not introduce a new schema unless the existing trace schema cannot express
   a real event.
4. Do not add a manifest just to describe files that the JSONL already contains.
5. Do not add Stargazer-specific runtime modes; keep Stargazer details in task
   data, prompts, and post-hoc evaluators.

Success criterion for the future change:

```text
one command -> one Stargazer trial -> one schema-valid JSONL trace
```
