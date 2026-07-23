# Repo Layout Rules

This repo should stay simple: source code in `src/`, runnable commands in
`scripts/`, compact benchmark data in `dataset/`, raw trial traces in
`data/batch/`, and human explanations in `docs/`.

## Top-Level Rule

Use the path that matches the artifact lifecycle:

```text
source code        -> src/traj_eval/
command wrappers   -> scripts/
configuration      -> configs/
schemas            -> schema/
benchmark sources  -> dataset/
raw trial traces   -> data/batch/
derived tables     -> data/analysis/
human reports      -> docs/
tests and fixtures -> tests/
local scratch      -> runs/, .codex/, local_reference/, .pytest-*
notebook scratch   -> notebooks/
```

Do not create a new top-level folder unless the existing folders cannot
represent the artifact clearly.

## Source Code

Put importable package code under:

```text
src/traj_eval/
```

Current subpackage ownership:

```text
agents/       agent/team construction and routing behavior
anchors/      anchor definitions and checks
dataset/      dataset loaders and problem conversion
detectors/    behavior detectors such as perseveration
metrics/      offline scoring and validation metrics
runtime/      deterministic runtime utilities
tools/        tool implementations called by agents or validators
trace_core/   JSONL trace schema, storage, and graph logic
```

Keep task-specific evidence out of generic runtime code. If a Lean, Stargazer,
or future benchmark detail is only evidence for one task, keep it in a task file,
trace, fixture, or report.

## Scripts

Put executable repo workflows under:

```text
scripts/
```

Scripts should be thin wrappers around package code. They may parse arguments,
load config, call `src/traj_eval`, and write outputs, but should not become a
second implementation of the framework.

## Configuration

Put non-secret shared configuration under:

```text
configs/
```

Local provider keys, API keys, and machine-specific settings must stay out of
Git. Use ignored local files such as:

```text
configs/*.local.env
.env
```

## Schemas

Put stable JSON contracts under:

```text
schema/
```

The trace/event schema belongs here. Do not create a new schema for an analysis
report unless the existing trace schema cannot express the evidence.

## Dataset

Put benchmark source material under:

```text
dataset/
dataset/Lean/
```

For Lean, `dataset/Lean/` is the package root for local validation. Track the
compact benchmark surface and package metadata. Keep bulky Lean sources, Lake
build caches, and local Mathlib artifacts private or ignored unless explicitly
requested.

## Raw Outputs

Put raw generated trial traces under:

```text
data/batch/
```

Use one JSONL file per task trial:

```text
{difficulty}_{task_id}_t{trial}.jsonl
```

Example:

```text
easy_fatem_111_t7.jsonl
```

Group retained traces by a versioned cohort or run bundle:

```text
data/batch/version_1_trial_traces/easy_fatem_111_t7.jsonl
data/batch/qwen_medium_subgoals_v1/medium_leancat_008_t0.jsonl
```

`data/` is ignored by default because raw outputs can become large. Track only
selected benchmark evidence that is intentionally part of the shared result.

## Derived Analysis

Put machine-readable analysis products under:

```text
data/analysis/
```

Examples:

```text
data/analysis/lean_easy_failure_patterns.csv
data/analysis/lean_easy_failure_patterns.json
```

Derived analysis must be reproducible from raw traces and code. Do not mix
manual prose into CSV or JSON outputs.

## Human Docs

Put human-facing explanations under:

```text
docs/
```

Use docs for:

```text
setup instructions
branch or merge status
analysis guides
human-readable reports
future direction notes
temporary handoff notes that are meant to be shared
```

Do not put raw JSONL traces, large tables, or notebook outputs in `docs/`.

Recommended report pairing:

```text
data/batch/<cohort>/*.jsonl
-> data/analysis/<cohort>/
-> docs/reports/ or docs/experiments/
```

## Tests

Put automated tests under:

```text
tests/
```

Use tests for stable fixtures and regression coverage only. Do not use
`tests/` as a storage location for fresh experiment runs.

If an output exists only to prove test behavior, it may live under a fixture
folder. If it is a research result, put it in `data/` or `docs/`.

## Notebooks

Use notebooks for exploration and legacy reproduction:

```text
notebooks/
```

Do not make notebooks the canonical output path for new Lean-agent batches.
Notebook `outputs/` folders are local scratch unless explicitly selected for a
shareable result.

## Local-Only Material

These paths are local or ignored by default:

```text
.codex/
local_reference/
runs/
.pytest_cache/
.pytest-basetemp-*
```

Use them for private planning, private learning notes, smoke runs, and temporary
diagnostics. Do not commit from these paths unless the user explicitly asks to
promote something into the shareable repo.

## Naming Rules

Prefer names that encode the artifact role:

```text
*_GUIDE.md       how to perform an analysis or workflow
*_ANALYSIS.md    human-readable findings
*_STATUS.md      current branch/project status
*_DIRECTION.md   future direction without implementation
*_t{trial}.jsonl raw trial trace
*.schema.json    stable machine contract
```

Avoid vague names such as `notes.md`, `output.json`, `final.md`, or
`experiment_new/`.

## Minimal Workflow

For Lean easy-task analysis, use this path:

```text
1. Run trials into data/batch/version_1_trial_traces/{difficulty}_{task_id}_t{trial}.jsonl
2. Aggregate them into data/analysis/lean_easy_failure_patterns.csv
3. Interpret them in docs/reports/LEAN_AGENT_BEHAVIOR_ANALYSIS.md
4. Keep private reruns and debugging under runs/ or local_reference/
```

This keeps the Lean-anchor output style: simple files, clear names, no dashboard
or database before the current traces are useful.
